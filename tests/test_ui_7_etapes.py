import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "src" / "forgeai" / "web" / "assets" / "index.html"
APP_JS_PATH = ROOT / "src" / "forgeai" / "web" / "assets" / "app.js"
FR_PATH = ROOT / "src" / "forgeai" / "data" / "locales" / "fr.json"
EN_PATH = ROOT / "src" / "forgeai" / "data" / "locales" / "en.json"


@pytest.fixture(scope="module")
def html():
    return HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_js():
    return APP_JS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fr():
    return json.loads(FR_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def en():
    return json.loads(EN_PATH.read_text(encoding="utf-8"))


def _extract_js_function(source: str, name: str) -> str:
    """Extrait le texte source d'une fonction `function <name>(...) { ... }` par comptage
    de accolades équilibrées — permet de charger UNIQUEMENT les fonctions PURES de app.js
    (sans DOM/EventSource/boot()) dans un vrai moteur Node pour preuve comportementale réelle,
    sans dupliquer la logique dans le test (source unique = app.js lui-même)."""
    marker = f"function {name}("
    start = source.index(marker)
    brace_start = source.index("{", start)
    depth = 0
    i = brace_start
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1
    raise AssertionError(f"accolade non équilibrée pour la fonction {name}")


def _node_eval(js_source: str, script_tail: str):
    """Exécute du JS réel via Node (aucun mock) et retourne la valeur JSON produite sur stdout."""
    program = js_source + "\n" + script_tail
    result = subprocess.run(
        ["node", "-e", program],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"node a échoué : {result.stderr}"
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def pure_step_functions(app_js):
    """Concatène les fonctions PURES de décision de statut d'étape (UI-039), directement
    extraites du fichier réel livré — toute régression dans app.js est détectée ici."""
    names = ["computeStepEvidence", "computeStepFailure", "computeStepStatus"]
    return "\n".join(_extract_js_function(app_js, n) for n in names)


def test_rail_7_etapes(html):
    assert 'data-step="7"' in html, "Le rail doit comporter une étape 7"
    rail = re.search(r'<nav id="step-rail".*?</nav>', html, re.S).group(0)
    order = re.findall(r'data-step="(\d+)".*?<span[^>]*data-i18n="([^"]+)"', rail, re.S)
    keys = [key for _, key in order]
    assert keys == [
        "step_hardware",
        "step_stack",
        "step_models",
        "step_embeddings",
        "step_bricks",
        "step_nodes",
        "step_deploy",
    ], f"Ordre des étapes incorrect : {keys}"


def test_section_embeddings(html):
    assert 'id="embeddings-step"' in html
    assert 'id="embeddings-list"' in html
    assert 'id="embedding-search"' in html
    assert 'id="embeddings-counts"' in html
    assert 'data-step-panel="4"' in html.split('id="embeddings-step"')[1].split("</section>")[0]

    panel_map = {
        "embeddings-step": "4",
        "bricks": "5",
        "nodes": "6",
        "deploy": "7",
    }
    for section_id, expected in panel_map.items():
        m = re.search(
            rf'<section id="{re.escape(section_id)}"[^>]*data-step-panel="(\d+)"',
            html,
        )
        assert m is not None, f"Section #{section_id} introuvable"
        assert m.group(1) == expected, f"#{section_id} doit être panel {expected}"


def test_selecteur_rag(html):
    deploy_section = html.split('id="deploy"')[1].split("</section>")[0]
    assert 'id="deploy-rag-select"' in deploy_section
    assert 'name="rag_node"' in deploy_section
    assert '<option value="local"' in deploy_section
    assert '<option value="auto"' in deploy_section


def test_cles_i18n_presentes(fr, en):
    keys = [
        "step_embeddings",
        "embeddings_step_title",
        "embeddings_step_lede",
        "embedding_search_placeholder",
        "aria_filter_embeddings",
        "f_rag_node",
        "f_target_node",
        "f_engine",
        "chosen_badge",
    ]
    for key in keys:
        assert key in fr.get("web", {}), f"Clé FR manquante : {key}"
        assert key in en.get("web", {}), f"Clé EN manquante : {key}"
        fr_val = fr["web"][key]
        en_val = en["web"][key]
        assert fr_val and en_val, f"Valeur vide pour {key}"
        # certains termes sont identiques par conception (« Embeddings », « Filtrer »…) :
        # n'exiger la différence que là où la traduction diverge réellement
        if key in {"embeddings_step_lede", "embedding_search_placeholder", "f_rag_node"}:
            assert fr_val != en_val, f"Les traductions fr/en doivent différer pour {key}"


# ---------------------------------------------------------------------------
# UI-039 — FAI-U-039 : le rail d'étapes ne doit JAMAIS marquer une étape
# "done" par simple position (sn < n) ; seule une preuve backend réelle compte.
# ---------------------------------------------------------------------------

def test_defaut_positionnel_absent_de_app_js(app_js):
    """Régression directe de FAI-U-039 (app.js:962 avant correctif) : la règle
    positionnelle brute ne doit plus jamais réapparaître dans le calcul de 'done'."""
    assert "classList.toggle('done', sn < n)" not in app_js, (
        "Régression FAI-U-039 : le rail redevient positionnel (sn < n), "
        "preuve backend contournée."
    )


def test_fonctions_pures_de_statut_existent(app_js):
    for name in ("collectEvidence", "computeStepEvidence", "computeStepFailure",
                 "computeStepStatus", "applyStepStatuses", "syncDeployStatus",
                 "stepStatusLabel"):
        assert f"function {name}(" in app_js, f"Fonction manquante : {name}"


def test_etape_non_executee_jamais_done(pure_step_functions):
    """Reproduction directe du défaut : étape 3 (Modèles IA) atteinte positionnellement
    (n=4) mais SANS aucun modèle choisi => ne doit jamais être 'done'."""
    ev = {
        "hardwareOk": True, "hardwareFailed": False, "stackChosen": True,
        "modelsChosenCount": 0, "embeddingsChosenCount": 0,
        "bricksLoaded": False, "nodesLoaded": False, "deployStatus": None,
    }
    script = f"""
    const ev = {json.dumps(ev)};
    console.log(JSON.stringify({{
      status3: computeStepStatus(3, 4, ev, true),
      status1: computeStepStatus(1, 4, ev, true)
    }}));
    """
    out = _node_eval(pure_step_functions, script)
    assert out["status3"] != "done", "Défaut FAI-U-039 reproduit : étape 3 marquée done sans preuve"
    assert out["status1"] == "done", "Étape 1 doit être done (preuve hardwareOk réelle)"


def test_backend_absent_jamais_done(pure_step_functions):
    """Étapes 5 (briques) et 6 (nœuds) : pas de données backend chargées => jamais 'done',
    même si l'utilisateur est positionnellement bien plus loin (n=7)."""
    ev = {
        "hardwareOk": True, "hardwareFailed": False, "stackChosen": True,
        "modelsChosenCount": 1, "embeddingsChosenCount": 1,
        "bricksLoaded": False, "nodesLoaded": False, "deployStatus": None,
    }
    script = f"""
    const ev = {json.dumps(ev)};
    console.log(JSON.stringify({{
      bricks: computeStepStatus(5, 7, ev, true),
      nodes: computeStepStatus(6, 7, ev, true)
    }}));
    """
    out = _node_eval(pure_step_functions, script)
    assert out["bricks"] != "done"
    assert out["nodes"] != "done"


def test_deploy_exit_code_non_nul_jamais_done_mais_failed(pure_step_functions):
    """Test négatif obligatoire (contrat UI-039) : exit_code non nul => étape 7 'failed',
    jamais 'done' ni simplement 'pending' (l'échec doit être visible distinctement)."""
    ev = {
        "hardwareOk": True, "hardwareFailed": False, "stackChosen": True,
        "modelsChosenCount": 1, "embeddingsChosenCount": 1,
        "bricksLoaded": True, "nodesLoaded": True, "deployStatus": "failed",
    }
    script = f"""
    const ev = {json.dumps(ev)};
    console.log(JSON.stringify({{ status: computeStepStatus(7, 7, ev, true) }}));
    """
    out = _node_eval(pure_step_functions, script)
    assert out["status"] == "failed"
    assert out["status"] != "done"


def test_etat_backend_absent_deploy_jamais_faussement_done(pure_step_functions):
    """Test négatif : aucun déploiement lancé (deployStatus=null, ex. rafraîchissement
    avant toute action) => étape 7 ne doit jamais afficher 'done'."""
    ev = {
        "hardwareOk": True, "hardwareFailed": False, "stackChosen": True,
        "modelsChosenCount": 1, "embeddingsChosenCount": 1,
        "bricksLoaded": True, "nodesLoaded": True, "deployStatus": None,
    }
    script = f"""
    const ev = {json.dumps(ev)};
    console.log(JSON.stringify({{ status: computeStepStatus(7, 7, ev, true) }}));
    """
    out = _node_eval(pure_step_functions, script)
    assert out["status"] != "done"


def test_rafraichissement_pendant_deploiement_ne_ment_jamais(pure_step_functions):
    """Test négatif (contrat UI-039) : un rafraîchissement PENDANT un déploiement en cours
    (deployStatus='running', ni ok ni failed) ne doit jamais afficher 'done'."""
    ev = {
        "hardwareOk": True, "hardwareFailed": False, "stackChosen": True,
        "modelsChosenCount": 1, "embeddingsChosenCount": 1,
        "bricksLoaded": True, "nodesLoaded": True, "deployStatus": "running",
    }
    script = f"""
    const ev = {json.dumps(ev)};
    console.log(JSON.stringify({{ status: computeStepStatus(7, 7, ev, true) }}));
    """
    out = _node_eval(pure_step_functions, script)
    assert out["status"] != "done"
    assert out["status"] != "failed"


def test_navigation_hors_sequence_ne_cree_pas_de_faux_done(pure_step_functions):
    """Test négatif (contrat UI-039, 'ordre hors séquence') : atteindre l'étape 5 sans être
    jamais passé par 3/4 ne doit PAS marquer 3/4 'done' (la règle positionnelle le ferait)."""
    ev = {
        "hardwareOk": True, "hardwareFailed": False, "stackChosen": True,
        "modelsChosenCount": 0, "embeddingsChosenCount": 0,
        "bricksLoaded": True, "nodesLoaded": False, "deployStatus": None,
    }
    script = f"""
    const ev = {json.dumps(ev)};
    console.log(JSON.stringify({{
      etape3: computeStepStatus(3, 5, ev, true),
      etape4: computeStepStatus(4, 5, ev, true),
      etape5: computeStepStatus(5, 5, ev, true)
    }}));
    """
    out = _node_eval(pure_step_functions, script)
    assert out["etape3"] not in ("done",)
    assert out["etape4"] not in ("done",)
    assert out["etape5"] == "done"  # briques réellement chargées


def test_reconstruction_deterministe_apres_rafraichissement(pure_step_functions):
    """'Le rafraîchissement et le redémarrage reconstruisent le même état' (critère
    d'acceptation UI-039) : à preuve backend identique, le statut recalculé est identique,
    quel que soit le nombre d'appels (idempotence — aucun flag mutable caché)."""
    ev = {
        "hardwareOk": True, "hardwareFailed": False, "stackChosen": True,
        "modelsChosenCount": 2, "embeddingsChosenCount": 0,
        "bricksLoaded": True, "nodesLoaded": True, "deployStatus": "ok",
    }
    script = f"""
    const ev = {json.dumps(ev)};
    const first = [1,2,3,4,5,6,7].map((n) => computeStepStatus(n, 7, ev, true));
    const second = [1,2,3,4,5,6,7].map((n) => computeStepStatus(n, 7, ev, true));
    console.log(JSON.stringify({{ first, second }}));
    """
    out = _node_eval(pure_step_functions, script)
    assert out["first"] == out["second"]
    assert out["first"] == ["done", "done", "done", "pending", "done", "done", "done"]


def test_etape_verrouillee_jamais_done_meme_avec_preuve(pure_step_functions):
    """Une étape non autorisée (`allowed=false`, ex. aucune stack choisie) reste 'locked'
    même si une preuve d'un round précédent traînait encore en mémoire."""
    ev = {
        "hardwareOk": True, "hardwareFailed": False, "stackChosen": False,
        "modelsChosenCount": 3, "embeddingsChosenCount": 0,
        "bricksLoaded": False, "nodesLoaded": False, "deployStatus": None,
    }
    script = f"""
    const ev = {json.dumps(ev)};
    console.log(JSON.stringify({{ status: computeStepStatus(3, 2, ev, false) }}));
    """
    out = _node_eval(pure_step_functions, script)
    assert out["status"] == "locked"


def test_statuts_textuels_pas_seulement_couleur(app_js):
    """'Les statuts sont textuels et ne reposent pas seulement sur la couleur' (critère
    d'acceptation UI-039) : un marqueur textuel (symbole + jeton) distinct existe pour
    chaque statut, indépendant de la langue (aucune traduction fr/en dupliquée en JS —
    locales hors périmètre de ce correctif, et invariant test_ui_n2b::test_pas_de_dico_embarque
    interdit tout dictionnaire fr/en embarqué)."""
    assert "STEP_STATUS_SYMBOL" in app_js
    assert re.search(r"function\s+stepStatusLabel\s*\(", app_js)
    for status in ("locked", "pending", "active", "done", "failed"):
        m = re.search(rf"{status}:\s*'([^']+)'", app_js)
        assert m is not None, f"Symbole manquant pour {status}"
        assert m.group(1).strip(), f"Symbole vide pour {status}"
    # Aucun dictionnaire de traduction fr/en embarqué (regression guard, cf. test_ui_n2b.py).
    assert not re.search(r"^\s+(fr|en):\s*\{", app_js, re.MULTILINE)
    # step-status-text : élément textuel réellement inséré dans le DOM (pas seulement aria)
    assert "step-status-text" in app_js
    assert "step-status-text" in (ROOT / "src" / "forgeai" / "web" / "assets" / "app.css").read_text(encoding="utf-8")
