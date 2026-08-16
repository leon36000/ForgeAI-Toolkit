"""Round 27 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : str_exc_sur() ne doit JAMAIS
lever, même si exc.__str__() lui-même est buggé."""
from __future__ import annotations

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


def test_str_exc_sur_str_leve_baseexception_ne_leve_pas() -> None:
    """Round 28 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : str_exc_sur() affirme ne
    jamais lever, mais son handler round 27 ne capturait que `Exception` — un `__str__` qui lève
    un `BaseException` (ex. SystemExit, KeyboardInterrupt — légal en Python, vérifié
    empiriquement) traversait la fonction malgré la garantie documentée."""
    class ExceptionStrLeveSystemExit(Exception):
        def __str__(self) -> str:
            raise SystemExit("str() cassé via SystemExit, délibéré pour ce test")

    exc = ExceptionStrLeveSystemExit()
    resultat = str_exc_sur(exc)  # ne doit JAMAIS lever, même pour un BaseException
    assert "ExceptionStrLeveSystemExit" in resultat
    assert isinstance(resultat, str)
