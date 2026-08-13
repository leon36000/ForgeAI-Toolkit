"""Sonde matérielle distante via SSH — exécution de l'Étape 0 sur le nœud distant."""

from __future__ import annotations

import atexit
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional

from forgeai.core.registre import append
from forgeai.core.runner import CommandRunner
from forgeai.hardware.detect import HardwareDetector
from forgeai.i18n import t
from forgeai.planner.profile import derive_profile
from forgeai.preflight import available_backends, run_checks


class RemoteProbeError(Exception):
    """Erreur lors de la sonde distante."""


def enroll_hostkey(host: str, hostkey_sha256: str, timeout_s: float = 20.0) -> str:
    """Validation SSH canonique (SSH-007/SSH-021). Retourne le chemin d'un known_hosts
    temporaire (0600) contenant la clé d'hôte offerte dont l'empreinte SHA256 ==
    ``hostkey_sha256``. Lève ``RemoteProbeError`` si l'empreinte est absente/mal formée
    (AVANT tout réseau), si ssh-keyscan ne rend rien, ou si aucune clé offerte ne
    correspond (MITM potentiel). Point unique réutilisé par ``SshRunner`` et le bootstrap
    de nœud (``node_add``)."""
    if not hostkey_sha256 or not hostkey_sha256.startswith("SHA256:"):
        raise RemoteProbeError(
            t("network.remote_probe.enroll_hostkey.empreinte_requise")
        )
    try:
        scan = subprocess.run(
            ["ssh-keyscan", "-t", "ed25519,ecdsa,rsa", host],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RemoteProbeError(t("network.remote_probe.enroll_hostkey.keyscan_timeout", host=host)) from exc
    offered = [
        line for line in scan.stdout.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not offered:
        raise RemoteProbeError(t("network.remote_probe.enroll_hostkey.keyscan_vide", host=host))

    for line in offered:
        fd, tmp = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "w") as f:
                f.write(line + "\n")
            kg = subprocess.run(
                ["ssh-keygen", "-lf", tmp],
                capture_output=True, text=True, timeout=timeout_s,
            )
        finally:
            os.unlink(tmp)
        match = re.search(r"SHA256:\S+", kg.stdout)
        if match and match.group(0) == hostkey_sha256:
            fd2, kh = tempfile.mkstemp(suffix=".known_hosts")
            with os.fdopen(fd2, "w") as f:
                f.write(line + "\n")
            os.chmod(kh, 0o600)
            return kh

    raise RemoteProbeError(
        t("network.remote_probe.enroll_hostkey.empreinte_non_correspondante",
          empreinte=hostkey_sha256)
    )


class SshRunner:
    """Exécute des commandes sur un nœud distant via SSH, avec enrôlement explicite
    de la clé d'hôte par empreinte SHA256 (jamais de TOFU)."""

    def __init__(
        self,
        user: str,
        host: str,
        keyfile: str,
        hostkey_sha256: str,
        timeout_s: float = 20.0,
    ) -> None:
        # Exiger le préfixe SHA256: (ssh-keygen n'émet que du SHA256) : rejette
        # « », « foo:bar », « MD5:... » de façon déterministe AVANT tout réseau (CA2).
        if not hostkey_sha256 or not hostkey_sha256.startswith("SHA256:"):
            raise RemoteProbeError(
                t("network.remote_probe.ssh_runner.empreinte_requise")
            )
        self.user = user
        self.host = host
        self.keyfile = keyfile
        self.hostkey_sha256 = hostkey_sha256
        self.timeout_s = timeout_s
        self._known_hosts: Optional[str] = None  # chemin du known_hosts temp

    def _enroll(self) -> None:
        """Enrôlement de la clé d'hôte via le helper canonique (SSH-021)."""
        self._known_hosts = enroll_hostkey(self.host, self.hostkey_sha256, self.timeout_s)
        atexit.register(self.close)

    def run(self, argv: list[str]) -> tuple[int, str]:
        if self._known_hosts is None:
            self._enroll()
        # SSH-030 : OpenSSH rejoint naivement les elements d'argv par un simple espace,
        # SANS les re-quoter, avant de les transmettre au shell distant (prouve via
        # `ssh -v` : "Sending command: sh -c command -v "$1" sh docker"). Tout argv dont
        # un element contient des espaces se retrouve alors tronque cote shell distant.
        # Un UNIQUE element shlex-joint apres "--" empeche cet aplatissement : SSH n'a
        # plus qu'une seule chaine a transmettre, que le shell distant reparse correctement.
        ssh_cmd = [
            "ssh",
            "-i",
            self.keyfile,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self._known_hosts}",
            "-o",
            "IdentitiesOnly=yes",
            f"{self.user}@{self.host}",
            "--",
            shlex.join(argv),
        ]
        try:
            proc = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
            return proc.returncode, proc.stdout
        except subprocess.TimeoutExpired:
            return 124, ""

    def close(self) -> None:
        """Nettoie le fichier known_hosts temporaire (best‑effort)."""
        if self._known_hosts and os.path.exists(self._known_hosts):
            try:
                os.unlink(self._known_hosts)
            except OSError:
                pass  # best‑effort
            self._known_hosts = None
    # Nettoyage : explicite via close() (testé), et de secours au process-exit via
    # atexit.register(self.close) posé à l'enrôlement. Pas de __del__ (éviter les
    # avertissements de finalisation au GC et un except-large).


