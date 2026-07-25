"""Verrouillage et remplacement atomique de fichiers locaux."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

MODELS_TRANSACTION_LOCK = ".models-transaction"
MODELS_TRANSACTION_JOURNAL = ".models-transaction.json"


@contextmanager
def file_lock(path: Path):
    """Context manager de verrou exclusif sur un fichier .lock associé à `path`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = str(path) + ".lock"
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()


def _fsync_directory(path: Path) -> None:
    """Persiste les changements de nom du répertoire contenant un fichier."""
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_write_text(path: Path, payload: str, *, mode: int = 0o600) -> None:
    """Écrit, fsync puis remplace `path`; l'ancien fichier reste intact avant replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            descriptor_open = False
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        if descriptor_open:
            os.close(fd)
        temporary.unlink(missing_ok=True)
        raise


def atomic_unlink(path: Path) -> None:
    """Supprime un fichier puis persiste le changement de répertoire."""
    path = Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


def restore_models_transaction_locked(
    home: Path, vault_path: Path, snapshot: dict
) -> None:
    """Restaure les deux fichiers; conserve le journal si une restauration échoue."""
    home = Path(home)
    vault_path = Path(vault_path)
    routes_path = home / "routes.json"
    journal_path = home / MODELS_TRANSACTION_JOURNAL
    rollback_error: Exception | None = None

    try:
        if snapshot["vault_existed"]:
            atomic_write_text(
                vault_path,
                json.dumps(snapshot["vault"], ensure_ascii=False, indent=1),
                mode=0o600,
            )
        else:
            atomic_unlink(vault_path)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        rollback_error = exc

    try:
        if snapshot["routes_existed"]:
            atomic_write_text(
                routes_path,
                json.dumps(snapshot["routes"], ensure_ascii=False, indent=1),
                mode=0o600,
            )
        else:
            atomic_unlink(routes_path)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        if rollback_error is None:
            rollback_error = exc

    if rollback_error is not None:
        raise rollback_error
    atomic_unlink(journal_path)


def recover_models_transaction_locked(home: Path, vault_path: Path) -> bool:
    """Récupère le write-ahead journal sous le verrou modèles déjà détenu."""
    home = Path(home)
    journal_path = home / MODELS_TRANSACTION_JOURNAL
    if not journal_path.exists():
        return False
    snapshot = json.loads(journal_path.read_text(encoding="utf-8"))
    restore_models_transaction_locked(home, vault_path, snapshot)
    return True
