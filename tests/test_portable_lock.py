"""Tests du verrou portable `_portable_lock` (lot PORT-286).

Chaque test énonce la PROPRIÉTÉ de sémantique prouvée — pas seulement l'absence
de crash. Le fichier est exécutable sur posix et nt : aucune primitive POSIX-only
n'y apparaît (os.open/os.close/lseek sont portables). Les workers multiprocessing
sont au niveau module — exigence spawn : picklables et importables sans effet de
bord (aucune création de Process/Queue à l'import).
"""

import errno
import multiprocessing
import os
import time

import pytest

from forgeai.core._portable_lock import (
    LockTimeoutError,
    _est_occupe,
    acquire_exclusive,
    locked_exclusive,
    release_exclusive,
)

# ----------------------------------------------------------------------
# Workers multiprocessing (niveau module, exigence spawn)
# ----------------------------------------------------------------------

def _worker_tenter_acquisition(chemin: str, timeout_s: float, file_attente) -> None:
    """Worker fils : rouvre le fichier par CHEMIN (un fd ne traverse pas spawn),
    tente l'acquisition exclusive et rapporte (résultat, durée mesurée) dans la
    file, résultat ∈ {"timeout", "acquis", "autre"}."""
    fd = os.open(chemin, os.O_RDWR)
    try:
        debut = time.monotonic()
        try:
            acquire_exclusive(fd, timeout_s=timeout_s)
        except LockTimeoutError:
            resultat = "timeout"
        except Exception:
            resultat = "autre"
        else:
            resultat = "acquis"
        duree = time.monotonic() - debut
        if resultat == "acquis":
            release_exclusive(fd)
        file_attente.put((resultat, duree))
        # Garantit la remontée du message avant la fin du fils : on ferme la file
        # puis on attend que le thread d'alimentation ait tout vidé vers le tube.
        file_attente.close()
        file_attente.join_thread()
    finally:
        os.close(fd)


# ----------------------------------------------------------------------
# T1 — exclusion réelle entre processus
# ----------------------------------------------------------------------

def test_exclusion_reelle_entre_processus(tmp_path):
    """Propriété : le verrou exclut RÉELLEMENT un autre processus (anti no-op).

    Le parent tient le verrou ; un fils qui rouvre le fichier par chemin doit
    échouer par timeout après ≥ 0,5 s. Après release par le parent, un fils
    identique doit acquérir. Un backend no-op laisserait le premier fils
    acquérir immédiatement → ce test serait ROUGE.
    """
    chemin = tmp_path / "exclusion.bin"
    chemin.write_bytes(b"\0")
    fd = os.open(str(chemin), os.O_RDWR)
    ctx = multiprocessing.get_context("fork" if os.name == "posix" else "spawn")
    try:
        acquire_exclusive(fd)

        file1 = ctx.Queue()
        fils1 = ctx.Process(
            target=_worker_tenter_acquisition, args=(str(chemin), 0.5, file1)
        )
        fils1.start()
        resultat1, duree1 = file1.get(timeout=30)
        fils1.join(timeout=30)
        assert fils1.exitcode == 0
        assert resultat1 == "timeout"
        assert duree1 >= 0.5

        release_exclusive(fd)

        file2 = ctx.Queue()
        fils2 = ctx.Process(
            target=_worker_tenter_acquisition, args=(str(chemin), 5.0, file2)
        )
        fils2.start()
        resultat2, _duree2 = file2.get(timeout=30)
        fils2.join(timeout=30)
        assert fils2.exitcode == 0
        assert resultat2 == "acquis"
    finally:
        os.close(fd)


# ----------------------------------------------------------------------
# T2 — borne du timeout
# ----------------------------------------------------------------------

def test_timeout_borne(tmp_path):
    """Propriété : l'acquisition échoue À L'ÉCHÉANCE demandée, ni avant ni très après.

    Deux os.open() distincts du même fichier au sein du MÊME processus : la
    contention est réelle sur les deux backends — flock verrouille la description
    de fichier ouvert (deux open() = deux descriptions distinctes, qui se
    bloquent mutuellement) et msvcrt/LockFile verrouille une plage par handle
    (deux handles d'un même processus sont en conflit). Le test passe donc pour
    la MÊME raison sur posix et sur nt.
    """
    chemin = tmp_path / "timeout.bin"
    chemin.write_bytes(b"\0")
    fd1 = os.open(str(chemin), os.O_RDWR)
    fd2 = os.open(str(chemin), os.O_RDWR)
    try:
        acquire_exclusive(fd1)
        debut = time.monotonic()
        with pytest.raises(LockTimeoutError):
            acquire_exclusive(fd2, timeout_s=0.2)
        duree = time.monotonic() - debut
        assert 0.2 <= duree < 2.0
        release_exclusive(fd1)
    finally:
        os.close(fd2)
        os.close(fd1)


# ----------------------------------------------------------------------
# T3 — fichier vide
# ----------------------------------------------------------------------

