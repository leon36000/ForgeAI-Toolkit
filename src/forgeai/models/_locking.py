"""Verrouillage et remplacement atomique de fichiers locaux."""

import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from forgeai.core._portable_lock import acquire_exclusive, release_exclusive
from forgeai.i18n import t

MODELS_TRANSACTION_LOCK = ".models-transaction"
MODELS_TRANSACTION_JOURNAL = ".models-transaction.json"


@contextmanager
def file_lock(path: Path):
    """Context manager de verrou exclusif sur un fichier .lock associé à `path`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(str(path) + ".lock")
    try:
        existing = lock_path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise OSError(t("models.locking.file_lock.verrou_non_regulier", lock_path=lock_path))

    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    locked = False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(t("models.locking.file_lock.verrou_non_regulier", lock_path=lock_path))
        acquire_exclusive(descriptor)
        locked = True
        yield
    finally:
        try:
            if locked:
                release_exclusive(descriptor)
        finally:
            os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    """Persiste les changements de nom du répertoire contenant un fichier."""
    # S2083 est un faux positif ici : `path` est le parent exact de la
    # destination locale choisie par l'opérateur, et aucun privilège n'est élevé.
    directory_fd = os.open(path, os.O_RDONLY)  # NOSONAR(S2083)
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
        # S2083 est un faux positif : le fichier temporaire est créé par
        # mkstemp dans `path.parent`; remplacer `path` est la fonction explicite
        # de ce writer local (notamment pour la destination CLI `--out`).
        os.replace(temporary, path)  # NOSONAR(S2083)
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


def _journal_vault_path(home: Path, snapshot: dict) -> Path:
    """Retourne le nom canonique lexical sans suivre un éventuel symlink injecté."""
    vault_name = snapshot.get("vault_name", "vault.json")
    if vault_name != "vault.json":
        raise ValueError(t("models.locking.journal_vault_path.identite_invalide"))
    return Path(os.path.abspath(Path(home) / vault_name))


def _paths_identify_same_file(left: Path, right: Path) -> bool:
    """Compare deux chemins en tenant compte des symlinks, hardlinks et de la casse."""
    try:
        return Path(left).samefile(right)
    except OSError:
        return Path(left).resolve(strict=False) == Path(right).resolve(strict=False)


def _restore_vault_image(path: Path, snapshot: dict) -> None:
    if snapshot["vault_existed"]:
        atomic_write_text(
            path,
            json.dumps(snapshot["vault"], ensure_ascii=False, indent=1),
            mode=0o600,
        )
    else:
        atomic_unlink(path)


def restore_models_transaction_locked(
    home: Path, vault_path: Path, snapshot: dict
) -> None:
    """Restaure les deux fichiers; conserve le journal si une restauration échoue."""
    home = Path(home)
    requested_vault_path = Path(os.path.abspath(vault_path))
    canonical_vault_path = _journal_vault_path(home, snapshot)
    if not _paths_identify_same_file(
        requested_vault_path, canonical_vault_path
    ):
        raise ValueError(t("models.locking.restore_models_transaction_locked.coffre_ne_correspond_pas"))
    routes_path = home / "routes.json"
    journal_path = home / MODELS_TRANSACTION_JOURNAL
    rollback_error: Exception | None = None

    try:
        _restore_vault_image(canonical_vault_path, snapshot)
        if (
            requested_vault_path != canonical_vault_path
            and not requested_vault_path.is_symlink()
        ):
            _restore_vault_image(requested_vault_path, snapshot)
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


def empreinte_canonique(charge: object) -> str:
    """Retourne le SHA-256 de la donnee parsee, jamais des octets bruts du fichier.

    Hacher les octets bruts ferait qu'un simple changement de ``indent=`` dans
    le writer casserait toutes les empreintes, et le mode d'echec serait
    « discordance => rollback », c'est-a-dire la perte de donnees d'origine
    reintroduite silencieusement par un changement de style.
    """
    import hashlib

    serialisee = json.dumps(
        charge,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(serialisee).hexdigest()


def commit_deja_applique(home: Path, vault_path: Path, snapshot: dict) -> bool:
    """Indique si les deux images cibles du journal sont deja sur disque."""
    import hmac

    # Journal LEGACY (ecrit par un binaire anterieur au correctif) : aucune cible enregistree,
    # donc rien a comparer. Branche EXPLICITE, jamais un defaut implicite : le rollback
    # inconditionnel est le comportement sur dans ce cas.
    cible = snapshot.get("cible")
    if cible is None:
        return False

    # Cible malformee : on ne peut pas conclure, donc on ne conclut pas — et « ne pas conclure »
    # signifie ROLLBACK, jamais planter. Lever ici ferait echouer RouteStore(home) a CHAQUE
    # ouverture sur un journal abime, ce qui est plus grave que la restauration qu'on veut eviter.
    #
    # Le `.get()` ci-dessus est deliberement suivi d'un test d'identite : le motif dangereux
    # serait `snapshot.get("cible") == calcule`, VRAI quand la cle manque ET que le calcul vaut
    # None — un journal PRE-commit legitime passerait alors pour un commit reussi.
    if not isinstance(cible, dict):
        return False
    cible_routes = cible.get("routes")
    cible_vault = cible.get("vault")
    if not isinstance(cible_routes, str) or not isinstance(cible_vault, str):
        return False

    routes_path = Path(home) / "routes.json"
    vault_path = Path(vault_path)
    try:
        if not routes_path.exists() or not vault_path.exists():
            return False
        routes = json.loads(routes_path.read_text(encoding="utf-8"))
        vault = json.loads(vault_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False

    routes_correspondent = hmac.compare_digest(
        empreinte_canonique(routes),
        cible_routes,
    )
    vault_correspond = hmac.compare_digest(
        empreinte_canonique(vault),
        cible_vault,
    )
    # Un crash entre les deux os.replace laisse une cle orpheline : son
    # rollback doit rester applique, donc toute correspondance partielle echoue.
    return routes_correspondent and vault_correspond


def recover_models_transaction_locked(home: Path, vault_path: Path) -> bool:
    """Recupere le write-ahead journal sous le verrou modeles deja detenu."""
    home = Path(home)
    journal_path = home / MODELS_TRANSACTION_JOURNAL
    if not journal_path.exists():
        return False
    snapshot = json.loads(journal_path.read_text(encoding="utf-8"))
    if not _paths_identify_same_file(
        Path(vault_path), _journal_vault_path(home, snapshot)
    ):
        return False
    if commit_deja_applique(home, vault_path, snapshot):
        atomic_unlink(journal_path)
        return True
    restore_models_transaction_locked(home, vault_path, snapshot)
    return True
