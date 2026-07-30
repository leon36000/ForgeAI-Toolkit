"""Story S3b — brique moteur AMD Vulkan déployable (llama.cpp server-vulkan).

Auto-fetch du modèle via `-hf` (repo HF public), auto-split multi-GPU (AUCUN --tensor-split
hardcodé = universel : llama.cpp répartit sur tous les GPU Vulkan présents). `gpu: true` =>
sur profil rocm, assemble (S2) pose gpu_vendor=amd et le renderer k3s (S3/LAB-033A) ajoute
la ressource de device plugin `amd.com/gpu` et la command en args. Le passthrough hostPath
historique est supprimé : le cgroup devices refuse l'accès au char device (EPERM). Serving
réel prouvé sur pc4 (dual RDNA4)."""
import json
import sys
from importlib.resources import files
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.planner.assemble import assemble_plan
from forgeai.renderers.k3s import render_k3s

BRICK = "llama-cpp-vulkan"


def test_brique_amd_vulkan_deployable():
    specs = json.loads((files("forgeai.data") / "deploy-specs.json").read_text(encoding="utf-8"))
    assert BRICK in specs, "la brique llama-cpp-vulkan doit être déployable (deploy-specs)"
    s = specs[BRICK]
    assert "vulkan" in s["image"], "image llama.cpp Vulkan"
    assert s.get("gpu") is True, "brique GPU"
    cmd = " ".join(str(c) for c in s.get("command", []))
    assert "-hf" in cmd, "auto-fetch du modèle via -hf (pas d'initContainer requis)"
    assert "--tensor-split" not in cmd, "pas de tensor-split hardcodé (universel, auto-split)"


def _overlay(tmp_path):
    ov = tmp_path / "ov.json"
    ov.write_text(json.dumps({"profile": "x", "engine_default": "ollama", "services": [
        {"name": "ollama", "brick_id": "ollama", "image": "ollama/ollama:latest",
         "container_port": 11434, "healthcheck_path": "/api/tags"}],
        "models": {"llm": "q", "embed": "b"}}), encoding="utf-8")
    return ov


def _assert_no_hostpath(manifest: str) -> None:
    for doc in yaml.safe_load_all(manifest):
        if doc and doc.get("kind") == "Deployment":
            for vol in doc["spec"]["template"]["spec"].get("volumes") or []:
                assert "hostPath" not in vol, f"volume hostPath interdit : {vol}"


def test_amd_vulkan_rendu_k3s_avec_device_plugin(tmp_path):
    # profil rocm => vendor amd ; le renderer S3 ajoute la ressource amd.com/gpu + la command en args.
    plan = assemble_plan("minimal-gpu-rocm", _overlay(tmp_path), extra_bricks=(BRICK,))
    svc = next((s for s in plan.services if s.name == BRICK), None)
    assert svc is not None, "la brique doit être au plan"
    assert svc.gpu is True and svc.gpu_vendor == "amd"
    out = render_k3s(plan)
    assert 'amd.com/gpu: "1"' in out  # ressource device plugin (LAB-033A)
    assert "-hf" in out  # command propagée en args (S3)
    _assert_no_hostpath(out)
    assert "privileged: true" not in out
