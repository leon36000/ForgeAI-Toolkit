from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.request

import pytest

from forgeai.network.prepare import (
    PrepareError,
    plan_preparation,
    preparer_noeud,
    sonder_noeud,
)
from forgeai.web.server import build_server


def _node_json(
    name: str,
    ready_status: str,
    *,
    nvidia_cap: int | None = None,
    amd_cap: int | None = None,
    nvidia_present: bool = False,
    amd_present: bool = False,
    arch: str = "amd64",
) -> str:
    conditions = []
    if ready_status:
        conditions.append({"type": "Ready", "status": ready_status})
    capacity: dict[str, str] = {}
    if nvidia_cap is not None:
        capacity["nvidia.com/gpu"] = str(nvidia_cap)
    if amd_cap is not None:
        capacity["amd.com/gpu"] = str(amd_cap)
    labels: dict[str, str] = {}
    if nvidia_present:
        labels["nvidia.com/gpu.present"] = "true"
    if amd_present:
        labels["amd.com/gpu.present"] = "true"
    return json.dumps(
        {
            "metadata": {"name": name, "labels": labels},
            "status": {
                "conditions": conditions,
                "capacity": capacity,
                "nodeInfo": {"architecture": arch},
            },
        }
    )


class FakeRunner:
    """CommandRunner injectable : enregistre les appels et renvoie des sorties en conserve."""

    def __init__(self, profiles: dict[str, tuple[int, str]]) -> None:
        self.profiles = profiles
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]) -> tuple[int, str]:
        self.calls.append(list(argv))
        # kubectl get nodes -o json (liste)
        if argv == ["kubectl", "get", "nodes", "-o", "json"]:
            items = [{"metadata": {"name": name}} for name in self.profiles]
            return 0, json.dumps({"items": items})
        # kubectl get node <hostname> -o json
        if (
            len(argv) == 6
            and argv[0] == "kubectl"
            and argv[1] == "get"
            and argv[2] == "node"
            and argv[4] == "-o"
            and argv[5] == "json"
        ):
            hostname = argv[3]
            if hostname in self.profiles:
                return self.profiles[hostname]
            return 1, ""
        # helm / kubectl label
        if argv[0] == "helm":
            return 0, ""
        if argv[0] == "kubectl" and argv[1] == "label":
            return 0, ""
        return 127, ""


@pytest.fixture
def profiles() -> dict[str, tuple[int, str]]:
    return {
        "gpu-expose": (0, _node_json("gpu-expose", "True", nvidia_cap=2, nvidia_present=True)),
        "gpu-non-expose": (
            0,
            _node_json("gpu-non-expose", "True", nvidia_cap=0, nvidia_present=True),
        ),
        "cpu": (0, _node_json("cpu", "True")),
        "injoignable": (0, _node_json("injoignable", "Unknown")),
    }


def test_sonde_4_profils(profiles: dict[str, tuple[int, str]]) -> None:
    runner = FakeRunner(profiles)
    expose = sonder_noeud(runner, "gpu-expose")
    assert expose["hostname"] == "gpu-expose"
    assert expose["ready"] is True
    assert expose["gpu_nvidia"] == 2
    assert expose["gpu_amd"] == 0
    assert expose["arch"] == "amd64"

    non_expose = sonder_noeud(runner, "gpu-non-expose")
    assert non_expose["ready"] is True
    assert non_expose["gpu_nvidia"] == 0
    assert non_expose["labels"]["nvidia.com/gpu.present"] == "true"

    cpu = sonder_noeud(runner, "cpu")
    assert cpu["ready"] is True
    assert cpu["gpu_nvidia"] == 0
    assert cpu["gpu_amd"] == 0

    inj = sonder_noeud(runner, "injoignable")
    assert inj["ready"] is None


# --- RC1-456-iter3 : même famille que #482/#492/#527/#528 — un nœud kubectl dont le kubelet
# n'a pas encore rapporté sa capacité/nodeInfo (état transitoire réel, PAS une erreur de
# structure) renvoie la clé PRÉSENTE avec une valeur `null` explicite — `.get(clé, défaut)` ne
# protège QUE l'absence de clé, pas une valeur `null` présente. ---
class _RunnerCapaciteNull:
    """Simule `kubectl get node` pour un nœud dont `status.capacity`/`nodeInfo` sont `null`."""

    def run(self, argv: list[str]) -> tuple[int, str]:
        return 0, json.dumps({
            "metadata": {"name": "n1", "labels": {}},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "capacity": None,
                "nodeInfo": None,
            },
        })


