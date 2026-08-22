"""Executable documentation contract for the Luna/Sol Task 4 deliverables."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
POLICY = REPO / "governance" / "autonomy-policy.json"
REFERENCE = REPO / "Docs" / "reference" / "autonomy-luna-sol.md"
STORY = REPO / "stories" / "ORCH-LUNA-SOL-603.md"
DECISION = REPO / "governance" / "decisions" / "D-2026-08-21-autonomie-luna-sol.md"
AUTHORITY = REPO / "governance" / "authority.json"
PATH_CLASSIFICATION = REPO / "governance" / "path-classification.json"
REVIEWS_GATE = REPO / "scripts" / "reviews_gate.py"
REVUE = REPO / "scripts" / "revue.py"


EXPECTED_TERMINAL_STATES = ("DONE_WITH_EVIDENCE", "BLOCKED_WITH_REASON")


LEGACY_SCOPE_SENTENCE = (
    "Historical `multi_vendor` doctrine only: the legacy 3/3 review and merge statements "
    "below remain unchanged."
)
DISPATCH_SENTENCE = (
    "In `reviews_gate.py`, receipt-mode dispatch preserves `multi_vendor`'s historical 3/3 "
    "tally; active `sol_blind` requires exactly one `GPT-5.6-Sol` verdict."
)
LANE_SCOPE_SENTENCE = (
    "Issue tracking may cover at most four disjoint issues, but it is subordinate to the policy: "
    "never more than two active writer lanes."
)
SOL_BINDING_FIELDS = (
    "fresh_context: true",
    "blind: true",
    "reviewer_read_only: true",
    "reviewer_model: GPT-5.6-Sol",
    "candidate_diff_digest",
    "sdd_diff_digest",
    "base_commit",
    "reviewed_head_commit",
    "reviewed_head_tree",
    "prompt_sha256",
    "template_sha256",
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
WORKFLOW_ACTION_PATTERN = (
    r"(?:contents:\s*write|force-push|decode(?:\s+(?:embedded\s+)?source)?|self-writing)"
)
AUTHORIZATION_PATTERN = (
    r"(?:allow(?:s|ed)?|permit(?:s|ted)?|authori[sz](?:e|es|ed)|enable(?:d|s)?)"
)
PERMISSIVE_WORKFLOW_PATTERNS = (
    r"\bno workflow restriction applies\b",
    rf"\b{WORKFLOW_ACTION_PATTERN}\b.{{0,40}}\b{AUTHORIZATION_PATTERN}\b",
    rf"\b{AUTHORIZATION_PATTERN}\b.{{0,40}}\b{WORKFLOW_ACTION_PATTERN}\b",
)
ACTIVE_MULTI_VENDOR_MARKERS = (
    "3/3",
    "3-of-3",
    "3 of 3",
    "3 vendors",
    "three vendor",
    "three-vendor",
)
STATUS_DECLARATION_RE = re.compile(
    r"^\s*(?:[-*+]\s+)?(?:\*\*|__)?"
    r"(?P<label>status|overall status|story status|overall|task 4 status|"
    r"task 5 status|terminal state|terminal status)"
    r"(?:\*\*|__)?\s*:\s*(?P<value>\S+)?",
    re.IGNORECASE,
)
TERMINAL_STATUS_VALUES = frozenset(
    {"DONE", "DONE_WITH_EVIDENCE", "BLOCKED_WITH_REASON", "COMPLETE", "COMPLETED"}
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
    ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix2-report.md": {
        "class": "WORKING",
        "rule_id": "working-superpowers-sdd",
        "owner": "working-cockpit",
    },
    ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix3-report.md": {
        "class": "WORKING",
        "rule_id": "working-superpowers-sdd",
        "owner": "working-cockpit",
    },
    ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix4-report.md": {
        "class": "WORKING",
        "rule_id": "working-superpowers-sdd",
        "owner": "working-cockpit",
    },
    ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix5-report.md": {
        "class": "WORKING",
        "rule_id": "working-superpowers-sdd",
        "owner": "working-cockpit",
    },
    ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix6-report.md": {
        "class": "WORKING",
        "rule_id": "working-superpowers-sdd",
        "owner": "working-cockpit",
    },
    "Docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md": {
        "class": "DOCS",
        "rule_id": "docs-user",
        "owner": "docs-utilisateur",
    },
}


def _contains_normalized(text: str, phrase: str) -> bool:
    return " ".join(phrase.split()) in " ".join(text.split())


def _assert_mode_contract(text: str, label: str) -> None:
    normalized = " ".join(text.split()).lower()
    assert _contains_normalized(text, DISPATCH_SENTENCE), (
        f"{label} omits the explicit receipt-mode contract"
    )
    assert re.search(r"historical.{0,80}multi_vendor|multi_vendor.{0,80}historical", normalized)
    for clause in re.split(r"[.;\n]+", normalized):
        if "sol_blind" in clause and any(marker in clause for marker in ACTIVE_MULTI_VENDOR_MARKERS):
            raise AssertionError(
                f"{label} applies a multi-vendor quorum to active sol_blind"
            )


def _assert_writer_lane_scope(text: str, label: str) -> None:
    normalized = " ".join(text.split()).lower()
    assert re.search(r"max_active_writer_lanes\s*[:=]\s*2", normalized), (
        f"{label} omits the exact two-lane policy value"
    )
    assert _contains_normalized(text, LANE_SCOPE_SENTENCE), (
        f"{label} does not subordinate issue tracking to the two-lane cap"
    )
    assert not re.search(
        r"\b(?:up to|at most)\s+(?:four|4)\s+(?:active\s+)?writer lanes?\b",
        normalized,
    ), f"{label} permits four active writer lanes"


def _normalize_status_line(line: str) -> str:
    normalized = line.strip()
    for _ in range(8):
        previous = normalized
        normalized = re.sub(r"^(?:>\s*)+", "", normalized)
        normalized = re.sub(r"^#{1,6}\s+", "", normalized)
        normalized = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", normalized)
        normalized = re.sub(r"^\[[ xX]\]\s+", "", normalized)
        normalized = re.sub(r"^[`*_]+", "", normalized)
        normalized = re.sub(
            r"^(?P<label>status|overall status|story status|overall|task 4 status|"
            r"task 5 status|terminal state|terminal status)[`*_]+(?=\s*:)",
            r"\g<label>",
            normalized,
            flags=re.IGNORECASE,
        )
        if normalized == previous:
            break
    return normalized


def _assert_story_status(text: str) -> None:
    declarations = []
    for line in text.splitlines():
        match = STATUS_DECLARATION_RE.match(_normalize_status_line(line))
        if match:
            declarations.append(
                (
                    match.group("label").lower(),
                    (match.group("value") or "").upper(),
                )
            )

    overall_declarations = [
        declaration
        for declaration in declarations
        if declaration[0] in {"status", "overall status", "story status", "overall"}
    ]
    task4_declarations = [
        declaration
        for declaration in declarations
        if declaration[0] == "task 4 status"
    ]
    task5_declarations = [
        declaration
        for declaration in declarations
        if declaration[0] == "task 5 status"
    ]
    assert len(overall_declarations) == 1 and overall_declarations[0][1] == "IN_PROGRESS", (
        "story must declare exactly one overall IN_PROGRESS status"
    )
    assert task4_declarations == [("task 4 status", "DONE_WITH_EVIDENCE")], (
        "story must declare exactly one Task 4 DONE_WITH_EVIDENCE status"
    )
    assert task5_declarations == [("task 5 status", "PENDING")], (
        "story must declare exactly one Task 5 PENDING status"
    )
    assert not [
        declaration
        for declaration in declarations
        if declaration[0] in {"terminal state", "terminal status"}
    ], "story contains an extra terminal status/state declaration"
    assert [
        declaration
        for declaration in declarations
        if declaration[1] in TERMINAL_STATUS_VALUES
    ] == [("task 4 status", "DONE_WITH_EVIDENCE")], (
        "story contains an extra terminal or complete declaration"
    )
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


def _assert_exact_policy(policy: dict) -> None:
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
            "story_id": "stories/ORCH-LUNA-SOL-603.md",
            "fresh_context": True,
            "blind": True,
            "reviewer_read_only": True,
            "read_only": True,
        },
        "terminal_states": list(EXPECTED_TERMINAL_STATES),
        "t3_limits": [
            "payments",
            "production_secrets",
            "permanent_deletions",
            "external_commitments",
        ],
    }


def _assert_expected_classifications(manifest: dict) -> None:
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    for path, expected in EXPECTED_CLASSIFICATIONS.items():
        assert path in entries, f"path classification missing {path}"
        for key, value in expected.items():
            assert entries[path][key] == value, f"{path}: unexpected {key}"


def _assert_authority_locators(authority: dict) -> None:
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
        "sdd_diff_digest",
        "template_sha256",
        "reviewed_head_commit",
        "reviewed_head_tree",
        "prompt_sha256",
        "stories/ORCH-LUNA-SOL-603.md",
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
        _assert_mode_contract(text, str(path))
        _assert_writer_lane_scope(text, str(path))

    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md"):
        text = path.read_text(encoding="utf-8")
        assert _contains_normalized(text, LEGACY_SCOPE_SENTENCE), (
            f"{path.relative_to(REPO)} leaves legacy 3/3 doctrine unscoped"
        )


def _assert_semantic_no_write_rule(text: str, label: str) -> None:
    """Require one negative workflow rule, not merely a bag of forbidden words."""
    normalized_document = " ".join(text.split()).lower()
    assert not any(
        re.search(pattern, normalized_document) for pattern in PERMISSIVE_WORKFLOW_PATTERNS
    ), f"{label} permits a forbidden workflow action"

    paragraphs = ("\n\n" + text).split("\n\n")
    found_prohibition = False
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
        found_prohibition = True
    assert found_prohibition, f"{label} lacks one semantic no-write workflow rule"


def test_no_write_rule_is_semantic_and_rejects_marker_only_text():
    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md", REFERENCE, STORY):
        _assert_semantic_no_write_rule(path.read_text(encoding="utf-8"), str(path))

    with pytest.raises(AssertionError):
        _assert_semantic_no_write_rule(
            "sol_blind contents: write force-push decode self-writing", "bad document"
        )
    for mutation in (
        "No workflow restriction applies: contents: write allowed; force-push permitted; "
        "decode source allowed; self-writing allowed.",
        "A workflow may receive contents: write; force-push is permitted; decode source "
        "is allowed; self-writing is enabled.",
    ):
        with pytest.raises(AssertionError):
            _assert_semantic_no_write_rule(mutation, "permissive mutation")


def test_no_write_rule_rejects_late_authorization_in_real_documents():
    contradictory_paragraphs = (
        "A later exception permits contents: write.",
        "A later emergency procedure authorizes force-push.",
        "A later helper is allowed to decode embedded source.",
        "A later workflow is authorized to be self-writing.",
    )
    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md", REFERENCE):
        text = path.read_text(encoding="utf-8")
        for paragraph in contradictory_paragraphs:
            with pytest.raises(AssertionError):
                _assert_semantic_no_write_rule(
                    f"{text}\n\n{paragraph}", f"{path} with late authorization"
                )


def test_policy_values_and_sol_binding_fields_are_exact():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    _assert_exact_policy(policy)

    reference_text = REFERENCE.read_text(encoding="utf-8")
    for field in SOL_BINDING_FIELDS:
        assert field in reference_text, f"reference omits Sol binding field: {field}"
    assert "mode: sol_blind" in reference_text
    assert "exactly one" in reference_text


def test_active_decision_matches_policy_default_and_historical_scope():
    text = DECISION.read_text(encoding="utf-8")
    normalized = " ".join(text.split()).lower()
    assert "sol_blind" in normalized
    assert "mode par défaut pour les pr courantes" in normalized
    assert "multi-vendor reste compatible pour les reçus d’archive" in normalized
    assert "multi-vendor par défaut" not in normalized


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
    _assert_story_status(text)

    mutations = (
        "Task 5 status: DONE_WITH_EVIDENCE — final evidence is complete.",
        "Overall status: DONE",
        "Terminal state: BLOCKED_WITH_REASON — final evidence is blocked.",
        "Terminal status: FAILED",
        "Terminal status: CANCELLED",
        "Terminal state: PENDING",
        "Terminal status: 123",
        "Terminal state: ???",
        "**Terminal status:** FAILED",
        "- Terminal state: FAILED",
        "*Terminal status:* FAILED",
        "_Terminal state:_ FAILED",
        "> Terminal status: FAILED",
        "# Terminal state: FAILED",
        "1. Terminal status: FAILED",
        "- [ ] Terminal state: FAILED",
        "`Terminal status`: FAILED",
    )
    for mutation in mutations:
        with pytest.raises(AssertionError):
            _assert_story_status(f"{text}\n{mutation}\n")


def test_policy_keeps_the_documented_terminal_contract():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    assert policy["worker"]["max_active_writer_lanes"] == 2
    assert policy["review"]["default_mode"] == "sol_blind"
    assert policy["review"]["reviewer_read_only"] is True
    assert set(policy["terminal_states"]) == set(EXPECTED_TERMINAL_STATES)
    assert len(policy["terminal_states"]) == len(EXPECTED_TERMINAL_STATES)

    for path in (REPO / "AGENTS.md", REPO / "CLAUDE.md", REFERENCE, STORY):
        text = path.read_text(encoding="utf-8")
        assert "DONE_WITH_EVIDENCE" in text
        assert "BLOCKED_WITH_REASON" in text


def test_declared_authority_locators_resolve_to_doctrine_text():
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    _assert_authority_locators(authority)

    bad_authority = deepcopy(authority)
    bad_position = next(
        position
        for source in bad_authority["sources"]
        if source["id"] == "agents-md"
        for position in source["positions"]
        if position["topic"] == "workspace_confinement"
    )
    bad_position["locator"] = "AGENTS.md:73-76"
    with pytest.raises(AssertionError):
        _assert_authority_locators(bad_authority)


def test_changed_sdd_and_document_paths_keep_expected_classification_rules():
    manifest = json.loads(PATH_CLASSIFICATION.read_text(encoding="utf-8"))
    _assert_expected_classifications(manifest)

    bad_manifest = deepcopy(manifest)
    bad_entry = next(
        entry
        for entry in bad_manifest["entries"]
        if entry["path"] == "Docs/reference/autonomy-luna-sol.md"
    )
    bad_entry["rule_id"] = "governance-stories"
    with pytest.raises(AssertionError):
        _assert_expected_classifications(bad_manifest)


def test_adversarial_mode_and_policy_mutations_fail_closed():
    reference_text = REFERENCE.read_text(encoding="utf-8")
    with pytest.raises(AssertionError):
        _assert_mode_contract(
            reference_text + "\nActive `sol_blind` uses 3 vendors and a 3-of-3 quorum.\n",
            "active-mode mutation",
        )

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    bad_policy = deepcopy(policy)
    bad_policy["terminal_states"] = ["DONE_WITH_EVIDENCE", "BLOCKED_WITH_REASON", "DONE"]
    with pytest.raises(AssertionError):
        _assert_exact_policy(bad_policy)

    with pytest.raises(AssertionError):
        _assert_writer_lane_scope(
            REFERENCE.read_text(encoding="utf-8")
            + "\nAt most four active writer lanes are allowed.\n",
            "writer-lane mutation",
        )


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
    assert ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix2-report.md" in classified
    assert ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix3-report.md" in classified
    assert ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix4-report.md" in classified
    assert ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix5-report.md" in classified
    assert ".superpowers/sdd/2026-08-22-autonomous-luna-sol/task-4-fix6-report.md" in classified
    assert "Docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md" in classified
