"""Round-1 regressions for Git-bound Sol receipts and prompt evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


revue = _load("revue_round1", REPO / "scripts" / "revue.py")
gate = _load("reviews_gate_round1", REPO / "scripts" / "reviews_gate.py")

PROMPT_BYTES = b""
PROMPT_SHA = ""
DIFF_DIGEST = hashlib.sha256(b"").hexdigest()
BASE_CURRENT = "b" * 40
BASE_HISTORICAL = "a" * 40
REVIEWED_HEAD = "c" * 40
REVIEWED_TREE = "d" * 40
CURRENT_HEAD = "e" * 40
CURRENT_TREE = "f" * 40
HISTORICAL_HEAD = "1" * 40
HISTORICAL_TREE = "2" * 40
UNBACKED_HEAD = "3" * 40
UNBACKED_TREE = "4" * 40
DATE = "2026-08-22T12:00:00+00:00"
VALIDATION_NOW = datetime.fromisoformat(DATE)


def _runner(command):
    if command[:3] == ["git", "merge-base", "--is-ancestor"]:
        return ""
    if command[:2] == ["git", "merge-base"]:
        return BASE_HISTORICAL if BASE_HISTORICAL in command else BASE_CURRENT
    if command[:3] == ["git", "diff", "--raw"]:
        return ""
    if command[:3] == ["git", "rev-parse", "--verify"]:
        ref = command[-1]
        if ref.endswith("^{tree}"):
            object_id = ref[: -len("^{tree}")]
            trees = {
                REVIEWED_HEAD: REVIEWED_TREE,
                CURRENT_HEAD: CURRENT_TREE,
                HISTORICAL_HEAD: HISTORICAL_TREE,
            }
            if object_id in trees:
                return trees[object_id]
        else:
            object_id = ref[: -len("^{commit}")] if ref.endswith("^{commit}") else ref
            if object_id in {
                BASE_CURRENT,
                BASE_HISTORICAL,
                REVIEWED_HEAD,
                CURRENT_HEAD,
                HISTORICAL_HEAD,
            }:
                return object_id
        raise subprocess.CalledProcessError(128, command)
    if command[:2] == ["git", "rev-parse"]:
        if command[-1].endswith("^{tree}"):
            return CURRENT_TREE
        return command[-1] if command[-1] in {
            BASE_CURRENT,
            BASE_HISTORICAL,
            REVIEWED_HEAD,
            CURRENT_HEAD,
            HISTORICAL_HEAD,
        } else CURRENT_HEAD
    if command[:2] == ["git", "diff"]:
        return ""
    if command[:2] == ["git", "show"]:
        return revue.TEMPLATE.read_text(encoding="utf-8")
    raise AssertionError(command)


PROMPT_BYTES, PROMPT_SHA = revue._canonical_sol_prompt(
    "S-sol", BASE_CURRENT, REVIEWED_HEAD, runner=_runner
)


def _verdict(
    *,
    base_commit: str = BASE_CURRENT,
    reviewed_head_commit: str = REVIEWED_HEAD,
    reviewed_head_tree: str = REVIEWED_TREE,
    prompt_sha256: str | None = None,
    candidate_diff_digest: str = DIFF_DIGEST,
    reviewer_model: str = "GPT-5.6-Sol",
) -> dict:
    return {
        "vendor": "sol",
        "fresh_context": True,
        "blind": True,
        "reviewer_read_only": True,
        "reviewer_model": reviewer_model,
        "candidate_diff_digest": candidate_diff_digest,
        "base_commit": base_commit,
        "reviewed_head_commit": reviewed_head_commit,
        "reviewed_head_tree": reviewed_head_tree,
        "prompt_sha256": prompt_sha256 or PROMPT_SHA,
        "verdict": "APPROVE",
        "blocking_findings": [],
        "reviewed_at": DATE,
    }


def _receipt(
    *,
    base_commit: str = BASE_CURRENT,
    head_commit: str = CURRENT_HEAD,
    head_tree: str = CURRENT_TREE,
    reviewed_head_commit: str = REVIEWED_HEAD,
    reviewed_head_tree: str = REVIEWED_TREE,
    prompt_sha256: str | None = None,
    candidate_diff_digest: str = DIFF_DIGEST,
) -> dict:
    return {
        "schema": "recu-revue/2",
        "mode": "sol_blind",
        "dossier": "S-sol",
        "issue": 603,
        "round": 1,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "head_tree": head_tree,
        "reviewed_head_commit": reviewed_head_commit,
        "reviewed_head_tree": reviewed_head_tree,
        "candidate_diff_digest": candidate_diff_digest,
        "diff_digest": DIFF_DIGEST,
        "prompt_sha256": prompt_sha256 or PROMPT_SHA,
        "reviewers_attendus": ["GPT-5.6-Sol"],
        "codeur": ["luna_writer"],
        "resultat": "APPROVE",
        "reviewed_at": DATE,
        "verdict": "APPROVE",
        "reviewer_model": "GPT-5.6-Sol",
        "date_heure": DATE,
        "fenetre_heures": 24,
    }


def _write_review(root: Path, name: str, receipt: dict, verdict: dict) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SOL-PROMPT.md").write_bytes(PROMPT_BYTES)
    (directory / "sol.verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    (directory / "RECU.json").write_text(json.dumps(receipt), encoding="utf-8")
    return directory


def _manifest(tmp_path: Path, entries: list[str]) -> Path:
    path = tmp_path / "BINDING.txt"
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return path


def test_sol_receipt_cannot_self_authenticate_git_metadata(tmp_path):
    directory = tmp_path / "review"
    directory.mkdir()
    (directory / "SOL-PROMPT.md").write_bytes(PROMPT_BYTES)
    receipt = _receipt(reviewed_head_commit=UNBACKED_HEAD, reviewed_head_tree=UNBACKED_TREE)
    verdict = _verdict(reviewed_head_commit=UNBACKED_HEAD, reviewed_head_tree=UNBACKED_TREE)

    result = revue.verifier_recu(
        receipt,
        [verdict],
        {
            "base_commit": BASE_CURRENT,
            "head_commit": CURRENT_HEAD,
            "head_tree": CURRENT_TREE,
            "diff_digest": DIFF_DIGEST,
        },
        review_dir=directory,
        runner=_runner,
        now=VALIDATION_NOW,
    )

    assert result["result"] != "APPROVE"
    assert any(marker in result["reason"].lower() for marker in ("git", "commit", "tree", "objet"))


def test_sol_receipt_prompt_hash_comes_from_stored_prompt_bytes(tmp_path):
    directory = tmp_path / "review"
    directory.mkdir()
    (directory / "SOL-PROMPT.md").write_bytes(PROMPT_BYTES)
    receipt = _receipt(prompt_sha256="0" * 64)
    verdict = _verdict(prompt_sha256="0" * 64)

    result = revue.verifier_recu(
        receipt,
        [verdict],
        {
            "base_commit": BASE_CURRENT,
            "head_commit": CURRENT_HEAD,
            "head_tree": CURRENT_TREE,
            "diff_digest": DIFF_DIGEST,
        },
        review_dir=directory,
        runner=_runner,
        now=VALIDATION_NOW,
    )

    assert result["result"] != "APPROVE"
    assert "prompt" in result["reason"] or "sha" in result["reason"]


@pytest.mark.parametrize(
    "field",
    ["candidate_diff_digest", "base_commit", "reviewed_head_commit", "reviewed_head_tree", "prompt_sha256"],
)
def test_sol_tally_rejects_malformed_expected_hashes(field):
    expected = {
        "candidate_diff_digest": DIFF_DIGEST,
        "diff_digest": DIFF_DIGEST,
        "base_commit": BASE_CURRENT,
        "reviewed_head_commit": REVIEWED_HEAD,
        "reviewed_head_tree": REVIEWED_TREE,
        "prompt_sha256": PROMPT_SHA,
        "reviewed_at": DATE,
    }
    expected[field] = None if field != "prompt_sha256" else "not-a-sha256"

    result = revue.tally_sol_blind([_verdict()], expected=expected, codeurs=["luna_writer"])

    assert result["result"] == "INVALIDE"
    assert field.split("_")[0] in result["reason"] or "hash" in result["reason"]


def test_current_gate_ignores_historical_sol_binding_when_current_sol_binding_is_valid(tmp_path):
    root = tmp_path / "reviews"
    historical = _write_review(
        root,
        "S-historical-sol",
        _receipt(
            base_commit=BASE_HISTORICAL,
            reviewed_head_commit=HISTORICAL_HEAD,
            reviewed_head_tree=HISTORICAL_TREE,
        ),
        _verdict(
            base_commit=BASE_HISTORICAL,
            reviewed_head_commit=HISTORICAL_HEAD,
            reviewed_head_tree=HISTORICAL_TREE,
        ),
    )
    _write_review(root, "S-current-sol", _receipt(), _verdict())

    ok, report = gate.check(
        _manifest(tmp_path, [historical.name, "S-current-sol"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=_runner,
        now=VALIDATION_NOW,
    )

    assert ok is True, report
    assert not any("ECHEC S-historical-sol" in line for line in report)
    assert any("reçu couvre le changement courant" in line for line in report)


def test_sol_prompt_rejects_artifact_not_generated_from_git_refs(monkeypatch, tmp_path):
    artefact = tmp_path / "arbitrary.diff"
    artefact.write_text("incomplete caller-supplied artifact", encoding="utf-8")
    out = tmp_path / "SOL-PROMPT.md"
    monkeypatch.setattr(
        revue,
        "_etat_git_reel",
        lambda base_ref, head_ref: {
            "base_commit": BASE_CURRENT,
            "head_commit": CURRENT_HEAD,
            "head_tree": CURRENT_TREE,
            "diff_digest": DIFF_DIGEST,
        },
    )
    monkeypatch.setattr(
        revue,
        "_diff_artifact_canonique",
        lambda base_ref, head_ref: "canonical Git artifact",
        raising=False,
    )

    with pytest.raises(ValueError, match="artefact"):
        revue._cmd_prompt(
            SimpleNamespace(
                artefact=str(artefact),
                criteres=None,
                story="S-sol",
                mode="sol_blind",
                base_ref="origin/main",
                head_ref="HEAD",
                out=str(out),
            )
        )


def test_build_sol_prompt_cannot_pair_arbitrary_artifact_with_git_metadata(monkeypatch):
    monkeypatch.setattr(
        revue,
        "_diff_artifact_canonique",
        lambda base_ref, head_ref: "canonical Git artifact",
    )
    monkeypatch.setattr(
        revue,
        "_etat_git_reel",
        lambda base_ref, head_ref: {
            "base_commit": BASE_CURRENT,
            "head_commit": CURRENT_HEAD,
            "head_tree": CURRENT_TREE,
            "diff_digest": DIFF_DIGEST,
        },
    )

    with pytest.raises(ValueError, match="artefact"):
        revue.build_prompt(
            "S-sol",
            "criteria",
            "caller.diff",
            "arbitrary caller artifact",
            mode="sol_blind",
            base_ref="origin/main",
            head_ref="HEAD",
            expected={"base_commit": BASE_CURRENT},
        )


def test_archive_gate_rejects_symbolic_sol_receipt_commit(tmp_path):
    root = tmp_path / "reviews"
    receipt = _receipt(head_commit="HEAD")
    _write_review(root, "S-sol-symbolic", receipt, _verdict())

    ok, report = gate.check(
        _manifest(tmp_path, ["S-sol-symbolic"]), root, mode="archive", runner=_runner
    )

    assert ok is False
    assert any("reçu archive illisible" in line for line in report)


def test_archive_gate_rejects_unmerged_sol_reviewed_head_even_with_merged_head(tmp_path):
    root = tmp_path / "reviews"
    historical_prompt, historical_prompt_sha = revue._canonical_sol_prompt(
        "S-sol", BASE_CURRENT, HISTORICAL_HEAD, runner=_runner
    )
    directory = _write_review(
        root,
        "S-sol-unmerged-reviewed",
        _receipt(
            reviewed_head_commit=HISTORICAL_HEAD,
            reviewed_head_tree=HISTORICAL_TREE,
            prompt_sha256=historical_prompt_sha,
        ),
        _verdict(
            reviewed_head_commit=HISTORICAL_HEAD,
            reviewed_head_tree=HISTORICAL_TREE,
            prompt_sha256=historical_prompt_sha,
        ),
    )
    (directory / "SOL-PROMPT.md").write_bytes(historical_prompt)

    def archive_runner(command):
        if command[:3] == ["git", "merge-base", "--is-ancestor"]:
            if command[3] == HISTORICAL_HEAD:
                raise subprocess.CalledProcessError(1, command)
            return ""
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, ["S-sol-unmerged-reviewed"]),
        root,
        mode="archive",
        runner=archive_runner,
    )

    assert ok is False
    assert any("reviewed_head_commit" in line for line in report), report


def test_archive_sol_receipt_requires_head_tree_to_match_commit():
    receipt = _receipt(head_tree="d" * 40)

    with pytest.raises(ValueError, match="arbre"):
        revue._validate_sol_archive_receipt(receipt, _runner)
