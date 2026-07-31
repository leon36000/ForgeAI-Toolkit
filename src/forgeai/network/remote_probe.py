"""Sonde matérielle distante via SSH — exécution de l'Étape 0 sur le nœud distant."""

from __future__ import annotations

import atexit
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional

from forgeai.core.registre import append
from forgeai.core.runner import CommandRunner
from forgeai.hardware.detect import HardwareDetector
from forgeai.planner.profile import derive_profile
from forgeai.preflight import available_backends, run_checks


class RemoteProbeError(Exception):
    """Erreur lors de la sonde distante."""


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
                "empreinte de clé d'hôte requise (SSH-007 : pas de TOFU) — format 'SHA256:...'"
            )
        self.user = user
        self.host = host
        self.keyfile = keyfile
        self.hostkey_sha256 = hostkey_sha256
        self.timeout_s = timeout_s
        self._known_hosts: Optional[str] = None  # chemin du known_hosts temp

    def _enroll(self) -> None:
        """Récupère les clés offertes par l'hôte, les compare à l'empreinte déclarée,
        et crée un fichier known_hosts temporaire contenant la clé correspondante.
        """
        # 1. Clés offertes par l'hôte (ed25519, ecdsa, rsa)
        scan = subprocess.run(
            ["ssh-keyscan", "-t", "ed25519,ecdsa,rsa", self.host],
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
        )
        offered = [
            line
            for line in scan.stdout.splitlines()
            if line.strip() and not line.startswith("#")
        ]

        for line in offered:
            # Calcul de l'empreinte de CETTE ligne
            fd, tmp = tempfile.mkstemp()
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(line + "\n")
                kg = subprocess.run(
                    ["ssh-keygen", "-lf", tmp],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )
            finally:
                os.unlink(tmp)

            match = re.search(r"SHA256:\S+", kg.stdout)
            if match and match.group(0) == self.hostkey_sha256:
                # Ligne confirmée → on peuple le known_hosts temp
                fd2, kh = tempfile.mkstemp(suffix=".known_hosts")
                with os.fdopen(fd2, "w") as f:
                    f.write(line + "\n")
                os.chmod(kh, 0o600)
                self._known_hosts = kh
                atexit.register(self.close)
                return

        raise RemoteProbeError(
            f"aucune clé d'hôte offerte ne correspond à l'empreinte déclarée "
            f"{self.hostkey_sha256} (SSH-007 : refus, MITM potentiel)"
        )

    def run(self, argv: list[str]) -> tuple[int, str]:
        if self._known_hosts is None:
            self._enroll()
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
        ] + argv
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
        raise RemoteProbeError("meminfo distant illisible")

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

        # 5. Vérifications pré-vol et backends disponibles
        checks = run_checks(
            runner,
            detector,
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
