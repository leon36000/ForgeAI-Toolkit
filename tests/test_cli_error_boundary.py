"""Tests de la frontière d'erreurs CLI-013 : rédaction, codes retour, pas de traceback.

Chaque handler de sous-commande est un global de ``forgeai.cli`` référencé par nom dans
``set_defaults(func=_handler)`` au moment où ``_run`` (re)construit le parser ; monkeypatcher
``cli._doctor`` intercepte donc réellement le dispatch de ``forgeai doctor``.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import forgeai.cli as cli
from forgeai.core.redaction import REDACTED

# DeployError est importé par cli.py (depuis forgeai.deploy.compose) et donc exposé sur le module.
DeployError = cli.DeployError


def _raise(exc_class, message):
    def _f(args):
        raise exc_class(message)
    return _f


# ---------------------------------------------------------------------------
# G1 — secret « api_key » dans une exception inattendue → code 1, rédigé, pas de traceback
# ---------------------------------------------------------------------------
def test_g1_api_key_redacted(capsys, monkeypatch):
    secret = "api_key=" + "h" * 32  # proof:allow (fixture faux-secret : test CLI-013)
    monkeypatch.setattr(cli, "_doctor", _raise(RuntimeError, secret))

    code = cli.main(["doctor"])
    _, err = capsys.readouterr()

    assert code == 1
    assert "Traceback" not in err
    assert REDACTED in err
    assert ("h" * 32) not in err
    # aucune fenêtre de 8 caractères consécutifs de la valeur secrète
    value = "h" * 32
    for i in range(len(value) - 7):
        window = value[i:i + 8]
        assert window not in err, f"fenêtre {window!r} détectée dans stderr"


# ---------------------------------------------------------------------------
# G2 — autres formes : la VALEUR secrète disparaît ; le label (Bearer/token=) peut rester
#      (M1/M2 conservent le schème/nom et ne rédigent QUE la valeur ; M3 « sk- » rédige tout).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("message, secret_value", [
    ("Bearer " + "e" * 40, "e" * 40),
    ("sk-" + "z" * 40, "z" * 40),
    ("token=" + "i" * 32, "i" * 32),
])
def test_g2_secret_value_redacted(message, secret_value, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_doctor", _raise(RuntimeError, message))

    code = cli.main(["doctor"])
    _, err = capsys.readouterr()

    assert code == 1
    assert "Traceback" not in err
    assert secret_value not in err, f"valeur secrète {secret_value[:12]}… non rédigée"
    assert REDACTED in err
    # fenêtres de 8 caractères de la valeur
    for i in range(len(secret_value) - 7):
        window = secret_value[i:i + 8]
        assert window not in err, f"fenêtre {window!r} détectée dans stderr"


# ---------------------------------------------------------------------------
# G3 — FORGEAI_DEBUG=1 rétablit la traceback (frontière bypassée : l'exception se propage)
# ---------------------------------------------------------------------------
def test_g3_debug_bypass(monkeypatch):
    monkeypatch.setenv("FORGEAI_DEBUG", "1")
    monkeypatch.setattr(cli, "_doctor", _raise(RuntimeError, "boom"))
    with pytest.raises(RuntimeError):
        cli.main(["doctor"])


# ---------------------------------------------------------------------------
# G4 — arguments argparse invalides → SystemExit(2) préservé (jamais converti en 1)
# ---------------------------------------------------------------------------
def test_g4_argparse_system_exit_preserved():
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["commande-inexistante-xyz"])
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# G5 — KeyboardInterrupt → code 130, message propre, pas de traceback
# ---------------------------------------------------------------------------
def test_g5_keyboard_interrupt(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_doctor", _raise(KeyboardInterrupt, ""))
    code = cli.main(["doctor"])
    _, err = capsys.readouterr()
    assert code == 130
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# G6 — non-régression : un int retourné par le handler traverse la frontière inchangé
# ---------------------------------------------------------------------------
def test_g6_handler_returns_int(monkeypatch):
    monkeypatch.setattr(cli, "_doctor", lambda a: 9)
    assert cli.main(["doctor"]) == 9

    monkeypatch.setattr(cli, "_doctor", lambda a: 0)
    assert cli.main(["doctor"]) == 0


# ---------------------------------------------------------------------------
# G7 — DeployError portant un secret → code 8, « ECHEC DEPLOIEMENT », secret rédigé
#      (le trou historique {exc} non rédigé est refermé)
# ---------------------------------------------------------------------------
def test_g7_deploy_error_redacted(monkeypatch, capsys):
    secret = "boom api_key=" + "h" * 32  # proof:allow (fixture faux-secret : test CLI-013)
    monkeypatch.setattr(cli, "_doctor", _raise(DeployError, secret))

    code = cli.main(["doctor"])
    _, err = capsys.readouterr()

    assert code == 8
    assert "ECHEC DEPLOIEMENT" in err
    assert "Traceback" not in err
    assert ("h" * 32) not in err
    assert REDACTED in err
