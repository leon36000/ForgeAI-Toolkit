"""Story S3 — renderer k3s : GPU par ressource de device plugin par vendor (LAB-033A).

NVIDIA  = ressource nvidia.com/gpu (device-plugin).
AMD     = ressource amd.com/gpu (device-plugin) — remplace le passthrough hostPath
          /dev/kfd+/dev/dri qui ne fonctionnait pas (cgroup devices refuse l'accès).
Intel   = ressource gpu.intel.com/i915 (device-plugin) — même remplacement.
gpu sans vendor => nvidia.
Prouve la FUSION propre : ressource GPU + volume data = UN seul bloc volumeMounts / volumes.
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s


def _plan(svc):
    return DeploymentPlan(plan_id="p1-test", profile="minimal-gpu-rocm", target=RenderTarget.K3S,
                          services=(svc,), model="m", embed_model="e")


def _gpu(vendor, volumes=()):
    return ServiceSpec(name="engine", image="img:latest", host_port=8000, container_port=8000,
                       gpu=True, gpu_vendor=vendor, volumes=volumes)


def _volumes(manifest: str) -> list[dict]:
    vols = []
    for doc in yaml.safe_load_all(manifest):
        if doc and doc.get("kind") == "Deployment":
            for v in doc["spec"]["template"]["spec"].get("volumes") or []:
                vols.append(v)
    return vols


def _assert_no_hostpath(manifest: str) -> None:
    """Vérifie qu'aucun volume n'utilise la clé YAML hostPath (pas seulement la sous-chaîne)."""
    for vol in _volumes(manifest):
        assert "hostPath" not in vol, f"volume hostPath interdit trouvé : {vol}"


def test_k3s_nvidia_garde_resource():
    out = render_k3s(_plan(_gpu("nvidia")))
    assert 'nvidia.com/gpu: "1"' in out
    assert "/dev/kfd" not in out


def test_k3s_amd_ressource_device_plugin():
    """LAB-033A : amd.com/gpu via device plugin ; plus de passthrough hostPath."""
    out = render_k3s(_plan(_gpu("amd")))
    assert 'amd.com/gpu: "1"' in out
    _assert_no_hostpath(out)
    assert "privileged: true" not in out
    assert "allowPrivilegeEscalation: false" in out


def test_k3s_intel_ressource_device_plugin():
    """LAB-033A : gpu.intel.com/i915 via device plugin ; plus de passthrough hostPath."""
    out = render_k3s(_plan(_gpu("intel")))
    assert 'gpu.intel.com/i915: "1"' in out
    _assert_no_hostpath(out)
    assert "privileged: true" not in out
    assert "allowPrivilegeEscalation: false" in out


def test_k3s_intel_device_plugin_sans_hostpath():
    """Variante Intel : seule la ressource de device plugin est émise."""
    out = render_k3s(_plan(_gpu("intel")))
    assert 'gpu.intel.com/i915: "1"' in out
    _assert_no_hostpath(out)
    assert "nvidia.com/gpu" not in out
    assert "amd.com/gpu" not in out


def test_k3s_gpu_vendor_inconnu_refuse():
    with pytest.raises((ValueError, KeyError)):
        render_k3s(_plan(_gpu("exotic-vendor")))


def test_k3s_amd_avec_volume_data_fusionne_un_seul_bloc():
    """Le volume data utilisateur reste fusionné avec la ressource GPU en un seul bloc YAML."""
    out = render_k3s(_plan(_gpu("amd", volumes=("data:/root/.cache",))))
    assert out.count("volumeMounts:") == 1, "un seul bloc volumeMounts (sinon YAML invalide)"
    assert out.count("\n      volumes:") == 1, "un seul bloc volumes (sinon YAML invalide)"
    assert "/root/.cache" in out
    assert 'amd.com/gpu: "1"' in out
    _assert_no_hostpath(out)


def test_k3s_sans_gpu_aucun_device_ni_privileged():
    out = render_k3s(_plan(
        ServiceSpec(name="x", image="i", host_port=1, container_port=1, gpu=False)))
    assert "/dev/kfd" not in out and "privileged" not in out and "nvidia.com/gpu" not in out


def test_k3s_gpu_sans_vendor_reste_nvidia():
    out = render_k3s(_plan(
        ServiceSpec(name="x", image="i", host_port=1, container_port=1, gpu=True)))
    assert 'nvidia.com/gpu: "1"' in out


def test_k3s_tous_les_volumes_rendus():
    svc = ServiceSpec(name="e", image="i", host_port=1, container_port=1,
                      volumes=("data:/a", "cache:/b"))
    out = render_k3s(_plan(svc))
    assert "/a" in out and "/b" in out
    assert "name: data" in out and "name: cache" in out
    assert out.count("volumeMounts:") == 1 and out.count("\n      volumes:") == 1


def test_k3s_command_rendu_en_args():
    svc = ServiceSpec(name="e", image="i", host_port=1, container_port=1,
                      command=("--model", "/m.gguf", "--tensor-split", "32,16"))
    out = render_k3s(_plan(svc))
    assert "args:" in out
    assert '- "--model"' in out and '- "/m.gguf"' in out and '- "32,16"' in out
