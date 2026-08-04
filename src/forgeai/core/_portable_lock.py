"""Verrou de fichier portable inter-processus — décision d'architecture #286, option A.

Backend unique sélectionné À L'IMPORT du module :
  - os.name == "posix" → fcntl.flock ;
  - os.name == "nt"    → msvcrt.locking ;
  - tout autre         → RuntimeError immédiat, nommant la valeur reçue d'os.name.

Contraintes d'architecture honorées :
  C1 — jamais de dégradation silencieuse : aucun chemin no-op n'existe dans ce
       module ; sur plateforme inconnue, l'échec est franc et survient à l'import,
       il est donc structurellement impossible d'écrire hors verrou.
  C2 — libération à la mort du processus : flock et msvcrt.locking (= LockFile
       Win32) sont de vrais verrous noyau, relâchés à la fermeture du
       descripteur, kill -9 / TerminateProcess inclus.

Plage verrouillée : 1 octet à l'offset 0, point fixe — le fichier peut être vide
et grandir librement. `os.lseek(fd, 0, SEEK_SET)` précède CHAQUE appel système de
verrouillage comme de déverrouillage : sous Windows, le déverrouillage doit
frapper exactement la même plage à la même position (exigence de l'API Win32
LockFile/UnlockFile).

Amendement A1 — contrat d'exceptions STRICT : la boucle d'acquisition n'interprète
comme « verrou occupé, réessayer » QUE la contention réelle (posix :
BlockingIOError, errno EAGAIN mesuré ; nt : OSError EACCES ou EDEADLOCK=36).
TOUTE autre exception (EBADF, EINVAL, ValueError sur fd fermé…) propage
immédiatement, sans réessai : un descripteur invalide ne doit JAMAIS être classé
« occupé » et boucler 30 s avant un timeout qui masquerait le vrai diagnostic.
"""

import errno
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

# NOTE i18n : PAS d'import de forgeai.i18n ici (délibéré). registre.py charge ce module via
# importlib.util.spec_from_file_location en repli quand le paquet forgeai n'est pas installé
# (exécution standalone, ex. gates.yml : `python3 scripts/registre.py verify ...` sans install
# préalable) — un `from forgeai.i18n import t` en tête de module romprait CET import de repli
# (ModuleNotFoundError au chargement, avant même d'atteindre un site raise()). Les 2 messages
# français ci-dessous restent donc non traduits, volontairement, hors périmètre I18N-042.

# ----------------------------------------------------------------------
# Sélection du backend à l'import — aucune branche par appel (C1)
# ----------------------------------------------------------------------

if os.name == "posix":
    import fcntl

    def _tenter_verrou(fd: int) -> None:
        """Tentative non bloquante posix : LOCK_EX | LOCK_NB (jamais bloquant)."""
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _lever_verrou(fd: int) -> None:
        """Déverrouillage posix : LOCK_UN sur la même plage (1 octet à l'offset 0)."""
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.flock(fd, fcntl.LOCK_UN)

    def _est_occupe(exc: BaseException) -> bool:
        """Contention posix : BlockingIOError uniquement (errno EAGAIN mesuré)."""
        return isinstance(exc, BlockingIOError)

elif os.name == "nt":  # pragma: no cover — exécuté et prouvé par guard-fs-multi-os (windows-latest) ; le job de couverture tourne sur ubuntu, qui ne peut pas exécuter msvcrt
    import msvcrt

    # Errnos signalant une contention sous Windows : EACCES (violation de verrou
    # sur plage occupée) et EDEADLOCK = 36. Ce dernier est exposé selon les
    # versions de la CRT sous le nom EDEADLOCK ou EDEADLK : on récupère les deux
    # via getattr (repli sur la valeur numérique 36) et le set déduplique.
    _ERRNOS_OCCUPES_NT = frozenset({
        errno.EACCES,
        36,
        getattr(errno, "EDEADLOCK", 36),
        getattr(errno, "EDEADLK", 36),
    })

    def _tenter_verrou(fd: int) -> None:
        """Tentative non bloquante nt : LK_NBLCK — jamais LK_LOCK, dont le
        comportement interne (1 essai/s × 10 puis OSError) est opaque et non
        paramétrable."""
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _lever_verrou(fd: int) -> None:
        """Déverrouillage nt : LK_UNLCK sur la même plage, même position (Win32)."""
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

    def _est_occupe(exc: BaseException) -> bool:
        """Contention nt : OSError dont l'errno est EACCES ou EDEADLOCK (36)."""
        return isinstance(exc, OSError) and exc.errno in _ERRNOS_OCCUPES_NT

else:  # pragma: no cover — aucune plateforme CI ne l'exécute par construction ; la propriété « échec franc à l'import » est le contrat C1, vérifiable par lecture
    raise RuntimeError(
        f"_portable_lock : plateforme non prise en charge, os.name={os.name!r} — "
        "aucun backend de verrouillage noyau disponible ; échec franc à l'import "
        "(contrainte C1 : jamais de dégradation silencieuse, aucun no-op)."
    )

__all__ = [
    "LockTimeoutError",
    "acquire_exclusive",
    "release_exclusive",
    "locked_exclusive",
]


class LockTimeoutError(TimeoutError):
    """Verrou non acquis dans le délai imparti."""


# ----------------------------------------------------------------------
# API publique
# ----------------------------------------------------------------------

def acquire_exclusive(fd: int, *, timeout_s: float = 30.0, retry_s: float = 0.05) -> None:
    """Acquiert le verrou exclusif noyau sur `fd` (plage fixe : 1 octet à l'offset 0).

    Tente une acquisition NON bloquante toutes les `retry_s` secondes, horloge
    `time.monotonic()`, jusqu'à l'échéance `timeout_s` où LockTimeoutError est
    levée avec le délai et le fd. Seules les erreurs de contention (cf.
    `_est_occupe`) déclenchent un réessai ; toute autre exception propage
    immédiatement (amendement A1).
    """
    echeance = time.monotonic() + timeout_s
    while True:
        try:
            _tenter_verrou(fd)
            return
        except Exception as exc:
            if not _est_occupe(exc):
                # EBADF, EINVAL, ValueError… : diagnostic réel, propagation franche.
                raise
            if time.monotonic() >= echeance:
                raise LockTimeoutError(
                    f"verrou exclusif non acquis dans le délai imparti "
                    f"({timeout_s} s) sur fd={fd}"
                ) from exc
            time.sleep(retry_s)


def release_exclusive(fd: int) -> None:
    """Relâche le verrou exclusif sur `fd` (même plage : 1 octet à l'offset 0).

    Comportement sur fd jamais verrouillé, figé par les tests : posix réussit
    silencieusement (LOCK_UN sans verrou), nt lève OSError (LK_UNLCK sur plage
    non verrouillée). Ne pas s'appuyer sur un comportement partagé.
    """
    _lever_verrou(fd)


@contextmanager
def locked_exclusive(
    fd: int, *, timeout_s: float = 30.0, retry_s: float = 0.05
) -> Iterator[None]:
    """Context manager : acquire_exclusive → yield → release_exclusive en finally."""
    acquire_exclusive(fd, timeout_s=timeout_s, retry_s=retry_s)
    try:
        yield
    finally:
        release_exclusive(fd)

