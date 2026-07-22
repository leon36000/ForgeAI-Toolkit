"""Story S6b — câblage UI du dropdown moteur filtré par vendor du nœud.

Preuves STRUCTURELLES (convention du dépôt, cf. test_ui_n2b) : le rendu réel du <select> se
vérifie EN NAVIGATEUR (cf. PR) — ici on garantit que le câblage EXISTE et ne régresse pas :
  1. index.html charge engine_filter.js AVANT app.js ;
  2. app.js délègue le filtrage au module pur ForgeAIEngineFilter et dérive le vendor du nœud ;
  3. engine_filter.js reste auto-suffisant (aucun lien http/https, cf. test_auto_suffisance).
La LOGIQUE de filtrage est prouvée par tests/js/engine_filter.test.cjs (Node, assertions réelles).
"""
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "src" / "forgeai" / "web" / "assets"


def test_index_charge_engine_filter_avant_app():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    assert 'src="engine_filter.js"' in html
    assert html.index("engine_filter.js") < html.index("app.js")


def test_app_delegue_au_module_pur():
    app = (ASSETS / "app.js").read_text(encoding="utf-8")
    assert "ForgeAIEngineFilter" in app          # délégation au module pur testé
    assert "engineChoices" in app                # liste finale filtrée (garde la sélection)
    assert "nodeVendorForFilter" in app          # dérive le vendor du nœud sélectionné


def test_engine_filter_auto_suffisant_et_exporte():
    js = (ASSETS / "engine_filter.js").read_text(encoding="utf-8")
    assert "http://" not in js and "https://" not in js
    for fn in ("filterEnginesByVendor", "nodeVendorForFilter", "engineChoices"):
        assert fn in js, f"fonction pure manquante : {fn}"
    assert "module.exports" in js                # réutilisable navigateur + Node (preuve)
