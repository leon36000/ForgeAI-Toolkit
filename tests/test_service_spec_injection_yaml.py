"""Story SEC-SVCSPEC-INJECT — ServiceSpec rejette les caractères de contrôle
interpolés en brut au rendu YAML/Compose (suivi de SEC-YAML-INJECT)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.compose import render_compose

_PAYLOAD_NAME = (
    "redis\n---\napiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRoleBinding\n"
    "metadata:\n  name: pwn\nroleRef:\n  kind: ClusterRole\n  name: cluster-admin\n"
    "  apiGroup: rbac.authorization.k8s.io\nsubjects:\n- kind: ServiceAccount\n"
    "  name: forgeai-sa\n  namespace: forgeai-minimal\n---\n# "
)


def _svc(**over):
    base = dict(
        name="redis",
        image="redis:7",
        host_port=6379,
        container_port=6379,
    )
    base.update(over)
    return ServiceSpec(**base)


def test_injection_yaml_via_name_est_bloquee_a_la_construction():
    """Le vecteur d'attaque : un `name` porteur de \n doit lever ValueError à la construction
    du ServiceSpec, avant tout rendu YAML/Compose."""
    with pytest.raises(ValueError, match="name"):
        _svc(name=_PAYLOAD_NAME)


def test_message_ne_divulgue_pas_le_payload_complet():
    """Le message d'erreur nomme le champ sans recracher le payload injecté (anti-fuite logs)."""
    with pytest.raises(ValueError) as exc:
        _svc(name=_PAYLOAD_NAME)
    msg = str(exc.value)
    assert "name" in msg
    assert "ClusterRoleBinding" not in msg and "cluster-admin" not in msg


@pytest.mark.parametrize("champ", ["name", "image", "healthcheck_url", "node"])
@pytest.mark.parametrize("mauvais", ["a\nb", "a\rb", "x\ty", "z\x00", "w\x1f", "d\x7f"])
def test_controle_rejete_par_champ(champ, mauvais):
    with pytest.raises(ValueError, match=champ):
        _svc(**{champ: mauvais})


@pytest.mark.parametrize(
    "champ,valeur",
    [
        ("volumes", ("data\n---\ninject:",)),
        ("command", ("echo\ninjected: true",)),
        ("depends", ("bad\nsvc",)),
    ],
)
def test_controle_rejete_dans_volumes_command_depends(champ, valeur):
    with pytest.raises(ValueError, match=champ):
        _svc(**{champ: valeur})


@pytest.mark.parametrize(
    "env",
    [
        {"BAD\nKEY": "x"},
        {"OK": "val\ninjected: true"},
    ],
)
def test_controle_rejete_dans_env_cle_et_valeur(env):
    with pytest.raises(ValueError, match="env"):
        _svc(env=env)


def test_service_spec_legitime_se_construit_sans_erreur():
    """Aucune régression : un ServiceSpec réaliste reste valide."""
    s = ServiceSpec(
        name="litellm",
        image="ghcr.io/berriai/litellm:main",
        host_port=4000,
        container_port=4000,
        volumes=("litellm-data:/data",),
        env={"LITELLM_LOG": "INFO", "PORT": "4000"},
        healthcheck_url="http://127.0.0.1:4000/health",
        depends=("redis",),
        command=("--config", "/app/config.yaml"),
        node="node-1",
    )
    assert s.name == "litellm"
    assert s.image == "ghcr.io/berriai/litellm:main"
    assert s.host_port == 4000
    assert s.container_port == 4000
    assert s.volumes == ("litellm-data:/data",)
    assert s.env == {"LITELLM_LOG": "INFO", "PORT": "4000"}
    assert s.healthcheck_url == "http://127.0.0.1:4000/health"
    assert s.depends == ("redis",)
    assert s.command == ("--config", "/app/config.yaml")
    assert s.node == "node-1"


def test_compose_ne_peut_jamais_recevoir_un_service_malveillant():
    """Le renderer compose n'a pas de `_safe` ; la défense à la source doit le protéger.
    Construire un DeploymentPlan avec un ServiceSpec malveillant lève ValueError à la
    construction du ServiceSpec : render_compose n'est donc JAMAIS atteint."""
    with pytest.raises(ValueError, match="name"):
        plan = DeploymentPlan(
            plan_id="p1-abcd1234",
            profile="minimal-cpu",
            target=RenderTarget.COMPOSE,
            services=(
                ServiceSpec(
                    name="x\n---\ninjected: true",
                    image="redis:7",
                    host_port=6379,
                    container_port=6379,
                ),
            ),
            model="qwen2.5:0.5b",
            embed_model="nomic-embed-text",
        )
        # Jamais atteint : la construction du ServiceSpec échoue avant.
        render_compose(plan)
