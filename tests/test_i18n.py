"""Tests du module i18n de ForgeAI Toolkit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgeai.i18n import MissingTranslation, Translator

_LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "forgeai" / "data" / "locales"


def _load_catalogue(code: str) -> dict[str, str]:
    path = _LOCALES_DIR / f"{code}.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_parite_cles_fr_en() -> None:
    """Les catalogues fr et en ont exactement les mêmes clés, sans valeur vide."""
    fr = _load_catalogue("fr")
    en = _load_catalogue("en")

    assert set(fr.keys()) == set(en.keys()), (
        f"Divergence de clés — seulement en fr : {set(fr) - set(en)}, "
        f"seulement en en : {set(en) - set(fr)}"
    )

    for key, value in fr.items():
        assert isinstance(value, str) and value.strip(), (
            f"fr['{key}'] est vide ou blanche : {value!r}"
        )
    for key, value in en.items():
        assert isinstance(value, str) and value.strip(), (
            f"en['{key}'] est vide ou blanche : {value!r}"
        )


def test_bascule_change_les_libelles() -> None:
    """Les traductions fr et en diffèrent et contiennent les valeurs formatées."""
    tr_fr = Translator("fr")
    tr_en = Translator("en")

    fr_text = tr_fr.t("catalogue.summary", n=5, k=2)
    en_text = tr_en.t("catalogue.summary", n=5, k=2)

    assert fr_text != en_text, "Les traductions fr et en doivent différer."
    assert "5" in fr_text and "2" in fr_text, f"fr ne contient pas 5 et 2 : {fr_text!r}"
    assert "5" in en_text and "2" in en_text, f"en ne contient pas 5 et 2 : {en_text!r}"


def test_cle_manquante_leve() -> None:
    """Une clé inexistante lève MissingTranslation."""
    tr = Translator("fr")
    with pytest.raises(MissingTranslation):
        tr.t("cette.cle.nexiste.pas")


def test_set_locale_et_available() -> None:
    """available() liste fr et en ; set_locale change la locale ; locale inconnue → ValueError."""
    tr = Translator("fr")

    avail = tr.available()
    assert "fr" in avail, f"'fr' absent de available() : {avail}"
    assert "en" in avail, f"'en' absent de available() : {avail}"

    tr.set_locale("en")
    assert tr.locale == "en"

    with pytest.raises(ValueError):
        tr.set_locale("zz")


def test_placeholders_formates() -> None:
    """Les placeholders {name}, {category}, {popularity} sont correctement substitués."""
    tr = Translator("fr")
    result = tr.t("catalogue.default_line", name="X", category="Y", popularity="★9")

    assert "X" in result, f"'X' absent du résultat : {result!r}"
    assert "Y" in result, f"'Y' absent du résultat : {result!r}"
    assert "★9" in result, f"'★9' absent du résultat : {result!r}"


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
