"""Tests FAI-0007 — env ${FORGEAI_*} → secretKeyRef / $(VAR) dans render_k3s."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s


def _svc(**kw):
    d = dict(name="litellm", image="litellm/litellm:latest", host_port=24000, container_port=4000)
    d.update(kw)
    return ServiceSpec(**d)


def _plan(services):
    return DeploymentPlan(
        plan_id="t", profile="minimal-cpu", target=RenderTarget.K3S,
        services=tuple(services), model="m", embed_model="e"
    )


def _plan_with_env():
    return _plan([
        _svc(
            env={
                "LITELLM_MASTER_KEY": "${FORGEAI_LITELLM_KEY}",
                "LANGFUSE_HOST": "http://langfuse:3000",
                "DATABASE_URL": "postgresql://postgres:${FORGEAI_PG_PASSWORD}@postgres:5432/langfuse",
            }
        )
    ])


def test_reference_pure_devient_secret_key_ref():
    out = render_k3s(_plan_with_env())
    assert 'value: "${FORGEAI_LITELLM_KEY}"' not in out
    assert "secretKeyRef" in out
    assert "name: forgeai-secrets" in out
    assert "key: FORGEAI_LITELLM_KEY" in out


def test_litteral_inchange_pas_secret_key_ref():
    out = render_k3s(_plan_with_env())
    assert 'value: "http://langfuse:3000"' in out
    langfuse_pos = out.find("name: LANGFUSE_HOST")
    assert langfuse_pos != -1
    following = out[langfuse_pos:langfuse_pos + 200]
    assert "secretKeyRef" not in following


def test_reference_embarquee_reecrite_et_auxiliaire_avant():
    out = render_k3s(_plan_with_env())
    assert "key: FORGEAI_PG_PASSWORD" in out
    assert out.find("key: FORGEAI_PG_PASSWORD") < out.find("name: DATABASE_URL")
    assert "$(FORGEAI_PG_PASSWORD)" in out
    assert "${FORGEAI_PG_PASSWORD}" not in out


def test_aucune_reference_forgeai_dans_sortie():
    out = render_k3s(_plan_with_env())
    assert "${FORGEAI" not in out


def test_non_regression_service_sans_env_secret():
    out = render_k3s(
        _plan([_svc(name="redis", image="redis:7", host_port=26379, container_port=6379)])
    )
    assert "secretKeyRef" not in out
    assert "env:" not in out
