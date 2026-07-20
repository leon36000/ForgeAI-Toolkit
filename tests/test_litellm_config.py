"""Tests E1b — génération de la config LiteLLM (routage réel vers les backends)."""
from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.litellm_config import render_litellm_config


def _ollama() -> ServiceSpec:
    return ServiceSpec(
        name="ollama",
        image="ollama/ollama:latest",
        host_port=21434,
        container_port=11434,
    )


def _make_plan(services: tuple[ServiceSpec, ...] = ()) -> DeploymentPlan:
    return DeploymentPlan(
        plan_id="test-plan",
        profile="minimal-cpu",
        target=RenderTarget.COMPOSE,
        services=services,
        model="llama3.1:8b",
        embed_model="nomic-embed-text:latest",
    )


def _redis() -> ServiceSpec:
    return ServiceSpec(name="redis", image="redis:7.4.9", host_port=16379, container_port=6379)


def _langfuse() -> ServiceSpec:
    return ServiceSpec(name="langfuse", image="langfuse/langfuse:2", host_port=13000,
                       container_port=3000)


# E3a : redis au plan -> LiteLLM active le cache Redis
def test_cache_redis_active_si_redis_au_plan() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(), _redis())))
    assert "litellm_settings:" in yaml
    assert "cache:" in yaml and "type: redis" in yaml
    assert 'host: "redis"' in yaml and "port: 6379" in yaml


def test_pas_de_cache_sans_redis_ni_langfuse() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(),)))
    assert "litellm_settings:" not in yaml, "sans redis ni langfuse, pas de litellm_settings (E1b inchangé)"


# E5 : langfuse au plan -> LiteLLM émet les traces via success_callback
def test_success_callback_langfuse_si_langfuse_au_plan() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(), _langfuse())))
    assert "litellm_settings:" in yaml
    assert "success_callback:" in yaml and "langfuse" in yaml


def test_pas_de_callback_sans_langfuse() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(), _redis())))
    assert "success_callback:" not in yaml, "sans langfuse, pas de callback (E3a cache seul)"


# E5 : cache (redis) ET callback (langfuse) coexistent sous UN SEUL litellm_settings
def test_cache_et_callback_coexistent_un_seul_bloc() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(), _redis(), _langfuse())))
    assert yaml.count("litellm_settings:") == 1, "un seul bloc litellm_settings (pas de doublon YAML)"
    assert "type: redis" in yaml and "success_callback:" in yaml and "langfuse" in yaml


def test_llm_route_ollama() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(),)))
    assert 'model_name: "llama3.1:8b"' in yaml
    assert "ollama_chat/llama3.1:8b" in yaml
    assert 'api_base: "http://ollama:11434"' in yaml


def test_embed_ollama_par_defaut() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(),)))
    assert 'model: "ollama/nomic-embed-text:latest"' in yaml
    assert 'api_base: "http://ollama:11434"' in yaml


def test_embed_bascule_tei() -> None:
    tei = ServiceSpec(
        name="text-embeddings-inference-tei",
        image="ghcr.io/huggingface/text-embeddings-inference:cpu-1.9",
        host_port=8080,
        container_port=80,
    )
    yaml = render_litellm_config(_make_plan((_ollama(), tei)))
    assert 'model: "openai/nomic-embed-text:latest"' in yaml
    assert 'api_base: "http://text-embeddings-inference-tei/v1"' in yaml
    assert 'api_key: "dummy"' in yaml  # proof:allow — placeholder inerte, pas un secret


def test_master_key_reference_env() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(),)))
    assert "os.environ/LITELLM_MASTER_KEY" in yaml
    for line in yaml.splitlines():
        if line.strip().startswith("master_key:"):
            assert "os.environ/LITELLM_MASTER_KEY" in line
            assert "sk-" not in line


def test_yaml_valide() -> None:
    yaml = render_litellm_config(_make_plan((_ollama(),)))
    assert "model_list:" in yaml
    assert "general_settings:" in yaml
    assert "\t" not in yaml
