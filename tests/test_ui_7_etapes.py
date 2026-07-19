import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "src" / "forgeai" / "web" / "assets" / "index.html"
FR_PATH = ROOT / "src" / "forgeai" / "data" / "locales" / "fr.json"
EN_PATH = ROOT / "src" / "forgeai" / "data" / "locales" / "en.json"


@pytest.fixture(scope="module")
def html():
    return HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fr():
    return json.loads(FR_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def en():
    return json.loads(EN_PATH.read_text(encoding="utf-8"))


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
