"""Story P1-S05 — bootstrap sécurisé local (codeur : fable).

Génère les secrets d'exécution (jetons aléatoires 256 bits) dans <out>/.env et
<out>/secrets/, permissions 0600, répertoire 0700. Idempotent : ne régénère pas
un secret existant sauf --regen. Aucun secret n'apparaît jamais dans les
manifestes rendus — ils sont référencés par env_file (vérifié par test).
"""
from __future__ import annotations

import os
import secrets as pysecrets
from pathlib import Path

# FORGEAI_LITELLM_KEY ajoutée EN FIN (ligne 0 = FORGEAI_API_TOKEN préservée, cf. test permissions) :
# master key de la passerelle LiteLLM du profil RAG durci (E2c). Interpolée dans le compose.
ENV_KEYS = ("FORGEAI_API_TOKEN", "QDRANT_SERVICE_KEY", "FORGEAI_LITELLM_KEY")


def bootstrap_secrets(out_dir: Path, regen: bool = False) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir = out_dir / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    os.chmod(secrets_dir, 0o700)

    env_path = out_dir / ".env"
    existing: dict[str, str] = {}
    if env_path.exists() and not regen:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                existing[key] = value

    lines = []
    for key in ENV_KEYS:
        value = existing.get(key) or pysecrets.token_hex(32)
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)

    key_path = secrets_dir / "forgeai_token.key"
    if not key_path.exists() or regen:
        key_path.write_text(pysecrets.token_hex(32) + "\n", encoding="utf-8")
    os.chmod(key_path, 0o600)

    return {"env": env_path, "token_key": key_path}
