"""Round 27 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : str_exc_sur() ne doit JAMAIS
lever pour une Exception normale, même si exc.__str__() lui-même est buggé. Round 28/30 : la
couverture BaseException a été tentée (28) puis délibérément revenue en arrière (30) — voir
docstring de str_exc_sur() pour l'historique complet du compromis retenu."""
from __future__ import annotations

import pytest

from forgeai.core.safe_repr import str_exc_sur


def test_str_exc_sur_exception_normale_retourne_le_message() -> None:
    exc = ValueError("message normal")
    assert str_exc_sur(exc) == "message normal"


def test_str_exc_sur_exception_str_casse_ne_leve_pas() -> None:
    class ExceptionStrCassee(Exception):
        def __str__(self) -> str:
            raise ValueError("str() cassé délibérément pour ce test")

    exc = ExceptionStrCassee()
    resultat = str_exc_sur(exc)  # ne doit JAMAIS lever
    assert "ExceptionStrCassee" in resultat
    assert isinstance(resultat, str)


def test_str_exc_sur_exception_sans_message_retourne_chaine_vide() -> None:
    assert str_exc_sur(ValueError()) == ""


def test_str_exc_sur_str_leve_exception_standard_ne_leve_pas() -> None:
    """Le cas courant qui justifie cette fonction : un __str__ personnalisé qui lève une
    Exception NORMALE (pas un BaseException) — toujours couvert après round 30."""
    class ExceptionStrLeveRuntimeError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("str() cassé via RuntimeError, délibéré pour ce test")

    exc = ExceptionStrLeveRuntimeError()
    resultat = str_exc_sur(exc)  # ne doit PAS lever pour une Exception standard
    assert "ExceptionStrLeveRuntimeError" in resultat
    assert isinstance(resultat, str)


def test_str_exc_sur_str_leve_baseexception_propage_delibrement() -> None:
    """Round 30 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : round 28 avait élargi à
    `except BaseException` pour couvrir ce cas, mais cela avale AUSSI un KeyboardInterrupt/
    SystemExit asynchrone sans rapport survenant pendant l'appel à str(exc) — Python ne peut pas
    distinguer les deux. Revenu à `except Exception` (sécurité signal, convention stdlib) :
    contre-preuve explicite que ce cas pathologique précis N'EST PLUS couvert, DÉLIBÉRÉMENT — la
    garantie documentée de str_exc_sur() porte maintenant sur Exception, pas BaseException."""
    class ExceptionStrLeveSystemExit(Exception):
        def __str__(self) -> str:
            raise SystemExit("str() cassé via SystemExit, délibéré pour ce test")

    exc = ExceptionStrLeveSystemExit()
    with pytest.raises(SystemExit):
        str_exc_sur(exc)
