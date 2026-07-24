"""S4 (#145) — service compose openbao-unsealer + depends_on service_healthy des consommateurs.

Preuve : le manifeste compose rendu est un YAML valide où (1) un service `openbao-unsealer` re-descelle
openbao à travers le réseau (clés en bind-mount hôte RO, même script que le sidecar k3s de S3) ; (2) un
consommateur d'openbao attend `service_healthy` (= coffre descellé) ; (3) non-régression : sans openbao,
aucun unsealer et depends_on garde la forme liste.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

try:  # PyYAML = dépendance de TEST seulement (le paquet runtime reste sans dépendance) ; skip si absent.
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers._openbao import UNSEAL_SCRIPT
from forgeai.renderers.compose import render_compose

pytestmark = pytest.mark.skipif(yaml is None, reason="PyYAML absent (dépendance de test) — validation YAML")

_OPENBAO = ServiceSpec(
    name="openbao", image="openbao/openbao:2.6.0", host_port=8200, container_port=8200,
    healthcheck_url="http://127.0.0.1:8200/v1/sys/health",
    volumes=("forgeai-openbao-data:/openbao/file",),
    command=("server", "-config=/openbao/config/openbao.hcl"),
)
_LITELLM = ServiceSpec(
    name="litellm", image="ghcr.io/berriai/litellm:main-stable", host_port=4000,
    container_port=4000, depends=("openbao",),
)
_REDIS = ServiceSpec(
    name="redis", image="redis:7-alpine", host_port=6379, container_port=6379,
    volumes=("forgeai-redis-data:/data",),
)


def _plan(services: tuple[ServiceSpec, ...]) -> DeploymentPlan:
    return DeploymentPlan(
        plan_id="s4-test", profile="minimal-cpu", target=RenderTarget.COMPOSE,
        services=services, model="qwen2.5:0.5b", embed_model="nomic-embed-text",
    )


def _render(services: tuple[ServiceSpec, ...]) -> dict:
    manifest = render_compose(_plan(services))
    data = yaml.safe_load(manifest)  # échoue si le YAML est invalide
    assert data is not None
    return data


def test_manifest_yaml_valide_avec_unsealer() -> None:
    data = _render((_OPENBAO, _LITELLM))
    assert "openbao-unsealer" in data["services"], list(data["services"])


def test_service_unsealer_champs() -> None:
    side = _render((_OPENBAO, _LITELLM))["services"]["openbao-unsealer"]
    assert side["image"] == _OPENBAO.image  # même image openbao (bao présent)
    assert side["restart"] == "unless-stopped"
    # depends_on openbao en service_STARTED (pas healthy : le unsealer EST ce qui descelle)
    assert side["depends_on"] == {"openbao": {"condition": "service_started"}}
    assert side["environment"]["BAO_ADDR"] == "http://openbao:8200"  # nom réseau, pas localhost
    assert "./openbao-keys:/keys:ro" in side["volumes"]  # key-store hôte séparé, RO
    cmd = side["command"]
    assert cmd[0] == "/bin/sh" and cmd[1] == "-c"
    script = cmd[2]
    assert "bao status" in script and "operator unseal" in script and "/keys/unseal_key" in script


def test_consommateur_attend_service_healthy() -> None:
    litellm = _render((_OPENBAO, _LITELLM))["services"]["litellm"]
    # le consommateur attend que le coffre soit DESCELLÉ (healthcheck openbao ne passe qu'unsealed)
    assert litellm["depends_on"] == {"openbao": {"condition": "service_healthy"}}


def test_depends_mixte_openbao_et_autre_en_forme_map() -> None:
    consumer = ServiceSpec(
        name="app", image="app:1", host_port=9000, container_port=9000,
        depends=("openbao", "redis"),
    )
    app = _render((_OPENBAO, _REDIS, consumer))["services"]["app"]
    assert app["depends_on"] == {
        "openbao": {"condition": "service_healthy"},
        "redis": {"condition": "service_started"},
    }


def test_non_regression_sans_openbao() -> None:
    consumer = ServiceSpec(
        name="app", image="app:1", host_port=9000, container_port=9000, depends=("redis",),
    )
    data = _render((_REDIS, consumer))
    assert "openbao-unsealer" not in data["services"]
    # sans openbao dans les deps, la forme LISTE historique est conservée
    assert data["services"]["app"]["depends_on"] == ["redis"]


def test_script_unsealer_ne_fuit_pas_la_cle() -> None:
    script = _render((_OPENBAO, _LITELLM))["services"]["openbao-unsealer"]["command"][2]
    for line in script.splitlines():
        if line.lstrip().startswith("echo"):
            assert "unseal_key" not in line and "$(cat" not in line, line


def test_script_partage_identique_entre_backends() -> None:
    # source unique : le service compose et le sidecar k3s exécutent EXACTEMENT le même script
    from forgeai.renderers.k3s import _UNSEAL_SCRIPT
    assert UNSEAL_SCRIPT == _UNSEAL_SCRIPT
