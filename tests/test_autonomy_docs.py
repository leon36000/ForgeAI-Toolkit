"""Executable documentation contract for the Luna/Sol Task 4 deliverables."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
POLICY = REPO / "governance" / "autonomy-policy.json"
REFERENCE = REPO / "Docs" / "reference" / "autonomy-luna-sol.md"
STORY = REPO / "stories" / "ORCH-LUNA-SOL-603.md"
AUTHORITY = REPO / "governance" / "authority.json"
PATH_CLASSIFICATION = REPO / "governance" / "path-classification.json"
REVIEWS_GATE = REPO / "scripts" / "reviews_gate.py"
REVUE = REPO / "scripts" / "revue.py"


LEGACY_SCOPE_SENTENCE = (
    "Historical `multi_vendor` doctrine only: the legacy 3/3 review and merge statements "
    "below remain unchanged."
)
DISPATCH_SENTENCE = (
    "In `reviews_gate.py`, receipt-mode dispatch preserves `multi_vendor`'s historical 3/3 "
    "tally; active `sol_blind` requires exactly one `GPT-5.6-Sol` verdict."
)
SOL_BINDING_FIELDS = (
    "fresh_context: true",
    "blind: true",
    "reviewer_read_only: true",
    "reviewer_model: GPT-5.6-Sol",
    "candidate_diff_digest",
    "base_commit",
    "reviewed_head_commit",
    "reviewed_head_tree",
    "prompt_sha256",
    "reviewed_at",
    "verdict: APPROVE",
    "blocking_findings: []",
)
FORBIDDEN_WORKFLOW_MARKERS = (
    "contents: write",
    "force-push",
    "decode",
    "self-writing",
)
EXPECTED_CLASSIFICATIONS = {
    "Docs/reference/autonomy-luna-sol.md": {
        "class": "DOCS",
        "rule_id": "docs-user",
        "owner": "docs-utilisateur",
    },
    "stories/ORCH-LUNA-SOL-603.md": {
        "class": "GOVERNANCE",
        "rule_id": "governance-stories",
        "owner": "gouvernance-stories",
    },
    ".superpowers/sdd/2026-08-22-autonomous-luna-sol/progress.md": {
        "class": "WORKING",
        "rule_id": "working-superpowers-sdd",
        "owner": "working-cockpit",
    },
    ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix1-report.md": {
        "class": "WORKING",
        "rule_id": "working-superpowers-sdd",
        "owner": "working-cockpit",
    },
    "docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md": {
        "class": "WORKING",
        "rule_id": "working-superpowers-docs",
        "owner": "working-cockpit",
    },
}


def _contains_normalized(text: str, phrase: str) -> bool:
    return " ".join(phrase.split()) in " ".join(text.split())


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
    documents = (REPO / "AGENTS.md", REPO / "CLAUDE.md", REFERENCE, STORY)
    for path in documents:
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

    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md", REFERENCE):
        text = path.read_text(encoding="utf-8")
        assert _contains_normalized(text, DISPATCH_SENTENCE), (
            f"{path.relative_to(REPO)} omits receipt dispatch"
        )

    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md"):
        text = path.read_text(encoding="utf-8")
        assert _contains_normalized(text, LEGACY_SCOPE_SENTENCE), (
            f"{path.relative_to(REPO)} leaves legacy 3/3 doctrine unscoped"
        )


def _assert_semantic_no_write_rule(text: str, label: str) -> None:
    """Require one negative workflow rule, not merely a bag of forbidden words."""
    paragraphs = ("\n\n" + text).split("\n\n")
    for paragraph in paragraphs:
        normalized = " ".join(paragraph.split()).lower()
        if not all(marker in normalized for marker in FORBIDDEN_WORKFLOW_MARKERS):
            continue
        negative_workflow = re.search(
            r"(?:\bno workflow\b|\baucun workflow\b|workflows?\s+(?:ne|cannot|must not))",
            normalized,
        )
        assert negative_workflow, (
            f"{label} lists forbidden workflow markers without a prohibition"
        )
        return
    raise AssertionError(f"{label} lacks one semantic no-write workflow rule")


def test_no_write_rule_is_semantic_and_rejects_marker_only_text():
    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md", REFERENCE, STORY):
        _assert_semantic_no_write_rule(path.read_text(encoding="utf-8"), str(path))

    with pytest.raises(AssertionError):
        _assert_semantic_no_write_rule(
            "sol_blind contents: write force-push decode self-writing", "bad document"
        )


def test_policy_values_and_sol_binding_fields_are_exact():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy == {
        "schema": "autonomy-policy/1",
        "decision": "D-2026-08-21-autonomie-luna-sol",
        "worker": {
            "primary_model": "GPT-5.6 Luna",
            "max_active_writer_lanes": 2,
        },
        "review": {
            "default_mode": "sol_blind",
            "reviewer_model": "GPT-5.6 Sol",
            "fresh_context": True,
            "blind": True,
            "reviewer_read_only": True,
            "read_only": True,
        },
        "terminal_states": ["DONE_WITH_EVIDENCE", "BLOCKED_WITH_REASON"],
        "t3_limits": [
            "payments",
            "production_secrets",
            "permanent_deletions",
            "external_commitments",
        ],
    }

    reference_text = REFERENCE.read_text(encoding="utf-8")
    for field in SOL_BINDING_FIELDS:
        assert field in reference_text, f"reference omits Sol binding field: {field}"
    assert "mode: sol_blind" in reference_text
    assert "exactly one" in reference_text


def test_reviews_gate_declares_receipt_dispatch_and_single_sol_verdict():
    gate_text = REVIEWS_GATE.read_text(encoding="utf-8")
    revue_text = REVUE.read_text(encoding="utf-8")
    assert 'receipt_mode = receipt.get("mode", "multi_vendor")' in gate_text
    assert 'receipt_mode == "sol_blind"' in gate_text
    assert "tally_sol_blind" in gate_text
    assert "Receipt mode is the dispatch contract" in gate_text
    assert "exact-one-Sol validator" in gate_text
    assert "sol_blind exige exactement un verdict" in revue_text


def test_story_has_testable_acceptance_and_explicit_checkpoint_status():
    text = STORY.read_text(encoding="utf-8")

    assert "Status: IN_PROGRESS — overall story remains active." in text
    assert "Task 4 status: DONE_WITH_EVIDENCE" in text
    assert "Task 5 status: PENDING — final fresh Sol evidence remains pending." in text
    assert "being synchronized" not in text
    assert "Checkpoint:" in text
    assert "## Critères d’acceptation" in text
    assert "- [x]" in text
    assert "- [ ]" in text
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

    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md", REFERENCE, STORY):
        text = path.read_text(encoding="utf-8")
        assert "DONE_WITH_EVIDENCE" in text
        assert "BLOCKED_WITH_REASON" in text


def test_declared_authority_locators_resolve_to_doctrine_text():
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    topic_markers = {
        "orchestration_seat": ("claude", "opus"),
        "workspace_confinement": ("repo", "dépôt", "external", "outillage"),
        "plan_of_record": ("plan",),
    }

    for source in authority["sources"]:
        for position in source.get("positions", []):
            locator = position["locator"]
            match = re.fullmatch(r"([^:]+):(\d+)(?:-(\d+))?", locator)
            assert match, f"invalid locator in test fixture: {locator}"
            relative_path, start, end = match.group(1), int(match.group(2)), match.group(3)
            target = (REPO / relative_path).resolve()
            assert target.is_relative_to(REPO.resolve())
            lines = target.read_text(encoding="utf-8").splitlines()
            excerpt = " ".join(lines[start - 1 : int(end) if end else start]).lower()
            assert excerpt.strip(), f"empty authority locator: {locator}"
            markers = topic_markers.get(position["topic"], ())
            assert any(marker in excerpt for marker in markers), (
                f"{locator} does not resolve to {position['topic']} doctrine"
            )

    agents_positions = next(
        source for source in authority["sources"] if source["id"] == "agents-md"
    )["positions"]
    confinement = next(
        position
        for position in agents_positions
        if position["topic"] == "workspace_confinement"
    )
    assert confinement["locator"] != "AGENTS.md:73-76"
    match = re.fullmatch(r"([^:]+):(\d+)(?:-(\d+))?", confinement["locator"])
    assert match
    lines = (REPO / match.group(1)).read_text(encoding="utf-8").splitlines()
    excerpt = " ".join(lines[int(match.group(2)) - 1 : int(match.group(3) or match.group(2))])
    assert "Confinement au repo" in excerpt


def test_changed_sdd_and_document_paths_keep_expected_classification_rules():
    manifest = json.loads(PATH_CLASSIFICATION.read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    for path, expected in EXPECTED_CLASSIFICATIONS.items():
        assert path in entries, f"path classification missing {path}"
        for key, value in expected.items():
            assert entries[path][key] == value, f"{path}: unexpected {key}"


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
    assert ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix1-report.md" in classified
    assert "docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md" in classified
