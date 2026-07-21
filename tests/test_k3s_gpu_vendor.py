"""Story S3 — renderer k3s : passthrough GPU PAR VENDOR (parallèle du renderer compose de S2).

AMD  = hostPath /dev/kfd + /dev/dri + privileged (marche sur un nœud NU, sans device-plugin AMD
       installé — c'est ce qui a servi le dual-GPU RDNA4 sur pc4).
Intel = hostPath /dev/dri + privileged.
NVIDIA = ressource nvidia.com/gpu (modèle device-plugin, inchangé). gpu sans vendor => nvidia.
Prouve la FUSION propre : montages device GPU + volume data = UN seul bloc volumeMounts / volumes
(sinon YAML invalide par clé dupliquée).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s


def _plan(svc):
    return DeploymentPlan(plan_id="p1-test", profile="minimal-gpu-rocm", target=RenderTarget.K3S,
                          services=(svc,), model="m", embed_model="e")


def _gpu(vendor, volumes=()):
    return ServiceSpec(name="engine", image="img:latest", host_port=8000, container_port=8000,
                       gpu=True, gpu_vendor=vendor, volumes=volumes)


def test_k3s_nvidia_garde_resource():
    out = render_k3s(_plan(_gpu("nvidia")))
    assert 'nvidia.com/gpu: "1"' in out
    assert "/dev/kfd" not in out


def test_k3s_amd_passthrough_kfd_dri_privileged():
    out = render_k3s(_plan(_gpu("amd")))
    assert "/dev/kfd" in out and "/dev/dri" in out
    assert "privileged: true" in out
    assert "nvidia.com/gpu" not in out


def test_k3s_intel_passthrough_dri():
    out = render_k3s(_plan(_gpu("intel")))
    assert "/dev/dri" in out
    assert "/dev/kfd" not in out and "nvidia.com/gpu" not in out


def test_k3s_amd_avec_volume_data_fusionne_un_seul_bloc():
    # piège YAML : montages device + volume data DOIVENT fusionner en UN volumeMounts + UN volumes
    out = render_k3s(_plan(_gpu("amd", volumes=("data:/root/.cache",))))
    assert out.count("volumeMounts:") == 1, "un seul bloc volumeMounts (sinon YAML invalide)"
    assert out.count("\n      volumes:") == 1, "un seul bloc volumes (sinon YAML invalide)"
    assert "/root/.cache" in out and "/dev/kfd" in out and "/dev/dri" in out
    assert "name: data" in out  # le volume data reste présent


def test_k3s_sans_gpu_aucun_device_ni_privileged():
    out = render_k3s(_plan(
        ServiceSpec(name="x", image="i", host_port=1, container_port=1, gpu=False)))
    assert "/dev/kfd" not in out and "privileged" not in out and "nvidia.com/gpu" not in out


def test_k3s_gpu_sans_vendor_reste_nvidia():
    out = render_k3s(_plan(
        ServiceSpec(name="x", image="i", host_port=1, container_port=1, gpu=True)))
    assert 'nvidia.com/gpu: "1"' in out


def test_k3s_tous_les_volumes_rendus():
    # finding revue : TOUS les volumes data doivent être rendus, pas seulement le premier.
    svc = ServiceSpec(name="e", image="i", host_port=1, container_port=1,
                      volumes=("data:/a", "cache:/b"))
    out = render_k3s(_plan(svc))
    assert "/a" in out and "/b" in out
    assert "name: data" in out and "name: cache" in out
    assert out.count("volumeMounts:") == 1 and out.count("\n      volumes:") == 1


def test_k3s_command_rendu_en_args():
    # parité compose : svc.command doit apparaître comme `args:` k8s (serving llama.cpp etc.)
    svc = ServiceSpec(name="e", image="i", host_port=1, container_port=1,
                      command=("--model", "/m.gguf", "--tensor-split", "32,16"))
    out = render_k3s(_plan(svc))
    assert "args:" in out
    assert '- "--model"' in out and '- "/m.gguf"' in out and '- "32,16"' in out
