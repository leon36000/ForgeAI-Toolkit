"""Story P1-S06 (déploiement) — docker compose up + attente de santé réelle.

La santé n'est jamais « le container tourne » : chaque service doit répondre
sur son endpoint HTTP de healthcheck (contrat de preuve du plan maître).
"""
from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from forgeai.core.models import DeploymentPlan


class DeployError(Exception):
    pass


def _compose(args: list[str], compose_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", str(compose_file), *args],
        capture_output=True, text=True, timeout=600,
    )


def compose_up(compose_file: Path) -> None:
    proc = _compose(["up", "-d"], compose_file)
    if proc.returncode != 0:
        raise DeployError(f"docker compose up a échoué :\n{proc.stderr[-2000:]}")


def compose_down(compose_file: Path, volumes: bool = False) -> None:
    args = ["down"]
    if volumes:
        args.append("-v")
    proc = _compose(args, compose_file)
    if proc.returncode != 0:
        raise DeployError(f"docker compose down a échoué :\n{proc.stderr[-2000:]}")


def http_ok(url: str, timeout_s: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_healthy(plan: DeploymentPlan, timeout_s: float = 180.0,
                 probe=http_ok) -> dict[str, str]:
    """Attend que chaque service réponde sur son healthcheck. Échec = DeployError
    avec l'état exact de chaque service (jamais de faux succès)."""
    deadline = time.monotonic() + timeout_s
    status = {s.name: "waiting" for s in plan.services if s.healthcheck_url}
    while time.monotonic() < deadline:
        for svc in plan.services:
            if svc.healthcheck_url and status[svc.name] != "healthy":
                if probe(svc.healthcheck_url):
                    status[svc.name] = "healthy"
        if all(v == "healthy" for v in status.values()):
            return status
        time.sleep(2.0)
    raise DeployError(f"Healthchecks incomplets après {timeout_s}s : {status}")
