"""Tests figeant le comportement d'adoption de services existants."""

import pytest
import yaml

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.compose import render_compose, RienADeployerError
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

def test_le_dependant_ne_reference_plus_le_service_adopte_dans_depends_on():
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
        # bug hunt (issue #530) : str.isdigit() accepte des chiffres Unicode non-ASCII
        # ('²' = '²') que int() ne sait pas parser — sans isascii(), ceci levait une
        # ValueError BRUTE non traduite (message int() natif) au lieu du ValueError traduit
        # ERR_ADOPT_PORT attendu.
        ("127.0.0.1:²", "ERR_ADOPT_PORT"),
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


def test_CA8_plan_entierement_adopte_refuse():
    redis = _service_redis(adopted_endpoint="127.0.0.1:6379")
    qdrant = ServiceSpec(
        name="qdrant",
        image="qdrant:1",
        host_port=6333,
        container_port=6333,
        adopted_endpoint="127.0.0.1:6333",
    )
    with pytest.raises(RienADeployerError) as exc_info:
        render_compose(_plan([redis, qdrant]))
    msg = str(exc_info.value)
    assert "ERR_ADOPT_RIEN_A_DEPLOYER" in msg
    assert "redis" in msg
    assert "qdrant" in msg
    assert "127.0.0.1:6379" in msg
    assert "127.0.0.1:6333" in msg


def test_CA8_plan_mixte_ne_refuse_pas():
    redis = _service_redis(adopted_endpoint="127.0.0.1:6379")
    litellm = _service_litellm(adopted_endpoint=None)
    services = _parse_compose(render_compose(_plan([redis, litellm])))["services"]
    assert "litellm" in services


def _env(compose, service):
    """Normalise l'environnement d'un service en dict, qu'il soit liste ou dict."""
    env = compose["services"][service]["environment"]
    if isinstance(env, dict):
        return env
    out = {}
    for item in env:
        key, _, value = item.partition("=")
        out[key] = value
    return out


def test_CA2_dependant_pointe_vers_endpoint_decouvert():
    """CA-2 : le dépendant reçoit host.docker.internal:<port découvert>.

    L'existant prime sur le catalogue : le port catalogue (3000) ne doit
    PLUS apparaître dans la variable recâblée — seul le port découvert
    (3999, issu de adopted_endpoint) reste.
    """
    langfuse = ServiceSpec(name="langfuse", image="lf:3",
                           host_port=3000, container_port=3000,
                           adopted_endpoint="127.0.0.1:3999")
    postgres = ServiceSpec(name="postgres", image="pg:16",
                           host_port=5432, container_port=5432,
                           adopted_endpoint="127.0.0.1:5555")
    litellm = ServiceSpec(name="litellm", image="l:1",
                          host_port=4000, container_port=4000,
                          depends=("langfuse",),
                          env={"LANGFUSE_HOST": "http://langfuse:3000",
                               "DATABASE_URL": "postgresql://u:pw@postgres:5432/db",
                               "PIEGE_1": "http://mylangfuse:3000",
                               "PIEGE_2": "langfuse_backup"})

    compose = _parse_compose(render_compose(_plan([langfuse, postgres, litellm])))
    host = _env(compose, "litellm")["LANGFUSE_HOST"]

    assert "host.docker.internal:3999" in host, (
        f"LANGFUSE_HOST doit pointer vers le port découvert 3999, got: {host!r}"
    )
    assert "3000" not in host, (
        f"Le port catalogue 3000 ne doit plus apparaître dans LANGFUSE_HOST, got: {host!r}"
    )


def test_CA2_chaine_de_connexion_recablee():
    """CA-2 : la chaîne de connexion postgres est entièrement recâblée."""
    langfuse = ServiceSpec(name="langfuse", image="lf:3",
                           host_port=3000, container_port=3000,
                           adopted_endpoint="127.0.0.1:3999")
    postgres = ServiceSpec(name="postgres", image="pg:16",
                           host_port=5432, container_port=5432,
                           adopted_endpoint="127.0.0.1:5555")
    litellm = ServiceSpec(name="litellm", image="l:1",
                          host_port=4000, container_port=4000,
                          depends=("langfuse",),
                          env={"LANGFUSE_HOST": "http://langfuse:3000",
                               "DATABASE_URL": "postgresql://u:pw@postgres:5432/db",
                               "PIEGE_1": "http://mylangfuse:3000",
                               "PIEGE_2": "langfuse_backup"})

    compose = _parse_compose(render_compose(_plan([langfuse, postgres, litellm])))
    db_url = _env(compose, "litellm")["DATABASE_URL"]

    assert db_url == "postgresql://u:pw@host.docker.internal:5555/db", (
        f"DATABASE_URL doit valoir la chaîne recâblée exacte, got: {db_url!r}"
    )


def test_CA2_pas_de_substitution_au_milieu_dun_mot():
    """CA-2 anti faux-positif : les valeurs qui RESSEMBLENT au nom du service
    sans en être (mylangfuse, langfuse_backup) ne doivent pas être touchées."""
    langfuse = ServiceSpec(name="langfuse", image="lf:3",
                           host_port=3000, container_port=3000,
                           adopted_endpoint="127.0.0.1:3999")
    postgres = ServiceSpec(name="postgres", image="pg:16",
                           host_port=5432, container_port=5432,
                           adopted_endpoint="127.0.0.1:5555")
    litellm = ServiceSpec(name="litellm", image="l:1",
                          host_port=4000, container_port=4000,
                          depends=("langfuse",),
                          env={"LANGFUSE_HOST": "http://langfuse:3000",
                               "DATABASE_URL": "postgresql://u:pw@postgres:5432/db",
                               "PIEGE_1": "http://mylangfuse:3000",
                               "PIEGE_2": "langfuse_backup"})

    compose = _parse_compose(render_compose(_plan([langfuse, postgres, litellm])))
    env = _env(compose, "litellm")

    assert env["PIEGE_1"] == "http://mylangfuse:3000", (
        f"PIEGE_1 (mylangfuse) ne doit pas être corrompu, got: {env.get('PIEGE_1')!r}"
    )
    assert env["PIEGE_2"] == "langfuse_backup", (
        f"PIEGE_2 (langfuse_backup) ne doit pas être corrompu, got: {env.get('PIEGE_2')!r}"
    )


def test_CA2_aucune_substitution_sans_adoption():
    """CA-2 non-régression : sans aucun adopted_endpoint, aucune substitution
    n'est appliquée — les variables du dépendant restent intactes."""
    langfuse = ServiceSpec(name="langfuse", image="lf:3",
                           host_port=3000, container_port=3000)
    postgres = ServiceSpec(name="postgres", image="pg:16",
                           host_port=5432, container_port=5432)
    litellm = ServiceSpec(name="litellm", image="l:1",
                          host_port=4000, container_port=4000,
                          depends=("langfuse",),
                          env={"LANGFUSE_HOST": "http://langfuse:3000",
                               "DATABASE_URL": "postgresql://u:pw@postgres:5432/db",
                               "PIEGE_1": "http://mylangfuse:3000",
                               "PIEGE_2": "langfuse_backup"})

    compose = _parse_compose(render_compose(_plan([langfuse, postgres, litellm])))
    env = _env(compose, "litellm")

    assert env["LANGFUSE_HOST"] == "http://langfuse:3000"
    assert env["DATABASE_URL"] == "postgresql://u:pw@postgres:5432/db"
    assert env["PIEGE_1"] == "http://mylangfuse:3000"
    assert env["PIEGE_2"] == "langfuse_backup"
