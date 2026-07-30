"""Tests pour MeteredTransport — ADR B-20 §1 chemin A, §2, §7.1.

Vérifie la porte pré-dispatch (COUPURE → QuotaAtteint, zéro émission),
la transparence sur le fil (retour inchangé), et la comptabilisation
post-réponse (usage présent → compteur ; exact=False → journal).
"""
import json
from pathlib import Path

import pytest

from forgeai.models.budget import BudgetTracker, QuotaAtteint
from forgeai.models.probe import MeteredTransport


class _InnerEspion:
    """Transport stub : compte les post() et renvoie une réponse programmée."""

    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self.text = text
        self.appels = 0

    def post(self, url, headers, body, timeout):
        self.appels += 1
        return self.status, self.text


def _lire_evenements(home: Path) -> list[dict]:
    """Lit le journal meter-events.jsonl et retourne la liste des événements."""
    log = home / "meter-events.jsonl"
    if not log.exists():
        return []
    return [json.loads(ligne) for ligne in log.read_text(encoding="utf-8").splitlines() if ligne.strip()]


def test_usage_present_incremente_le_compteur_de_n(tmp_path):
    """Usage présent dans la réponse → compteur incrémenté de n, retour inchangé."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("probe", 1000)
    inner = _InnerEspion(200, json.dumps({"usage": {"total_tokens": 42}}))
    mt = MeteredTransport(inner, tracker, agent="probe")

    status, text = mt.post("http://example.com", {}, b"", 10.0)

    assert tracker.status("probe").used_tokens == 42
    assert inner.appels == 1
    assert status == 200
    assert text == json.dumps({"usage": {"total_tokens": 42}})


def test_coupure_leve_avant_toute_emission_zero_post(tmp_path):
    """COUPURE → QuotaAtteint AVANT toute émission (espion : zéro post)."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("probe", 10)
    tracker.record("probe", 20)  # COUPURE
    inner = _InnerEspion(200, json.dumps({"usage": {"total_tokens": 5}}))
    mt = MeteredTransport(inner, tracker, agent="probe")

    with pytest.raises(QuotaAtteint):
        mt.post("http://example.com", {}, b"", 10.0)

    assert inner.appels == 0


def test_reponse_sans_usage_journalise_exact_false(tmp_path):
    """Réponse 200 sans champ usage → journal exact=false, motif=usage_absent."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("probe", 1000)
    inner = _InnerEspion(200, json.dumps({"choices": []}))
    mt = MeteredTransport(inner, tracker, agent="probe")

    mt.post("http://example.com", {}, b"", 10.0)

    assert tracker.status("probe").used_tokens == 0
    evenements = _lire_evenements(tmp_path)
    assert len(evenements) == 1
    assert evenements[0]["exact"] is False
    assert evenements[0]["motif"] == "usage_absent"


def test_status_zero_journalise_timeout(tmp_path):
    """Échec réseau (status 0) → journal exact=false, motif=timeout, retour (0,'')."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("probe", 1000)
    inner = _InnerEspion(0, "")
    mt = MeteredTransport(inner, tracker, agent="probe")

    status, text = mt.post("http://example.com", {}, b"", 10.0)

    assert status == 0
    assert text == ""
    assert tracker.status("probe").used_tokens == 0
    evenements = _lire_evenements(tmp_path)
    assert len(evenements) == 1
    assert evenements[0]["exact"] is False
    assert evenements[0]["motif"] == "timeout"


def test_corps_non_json_journalise_usage_absent(tmp_path):
    """Corps non-JSON → parse échoue → reponse={} → journal usage_absent."""
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("probe", 1000)
    inner = _InnerEspion(200, "<html>err</html>")
    mt = MeteredTransport(inner, tracker, agent="probe")

    mt.post("http://example.com", {}, b"", 10.0)

    evenements = _lire_evenements(tmp_path)
    assert len(evenements) == 1
    assert evenements[0]["exact"] is False
    assert evenements[0]["motif"] == "usage_absent"
