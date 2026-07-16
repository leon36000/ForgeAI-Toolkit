from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_IDES = ("aider", "claude-code", "cline", "cursor", "opencode")

class IDEError(Exception):
    """Erreur liée à la configuration IDE."""

@dataclass(frozen=True)
class IdeConfig:
    ide: str
    path: str
    content: str
    fmt: str  # "yaml" ou "json"


def list_ides() -> list[str]:
    """Retourne la liste des IDE supportés."""
    return list(SUPPORTED_IDES)


def generate_ide_config(
    ide: str,
    gateway_url: str,
    model: str,
    *,
    key_env: str = "FORGEAI_GATEWAY_KEY",
) -> IdeConfig:
    """
    Génère la configuration pour un IDE donné.

    Args:
        ide: nom de l'IDE (doit appartenir à SUPPORTED_IDES).
        gateway_url: URL du gateway local.
        model: nom du modèle à utiliser.
        key_env: nom de la variable d'environnement contenant le jeton.

    Returns:
        IdeConfig décrivant le fichier de configuration.

    Raises:
        IDEError si l'IDE n'est pas supporté.
    """
    if ide not in SUPPORTED_IDES:
        raise IDEError(f"IDE '{ide}' non supporté. IDEs supportés : {', '.join(SUPPORTED_IDES)}")

    if ide == "aider":
        path = ".aider.conf.yml"
        content = (
            f"openai-api-base: {gateway_url}\n"
            f"model: openai/{model}\n"
            "# clé via $OPENAI_API_KEY\n"
        )
        fmt = "yaml"

    elif ide == "claude-code":
        path = ".claude/settings.json"
        data = {
            "env": {
                "ANTHROPIC_BASE_URL": gateway_url,
                "ANTHROPIC_AUTH_TOKEN": f"${{{key_env}}}",
            },
            "model": model,
        }
        content = json.dumps(data, ensure_ascii=False, indent=1)
        fmt = "json"

    elif ide == "cline":
        path = "cline.openai-compatible.json"
        data = {
            "apiProvider": "openai",
            "openAiBaseUrl": gateway_url,
            "openAiApiKey": f"${{{key_env}}}",
            "openAiModelId": model,
        }
        content = json.dumps(data, ensure_ascii=False, indent=1)
        fmt = "json"

    elif ide == "cursor":
        path = ".cursor/openai.json"
        data = {
            "openAIBaseUrl": gateway_url,
            "openAIApiKey": f"${{{key_env}}}",
            "model": model,
        }
        content = json.dumps(data, ensure_ascii=False, indent=1)
        fmt = "json"

    elif ide == "opencode":
        path = "opencode.json"
        data = {
            "provider": {
                "forgeai-gateway": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "ForgeAI Gateway",
                    "options": {
                        "baseURL": gateway_url,
                        "apiKey": f"${{{key_env}}}",
                    },
                    "models": {
                        model: {}
                    },
                }
            }
        }
        content = json.dumps(data, ensure_ascii=False, indent=1)
        fmt = "json"

    return IdeConfig(ide=ide, path=path, content=content, fmt=fmt)


def write_ide_config(cfg: IdeConfig, dest_dir: str | Path) -> Path:
    """
    Écrit la configuration IDE dans le répertoire destination.

    Args:
        cfg: instance IdeConfig.
        dest_dir: répertoire de destination.

    Returns:
        Chemin absolu du fichier écrit.
    """
    dest = Path(dest_dir)
    target = dest / cfg.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(cfg.content, encoding="utf-8")
    return target.resolve()
