"""Régressions #578 : un reçu courant ne peut plus sceller une boucle runaway."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reviews_gate", REPO / "scripts" / "reviews_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_current_receipt_rounds_1_and_3_are_admissible() -> None:
    assert gate._current_receipt_round_allowed({"round": 1}) == (True, "AUTO")
    assert gate._current_receipt_round_allowed({"round": 3}) == (True, "REPLAN")


def test_current_receipt_round_4_is_rejected() -> None:
    assert gate._current_receipt_round_allowed({"round": 4}) == (False, "STOP")


def test_current_receipt_round_120_from_runaway_incident_is_rejected() -> None:
    assert gate._current_receipt_round_allowed({"round": 120}) == (False, "STOP")


def test_current_receipt_requires_integer_round() -> None:
    assert gate._current_receipt_round_allowed({}) == (False, "INVALID_ROUND")
    assert gate._current_receipt_round_allowed({"round": True}) == (False, "INVALID_ROUND")
    assert gate._current_receipt_round_allowed(None) == (False, "INVALID_RECEIPT")
