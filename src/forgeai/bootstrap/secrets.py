"""Story P1-S05 — bootstrap sécurisé local (codeur : fable).

Génère les secrets d'exécution (jetons aléatoires 256 bits) dans <out>/.env et
<out>/secrets/, permissions 0600, répertoire 0700. Idempotent : ne régénère pas
un secret existant sauf --regen. Aucun secret n'apparaît jamais dans les
manifestes rendus — ils sont référencés par env_file (vérifié par test).
"""
from __future__ import annotations

import os
import secrets as pysecrets
import stat
from pathlib import Path

from forgeai.models._locking import file_lock
from forgeai.models.vault import (
    atomic_write_secret_text,
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


def _ensure_directory_path_matches(
    path: Path, descriptor_state: os.stat_result
) -> None:
    current = path.lstat()
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino)
        != (descriptor_state.st_dev, descriptor_state.st_ino)
    ):
        raise OSError("le répertoire de secrets a changé")


def _ensure_regular_path_matches(
    path: Path, expected_state: os.stat_result
) -> None:
    current = path.lstat()
    if (
        not stat.S_ISREG(current.st_mode)
        or current.st_nlink != 1
        or (current.st_dev, current.st_ino)
        != (expected_state.st_dev, expected_state.st_ino)
    ):
        raise OSError("le fichier de verrouillage a changé")


def _set_mode_without_following_preexisting_symlink(
    path: Path, mode: int, expected_state: os.stat_result
) -> os.stat_result:
    current = path.lstat()
    if (
        stat.S_IFMT(current.st_mode) != stat.S_IFMT(expected_state.st_mode)
        or (current.st_dev, current.st_ino)
        != (expected_state.st_dev, expected_state.st_ino)
    ):
        raise OSError("le chemin sécurisé a changé")

    if os.chmod in os.supports_follow_symlinks:
        os.chmod(path, mode, follow_symlinks=False)
    else:
        # Limite POSIX : certaines plateformes ne proposent pas chmod nofollow.
        # La double validation borne les erreurs accidentelles; l'hypothèse
        # operator-owned sur le parent exclut un renommage hostile à cet instant.
        os.chmod(path, mode)

    updated = path.lstat()
    if (
        stat.S_IFMT(updated.st_mode) != stat.S_IFMT(expected_state.st_mode)
        or (updated.st_dev, updated.st_ino)
        != (expected_state.st_dev, expected_state.st_ino)
    ):
        raise OSError("le chemin sécurisé a changé")
    return updated


def _open_private_directory(path: Path, *, final_mode: int = 0o700) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory is None:
        raise OSError("validation de répertoire sans suivi indisponible")

    try:
        path.mkdir(mode=final_mode)
    except FileExistsError:
        path_state = path.lstat()
    else:
        path_state = path.lstat()
    if not stat.S_ISDIR(path_state.st_mode):
        raise OSError("le chemin sécurisé n'est pas un répertoire")
    if stat.S_IMODE(path_state.st_mode) & 0o500 != 0o500:
        path_state = _set_mode_without_following_preexisting_symlink(
            path, final_mode, path_state
        )

    flags = os.O_RDONLY | no_follow | directory
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        descriptor_state = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(descriptor_state.st_mode)
            or (descriptor_state.st_dev, descriptor_state.st_ino)
            != (path_state.st_dev, path_state.st_ino)
        ):
            raise OSError("le chemin sécurisé n'est pas un répertoire")
        os.fchmod(descriptor, final_mode)
        _ensure_directory_path_matches(path, descriptor_state)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _prepare_output_directory(path: Path) -> None:
    creation_chain_started = False
    for candidate in (*reversed(path.parents), path):
        try:
            current = candidate.lstat()
        except FileNotFoundError:
            creation_chain_started = True
            try:
                candidate.mkdir(mode=0o700)
            except FileExistsError:
                current = candidate.lstat()
            else:
                current = candidate.lstat()
        else:
            if not stat.S_ISDIR(current.st_mode):
                raise OSError("le chemin de sortie n'est pas un répertoire")
            if not creation_chain_started:
                continue

        if not stat.S_ISDIR(current.st_mode):
            raise OSError("le chemin de sortie n'est pas un répertoire")
        descriptor = _open_private_directory(candidate)
        os.close(descriptor)

    final_state = path.lstat()
    final_permissions = stat.S_IMODE(final_state.st_mode)
    if final_permissions & 0o700 != 0o700:
        descriptor = _open_private_directory(
            path, final_mode=final_permissions | 0o700
        )
        os.close(descriptor)


def _prepare_bootstrap_lock(path: Path) -> None:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise OSError("ouverture sans suivi de lien indisponible")
    flags = os.O_RDWR | no_follow
    flags |= getattr(os, "O_CLOEXEC", 0)
    lock_path = Path(str(path) + ".lock")

    try:
        descriptor = os.open(
            lock_path, flags | os.O_CREAT | os.O_EXCL, 0o600
        )
        expected_state = None
    except FileExistsError:
        expected_state = lock_path.lstat()
        if (
            not stat.S_ISREG(expected_state.st_mode)
            or expected_state.st_nlink != 1
        ):
            raise OSError("le verrou n'est pas un fichier régulier")
        if stat.S_IMODE(expected_state.st_mode) & 0o600 != 0o600:
            expected_state = _set_mode_without_following_preexisting_symlink(
                lock_path, 0o600, expected_state
            )
        descriptor = os.open(lock_path, flags)

    try:
        descriptor_state = os.fstat(descriptor)
        if (
            not stat.S_ISREG(descriptor_state.st_mode)
            or descriptor_state.st_nlink != 1
        ):
            raise OSError("le verrou n'est pas un fichier régulier")
        if expected_state is not None and (
            descriptor_state.st_dev,
            descriptor_state.st_ino,
        ) != (expected_state.st_dev, expected_state.st_ino):
            raise OSError("le fichier de verrouillage a changé")
        os.fchmod(descriptor, 0o600)
        _ensure_regular_path_matches(lock_path, descriptor_state)
    finally:
        os.close(descriptor)


def bootstrap_secrets(out_dir: Path, regen: bool = False) -> dict[str, Path]:
    # Limite du modèle de menace : `out_dir` et ses ancêtres sont contrôlés par
    # l'opérateur et non inscriptibles par un attaquant. O_NOFOLLOW protège les
    # composants finaux; une prévalidation user-space ne peut pas neutraliser
    # le renommage concurrent d'un composant parent contrôlé par un tiers.
    _prepare_output_directory(out_dir)
    _prepare_bootstrap_lock(out_dir / _BOOTSTRAP_LOCK_ANCHOR)
    with file_lock(out_dir / _BOOTSTRAP_LOCK_ANCHOR):
        secrets_dir = out_dir / "secrets"
        secrets_directory_descriptor = _open_private_directory(secrets_dir)
        try:
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

            descriptor_state = os.fstat(secrets_directory_descriptor)
            _ensure_directory_path_matches(secrets_dir, descriptor_state)
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
        finally:
            os.close(secrets_directory_descriptor)

        return {"env": env_path, "token_key": key_path}