def test_fichier_vide(tmp_path):
    """Propriété : la plage [0,1) est verrouillable AU-DELÀ d'EOF sur les deux
    backends — acquire/release/acquire/release sur un fichier de 0 octet, sans
    aucune écriture."""
    chemin = tmp_path / "vide.bin"
    chemin.write_bytes(b"")
    fd = os.open(str(chemin), os.O_RDWR)
    try:
        acquire_exclusive(fd)
        release_exclusive(fd)
        acquire_exclusive(fd)
        release_exclusive(fd)
    finally:
        os.close(fd)


# ----------------------------------------------------------------------
# T4 — erreur non-« occupé » : propagation immédiate (amendement A1)
# ----------------------------------------------------------------------

def test_erreur_non_occupe_propage_immediatement(tmp_path):
    """Propriété (amendement A1) : un fd invalide échoue FRANCHEMENT, en moins
    d'une seconde, avec l'erreur d'origine — JAMAIS un LockTimeoutError après 5 s
    de réessais aveugles. Le test tombe si le contrat d'exceptions est trop large."""
    chemin = tmp_path / "fd_invalide.bin"
    chemin.write_bytes(b"\0")
    fd = os.open(str(chemin), os.O_RDWR)
    os.close(fd)  # descripteur désormais invalide
    debut = time.monotonic()
    with pytest.raises((OSError, ValueError)) as info:
        acquire_exclusive(fd, timeout_s=5.0)
    duree = time.monotonic() - debut
    # LockTimeoutError ⊂ TimeoutError ⊂ OSError : il faut l'exclure explicitement.
    assert not isinstance(info.value, LockTimeoutError)
    assert duree < 1.0


# ----------------------------------------------------------------------
# T5 — prédicat _est_occupe testé directement
# ----------------------------------------------------------------------

def test_predicat_occupe():
    """Propriété : `_est_occupe` ne classe « occupé » QUE les erreurs de
    contention du backend actif — posix : BlockingIOError ; nt : OSError EACCES
    ou EDEADLOCK(36). EBADF n'est JAMAIS « occupé »."""
    if os.name == "posix":
        assert _est_occupe(BlockingIOError(errno.EAGAIN, "x")) is True
        assert _est_occupe(OSError(errno.EBADF, "x")) is False
    elif os.name == "nt":
        assert _est_occupe(OSError(errno.EACCES, "x")) is True
        # EDEADLOCK Windows, valeur numérique 36 quelle que soit la CRT.
        assert _est_occupe(OSError(36, "x")) is True
        assert _est_occupe(OSError(errno.EBADF, "x")) is False
    else:  # unreachable : l'import du module aurait déjà levé RuntimeError
        pytest.fail(f"plateforme non prise en charge : os.name={os.name!r}")


# ----------------------------------------------------------------------
# T6 — context manager : relâche sur exception et propage l'erreur d'origine
# ----------------------------------------------------------------------

def test_context_manager_relache_sur_exception(tmp_path):
    """Propriété : `locked_exclusive` relâche le verrou quand le corps du with
    lève, et l'exception d'origine se propage. La preuve de relâchement est
    discriminante : une acquisition sur un SECOND descripteur (seconde
    description de fichier ouvert / second handle) doit réussir immédiatement —
    ré-acquérir sur le même fd ne prouverait rien."""

    class _ErreurMetier(Exception):
        pass

    chemin = tmp_path / "contexte.bin"
    chemin.write_bytes(b"\0")
    fd = os.open(str(chemin), os.O_RDWR)
    try:
        with pytest.raises(_ErreurMetier):
            with locked_exclusive(fd):
                raise _ErreurMetier("panne simulée")
        # Verrou relâché : un second open() doit acquérir sans attendre.
        fd2 = os.open(str(chemin), os.O_RDWR)
        try:
            acquire_exclusive(fd2, timeout_s=0.5)
            release_exclusive(fd2)
        finally:
            os.close(fd2)
    finally:
        os.close(fd)


# ----------------------------------------------------------------------
# T7 — release sans acquire : contrat figé par plateforme
# ----------------------------------------------------------------------

def test_release_sans_acquire_est_une_erreur_franche(tmp_path):
    """Propriété : fige le comportement RÉEL de release-sans-acquire, qui diffère
    par backend, afin que personne ne s'appuie sur un comportement non partagé :
    - posix : flock(LOCK_UN) sans verrou détenu réussit silencieusement ;
    - nt    : msvcrt LK_UNLCK sur plage non verrouillée lève OSError."""
    chemin = tmp_path / "release_sans_acquire.bin"
    chemin.write_bytes(b"\0")
    fd = os.open(str(chemin), os.O_RDWR)
    try:
        if os.name == "posix":
            release_exclusive(fd)  # succès silencieux, comportement noyau documenté
        elif os.name == "nt":
            with pytest.raises(OSError):
                release_exclusive(fd)
        else:  # unreachable : l'import du module aurait déjà levé RuntimeError
            pytest.fail(f"plateforme non prise en charge : os.name={os.name!r}")
    finally:
        os.close(fd)

