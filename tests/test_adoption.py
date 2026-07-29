"""Tests figeant le comportement d'adoption de services existants."""

import pytest
import yaml

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import AdoptionNonSupporteeK3s, render_k3s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _service_litellm(adopted_endpoint=None):
    """Service dépendant : litellm, éventuellement branché sur un endpoint adopté."""
    return ServiceSpec(
        name="litellm",
        image="ghcr.io/berriai/litellm:latest",
        host_port=4000,
        container_port=4000,
        depends=("redis",),
        adopted_endpoint=adopted_endpoint,
    )


def _service_redis(adopted_endpoint=None):
    return ServiceSpec(
        name="redis",
        image="redis:7",
        host_port=6379,
        container_port=6379,
        depends=(),
        adopted_endpoint=adopted_endpoint,
    )


def _plan(services, target=RenderTarget.COMPOSE, profile="minimal-cpu", model="m", embed_model="e"):
    return DeploymentPlan(
        plan_id="p",
        profile=profile,
        target=target,
        services=tuple(services),
        model=model,
        embed_model=embed_model,
    )


def _parse_compose(yaml_text):
    return yaml.safe_load(yaml_text)


# ---------------------------------------------------------------------------
# CA-1 : service adopté absent de la section services
# ---------------------------------------------------------------------------

def test_CA1_service_adopte_absent_de_services():
    plan = _plan([_service_redis(adopted_endpoint="127.0.0.1:6379"), _service_litellm()])
    compose = _parse_compose(render_compose(plan))
    services = compose["services"]
    assert "redis" not in services
    assert "litellm" in services


# ---------------------------------------------------------------------------
# CA-2 : le dépendant ne référence plus le service adopté dans depends_on
# ---------------------------------------------------------------------------

def test_CA2_dependant_ne_reference_plus_service_adopte():
    plan = _plan([_service_redis(adopted_endpoint="127.0.0.1:6379"), _service_litellm()])
    compose = _parse_compose(render_compose(plan))
    litellm = compose["services"]["litellm"]
    depends_on = litellm.get("depends_on")
    assert depends_on is None or depends_on == [] or depends_on == {}
    assert "redis" not in (depends_on or [])


# ---------------------------------------------------------------------------
# CA-3 : extra_hosts host.docker.internal:host-gateway
# ---------------------------------------------------------------------------

def test_CA3_dependant_porte_extra_hosts():
    plan = _plan([_service_redis(adopted_endpoint="127.0.0.1:6379"), _service_litellm()])
    compose = _parse_compose(render_compose(plan))
    extra_hosts = compose["services"]["litellm"].get("extra_hosts")
    assert extra_hosts == ["host.docker.internal:host-gateway"]


# ---------------------------------------------------------------------------
# CA-4 : render_k3s lève AdoptionNonSupporteeK3s (adoption non supportée)
# ---------------------------------------------------------------------------

def test_CA4_k3s_leve_adoption_non_supportee():
    plan = _plan(
        services=[
            ServiceSpec(
                name="svc-a",
                image="img-a:1",
                host_port=8001,
                container_port=8000,
                depends=(),
                adopted_endpoint="10.0.0.1:6379",
            ),
            ServiceSpec(
                name="svc-b",
                image="img-b:1",
                host_port=8002,
                container_port=8000,
                depends=(),
                adopted_endpoint="10.0.0.2:5432",
            ),
        ],
        target=RenderTarget.K3S,
    )
    with pytest.raises(AdoptionNonSupporteeK3s) as excinfo:
        render_k3s(plan)
    msg = str(excinfo.value)
    assert "ERR_ADOPT_K3S_NON_SUPPORTE" in msg
    assert "svc-a" in msg
    assert "svc-b" in msg
    assert "10.0.0.1:6379" in msg
    assert "10.0.0.2:5432" in msg


# ---------------------------------------------------------------------------
# CA-5 : rejets de ServiceSpec(adopted_endpoint=...) — 7 cas paramétrés
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "valeur_invalide, code_attendu",
    [
        ("pasdeport", "ERR_ADOPT_FORME"),
        ("::1:6379", "ERR_ADOPT_FORME"),
        (":6379", "ERR_ADOPT_FORME"),
        ("ho te:6379", "ERR_ADOPT_HOTE"),
        ("127.0.0.1:abc", "ERR_ADOPT_PORT"),
        ("127.0.0.1:0", "ERR_ADOPT_PORT_BORNES"),
        ("127.0.0.1:70000", "ERR_ADOPT_PORT_BORNES"),
    ],
)
def test_CA5_service_spec_rejette_adopted_endpoint_invalide(valeur_invalide, code_attendu):
    with pytest.raises(ValueError, match=code_attendu):
        ServiceSpec(
            name="litellm",
            image="ghcr.io/berriai/litellm:latest",
            host_port=4000,
            container_port=4000,
            depends=("redis",),
            adopted_endpoint=valeur_invalide,
        )


# ---------------------------------------------------------------------------
# CA-6 : non-régression — sans adoption, comportement nominal
# ---------------------------------------------------------------------------

def test_CA6_non_regression_sans_adoption_compose():
    plan = _plan([_service_litellm(adopted_endpoint=None), _service_redis()])
    compose = _parse_compose(render_compose(plan))
    services = compose["services"]
    assert "litellm" in services
    assert "redis" in services
    assert list(services["litellm"]["depends_on"]) == ["redis"]
    assert "extra_hosts" not in services["litellm"]


def test_CA6_non_regression_sans_adoption_k3s_ne_leve_pas():
    plan = _plan(
        services=[_service_litellm(adopted_endpoint=None), _service_redis()],
        target=RenderTarget.K3S,
    )
    # Ne doit PAS lever : l'adoption n'est pas en cause ici.
    output = render_k3s(plan)
    assert isinstance(output, str)
    assert output.strip() != ""