def test_sonde_capacity_et_nodeinfo_null_ne_leve_pas() -> None:
    """RC1-456-iter3 : un nœud en cours d'initialisation (kubelet pas encore prêt) peut avoir
    `status.capacity`/`status.nodeInfo` PRÉSENTS mais explicitement `null` — ne doit jamais lever
    AttributeError, seulement produire des valeurs par défaut (0 GPU, arch vide)."""
    etat = sonder_noeud(_RunnerCapaciteNull(), "n1")
    assert etat["gpu_nvidia"] == 0
    assert etat["gpu_amd"] == 0
    assert etat["arch"] == ""
    assert etat["ready"] is True


def test_plan_gpu_expose(profiles: dict[str, tuple[int, str]]) -> None:
    runner = FakeRunner(profiles)
    etat = sonder_noeud(runner, "gpu-expose")
    plan = plan_preparation(etat, helm_present=True)
    ids = [s["id"] for s in plan]
    assert ids == ["verifier-gpu-nvidia", "label-pret"]
    assert plan[0]["action"] == "verifier"
    assert plan[0]["commande"] is None
    assert plan[1]["action"] == "label"
    assert plan[1]["commande"] == [
        "kubectl",
        "label",
        "node",
        "gpu-expose",
        "forgeai/receptacle=pret",
        "--overwrite",
    ]


def test_plan_gpu_non_expose_helm(profiles: dict[str, tuple[int, str]]) -> None:
    runner = FakeRunner(profiles)
    etat = sonder_noeud(runner, "gpu-non-expose")
    plan = plan_preparation(etat, helm_present=True)
    ids = [s["id"] for s in plan]
    assert ids == ["helm-nvidia", "label-pret"]
    assert plan[0]["action"] == "helm"
    assert plan[0]["commande"] == [
        "helm",
        "upgrade",
        "--install",
        "gpu-operator",
        "gpu-operator",
        "--repo",
        "https://helm.ngc.nvidia.com/nvidia",
        "-n",
        "gpu-operator",
        "--create-namespace",
    ]


def test_plan_cpu(profiles: dict[str, tuple[int, str]]) -> None:
    runner = FakeRunner(profiles)
    etat = sonder_noeud(runner, "cpu")
    plan = plan_preparation(etat, helm_present=True)
    assert len(plan) == 1
    assert plan[0]["id"] == "label-cpu"
    assert plan[0]["commande"] == [
        "kubectl",
        "label",
        "node",
        "cpu",
        "forgeai/receptacle=pret-cpu",
        "--overwrite",
    ]


def test_plan_injoignable(profiles: dict[str, tuple[int, str]]) -> None:
    runner = FakeRunner(profiles)
    etat = sonder_noeud(runner, "injoignable")
    plan = plan_preparation(etat, helm_present=True)
    assert len(plan) == 1
    assert plan[0]["id"] == "diagnostic"
    assert plan[0]["action"] == "aucune"
    assert plan[0]["commande"] is None


def test_preparer_applique(profiles: dict[str, tuple[int, str]]) -> None:
    runner = FakeRunner(profiles)
    result = preparer_noeud(
        runner, "gpu-non-expose", appliquer=True, helm_present=True
    )
    assert result["receptacle"] == "pret"
    helm_calls = [c for c in runner.calls if c[0] == "helm"]
    label_calls = [c for c in runner.calls if c[:2] == ["kubectl", "label"]]
    assert len(helm_calls) == 1
    assert len(label_calls) == 1
    assert [e["statut"] for e in result["etapes"]] == ["ok", "ok"]

    # Échec à la première étape : le label ne doit pas être exécuté.
    class HelmFailingRunner(FakeRunner):
        def run(self, argv: list[str]) -> tuple[int, str]:
            if argv and argv[0] == "helm":
                self.calls.append(list(argv))
                return 1, "helm not ready"
            return super().run(argv)

    failing_runner = HelmFailingRunner(profiles)
    with pytest.raises(PrepareError):
        preparer_noeud(
            failing_runner, "gpu-non-expose", appliquer=True, helm_present=True
        )
    assert len([c for c in failing_runner.calls if c[0] == "helm"]) == 1
    assert len([c for c in failing_runner.calls if c[:2] == ["kubectl", "label"]]) == 0