@dataclass(frozen=True)
class NodeProbe:
    node_host: str
    profile: str
    backends: list[str]
    hardware: dict


class _CachedDetector:
    """Adaptateur : expose l'interface `full_report()` de `HardwareDetector` en servant
    un rapport DÉJÀ calculé (aucune sonde). `run_checks()` -> `check_hardware()` appelle
    `.full_report()` sur le détecteur qu'on lui passe ; sans cet adaptateur, il resonderait
    le nœud DISTANT une seconde fois pour rien (le résultat n'est utilisé que pour
    reformuler `Check.detail` avec des données déjà connues du premier `full_report()`).
    Sur `SshRunner`, chaque `full_report()` déclenche 4 `runner.run()` (lscpu, nvidia-smi,
    lspci, df), chacun une connexion SSH complète (handshake + auth, sans multiplexage
    ControlMaster/ControlPersist) : la duplication double inutilement le coût réseau."""

    def __init__(self, report) -> None:
        self._report = report

    def full_report(self):
        return self._report


def probe_remote_node(
    node_host: str,
    *,
    runner: CommandRunner,
    http_ok: Optional[Callable[[str], bool]] = None,
    registre_path: str,
    tmp_dir: Optional[str] = None,
) -> NodeProbe:
    # 1. Récupération du meminfo distant
    code, meminfo = runner.run(["cat", "/proc/meminfo"])
    if code != 0:
        raise RemoteProbeError(t("network.remote_probe.probe_remote_node.meminfo_illisible"))

    # Écrire le meminfo dans un fichier temporaire (sur le nœud local exécutant ce code)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".meminfo", dir=tmp_dir)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(meminfo)
        os.chmod(tmp_path, 0o600)

        # 2. Détection matérielle en utilisant le runner (distant) pour CPU/GPU/disques
        detector = HardwareDetector(runner, meminfo_path=tmp_path)

        # 3. Rapport matériel complet
        report = detector.full_report()

        # 4. Profil pour le planificateur
        profile = derive_profile(report)

        # 5. Vérifications pré-vol et backends disponibles — réutilise le rapport matériel
        # déjà obtenu à l'étape 3 (via l'adaptateur _CachedDetector) au lieu de laisser
        # check_hardware() resonder le nœud distant une seconde fois (BUG-remote-probe-
        # double-full-report : 4 runner.run() SSH redondants par appel).
        checks = run_checks(
            runner,
            _CachedDetector(report),
            http_ok or (lambda url: False),
        )
        backends = available_backends(checks)

        # 6. Données matérielles sérialisées
        hardware = json.loads(report.to_json())

        # 7. Journalisation dans le registre
        append(
            Path(registre_path),
            "node_hardware",
            "network",
            {
                "node_host": node_host,
                "profile": profile,
                "backends": backends,
                "hardware": hardware,
            },
        )

    finally:
        # 8. Nettoyage du fichier temporaire
        os.unlink(tmp_path)

    # 9. Construction du résultat
    return NodeProbe(
        node_host=node_host,
        profile=profile,
        backends=backends,
        hardware=hardware,
    )
