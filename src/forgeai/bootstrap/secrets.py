"""Story P1-S05 — bootstrap sécurisé local (codeur : fable).

Génère les secrets d'exécution (jetons aléatoires 256 bits) dans <out>/.env et
<out>/secrets/, permissions 0600, répertoire 0700. Idempotent : ne régénère pas
un secret existant sauf --regen. Aucun secret n'apparaît jamais dans les
manifestes rendus — ils sont référencés par env_file (vérifié par test).
"""
from __future__ import annotations

import secrets as pysecrets
from pathlib import Path

from forgeai.models._locking import file_lock
from forgeai.models.vault import (
    atomic_write_secret_text,
    prepare_lock_file,
    prepare_secure_directory,
    read_secret_text,
    republish_existing_secret_file,
)

# Secrets ajoutés EN FIN (ligne 0 = FORGEAI_API_TOKEN préservée, cf. test permissions) :
# - FORGEAI_LITELLM_KEY : master key de la passerelle LiteLLM du profil RAG durci (E2c).
# - FORGEAI_PG_PASSWORD, FORGEAI_LANGFUSE_* : socle observabilité langfuse (E5) — postgres +
#   clés d'ingestion (pk-lf-/sk-lf-), NextAuth/SALT/ENCRYPTION_KEY (64 hex requis par langfuse).
# Tous interpolés dans le compose (${…}), jamais en clair dans un manifeste rendu.
# NB (FAI-0005 S5) : PLUS de FORGEAI_BAO_TOKEN. En mode PRODUCTION le coffre openbao n'a pas de
# dev-root-token pré-partagé — le token applicatif est créé au déploiement par ensure_openbao_ready
# (secrets/openbao_init.py) et persisté RUNTIME (FileSecretStore / Secret k8s), jamais dans .env.
ENV_KEYS = ("FORGEAI_API_TOKEN", "QDRANT_SERVICE_KEY", "FORGEAI_LITELLM_KEY",
            "FORGEAI_PG_PASSWORD", "FORGEAI_LANGFUSE_NEXTAUTH_SECRET", "FORGEAI_LANGFUSE_SALT",
            "FORGEAI_LANGFUSE_ENCRYPTION_KEY", "FORGEAI_LANGFUSE_PK", "FORGEAI_LANGFUSE_SK",
            "FORGEAI_LANGFUSE_UI_PASSWORD")

# Préfixes de format exigés par langfuse pour ses clés d'API (le reste = 256 bits hex).
_KEY_PREFIX = {"FORGEAI_LANGFUSE_PK": "pk-lf-", "FORGEAI_LANGFUSE_SK": "sk-lf-"}

# `file_lock` ajoute le suffixe `.lock`. L'ancre reste volontairement dans
# `out_dir`, à côté de `secrets/`, afin que l'artefact persistant de coordination
# n'entre jamais dans le répertoire monté qui ne contient que les secrets.
_BOOTSTRAP_LOCK_ANCHOR = ".bootstrap-secrets"


def bootstrap_secrets(out_dir: Path, regen: bool = False) -> dict[str, Path]:
    # Limite du modèle de menace : `out_dir` et ses ancêtres sont contrôlés par
    # l'opérateur et non inscriptibles par un attaquant. O_NOFOLLOW protège les
    # composants finaux; une prévalidation user-space ne peut pas neutraliser
    # le renommage concurrent d'un composant parent contrôlé par un tiers.
    prepare_secure_directory(out_dir, preserve_existing_final=True)
    prepare_lock_file(out_dir / _BOOTSTRAP_LOCK_ANCHOR)
    with file_lock(out_dir / _BOOTSTRAP_LOCK_ANCHOR):
        secrets_dir = out_dir / "secrets"
        prepare_secure_directory(secrets_dir)
        env_path = out_dir / ".env"
        existing: dict[str, str] = {}
        if not regen:
            try:
                existing_payload = read_secret_text(env_path)
            except FileNotFoundError:
                existing_payload = ""
            for line in existing_payload.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    existing[key] = value

        lines = []
        for key in ENV_KEYS:
            value = existing.get(key) or (
                _KEY_PREFIX.get(key, "") + pysecrets.token_hex(32)
            )
            lines.append(f"{key}={value}")
        atomic_write_secret_text(
            env_path, "\n".join(lines) + "\n", mode=0o600
        )

        prepare_secure_directory(secrets_dir)
        key_path = secrets_dir / "forgeai_token.key"
        if regen:
            atomic_write_secret_text(
                key_path, pysecrets.token_hex(32) + "\n", mode=0o600
            )
        else:
            try:
                republish_existing_secret_file(key_path, mode=0o600)
            except FileNotFoundError:
                atomic_write_secret_text(
                    key_path, pysecrets.token_hex(32) + "\n", mode=0o600
                )

        return {"env": env_path, "token_key": key_path}