def test_preparer_etape_sans_commande_id_non_diagnostic(
    profiles: dict[str, tuple[int, str]]
) -> None:
    """CAND-016 — dans la boucle de preparer_noeud, une étape sans `commande` dont
    l'id N'EST PAS "diagnostic" (ex. "verifier-gpu-nvidia", simple constat) doit
    être marquée 'sautee' et NE PAS interrompre la préparation — contrairement à
    l'étape spéciale "diagnostic" (même absence de commande) qui, elle, échoue et
    lève PrepareError. Non pinné avant CAND-016 : sans la garde
    `if step["id"] == "diagnostic":`, "verifier-gpu-nvidia" serait traitée comme
    l'étape diagnostic et lèverait à tort, empêchant toute préparation d'un nœud
    dont le GPU est déjà exposé."""
    runner = FakeRunner(profiles)
    # gpu-expose -> plan == ["verifier-gpu-nvidia" (commande=None), "label-pret"]
    result = preparer_noeud(runner, "gpu-expose", appliquer=True, helm_present=True)
    statuts = {e["id"]: e["statut"] for e in result["etapes"]}
    assert statuts["verifier-gpu-nvidia"] == "sautee"
    assert statuts["label-pret"] == "ok"
    assert result["receptacle"] == "pret"

    # Contraste : l'étape "diagnostic" (même absence de commande) DOIT lever.
    with pytest.raises(PrepareError):
        preparer_noeud(runner, "injoignable", appliquer=True, helm_present=True)


def test_cli_plan_sans_apply() -> None:
    # Test subprocess réel : le CLI utilise le vrai kubectl/helm du système.
    # Selon l'environnement, le nœud 'pc-inexistant' est absent (exit 11) ou,
    # si kubectl n'est pas installé, la sonde échoue également (exit 11).
    # On accepte 0 ou 11 et on vérifie que la sortie n'est pas vide.
    result = subprocess.run(
        [sys.executable, "-m", "forgeai.cli", "node", "prepare", "pc-inexistant"],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 11), result.stderr
    assert result.stdout or result.stderr


def test_api_receptacles_graceful() -> None:
    server = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with urllib.request.urlopen(
            f"http://{host}:{port}/api/nodes/receptacles", timeout=5
        ) as resp:
            assert resp.status == 200
            data = json.loads(resp.read())
            assert "nodes" in data
            # Soit le cluster est accessible et on a une liste, soit on a un detail d'erreur.
            if "detail" in data:
                assert data["nodes"] == []
            else:
                assert isinstance(data["nodes"], list)
    finally:
        server.shutdown()
        server.server_close()


def test_plan_amd_expose_symetrique() -> None:
    """Objection revue N3 : AMD exposé doit VÉRIFIER (pas helm), comme NVIDIA."""
    etat = {"hostname": "n-amd", "ready": True, "gpu_nvidia": 0, "gpu_amd": 2,
            "arch": "amd64", "labels": {}}
    plan = plan_preparation(etat, helm_present=True)
    ids = [s["id"] for s in plan]
    assert ids == ["verifier-gpu-amd", "label-pret"]
    assert not any(s["action"] == "helm" for s in plan)


def test_plan_amd_non_expose_helm() -> None:
    """Objection revue N3 : AMD probable non exposé -> helm AMD."""
    etat = {"hostname": "n-amd2", "ready": True, "gpu_nvidia": 0, "gpu_amd": 0,
            "arch": "amd64", "labels": {"feature.node.kubernetes.io/pci-1002.present": "true"}}
    plan = plan_preparation(etat, helm_present=True)
    helm = next(s for s in plan if s["action"] == "helm")
    assert helm["id"] == "helm-amd"
    assert "rocm.github.io" in " ".join(helm["commande"])


def test_statut_attente_si_helm_manquant() -> None:
    """Objection revue N3 : sans helm, JAMAIS étiqueté prêt — statut attente-installation."""
    etat = {"hostname": "n-x", "ready": True, "gpu_nvidia": 0, "gpu_amd": 0,
            "arch": "amd64", "labels": {"feature.node.kubernetes.io/pci-10de.present": "true"}}
    plan = plan_preparation(etat, helm_present=False)
    assert not any(s["id"] in ("label-pret", "label-cpu") for s in plan)
    assert any(s["id"] == "helm-nvidia-manuel" for s in plan)
