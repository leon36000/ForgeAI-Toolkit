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
from forgeai.i18n import t

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
                 t("preflight.python.detail", version=v),
                 t("preflight.python.enables"))


def check_docker(runner: CommandRunner) -> Check:
    if not _tool_present(runner, ["docker", "--version"]):
        return Check("docker", MISSING,
                     t("preflight.docker.missing.detail"),
                     t("preflight.docker.missing.enables"))
    if not _tool_present(runner, ["docker", "info"]):
        return Check("docker", DEGRADED,
                     t("preflight.docker.daemon_unreachable.detail"),
                     t("preflight.docker.daemon_unreachable.enables"))
    if not _tool_present(runner, ["docker", "compose", "version"]):
        return Check("docker", DEGRADED,
                     t("preflight.docker.compose_missing.detail"),
                     t("preflight.docker.compose_missing.enables"))
    return Check("docker", OK,
                 t("preflight.docker.ok.detail"),
                 t("preflight.docker.ok.enables"))


def check_kubectl(runner: CommandRunner) -> Check:
    if not _tool_present(runner, ["kubectl", "version", "--client"]):
        return Check("kubectl", MISSING,
                     t("preflight.kubectl.missing.detail"),
                     t("preflight.kubectl.missing.enables"))
    if not _tool_present(runner, ["kubectl", "get", "nodes"]):
        return Check("kubectl", DEGRADED,
                     t("preflight.kubectl.cluster_unreachable.detail"),
                     t("preflight.kubectl.cluster_unreachable.enables"))
    return Check("kubectl", OK,
                 t("preflight.kubectl.ok.detail"),
                 t("preflight.kubectl.ok.enables"))


def check_ollama(http_ok: Callable[[str], bool],
                 base_url: str = "http://127.0.0.1:11434") -> Check:
    if http_ok(f"{base_url}/api/tags"):
        return Check("ollama", OK,
                     t("preflight.ollama.ok.detail", base_url=base_url),
                     t("preflight.ollama.ok.enables"))
    return Check("ollama", MISSING,
                 t("preflight.ollama.missing.detail"),
                 t("preflight.ollama.missing.enables"))


def check_hardware(detector: HardwareDetector) -> Check:
    profile = detector.full_report()
    gpus = [f"{g.vendor}:{g.name}" for g in profile.gpus if g.vram_mb > 0]
    if gpus:
        return Check("hardware", OK,
                     t("preflight.hardware.gpu.detail",
                       cpu_cores=profile.cpu_cores, gpus=", ".join(gpus)),
                     t("preflight.hardware.gpu.enables"))
    return Check("hardware", OK,
                 t("preflight.hardware.cpu.detail",
                   cpu_cores=profile.cpu_cores, ram_gb=profile.ram_gb),
                 t("preflight.hardware.cpu.enables"))


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
