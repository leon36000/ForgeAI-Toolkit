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
    assert policy["review"]["story_id"] == "stories/ORCH-LUNA-SOL-603.md"
    assert all(
        policy["review"][field] is True
        for field in ("fresh_context", "blind", "reviewer_read_only", "read_only")
    )
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


def test_production_policy_rejects_one_lane_and_missing_sol_requirement(tmp_path):
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["worker"]["max_active_writer_lanes"] = 1
    policy["review"].pop("blind")
    invalid_path = tmp_path / "autonomy-policy.json"
    invalid_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="max_active_writer_lanes"):
        revue.load_autonomy_policy(invalid_path)

    policy["worker"]["max_active_writer_lanes"] = 2
    invalid_path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="blind"):
        revue.load_autonomy_policy(invalid_path)


@pytest.mark.parametrize("lanes", [True, 1])
def test_production_policy_requires_exact_integer_two(tmp_path, lanes):
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["worker"]["max_active_writer_lanes"] = lanes
    invalid_path = tmp_path / "autonomy-policy.json"
    invalid_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="max_active_writer_lanes"):
        revue.load_autonomy_policy(invalid_path)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("schema",), "wrong-schema", "schema"),
        (("worker", "primary_model"), "GPT-5.6-Sol", "primary_model"),
        (("review", "default_mode"), "multi_vendor", "default_mode"),
        (("review", "reviewer_model"), "GPT-5.6 Luna", "reviewer_model"),
        (("review", "fresh_context"), 1, "fresh_context"),
        (("review", "blind"), 1, "blind"),
        (("review", "reviewer_read_only"), 1, "reviewer_read_only"),
        (("review", "read_only"), 1, "read_only"),
    ],
)
def test_production_policy_rejects_every_invalid_contract_field(tmp_path, path, value, message):
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    target = policy
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    invalid_path = tmp_path / "autonomy-policy.json"
    invalid_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        revue.load_autonomy_policy(invalid_path)


def test_active_luna_and_sol_roster_identities_are_resolvable():
    assert revue.vendor_of("GPT-5.6-Luna-Writer") == "openai"
    assert revue.vendor_of("GPT-5.6-Sol") == "openai"


def test_historical_luna_identity_remains_retired_and_resolvable():
    assert revue.vendor_of("GPT-5.6-Luna-Pro") == "openai"
    roles_text = (REPO / "manifests" / "roles.yaml").read_text(encoding="utf-8")
    luna_start = roles_text.index("  - id: luna\n")
    luna_entry = roles_text[luna_start : roles_text.index("\n  - id:", luna_start + 1)]
    assert "statut: retire" in luna_entry
