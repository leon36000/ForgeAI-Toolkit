"""Préflight portable (P3) — détecte ce que la machine de l'utilisateur possède.

Le Toolkit est distribué : il doit s'adapter à l'environnement de qui le télécharge,
jamais exiger la stack exacte d'un développeur. `forgeai doctor` sonde les outils
présents (Docker, kubectl, cluster, Ollama, GPU) et rapporte, pour chacun, ce qu'il
active — sans jamais planter si un composant manque.
"""
from __future__ import annotations

import platform
from collections.abc import Callable
from dataclasses import dataclass

from forgeai.core.runner import CommandRunner
from forgeai.hardware.detect import HardwareDetector

OK = "ok"
MISSING = "missing"
DEGRADED = "degraded"


@dataclass(frozen=True)
class Check:
    name: str
    status: str          # OK | MISSING | DEGRADED
    detail: str
    enables: str         # ce que ce composant rend possible


def _tool_present(runner: CommandRunner, argv: list[str]) -> bool:
    code, _ = runner.run(argv)
    return code == 0


def check_python() -> Check:
    v = platform.python_version()
    ok = tuple(int(x) for x in v.split(".")[:2]) >= (3, 10)
    return Check("python", OK if ok else DEGRADED,
                 f"Python {v}", "exécution du Toolkit (requis ≥3.10)")


def check_docker(runner: CommandRunner) -> Check:
    if not _tool_present(runner, ["docker", "--version"]):
        return Check("docker", MISSING, "docker introuvable",
                     "backend Docker Compose (installer Docker pour l'activer)")
    if not _tool_present(runner, ["docker", "info"]):
        return Check("docker", DEGRADED, "docker installé mais démon injoignable",
                     "démarrer le démon Docker pour déployer via Compose")
    if not _tool_present(runner, ["docker", "compose", "version"]):
        return Check("docker", DEGRADED, "docker démon OK mais plugin compose (v2) absent",
                     "installer le plugin docker compose (paquet docker-compose-v2)")
    return Check("docker", OK, "docker + compose opérationnels", "déploiement backend Compose")


def check_kubectl(runner: CommandRunner) -> Check:
    if not _tool_present(runner, ["kubectl", "version", "--client"]):
        return Check("kubectl", MISSING, "kubectl introuvable",
                     "backend K3s (installer kubectl + un cluster pour l'activer)")
    if not _tool_present(runner, ["kubectl", "get", "nodes"]):
        return Check("kubectl", DEGRADED, "kubectl présent mais aucun cluster joignable",
                     "configurer un kubeconfig pour déployer via K3s")
    return Check("kubectl", OK, "cluster joignable", "déploiement backend K3s")


def check_ollama(http_ok: Callable[[str], bool],
                 base_url: str = "http://127.0.0.1:11434") -> Check:
    if http_ok(f"{base_url}/api/tags"):
        return Check("ollama", OK, f"Ollama répond ({base_url})",
                     "moteur LLM par défaut déjà disponible")
    return Check("ollama", MISSING, "Ollama non détecté localement",
                 "le Toolkit peut le déployer comme brique (aucune action requise)")


def check_hardware(detector: HardwareDetector) -> Check:
    profile = detector.full_report()
    gpus = [f"{g.vendor}:{g.name}" for g in profile.gpus if g.vram_mb > 0]
    if gpus:
        return Check("hardware", OK, f"{profile.cpu_cores} cœurs, GPU: {', '.join(gpus)}",
                     "profil GPU accéléré disponible")
    return Check("hardware", OK,
                 f"{profile.cpu_cores} cœurs, {profile.ram_gb} Go RAM, pas de GPU dédié",
                 "profil CPU (minimal-cpu) — fonctionne partout")


def run_checks(runner: CommandRunner, detector: HardwareDetector,
               http_ok: Callable[[str], bool]) -> list[Check]:
    return [
        check_python(),
        check_hardware(detector),
        check_docker(runner),
        check_kubectl(runner),
        check_ollama(http_ok),
    ]


def available_backends(checks: list[Check]) -> list[str]:
    by_name = {c.name: c.status for c in checks}
    backends = []
    if by_name.get("docker") == OK:
        backends.append("compose")
    if by_name.get("kubectl") == OK:
        # k3s et k8s partagent l'API Kubernetes (kubectl + manifestes standard) : un cluster
        # joignable active les DEUX ; l'utilisateur choisit son distro/exposition (NodePort/LB).
        backends.append("k3s")
        backends.append("k8s")
    return backends
