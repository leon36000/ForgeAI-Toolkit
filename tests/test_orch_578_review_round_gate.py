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
    assert gate._current_receipt_round_allowed({"round": 3}) == (False, "REPLAN_REQUIRED")
    assert gate._current_receipt_round_allowed({"round": 3, "replanned": True}) == (True, "REPLAN")


def test_current_receipt_round_4_is_rejected() -> None:
    assert gate._current_receipt_round_allowed({"round": 4}) == (False, "STOP")


def test_current_receipt_round_120_from_runaway_incident_is_rejected() -> None:
    assert gate._current_receipt_round_allowed({"round": 120}) == (False, "STOP")


def test_current_receipt_requires_integer_round() -> None:
    assert gate._current_receipt_round_allowed({}) == (False, "INVALID_ROUND")
    assert gate._current_receipt_round_allowed({"round": True}) == (False, "INVALID_ROUND")
    assert gate._current_receipt_round_allowed(None) == (False, "INVALID_RECEIPT")


def test_current_receipt_replan_requires_boolean() -> None:
    assert gate._current_receipt_round_allowed({"round": 3, "replanned": "yes"}) == (
        False,
        "INVALID_REPLAN",
    )


def test_receipt_round_chain_is_monotone_by_issue(tmp_path: Path) -> None:
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / "RECU.json").write_text(
        '{"issue": 597, "round": 1, "base_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}',
        encoding="utf-8",
    )
    root = tmp_path

    assert gate._receipt_round_chain_allowed(
        {"issue": 597, "round": 1, "base_commit": "b" * 40},
        "current",
        ["prior", "current"],
        root,
    ) == (False, "ROUND_NOT_MONOTONIC")
    assert gate._receipt_round_chain_allowed(
        {"issue": 597, "round": 2, "base_commit": "b" * 40},
        "current",
        ["prior", "current"],
        root,
    ) == (True, "CHAIN")
    assert gate._receipt_round_chain_allowed(
        {"issue": 598, "round": 1, "base_commit": "b" * 40},
        "current",
        ["prior", "current"],
        root,
    ) == (True, "CHAIN")


def test_receipt_round_chain_fail_closed_sur_recu_corrompu(tmp_path: Path) -> None:
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / "RECU.json").write_text("{not-json", encoding="utf-8")
    assert gate._receipt_round_chain_allowed(
        {"issue": 597, "round": 1, "base_commit": "b" * 40},
        "current",
        ["prior", "current"],
        tmp_path,
    ) == (False, "PRIOR_RECEIPT_UNREADABLE")
