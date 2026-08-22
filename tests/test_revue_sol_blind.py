"""Contrat RED du dépouillement strict `sol_blind` (#603)."""
from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("revue", REPO / "scripts" / "revue.py")
revue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revue)

PROMPT_BYTES = b""
PROMPT_SHA = ""
DIFF_DIGEST = hashlib.sha256(b"").hexdigest()
BASE_COMMIT = "c" * 40
HEAD_COMMIT = "d" * 40
HEAD_TREE = "e" * 40
REVIEWED_AT = "2026-08-22T12:00:00+00:00"
VALIDATION_NOW = datetime.fromisoformat(REVIEWED_AT)


def _git_runner(command):
    if command[:2] == ["git", "merge-base"]:
        return BASE_COMMIT
    if command[:3] == ["git", "rev-parse", "--verify"]:
        ref = command[-1]
        if ref.endswith("^{tree}"):
            return HEAD_TREE
        return ref[: -len("^{commit}")] if ref.endswith("^{commit}") else ref
    if command[:3] == ["git", "diff", "--raw"]:
        return ""
    if command[:2] == ["git", "diff"]:
        return ""
    if command[:2] == ["git", "show"]:
        return revue.TEMPLATE.read_text(encoding="utf-8")
    if command[:2] == ["git", "rev-parse"]:
        return HEAD_TREE if command[-1].endswith("^{tree}") else HEAD_COMMIT
    raise AssertionError(command)


PROMPT_BYTES, PROMPT_SHA = revue._canonical_sol_prompt(
    "S-sol", BASE_COMMIT, HEAD_COMMIT, runner=_git_runner
)


def _expected() -> dict[str, str]:
    return {
        "candidate_diff_digest": DIFF_DIGEST,
        "diff_digest": DIFF_DIGEST,
        "base_commit": BASE_COMMIT,
        "head_commit": HEAD_COMMIT,
        "head_tree": HEAD_TREE,
        "reviewed_head_commit": HEAD_COMMIT,
        "reviewed_head_tree": HEAD_TREE,
        "prompt_sha256": PROMPT_SHA,
        "reviewed_at": REVIEWED_AT,
    }


def _sol_verdict(*, prompt_sha256: str | None = None, **changes) -> dict:
    verdict = {
        "fresh_context": True,
        "blind": True,
        "reviewer_read_only": True,
        "reviewer_model": "GPT-5.6-Sol",
        "candidate_diff_digest": DIFF_DIGEST,
        "base_commit": BASE_COMMIT,
        "reviewed_head_commit": HEAD_COMMIT,
        "reviewed_head_tree": HEAD_TREE,
        "prompt_sha256": prompt_sha256 or PROMPT_SHA,
        "verdict": "APPROVE",
        "blocking_findings": [],
        "reviewed_at": REVIEWED_AT,
    }
    verdict.update(changes)
    return verdict


def _receipt(*, include_blocking_findings: bool = True, **changes) -> dict:
    receipt = {
        "schema": "recu-revue/2",
        "mode": "sol_blind",
        "story": "S-sol",
        "dossier": "S-sol",
        "issue": 603,
        "round": 1,
        "candidate_diff_digest": DIFF_DIGEST,
        "diff_digest": DIFF_DIGEST,
        "base_commit": BASE_COMMIT,
        "head_commit": HEAD_COMMIT,
        "head_tree": HEAD_TREE,
        "reviewed_head_commit": HEAD_COMMIT,
        "reviewed_head_tree": HEAD_TREE,
        "prompt_sha256": PROMPT_SHA,
        "reviewers_attendus": ["GPT-5.6-Sol"],
        "codeur": ["luna_writer"],
        "resultat": "APPROVE",
        "reviewed_at": REVIEWED_AT,
        "verdict": "APPROVE",
        "reviewer_model": "GPT-5.6-Sol",
        "date_heure": REVIEWED_AT,
        "fenetre_heures": 24,
    }
    if include_blocking_findings:
        receipt["blocking_findings"] = []
    receipt.update(changes)
    return receipt


def test_sol_blind_exact_binding_approves_and_receipt_is_accepted(tmp_path):
    verdict = _sol_verdict()
    expected = _expected()
    (tmp_path / "SOL-PROMPT.md").write_bytes(PROMPT_BYTES)

    result = revue.tally_sol_blind([verdict], expected=expected, codeurs=["luna_writer"])
    receipt_result = revue.verifier_recu(
        _receipt(),
        [verdict],
        expected,
        review_dir=tmp_path,
        runner=_git_runner,
        now=VALIDATION_NOW,
    )

    assert result["result"] == "APPROVE"
    assert receipt_result["result"] == "APPROVE"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"fresh_context": False}, "fresh_context"),
        ({"blind": False}, "blind"),
        ({"reviewer_read_only": False}, "reviewer_read_only"),
        ({"reviewed_at": "2025-01-01T12:00:00+00:00"}, "reviewed_at"),
        ({"candidate_diff_digest": "f" * 64}, "candidate_diff_digest"),
        ({"reviewer_model": None}, "reviewer_model"),
        ({"reviewer_model": "GPT-5.6-Luna-Pro"}, "reviewer_model"),
        ({"verdict": "REJECT"}, "verdict"),
        ({"blocking_findings": [{"severity": "critical", "description": "unsafe"}]}, "blocking_findings"),
    ],
)
def test_sol_blind_rejects_each_bypass(change, reason):
    result = revue.tally_sol_blind(
        [_sol_verdict(**change)], expected=_expected(), codeurs=["luna_writer"]
    )

    assert result["result"] != "APPROVE"
    assert reason in result["reason"]


