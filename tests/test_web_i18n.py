"""B-02f — gate i18n/a11y déterministe de l'UI web.

Fige les invariants : chaque clé utilisée (data-i18n, data-i18n-aria, t('…')) existe
dans les DEUX dictionnaires ; fr et en portent exactement les mêmes clés ; aucune clé
morte ; aucun attribut accentué en dur sans mécanisme de traduction."""
import json
import re
import threading
import time
import urllib.request
from pathlib import Path


ASSETS = Path(__file__).parent.parent / "src" / "forgeai" / "web" / "assets"
DATA_LOCALES = Path(__file__).parent.parent / "src" / "forgeai" / "data" / "locales"


def _html() -> str:
    return (ASSETS / "index.html").read_text(encoding="utf-8")


def _js() -> str:
    return (ASSETS / "app.js").read_text(encoding="utf-8")


def _used_keys() -> set[str]:
    html, js = _html(), _js()
    keys = set(re.findall(r'data-i18n="([a-z_]+)"', html))
    keys |= set(re.findall(r'data-i18n-aria="([a-z_]+)"', html))
    keys |= set(re.findall(r'data-i18n-placeholder="([a-z_]+)"', html))
    keys |= set(re.findall(r"\bt\('([a-z_]+)'\)", js))
    return keys


def _dict_keys() -> tuple[set[str], set[str]]:
    fr = json.loads((DATA_LOCALES / "fr.json").read_text(encoding="utf-8"))["web"]
    en = json.loads((DATA_LOCALES / "en.json").read_text(encoding="utf-8"))["web"]
    return set(fr.keys()), set(en.keys())


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


FR_MARKERS = r"[éèêàçœùîôÉÈÊÀÇ]|\b(le|la|les|des|un|une|du|de la|tapez|ajoutez|choisissez)\b"


def test_aucun_attribut_accentue_sans_mecanisme():
    """Tout aria-label ou placeholder portant du français (accents OU mots outils français)
    doit porter le mécanisme de traduction correspondant sur le même élément :
    data-i18n-aria pour aria-label, data-i18n-placeholder pour placeholder."""
    html = _html()
    mechanism = {"aria-label": "data-i18n-aria", "placeholder": "data-i18n-placeholder"}
    for m in re.finditer(r"<[^>]+>", html):
        tag = m.group(0)
        attrs = dict(re.findall(
            r'(aria-label|placeholder|data-i18n-aria|data-i18n-placeholder)="([^"]*)"', tag))
        for attr, needed in mechanism.items():
            value = attrs.get(attr, "")
            if re.search(FR_MARKERS, value, re.IGNORECASE):
                assert needed in attrs, f"{attr} FR en dur sans {needed} : {tag}"


def test_setlang_traduit_aria_et_placeholder():
    js = _js()
    assert "data-i18n-aria" in _html()
    assert "data-i18n-placeholder" in _html()
    assert "i18nAria" in js, "setLang doit traduire les attributs data-i18n-aria"
    assert "i18nPlaceholder" in js, "setLang doit traduire les attributs data-i18n-placeholder"


def test_focus_visible_present():
    css = (ASSETS / "app.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css, "styles clavier :focus-visible requis (a11y)"


def test_log_deploiement_role_log():
    assert 'role="log"' in _html(), "le journal de déploiement doit porter role=log"


def test_app_js_sans_dictionnaire_embarque():
    """Ancré en début de ligne (le substring nu piégeait modelsChosen: {})."""
    js = _js()
    assert not re.search(r"^\s+(fr|en): \{\s*$", js, re.M), (
        "app.js ne doit plus contenir de dictionnaire fr/en embarqué")


def test_api_sert_toutes_les_cles_utilisees():
    """Serveur réel : /api/i18n/fr et /en couvrent TOUTES les clés utilisées par l'UI."""
    from forgeai.web.server import build_server

    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    used = _used_keys()
    try:
        for lang in ("fr", "en"):
            with urllib.request.urlopen(f"{base}/api/i18n/{lang}", timeout=10) as resp:
                table = json.loads(resp.read().decode("utf-8"))
            manquantes = sorted(used - set(table))
            assert not manquantes, f"clés absentes de /api/i18n/{lang} : {manquantes}"
    finally:
        srv.shutdown()
        srv.server_close()
