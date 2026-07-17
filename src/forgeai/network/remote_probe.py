"""Sonde matérielle distante via SSH — exécution de l'Étape 0 sur le nœud distant."""

from __future__ import annotations

import json
import os
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
    """Exécute des commandes sur un nœud distant via SSH."""

    def __init__(self, user: str, host: str, keyfile: str, timeout_s: float = 20.0) -> None:
        self.user = user
        self.host = host
        self.keyfile = keyfile
        self.timeout_s = timeout_s

    def run(self, argv: list[str]) -> tuple[int, str]:
        ssh_cmd = [
            "ssh",
            "-i",
            self.keyfile,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
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
