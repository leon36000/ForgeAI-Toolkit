"""Story P1-S07 (déploiement) — kubectl apply + attente de disponibilité réelle.

Même contrat que le déployeur Compose : la santé est mesurée sur l'endpoint HTTP
des services (via NodePort), jamais sur le simple état des pods.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from forgeai.deploy.compose import DeployError


def _kubectl(args: list[str], timeout_s: float = 300.0) -> subprocess.CompletedProcess:
    return subprocess.run(["kubectl", *args], capture_output=True, text=True,
                          timeout=timeout_s)


def k3s_apply(manifest: Path) -> None:
    proc = _kubectl(["apply", "-f", str(manifest)])
    if proc.returncode != 0:
        raise DeployError(f"kubectl apply a échoué :\n{proc.stderr[-2000:]}")


def k3s_wait_deployments(namespace: str, timeout_s: float = 600.0) -> None:
    proc = _kubectl(["wait", "--for=condition=available", "deployment", "--all",
                     "-n", namespace, f"--timeout={int(timeout_s)}s"],
                    timeout_s=timeout_s + 30)
    if proc.returncode != 0:
        state = _kubectl(["get", "pods", "-n", namespace, "-o", "wide"]).stdout
        raise DeployError(
            f"Déploiements non disponibles après {timeout_s}s :\n{state}\n{proc.stderr[-1000:]}")


def k3s_delete_namespace(namespace: str) -> None:
    proc = _kubectl(["delete", "namespace", namespace, "--ignore-not-found",
                     "--wait=false"])
    if proc.returncode != 0:
        raise DeployError(f"kubectl delete namespace a échoué :\n{proc.stderr[-1000:]}")
