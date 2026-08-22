"""Tests for the versioned Luna/Sol autonomy contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import importlib.util

REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "governance" / "autonomy-policy.json"

spec = importlib.util.spec_from_file_location("revue", REPO / "scripts" / "revue.py")
revue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revue)


def load_policy(path: Path = POLICY_PATH) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy["worker"]["max_active_writer_lanes"] not in (1, 2):
        raise ValueError("max_active_writer_lanes must be between 1 and 2")
    return policy


def test_autonomy_policy_has_literal_contract_values():
    policy = load_policy()

    assert policy["worker"]["primary_model"] == "GPT-5.6 Luna"
    assert policy["worker"]["max_active_writer_lanes"] == 2
    assert policy["review"]["default_mode"] == "sol_blind"
    assert policy["review"]["reviewer_model"] == "GPT-5.6 Sol"
    assert set(policy["terminal_states"]) == {
        "DONE_WITH_EVIDENCE",
        "BLOCKED_WITH_REASON",
    }


def test_autonomy_policy_rejects_three_writer_lanes(tmp_path):
    invalid_path = tmp_path / "autonomy-policy.json"
    invalid_path.write_text(
        json.dumps(
            {
                "worker": {
                    "primary_model": "GPT-5.6 Luna",
                    "max_active_writer_lanes": 3,
                },
                "review": {
                    "default_mode": "sol_blind",
                    "reviewer_model": "GPT-5.6 Sol",
                },
                "terminal_states": [
                    "DONE_WITH_EVIDENCE",
                    "BLOCKED_WITH_REASON",
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="max_active_writer_lanes"):
        load_policy(invalid_path)


def test_active_luna_and_sol_roster_identities_are_resolvable():
    assert revue.vendor_of("GPT-5.6-Luna-Writer") == "openai"
    assert revue.vendor_of("GPT-5.6-Sol") == "openai"


def test_historical_luna_identity_remains_retired_and_resolvable():
    assert revue.vendor_of("GPT-5.6-Luna-Pro") == "openai"
    roles_text = (REPO / "manifests" / "roles.yaml").read_text(encoding="utf-8")
    luna_start = roles_text.index("  - id: luna\n")
    luna_entry = roles_text[luna_start : roles_text.index("\n  - id:", luna_start + 1)]
    assert "statut: retire" in luna_entry
