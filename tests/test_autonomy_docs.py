"""Executable documentation contract for the Luna/Sol Task 4 deliverables."""
from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
POLICY = REPO / "governance" / "autonomy-policy.json"
REFERENCE = REPO / "Docs" / "reference" / "autonomy-luna-sol.md"
STORY = REPO / "stories" / "ORCH-LUNA-SOL-603.md"


COMMON_MARKERS = (
    "governance/autonomy-policy.json",
    "GPT-5.6 Luna",
    "GPT-5.6 Sol",
    "luna_writer",
    "sol_blind",
    "max_active_writer_lanes",
    "contents: write",
    "force-push",
    "decode",
    "self-writing",
    "DONE_WITH_EVIDENCE",
    "BLOCKED_WITH_REASON",
)


def test_active_contract_is_documented_without_runtime_or_external_claims():
    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md", REFERENCE):
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in COMMON_MARKERS if marker not in text]
        assert not missing, f"{path.relative_to(REPO)} omits: {missing}"

    reference_text = REFERENCE.read_text(encoding="utf-8")
    for marker in (
        "fresh",
        "read-only",
        "candidate_diff_digest",
        "reviewed_head_commit",
        "reviewed_head_tree",
        "prompt_sha256",
        "T3",
        "source de vérité",
        "GitHub",
        "scripts/registre.py verify",
        "no runtime evidence",
        "no external evidence",
    ):
        assert marker in reference_text, f"reference omits: {marker}"


def test_story_has_testable_acceptance_and_explicit_checkpoint_status():
    text = STORY.read_text(encoding="utf-8")

    assert "Status: IN_PROGRESS" in text
    assert "Checkpoint:" in text
    assert "## Critères d’acceptation" in text
    assert "[ ]" in text
    assert "DONE_WITH_EVIDENCE" in text
    assert "BLOCKED_WITH_REASON" in text
    assert "no final runtime or external evidence is claimed" in text


def test_policy_keeps_the_documented_terminal_contract():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["worker"]["max_active_writer_lanes"] == 2
    assert policy["review"]["default_mode"] == "sol_blind"
    assert policy["review"]["reviewer_read_only"] is True
    assert policy["terminal_states"] == [
        "DONE_WITH_EVIDENCE",
        "BLOCKED_WITH_REASON",
    ]


def test_generated_views_reference_the_task4_paths_and_contract_source():
    authority_map = (REPO / "governance" / "AUTHORITY-MAP.md").read_text(
        encoding="utf-8"
    )
    state = json.loads(
        (REPO / "governance" / "STATE-CURRENT.json").read_text(encoding="utf-8")
    )
    path_manifest = json.loads(
        (REPO / "governance" / "path-classification.json").read_text(
            encoding="utf-8"
        )
    )

    assert "NE PAS ÉDITER À LA MAIN" in authority_map
    assert "governance/decisions/D-2026-08-21-autonomie-luna-sol.md" in authority_map
    assert "tests/test_autonomy_docs.py" in {
        item["path"] for item in state["deterministe"]["inputs"]
    }
    classified = {entry["path"] for entry in path_manifest["entries"]}
    assert "Docs/reference/autonomy-luna-sol.md" in classified
    assert "stories/ORCH-LUNA-SOL-603.md" in classified
