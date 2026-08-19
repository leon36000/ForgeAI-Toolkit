"""Tests unitaires S08/S09 — HTTP ollama/qdrant mocké (services externes, tests/ uniquement)."""
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.rag import client as rc


@pytest.fixture
def fake_http(monkeypatch):
    calls = {"post": [], "put": []}

    def fake_post(url, payload, timeout_s=300.0):
        calls["post"].append((url, payload))
        if "/api/embed" in url:
            return {"embeddings": [[0.1, 0.2, 0.3]] * len(payload["input"])}
        if "/api/generate" in url:
            assert "CONTEXTE:" in payload["prompt"]
            return {"response": " Python 3.10 est exigé. "}
        if "/points/search" in url:
            return {"result": [
                {"payload": {"text": "Le Toolkit exige Python 3.10.", "source": "doc.txt"}},
            ]}
        if "/api/pull" in url:
            return {"status": "success"}
        raise AssertionError(f"URL inattendue: {url}")

    def fake_put(url, payload, timeout_s=60.0):
        calls["put"].append((url, payload))
        return {"status": "ok"}

    monkeypatch.setattr(rc, "_post", fake_post)
    monkeypatch.setattr(rc, "_put", fake_put)
    return calls


def _client():
    return rc.RagClient(ollama_url="http://o", qdrant_url="http://q",
                        llm_model="llm", embed_model="emb")


def test_ingest_cree_collection_et_upsert(fake_http):
    n = _client().ingest("Un paragraphe.\n\nUn autre paragraphe.", source="doc.txt")
    assert n == 1  # regroupés sous 800 caractères
    urls = [u for u, _ in fake_http["put"]]
    assert any("/collections/forgeai-p1/points" in u for u in urls)
    points = fake_http["put"][-1][1]["points"]
    assert points[0]["payload"]["source"] == "doc.txt"


def test_ingest_document_vide_leve(fake_http):
    with pytest.raises(ValueError, match="vide"):
        _client().ingest("   ", source="x")


def test_ask_reponse_avec_sources(fake_http):
    result = _client().ask("Quelle version de Python ?")
    assert "3.10" in result["answer"]
    assert result["sources"] == ["doc.txt"]
    assert result["context_used"] is True


def test_ask_sans_resultat_ne_generere_pas(monkeypatch):
    monkeypatch.setattr(rc, "_post", lambda url, p, timeout_s=300.0:
                        {"embeddings": [[0.1]]} if "/api/embed" in url
                        else {"result": []})
    result = _client().ask("question")
    assert result == {"answer": "", "sources": [], "context_used": False}


def test_pull_models_appelle_les_deux(fake_http):
    _client().pull_models()
    pulls = [p["model"] for u, p in fake_http["post"] if "/api/pull" in u]
    assert pulls == ["llm", "emb"]


def test_ensure_collection_erreur_non_409_remonte(monkeypatch):
    """CAND-018 (audit v7.1) — pinning de la garde `if exc.code != 409: raise` de
    RagClient.ensure_collection : seul 409 (collection déjà existante) est toléré.
    Tout AUTRE code HTTP (ex. 500) DOIT remonter, jamais être avalé silencieusement."""
    def fake_put_500(url, payload, timeout_s=60.0):
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", None, None)

    monkeypatch.setattr(rc, "_put", fake_put_500)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _client().ensure_collection(dim=4)
    assert exc_info.value.code == 500


def test_ingest_ids_disjoints_entre_documents_differents(fake_http):
    """AUDIT-RAG #584 — deux ingestions successives avec sources différentes
    doivent produire des IDs disjoints (pas de collision par compteur local)."""
    c = _client()
    c.ingest("doc A", "a.md")
    ids_a = {p["id"] for p in fake_http["put"][-1][1]["points"]}
    c.ingest("doc B", "b.md")
    ids_b = {p["id"] for p in fake_http["put"][-1][1]["points"]}
    assert ids_a.isdisjoint(ids_b)
    assert len(ids_a) > 0
    assert len(ids_b) > 0


def test_ingest_reingestion_idempotente_meme_ids(fake_http):
    """AUDIT-RAG #584 — ré-ingestion du même texte/source produit les mêmes UUID
    déterministes (idempotence)."""
    c = _client()
    texte = "meme texte pour idempotence"
    source = "same.md"
    c.ingest(texte, source)
    ids_1 = [p["id"] for p in fake_http["put"][-1][1]["points"]]
    c.ingest(texte, source)
    ids_2 = [p["id"] for p in fake_http["put"][-1][1]["points"]]
    assert ids_1 == ids_2


def test_ingest_sources_differentes_meme_contenu_ids_differents(fake_http):
    """AUDIT-RAG #584 — deux sources différentes avec contenu identique
    produisent des IDs différents (source participe à l'espace de noms)."""
    c = _client()
    texte = "contenu identique chunké de façon identique"
    c.ingest(texte, "source1.md")
    ids_1 = {p["id"] for p in fake_http["put"][-1][1]["points"]}
    c.ingest(texte, "source2.md")
    ids_2 = {p["id"] for p in fake_http["put"][-1][1]["points"]}
    assert ids_1.isdisjoint(ids_2)
