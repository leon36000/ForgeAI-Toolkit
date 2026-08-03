import re
from pathlib import Path


APP_JS = Path(__file__).resolve().parent.parent / "src" / "forgeai" / "web" / "assets" / "app.js"


def test_pas_de_dico_embarque():
    text = APP_JS.read_text(encoding="utf-8")
    assert not re.search(r"^\s+(fr|en):\s*\{", text, re.MULTILINE)


def test_etape_embeddings_cablee():
    text = APP_JS.read_text(encoding="utf-8")
    assert "embeddings-list" in text
    assert "loadEmbeddings" in text
    assert "embeddings-rerank" in text


def test_selection_v2_envoyee():
    text = APP_JS.read_text(encoding="utf-8")
    assert "rag_node" in text
    assert "engine" in text


def test_7_etapes():
    text = APP_JS.read_text(encoding="utf-8")
    assert "TOTAL_STEPS = 7" in text
