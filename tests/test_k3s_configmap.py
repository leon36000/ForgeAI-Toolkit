"""Tests FAI-0006 — bind-mount de fichier de config via ConfigMap dans render_k3s."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


LITELLM_CONFIG = """model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
"""


def _svc(**kw):
    d = dict(name="ollama", image="ollama/ollama:latest", host_port=21434, container_port=11434)
    d.update(kw)
    return ServiceSpec(**d)


def _plan(services):
    return DeploymentPlan(
        plan_id="t", profile="minimal-cpu", target=RenderTarget.K3S,
        services=tuple(services), model="m", embed_model="e"
    )


def _plan_litellm():
    return _plan([
        _svc(
            name="litellm",
            image="litellm/litellm:latest",
            host_port=24000,
            container_port=4000,
            volumes=("./litellm-config.yaml:/app/litellm-config.yaml:ro",),
            command=["litellm", "--config", "/app/litellm-config.yaml"],
        )
    ])


def _plan_redis():
    return _plan([
        _svc(
            name="redis",
            image="redis:7",
            host_port=26379,
            container_port=6379,
            volumes=("forgeai-redis-data:/data",),
        )
    ])


def test_configmap_emis_pour_bind_mount_fichier():
    out = render_k3s(_plan_litellm(), config_files={"litellm-config.yaml": LITELLM_CONFIG})

    assert "kind: ConfigMap" in out
    assert "name: litellm-config" in out
    assert "subPath: litellm-config.yaml" in out
    assert "readOnly: true" in out
    assert "mountPath: /app/litellm-config.yaml" in out
    assert "/app/litellm-config.yaml:ro" not in out
    assert "./litellm-config.yaml" not in out
    assert "configMap:" in out


def test_configmap_avant_deployment_et_contenu_preserve():
    out = render_k3s(_plan_litellm(), config_files={"litellm-config.yaml": LITELLM_CONFIG})

    assert out.find("kind: ConfigMap") < out.find("kind: Deployment")

    if yaml is not None:
        docs = list(yaml.safe_load_all(out))
        cm = next(d for d in docs if d.get("kind") == "ConfigMap")
        assert cm["data"]["litellm-config.yaml"] == LITELLM_CONFIG
    else:
        for line in LITELLM_CONFIG.splitlines():
            assert f"    {line}" in out


def test_fail_fast_sans_config_files():
    with pytest.raises(ValueError):
        render_k3s(_plan_litellm(), config_files=None)


def test_non_regression_volume_data():
    out = render_k3s(_plan_redis(), config_files=None)

    assert "emptyDir: {}" in out
    assert "forgeai-redis-data" in out
    assert "kind: ConfigMap" not in out


def test_backward_compat_sans_bind_mount_config():
    assert render_k3s(_plan_redis()) == render_k3s(_plan_redis(), config_files=None)
