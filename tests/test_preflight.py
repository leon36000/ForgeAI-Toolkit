"""Tests du préflight portable (P3) — adaptation à l'environnement de l'utilisateur."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.runner import FixtureRunner
from forgeai.hardware.detect import HardwareDetector
from forgeai import preflight

FIXTURES = Path(__file__).parent / "fixtures" / "hardware"


def _hw_detector():
    outputs = {
        "lscpu": (FIXTURES / "lscpu_amd64.json").read_text(encoding="utf-8"),
        "nvidia-smi": "",
        "lspci": "",
        "df": (FIXTURES / "df_root.txt").read_text(encoding="utf-8"),
    }
    return HardwareDetector(FixtureRunner(outputs),
                            meminfo_path=str(FIXTURES / "meminfo_46g.txt"))


class ToolRunner:
    """Simule la présence/absence d'outils : les argv dont le 1er mot est listé → code 0."""
    def __init__(self, present_commands: set[str], failing: set[str] = frozenset()):
        self.present = present_commands
        self.failing = failing  # présent mais sous-commande échoue (ex. daemon down)

    def run(self, argv):
        key = " ".join(argv)
        if argv[0] not in self.present:
            return 127, ""
        if any(key.startswith(f) for f in self.failing):
            return 1, ""
        return 0, ""


def test_machine_sans_rien_ne_plante_pas():
    checks = preflight.run_checks(
        ToolRunner(present_commands=set()), _hw_detector(), http_ok=lambda url: False)
    by = {c.name: c.status for c in checks}
    assert by["docker"] == preflight.MISSING
    assert by["kubectl"] == preflight.MISSING
    assert by["ollama"] == preflight.MISSING
    assert by["python"] == preflight.OK           # on tourne, donc ok
    assert by["hardware"] == preflight.OK          # toujours détectable
    assert preflight.available_backends(checks) == []


def test_docker_installe_mais_demon_arrete():
    runner = ToolRunner(present_commands={"docker"}, failing={"docker info"})
    check = preflight.check_docker(runner)
    assert check.status == preflight.DEGRADED
    assert "démon" in check.detail


def test_machine_avec_docker_active_compose():
    checks = preflight.run_checks(
        ToolRunner(present_commands={"docker"}), _hw_detector(), http_ok=lambda url: False)
    assert "compose" in preflight.available_backends(checks)
    assert "k3s" not in preflight.available_backends(checks)


def test_docker_sans_plugin_compose_est_degrade():
    """Ubuntu vierge : le paquet docker.io fournit le CLI docker + daemon mais PAS le plugin
    `docker compose` v2 (découvert par la preuve Ubuntu vierge, 2026-07-20)."""
    runner = ToolRunner(present_commands={"docker"}, failing={"docker compose"})
    check = preflight.check_docker(runner)
    assert check.status == preflight.DEGRADED
    assert "compose" in check.detail.lower()


def test_compose_indisponible_si_plugin_absent():
    """Sans le plugin compose, le backend 'compose' ne doit PAS être annoncé disponible
    (sinon faux positif : le déploiement échoue ensuite à `docker compose up`)."""
    checks = preflight.run_checks(
        ToolRunner(present_commands={"docker"}, failing={"docker compose"}),
        _hw_detector(), http_ok=lambda url: False)
    assert "compose" not in preflight.available_backends(checks)


def test_machine_avec_cluster_active_k3s():
    checks = preflight.run_checks(
        ToolRunner(present_commands={"docker", "kubectl"}),
        _hw_detector(), http_ok=lambda url: False)
    assert set(preflight.available_backends(checks)) == {"compose", "k3s"}


def test_ollama_detecte_si_repond():
    check = preflight.check_ollama(http_ok=lambda url: True)
    assert check.status == preflight.OK


def test_hardware_sans_gpu_propose_cpu():
    check = preflight.check_hardware(_hw_detector())
    assert check.status == preflight.OK
    assert "CPU" in check.enables or "cpu" in check.enables
