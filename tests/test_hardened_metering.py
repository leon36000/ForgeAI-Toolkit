"""Tests B-20b lot 3 — metering du chemin RAG dans hardened.py.

Contrat ADR B-20 §1 (chemin B), §2, §4, §7.1 :
- porte pré-dispatch : QuotaAtteint levée AVANT toute émission réseau ;
- réponse reçue : comptabilisation via extraire_tokens (usage présent ou absent) ;
- timeout : journal exact=False/motif="timeout" puis re-levée, jamais de double
  comptage ni d'estimation ;
- tracker=None (défaut) : aucun metering, comportement B-24 strictement inchangé.

Le retrieval est isolé (guardrails=False, reranker_url="", _search stubée) : seul
le metering de la génération (autour de _post_bearer) est testé ici. Le metering
s'exécute AVANT verify_grounding : le verdict d'ancrage n'affecte pas les
assertions sur used_tokens ni sur le journal. QuotaAtteint n'est pas un
GuardrailBlocked : il propage hors de ask().
"""

import json
import pytest
import urllib.error
from forgeai.models.budget import BudgetTracker, QuotaAtteint
from forgeai.rag import hardened
from forgeai.rag.hardened import HardenedRagClient


def _client(tracker):
    # Signature RÉELLE (vérifiée) : ollama_url, qdrant_url, llm_model, embed_model sont
    # REQUIS (pas de défaut), puis les champs à défaut dont tracker (ajouté par MOD 2).
    c = HardenedRagClient(
        ollama_url="http://ollama", qdrant_url="http://qdrant",
        llm_model="glm-4.6", embed_model="bge",
        tei_url="http://tei", gateway_url="http://gw", gateway_key="k",
        reranker_url="", guardrails=False, tracker=tracker,
    )
    # ISOLER le retrieval (`_search` est hérité de RagClient) : on ne teste ICI que
    # le metering de la génération, pas le retrieval Qdrant.
    c._search = lambda question, k: [
        {"payload": {"text": "doc", "source": "s"}, "score": 1.0}
    ]
    return c


def test_usage_present_incremente_rag(tmp_path, monkeypatch):
    """Réponse avec usage.total_tokens -> comptabilisation exacte sur l'agent 'rag'."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("rag", 1000)
    monkeypatch.setattr(
        hardened,
        "_post_bearer",
        lambda url, payload, key: {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 77},
        },
    )

    _client(tracker).ask("q")

    assert tracker.status("rag").used_tokens == 77


def test_coupure_leve_avant_post_bearer(tmp_path, monkeypatch):
    """COUPURE -> QuotaAtteint en pré-dispatch, _post_bearer jamais appelé (zéro émission)."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("rag", 10)
    tracker.record("rag", 20)  # 20/10 -> COUPURE
    appels = {"n": 0}

    def _post_bearer_compte(url, payload, key):
        appels["n"] += 1
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 1},
        }

    monkeypatch.setattr(hardened, "_post_bearer", _post_bearer_compte)

    with pytest.raises(QuotaAtteint):
        _client(tracker).ask("q")

    assert appels["n"] == 0


def test_reponse_sans_usage_journalise_exact_false(tmp_path, monkeypatch):
    """Réponse SANS usage -> 0 token compté, 1 événement exact=false/motif=usage_absent."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("rag", 1000)
    monkeypatch.setattr(
        hardened,
        "_post_bearer",
        lambda url, payload, key: {"choices": [{"message": {"content": "ok"}}]},
    )

    _client(tracker).ask("q")

    assert tracker.status("rag").used_tokens == 0
    lignes = (tmp_path / "meter-events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 1
    evenement = json.loads(lignes[0])
    assert evenement["exact"] is False
    assert evenement["motif"] == "usage_absent"


def test_timeout_journalise_puis_releve(tmp_path, monkeypatch):
    """Erreur transport -> journal motif=timeout, puis l'erreur propage (§7.1)."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("rag", 1000)

    def _post_bearer_timeout(url, payload, key):
        raise urllib.error.URLError("x")

    monkeypatch.setattr(hardened, "_post_bearer", _post_bearer_timeout)

    with pytest.raises(urllib.error.URLError):
        _client(tracker).ask("q")

    assert tracker.status("rag").used_tokens == 0  # jamais d'estimation
    lignes = (tmp_path / "meter-events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 1
    evenement = json.loads(lignes[0])
    assert evenement["exact"] is False
    assert evenement["motif"] == "timeout"


def test_sans_tracker_aucun_metering(tmp_path, monkeypatch):
    """tracker=None (défaut) -> ask() réussit, aucun journal : chemin B-24 inchangé."""
    monkeypatch.setattr(
        hardened,
        "_post_bearer",
        lambda url, payload, key: {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 77},
        },
    )

    _client(None).ask("q")

    assert not (tmp_path / "meter-events.jsonl").exists()