"""Générateur de configuration LiteLLM pour un plan de déploiement (story E1b).

Émet un `litellm-config.yaml` qui route les modèles du plan vers leurs backends réels :
le LLM vers Ollama (`ollama_chat/…`), les embeddings vers TEI si présent sinon Ollama. La
master key n'est JAMAIS une valeur en clair : uniquement la référence `os.environ/LITELLM_MASTER_KEY`.
YAML écrit à la main (aucune dépendance PyYAML) puis validé par LiteLLM au démarrage.
"""
from __future__ import annotations

from forgeai.core.models import DeploymentPlan

TEI_SERVICE = "text-embeddings-inference-tei"


def render_litellm_config(plan: DeploymentPlan) -> str:
    """Retourne un document YAML configurant LiteLLM selon le plan."""
    has_tei = any(service.name == TEI_SERVICE for service in plan.services)

    llm_model = plan.model
    embed_model = plan.embed_model

    if has_tei:
        embed_model_value = f"openai/{embed_model}"
        embed_api_base = f"http://{TEI_SERVICE}/v1"
        # TEI n'authentifie pas ; LiteLLM exige néanmoins un champ api_key pour un
        # provider openai-compatible → placeholder inerte, jamais un secret.  proof:allow
        embed_api_key_line = '      api_key: "dummy"'  # proof:allow
    else:
        embed_model_value = f"ollama/{embed_model}"
        embed_api_base = "http://ollama:11434"
        embed_api_key_line = ""

    lines = [
        "model_list:",
        f'  - model_name: "{llm_model}"',
        "    litellm_params:",
        f'      model: "ollama_chat/{llm_model}"',
        '      api_base: "http://ollama:11434"',
        f'  - model_name: "{embed_model}"',
        "    litellm_params:",
        f'      model: "{embed_model_value}"',
        f'      api_base: "{embed_api_base}"',
    ]

    if embed_api_key_line:
        lines.append(embed_api_key_line)

    lines.extend(
        [
            "general_settings:",
            '  master_key: "os.environ/LITELLM_MASTER_KEY"',
        ]
    )

    # E3a — si Redis est déployé au plan, LiteLLM l'utilise comme cache de réponses
    # (branche la brique redis du châssis ; les requêtes identiques ne re-génèrent pas).
    if any(service.name == "redis" for service in plan.services):
        lines.extend(
            [
                "litellm_settings:",
                "  cache: true",
                "  cache_params:",
                "    type: redis",
                '    host: "redis"',
                "    port: 6379",
            ]
        )

    return "\n".join(lines) + "\n"