def test_sol_blind_rejects_codewriter_sol_identity():
    result = revue.tally_sol_blind(
        [_sol_verdict()], expected=_expected(), codeurs=["sol"]
    )

    assert result["result"] != "APPROVE"
    assert "codeur" in result["reason"] or "auteur" in result["reason"]


def test_sol_blind_rejects_retired_luna_codewriter():
    result = revue.tally_sol_blind(
        [_sol_verdict()], expected=_expected(), codeurs=["luna"]
    )

    assert result["result"] != "APPROVE"
    assert "codeur" in result["reason"] or "retir" in result["reason"]


def test_sol_blind_rejects_unknown_codewriter_identity():
    result = revue.tally_sol_blind(
        [_sol_verdict()], expected=_expected(), codeurs=["writer-that-is-not-rostered"]
    )

    assert result["result"] != "APPROVE"
    assert "codeur" in result["reason"] or "inconnu" in result["reason"]


def test_sol_blind_allows_luna_writer_and_sol_reviewer_same_vendor():
    result = revue.tally_sol_blind(
        [_sol_verdict()], expected=_expected(), codeurs=["luna_writer"]
    )

    assert result["result"] == "APPROVE"


def test_sol_blind_fails_closed_when_active_sol_roster_entry_is_unavailable(
    monkeypatch, tmp_path
):
    roles = tmp_path / "roles.yaml"
    routes = tmp_path / "routes.yaml"
    roles.write_text(
        "membres:\n"
        "  - id: luna_writer\n"
        "    vendor: openai\n"
        "    provider_id: GPT-5.6-Luna-Writer\n",
        encoding="utf-8",
    )
    routes.write_text("routes:\n", encoding="utf-8")
    real_vendor_table = revue._vendor_table
    monkeypatch.setattr(
        revue,
        "_vendor_table",
        lambda: real_vendor_table(roles_path=roles, routes_path=routes),
    )

    result = revue.tally_sol_blind(
        [_sol_verdict()], expected=_expected(), codeurs=["luna_writer"]
    )

    assert result["result"] != "APPROVE"
    assert any(
        marker in result["reason"].lower()
        for marker in ("sol", "roster", "identit", "reviewer")
    )


def test_sol_blind_receipt_rejects_mismatched_base_without_tally_call():
    result = revue.verifier_recu(
        _receipt(base_commit="f" * 40), [_sol_verdict()], _expected()
    )

    assert result["result"] != "APPROVE"
    assert "commit" in result["reason"] or "base" in result["reason"]


def test_sol_blind_receipt_rejects_mismatched_candidate_digest_without_tally_call():
    result = revue.verifier_recu(
        _receipt(candidate_diff_digest="f" * 64), [_sol_verdict()], _expected()
    )

    assert result["result"] != "APPROVE"
    assert "diff" in result["reason"] or "digest" in result["reason"]


def test_sol_blind_receipt_requires_blocking_findings_field(tmp_path):
    (tmp_path / "SOL-PROMPT.md").write_bytes(PROMPT_BYTES)

    result = revue.verifier_recu(
        _receipt(include_blocking_findings=False),
        [_sol_verdict()],
        _expected(),
        review_dir=tmp_path,
        runner=_git_runner,
        now=VALIDATION_NOW,
    )

    assert result["result"] == "INVALIDE"
    assert "blocking_findings" in result["reason"]


def test_sol_blind_receipt_rejects_non_empty_blocking_findings_field(tmp_path):
    (tmp_path / "SOL-PROMPT.md").write_bytes(PROMPT_BYTES)

    result = revue.verifier_recu(
        _receipt(blocking_findings=[{"severity": "critical", "description": "unsafe"}]),
        [_sol_verdict()],
        _expected(),
        review_dir=tmp_path,
        runner=_git_runner,
        now=VALIDATION_NOW,
    )

    assert result["result"] == "REJECT"
    assert "blocking_findings" in result["reason"]


def test_historical_three_vendor_tally_remains_compatible():
    def historical(vendor):
        return {
            "vendor": vendor,
            "prompt_sha256": PROMPT_SHA,
            "verdict": "APPROVE",
            "objections": [],
            "date_heure": "2025-01-01T12:00:00+00:00",
        }

    result = revue.tally(
        [historical("deepseek"), historical("gemini_flash"), historical("longcat_20")]
    )

    assert result["result"] == "APPROVE"
