"""Story S2 — réservation GPU PAR VENDOR au rendu compose (corrige le « CPU muet » AMD/Intel).

NVIDIA  = deploy.resources.reservations (driver nvidia, capabilities [gpu]).
AMD ROCm = passthrough devices /dev/kfd + /dev/dri.
Intel    = passthrough device /dev/dri.
Piloté par ServiceSpec.gpu_vendor, dérivé du profil (cuda→nvidia, rocm→amd, intel→intel).
Rétrocompat : gpu=True sans vendor → réservation nvidia (comportement historique préservé).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.planner.assemble import assemble_plan
from forgeai.renderers.compose import render_compose


def _plan(svc):
    return DeploymentPlan(plan_id="p", profile="x", target=RenderTarget.COMPOSE,
                          services=(svc,), model="m", embed_model="e")


def _gpu_svc(vendor):
    return ServiceSpec(name="engine", image="img:latest", host_port=8000,
                       container_port=8000, gpu=True, gpu_vendor=vendor)


def test_render_nvidia_reserve_driver_nvidia():
    out = render_compose(_plan(_gpu_svc("nvidia")))
    assert "driver: nvidia" in out and "capabilities: [gpu]" in out
    assert "/dev/kfd" not in out


def test_render_amd_reserve_kfd_et_dri():
    out = render_compose(_plan(_gpu_svc("amd")))
    assert "/dev/kfd" in out and "/dev/dri" in out
    assert "driver: nvidia" not in out


def test_render_intel_reserve_dri():
    out = render_compose(_plan(_gpu_svc("intel")))
    assert "/dev/dri" in out
    assert "driver: nvidia" not in out and "/dev/kfd" not in out


def test_render_gpu_sans_vendor_reste_nvidia_retrocompat():
    out = render_compose(_plan(
        ServiceSpec(name="e", image="i", host_port=1, container_port=1, gpu=True)))
    assert "driver: nvidia" in out


def test_render_sans_gpu_aucune_reservation():
    out = render_compose(_plan(
        ServiceSpec(name="e", image="i", host_port=1, container_port=1, gpu=False)))
    assert "driver: nvidia" not in out and "/dev/kfd" not in out and "/dev/dri" not in out


# --- assemblage : le profil vendor propage gpu=True + gpu_vendor -------------------
def _overlay(tmp_path):
    ov = tmp_path / "ov.json"
    ov.write_text(json.dumps({"profile": "x", "engine_default": "ollama", "services": [
        {"name": "ollama", "brick_id": "ollama",
         "image": "ollama/ollama:rocm@sha256:0000000000000000000000000000000000000000000000000000000000000000",
         "container_port": 11434, "healthcheck_path": "/api/tags", "gpu_capable": True}],
        "models": {"llm": "qwen2.5:0.5b", "embed": "bge-m3"}}), encoding="utf-8")
    return ov


def test_assemble_profil_rocm_marque_gpu_amd(tmp_path):
    plan = assemble_plan("minimal-gpu-rocm", _overlay(tmp_path))
    ollama = next(s for s in plan.services if s.name == "ollama")
    assert ollama.gpu is True and ollama.gpu_vendor == "amd"
    assert "/dev/kfd" in render_compose(plan)


def test_assemble_profil_cuda_marque_gpu_nvidia(tmp_path):
    plan = assemble_plan("minimal-gpu-cuda", _overlay(tmp_path))
    ollama = next(s for s in plan.services if s.name == "ollama")
    assert ollama.gpu is True and ollama.gpu_vendor == "nvidia"


def test_assemble_profil_cpu_pas_de_gpu(tmp_path):
    plan = assemble_plan("minimal-cpu", _overlay(tmp_path))
    ollama = next(s for s in plan.services if s.name == "ollama")
    assert ollama.gpu is False
