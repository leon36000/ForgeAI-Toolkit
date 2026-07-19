"""B-02f — gate i18n/a11y déterministe de l'UI web.

Fige les invariants : chaque clé utilisée (data-i18n, data-i18n-aria, t('…')) existe
dans les DEUX dictionnaires ; fr et en portent exactement les mêmes clés ; aucune clé
morte ; aucun attribut accentué en dur sans mécanisme de traduction."""
import re
from pathlib import Path

ASSETS = Path(__file__).parent.parent / "src" / "forgeai" / "web" / "assets"


def _html() -> str:
    return (ASSETS / "index.html").read_text(encoding="utf-8")


def _js() -> str:
    return (ASSETS / "app.js").read_text(encoding="utf-8")


def _used_keys() -> set[str]:
    html, js = _html(), _js()
    keys = set(re.findall(r'data-i18n="([a-z_]+)"', html))
    keys |= set(re.findall(r'data-i18n-aria="([a-z_]+)"', html))
    keys |= set(re.findall(r"\bt\('([a-z_]+)'\)", js))
    return keys


def _dict_keys() -> tuple[set[str], set[str]]:
    js = _js()
    fr_block = js.split("fr: {")[1].split("\n    },")[0]
    en_block = js.split("en: {")[1].split("\n    }\n  };")[0]
    fr = set(re.findall(r"^\s+([a-z_]+):", fr_block, re.M))
    en = set(re.findall(r"^\s+([a-z_]+):", en_block, re.M))
    return fr, en


def test_toutes_les_cles_utilisees_sont_traduites():
    used = _used_keys()
    fr, en = _dict_keys()
    assert used - fr == set(), f"clés sans traduction fr : {sorted(used - fr)}"
    assert used - en == set(), f"clés sans traduction en : {sorted(used - en)}"


def test_dictionnaires_fr_en_alignes():
    fr, en = _dict_keys()
    assert fr == en, f"désalignement fr/en : {sorted(fr ^ en)}"


def test_aucune_cle_morte():
    used = _used_keys()
    fr, en = _dict_keys()
    dead = (fr & en) - used
    assert dead == set(), f"clés définies mais jamais utilisées : {sorted(dead)}"


def test_aucun_attribut_accentue_sans_mecanisme():
    """Tout placeholder/aria-label contenant un caractère accentué (donc du français en dur)
    doit porter data-i18n-aria sur le même élément (le placeholder de recherche est traduit
    par setLang via t('search_placeholder'))."""
    html = _html()
    for m in re.finditer(r"<[^>]+>", html):
        tag = m.group(0)
        attrs = dict(re.findall(r'(aria-label|placeholder|data-i18n-aria)="([^"]*)"', tag))
        for attr in ("aria-label",):
            value = attrs.get(attr, "")
            if re.search(r"[éèêàçœÉÈÊÀÇ]", value):
                assert "data-i18n-aria" in attrs, f"{attr} FR en dur sans data-i18n-aria : {tag}"


def test_setlang_traduit_les_aria():
    js = _js()
    assert "data-i18n-aria" in _html()
    assert "i18nAria" in js, "setLang doit traduire les attributs data-i18n-aria"


def test_focus_visible_present():
    css = (ASSETS / "app.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css, "styles clavier :focus-visible requis (a11y)"


def test_log_deploiement_role_log():
    assert 'role="log"' in _html(), "le journal de déploiement doit porter role=log"
