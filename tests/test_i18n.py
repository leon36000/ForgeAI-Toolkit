"""Tests du module forgeai.i18n — parité, bascule, placeholders, robustesse."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import forgeai.i18n as i18n
from forgeai.i18n import (
    MissingTranslation,
    Translator,
    available_locales,
    get_translator,
)


_LOCALES_DIR: Path = Path(i18n.__file__).resolve().parent.parent / "data" / "locales"


def _load(code: str) -> dict[str, str]:
    with (_LOCALES_DIR / f"{code}.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_parite_cles_fr_en() -> None:
    fr = _load("fr")
    en = _load("en")
    assert set(fr.keys()) == set(en.keys()), (
        f"Différence de clés fr/en : "
        f"only_fr={set(fr) - set(en)}, only_en={set(en) - set(fr)}"
    )
    def _verifie(prefix: str, table: dict) -> None:
        for k, v in table.items():
            if isinstance(v, dict):
                # section imbriquée (ex. "web", i18n unifiée P1.2) : mêmes règles
                _verifie(f"{prefix}[{k!r}]", v)
            else:
                assert isinstance(v, str) and v.strip(), f"{prefix}[{k!r}] vide ou blanche"

    _verifie("fr", fr)
    _verifie("en", en)
    # parité aussi DANS la section web
    if "web" in fr or "web" in en:
        assert set(fr.get("web", {})) == set(en.get("web", {})), "section web désalignée fr/en"


def test_bascule_change_les_libelles() -> None:
    fr_text = Translator("fr").t("catalogue.summary", n=5, k=2)
    en_text = Translator("en").t("catalogue.summary", n=5, k=2)
    assert fr_text != en_text
    assert "5" in fr_text and "2" in fr_text
    assert "5" in en_text and "2" in en_text


def test_cle_manquante_leve() -> None:
    tr = Translator("fr")
    with pytest.raises(MissingTranslation):
        tr.t("cette.cle.nexiste.pas")


def test_set_locale_et_available() -> None:
    tr = Translator("fr")
    avail = tr.available()
    assert "fr" in avail and "en" in avail
    tr.set_locale("en")
    assert tr.locale == "en"
    with pytest.raises(ValueError):
        tr.set_locale("zz")


def test_placeholders_formates() -> None:
    tr = Translator("fr")
    out = tr.t("catalogue.default_line", name="X", category="Y", popularity="★9")
    assert "X" in out and "Y" in out and "★9" in out


def test_available_locales_liste_fr_en() -> None:
    codes = available_locales()
    assert "fr" in codes and "en" in codes
    assert codes == sorted(codes)


def test_get_translator_env_invalide_retombe_sur_fr(monkeypatch: pytest.MonkeyPatch) -> None:
    # Réinitialise le singleton pour éviter toute contamination inter-tests.
    i18n._global_translator = None
    monkeypatch.setenv("FORGEAI_LANG", "es")
    tr = get_translator()  # ne doit pas lever
    assert tr.locale == "fr"
    # Nettoyage : réinitialise pour les tests suivants.
    i18n._global_translator = None


def test_cli_lang_bascule_les_libelles(capsys):
    """La bascule --lang change les libellés visibles de la commande catalogue
    (preuve que la sortie vient des locales, pas de chaînes codées en dur)."""
    from forgeai.cli import main

    assert main(["--lang", "en", "catalogue"]) == 0
    out_en = capsys.readouterr().out
    assert main(["--lang", "fr", "catalogue"]) == 0
    out_fr = capsys.readouterr().out

    assert "bricks" in out_en and "briques" not in out_en
    assert "briques" in out_fr
    assert out_en != out_fr
