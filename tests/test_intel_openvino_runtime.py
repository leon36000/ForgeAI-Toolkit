"""Story S5 — brique moteur Intel/OpenVINO déployable (OpenVINO Model Server / OVMS).

Image OVMS, API OpenAI `/v3/chat/completions`, modèle OV pré-converti (repo HF public), auto-fetch
via --source_model. `--target_device AUTO` = universel (GPU Intel si présent, sinon CPU). gpu:false
par défaut (CPU/AUTO ; l'accélération GPU Intel s'obtient sur un nœud Intel via le passthrough
intel de S3 + --target_device GPU). Serving réel prouvé sur le CPU de pc4 (OVMS sert /v3).
"""
import json
import sys
from importlib.resources import files
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.planner.assemble import assemble_plan
from forgeai.renderers.k3s import render_k3s

BRICK = "intel-openvino"


def test_brique_intel_openvino_deployable():
    specs = json.loads((files("forgeai.data") / "deploy-specs.json").read_text(encoding="utf-8"))
    assert BRICK in specs, "la brique intel-openvino doit être déployable (deploy-specs)"
    s = specs[BRICK]
    assert "openvino" in s["image"] or "model_server" in s["image"]
    cmd = " ".join(str(c) for c in s.get("command", []))
    assert "text_generation" in cmd, "OVMS servi en génération de texte (API OpenAI)"
    assert "--source_model" in cmd, "auto-fetch du modèle OV via --source_model"


def _overlay(tmp_path):
    ov = tmp_path / "ov.json"
    ov.write_text(json.dumps({"profile": "x", "engine_default": "ollama", "services": [
        {"name": "ollama", "brick_id": "ollama", "image": "ollama/ollama:latest@sha256:0000000000000000000000000000000000000000000000000000000000000000",
         "container_port": 11434, "healthcheck_path": "/api/tags"}],
        "models": {"llm": "q", "embed": "b"}}))
    return ov


def test_intel_openvino_rendu_k3s(tmp_path):
    plan = assemble_plan("minimal-cpu", _overlay(tmp_path), extra_bricks=(BRICK,))
    svc = next((s for s in plan.services if s.name == BRICK), None)
    assert svc is not None, "la brique doit être au plan"
    out = render_k3s(plan)
    assert "openvino" in out.lower() or "model_server" in out
    assert "text_generation" in out  # command OVMS propagée en args
    assert "/models" in out  # volume writable pour le download du modèle (sinon Permission denied)
