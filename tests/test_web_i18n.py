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


def _css() -> str:
    return (ASSETS / "app.css").read_text(encoding="utf-8")


def _css_custom_props(block_selector: str, css: str) -> dict:
    """Extrait les custom properties (--nom: valeur;) d'un bloc CSS ciblé par sélecteur exact."""
    m = re.search(re.escape(block_selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"bloc CSS introuvable : {block_selector}"
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", m.group(1)))


def _relative_luminance(hexcolor: str) -> float:
    hexcolor = hexcolor.strip().lstrip("#")
    if len(hexcolor) == 3:
        hexcolor = "".join(c * 2 for c in hexcolor)
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = f(r), f(g), f(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(c1: str, c2: str) -> float:
    """Ratio de contraste WCAG (formule officielle des luminances relatives)."""
    l1, l2 = _relative_luminance(c1), _relative_luminance(c2)
    l1, l2 = max(l1, l2), min(l1, l2)
    return (l1 + 0.05) / (l2 + 0.05)


def test_skip_link_present_et_focusable():
    """FAI-U-040 (critère d'acceptation) : un skip-link utilisable au clavier mène au
    contenu principal, et doit être le tout premier élément focusable de <body>."""
    html = _html()
    assert re.search(r'<a\s+href="#app"\s+class="skip-link"', html), (
        "skip-link absent ou ne ciblant pas #app")
    body_idx = html.index("<body>")
    skip_idx = html.index('class="skip-link"')
    header_idx = html.index('class="app-header"')
    assert body_idx < skip_idx < header_idx, (
        "le skip-link doit précéder tout autre élément focusable de <body>")
    assert re.search(r'<main id="app" tabindex="-1"', html), (
        '#app doit porter tabindex="-1" pour recevoir le focus programmatique du skip-link '
        "(motif WAI standard pour une cible <main> non nativement focusable)")


def test_skip_link_hors_ecran_pas_display_none():
    """Le skip-link doit rester dans l'ordre de tabulation (technique off-screen), jamais
    display:none/visibility:hidden qui le retirerait complètement du clavier."""
    css = _css()
    m = re.search(r"\.skip-link\s*\{([^}]*)\}", css)
    assert m, "règle .skip-link absente de app.css"
    rule = m.group(1)
    assert "display: none" not in rule and "visibility: hidden" not in rule
    assert "position: absolute" in rule and "-9999px" in rule
    assert re.search(r"\.skip-link:focus\s*\{[^}]*left:\s*0", css), (
        "le skip-link doit redevenir visible au focus clavier (.skip-link:focus)")


def test_prefers_reduced_motion_present():
    """FAI-U-040 (critère d'acceptation) : prefers-reduced-motion neutralise les
    animations/transitions non essentielles."""
    css = _css()
    assert "@media (prefers-reduced-motion: reduce)" in css
    m = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", css, re.S)
    assert m, "bloc prefers-reduced-motion introuvable"
    body = m.group(1)
    assert "transition-duration" in body
    assert "animation-duration" in body


def test_contraste_erreur_wcag_aa():
    """FAI-U-040 (critère d'acceptation) : couleurs de texte d'erreur >= 4.5:1 (WCAG AA
    texte normal) sur les deux thèmes, contre --bg ET --card-bg."""
    css = _css()
    root = _css_custom_props(":root", css)
    dark = _css_custom_props('[data-theme="dark"]', css)
    for theme_name, props in (("clair", root), ("sombre", dark)):
        error = props.get("--error")
        assert error, f"--error manquant pour le thème {theme_name}"
        for bg_key in ("--bg", "--card-bg"):
            bg_color = props.get(bg_key)
            assert bg_color, f"{bg_key} manquant pour le thème {theme_name}"
            ratio = _contrast_ratio(error.strip(), bg_color.strip())
            assert ratio >= 4.5, (
                f"contraste --error/{bg_key} insuffisant en thème {theme_name} : "
                f"{ratio:.2f}:1 (< 4.5:1 AA)")


def test_regle_erreur_utilise_variable_error():
    """Les règles .error et .form-status.error doivent utiliser --error (couleur conforme
    AA), plus jamais l'ancienne couleur en dur #E5533D (~3.4-3.7:1, sous le seuil AA) ni
    --accent (4.28:1 sur --card-bg en thème clair, également sous le seuil AA)."""
    css = _css()
    assert re.search(r"\.error\s*\{\s*color:\s*var\(--error\)", css)
    assert re.search(r"\.form-status\.error\s*\{\s*color:\s*var\(--error\)", css)
    assert "#E5533D" not in css, "ancienne couleur d'erreur non conforme AA doit être supprimée"


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
