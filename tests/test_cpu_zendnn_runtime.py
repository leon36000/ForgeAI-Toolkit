"""Story S-ZEN — inférence CPU AMD Zen via ZenDNN : brique `cpu-zendnn` + rendu `env` k3s.

Image AMD `amdih/zendnn_zentorch` (vLLM + plugin zentorch, plug-and-play), gpu:false (CPU), env de
tuning ZENDNNL_*. Le renderer k3s doit rendre le champ `env` (parité compose) sinon les réglages
ZenDNN sont perdus. Serving réel prouvé sur le CPU Zen5 de pc4 (zentorch activé, complétion OpenAI).
"""
import json
import sys
from importlib.resources import files
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.planner.assemble import assemble_plan
from forgeai.renderers.k3s import render_k3s

BRICK = "cpu-zendnn"


def test_brique_cpu_zendnn_deployable():
    specs = json.loads((files("forgeai.data") / "deploy-specs.json").read_text(encoding="utf-8"))
    assert BRICK in specs, "la brique cpu-zendnn doit être déployable (deploy-specs)"
    s = specs[BRICK]
    assert "zendnn" in s["image"].lower() or "zentorch" in s["image"].lower()
    assert s.get("gpu", False) is False, "ZenDNN = inférence CPU (pas GPU)"
    cmd = " ".join(str(c) for c in s.get("command", []))
    assert "vllm" in cmd and "serve" in cmd, "vllm serve (API OpenAI)"
    assert "ZENDNNL_MATMUL_ALGO" in s.get("env", {}), "tuning ZenDNN présent"


def test_k3s_rend_le_champ_env():
    # GAP corrigé : le renderer k3s doit émettre le bloc env (parité compose).
    svc = ServiceSpec(name="e", image="i", host_port=1, container_port=1,
                      env={"ZENDNNL_MATMUL_ALGO": "1", "FOO": "bar"})
    out = render_k3s(DeploymentPlan(plan_id="p", profile="x", target=RenderTarget.K3S,
                                    services=(svc,), model="m", embed_model="e"))
    assert "env:" in out
    assert "ZENDNNL_MATMUL_ALGO" in out and "FOO" in out and "bar" in out


def _overlay(tmp_path):
    ov = tmp_path / "ov.json"
    ov.write_text(json.dumps({"profile": "x", "engine_default": "ollama", "services": [
        {"name": "ollama", "brick_id": "ollama", "image": "ollama/ollama:latest",
         "container_port": 11434, "healthcheck_path": "/api/tags"}],
        "models": {"llm": "q", "embed": "b"}}))
    return ov


def test_cpu_zendnn_assemble_sans_gpu(tmp_path):
    # ZenDNN = CPU : la brique ne doit PAS être marquée GPU quel que soit le profil.
    plan = assemble_plan("minimal-cpu", _overlay(tmp_path), extra_bricks=(BRICK,))
    svc = next((s for s in plan.services if s.name == BRICK), None)
    assert svc is not None and svc.gpu is False
    out = render_k3s(plan)
    assert "vllm" in out and "ZENDNNL_MATMUL_ALGO" in out
