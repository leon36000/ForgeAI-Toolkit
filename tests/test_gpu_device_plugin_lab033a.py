"""Tests LAB-033A — GPU par ressource de device plugin, sans passthrough hostPath.

Mesuré sur cluster k3s v1.35.5 réel :
- hostPath de char device : le cgroup devices refuse l'accès (EPERM), même root ;
- `limits: <vendor>.com/gpu: "1"` sans hostPath ni privileged rend le GPU accessible ;
- un pod GPU root est refusé par enforce=restricted mais accepté par enforce=baseline.
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import CapaciteCluster, DeploymentPlan, QuotaError, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s


def _plan(*services):
    return DeploymentPlan(
        plan_id="p1-lab033a",
        profile="minimal-gpu-rocm",
        target=RenderTarget.K3S,
        services=services,
        model="m",
        embed_model="e",
    )


def _gpu(vendor: str, name: str = "engine"):
    return ServiceSpec(
        name=name,
        image="img:latest",
        host_port=8000,
        container_port=8000,
        gpu=True,
        gpu_vendor=vendor,
    )


def _volumes(manifest: str) -> list[dict]:
    vols = []
    for doc in yaml.safe_load_all(manifest):
        if doc and doc.get("kind") == "Deployment":
            for v in doc["spec"]["template"]["spec"].get("volumes") or []:
                vols.append(v)
    return vols


def _namespace(manifest: str) -> dict:
    for doc in yaml.safe_load_all(manifest):
        if doc and doc.get("kind") == "Namespace":
            return doc
    raise AssertionError("aucun Namespace dans le manifeste")


_ALL_GPU_RESOURCES = frozenset({
    "nvidia.com/gpu",
    "amd.com/gpu",
    "gpu.intel.com/i915",
})


@pytest.mark.parametrize("vendor,ressource", [
    ("nvidia", "nvidia.com/gpu"),
    ("amd", "amd.com/gpu"),
    ("intel", "gpu.intel.com/i915"),
])
def test_ressource_par_vendor(vendor, ressource):
    """Chaque vendor reçoit la ressource de SON device plugin, et jamais celle d'un autre."""
    out = render_k3s(_plan(_gpu(vendor)))
    assert f'{ressource}: "1"' in out
    for autre in _ALL_GPU_RESOURCES - {ressource}:
        assert autre not in out


@pytest.mark.parametrize("vendor", ["nvidia", "amd", "intel"])
def test_aucun_volume_hostpath_pour_aucun_vendor(vendor):
    """LAB-033A : le passthrough hostPath est inopérant (cgroup devices refuse l'accès) ;
    aucun volume de pod ne doit donc porter la clé `hostPath`."""
    out = render_k3s(_plan(_gpu(vendor)))
    for vol in _volumes(out):
        assert "hostPath" not in vol, f"volume hostPath trouvé pour {vendor} : {vol}"


def test_enforce_baseline_pour_plan_gpu_et_restricted_sinon():
    """Un plan GPU root est refusé par enforce=restricted mais accepté par enforce=baseline,
    mesuré sur k3s v1.35.5. Un plan sans GPU reste conforme restricted."""
    gpu_labels = _namespace(render_k3s(_plan(_gpu("amd"))))["metadata"].get("labels") or {}
    assert gpu_labels["pod-security.kubernetes.io/enforce"] == "baseline"
    assert gpu_labels["pod-security.kubernetes.io/audit"] == "restricted"
    assert gpu_labels["pod-security.kubernetes.io/warn"] == "restricted"

    cpu = ServiceSpec(name="cpu", image="i", host_port=1, container_port=1, gpu=False)
    cpu_labels = _namespace(render_k3s(_plan(cpu)))["metadata"].get("labels") or {}
    assert cpu_labels["pod-security.kubernetes.io/enforce"] == "restricted"


def test_capacite_refuse_si_ressource_gpu_absente():
    """Si le cluster déclare une ressource GPU mais pas celle du vendor demandé, le plan
    doit être refusé AVANT application, avec le nom de la ressource manquante."""
    plan = _plan(_gpu("amd"))
    cap = CapaciteCluster(
        cpu_millicores=16000,
        memoire_mib=32768,
        ressources_gpu={"nvidia.com/gpu": 1},
    )
    with pytest.raises(QuotaError) as exc:
        render_k3s(plan, capacite=cap)
    message = str(exc.value)
    assert "ERR_QUOTA_GPU_PLUGIN_ABSENT" in message
    assert "amd.com/gpu" in message


def test_capacite_accepte_si_ressource_gpu_suffisante():
    """Capacité GPU suffisante pour le vendor demandé -> rendu OK."""
    plan = _plan(_gpu("amd"))
    cap = CapaciteCluster(
        cpu_millicores=16000,
        memoire_mib=32768,
        ressources_gpu={"amd.com/gpu": 2},
    )
    out = render_k3s(plan, capacite=cap)
    assert 'amd.com/gpu: "1"' in out


def test_retrocompat_capacite_none_et_ressources_gpu_vide():
    """Aucune information GPU fournie -> on ne refuse pas le rendu (rétro-compatibilité).
    Les vérifications CPU/mémoire continuent de s'appliquer."""
    plan = _plan(_gpu("amd"))
    out = render_k3s(plan, capacite=None)
    assert 'amd.com/gpu: "1"' in out

    cap_ok = CapaciteCluster(
        cpu_millicores=16000,
        memoire_mib=32768,
        ressources_gpu={},
    )
    out = render_k3s(plan, capacite=cap_ok)
    assert 'amd.com/gpu: "1"' in out

    # CPU/mémoire toujours vérifiés même si ressources_gpu est vide.
    gros_gpu = ServiceSpec(
        name="engine",
        image="img:latest",
        host_port=8000,
        container_port=8000,
        gpu=True,
        gpu_vendor="amd",
        resource_class="llm",
    )
    cap_trop_petit = CapaciteCluster(
        cpu_millicores=100,
        memoire_mib=32768,
        ressources_gpu={},
    )
    with pytest.raises(QuotaError):
        render_k3s(_plan(gros_gpu), capacite=cap_trop_petit)


def test_capacite_gpu_negative_refusee():
    """Une capacité GPU négative est incohérente et doit être rejetée."""
    with pytest.raises(ValueError, match="ERR_QUOTA_GPU_INVALIDE"):
        CapaciteCluster(
            cpu_millicores=16000,
            memoire_mib=32768,
            ressources_gpu={"amd.com/gpu": -1},
        )
