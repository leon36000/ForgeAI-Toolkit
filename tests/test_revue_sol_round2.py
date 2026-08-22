"""Round-2 regressions for canonical Sol prompts, freshness, roster, and schema."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


revue = _load("revue_round2", REPO / "scripts" / "revue.py")
gate = _load("reviews_gate_round2", REPO / "scripts" / "reviews_gate.py")

BASE = "b" * 40
HEAD = "c" * 40
TREE = "d" * 40
DIFF = hashlib.sha256(b"").hexdigest()
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
DATE = NOW.isoformat()


def _runner(command):
    if command[:2] == ["git", "merge-base"]:
        return BASE
    if command[:3] == ["git", "diff", "--raw"]:
        return ""
    if command[:2] == ["git", "diff"]:
        return ""
    if command[:2] == ["git", "show"]:
        return revue.TEMPLATE.read_text(encoding="utf-8")
    if command[:3] == ["git", "rev-parse", "--verify"]:
        ref = command[-1]
        if ref.endswith("^{tree}"):
            return TREE
        return ref[: -len("^{commit}")] if ref.endswith("^{commit}") else ref
    if command[:2] == ["git", "rev-parse"]:
        return TREE if command[-1].endswith("^{tree}") else HEAD
    raise AssertionError(command)


CANONICAL_PROMPT, CANONICAL_SHA = revue._canonical_sol_prompt(
    "S-sol", BASE, HEAD, runner=_runner
)


def _verdict(*, reviewed_at: str = DATE, prompt_sha256: str | None = None) -> dict:
    return {
        "vendor": "sol",
        "fresh_context": True,
        "blind": True,
        "reviewer_read_only": True,
        "reviewer_model": "GPT-5.6-Sol",
        "candidate_diff_digest": DIFF,
        "base_commit": BASE,
        "reviewed_head_commit": HEAD,
        "reviewed_head_tree": TREE,
        "prompt_sha256": prompt_sha256 or hashlib.sha256(b"canonical").hexdigest(),
        "verdict": "APPROVE",
        "blocking_findings": [],
        "reviewed_at": reviewed_at,
    }


def _receipt(
    *,
    schema: str = "recu-revue/2",
    reviewed_at: str = DATE,
    date_heure: str = DATE,
    prompt_sha256: str | None = None,
) -> dict:
    return {
        "schema": schema,
        "mode": "sol_blind",
        "story": "S-sol",
        "dossier": "S-sol",
        "issue": 603,
        "round": 1,
        "base_commit": BASE,
        "head_commit": HEAD,
        "head_tree": TREE,
        "reviewed_head_commit": HEAD,
        "reviewed_head_tree": TREE,
        "candidate_diff_digest": DIFF,
        "diff_digest": DIFF,
        "prompt_sha256": prompt_sha256 or hashlib.sha256(b"canonical").hexdigest(),
        "reviewers_attendus": ["GPT-5.6-Sol"],
        "codeur": ["luna_writer"],
        "resultat": "APPROVE",
        "reviewed_at": reviewed_at,
        "verdict": "APPROVE",
        "reviewer_model": "GPT-5.6-Sol",
        "date_heure": date_heure,
        "fenetre_heures": 24,
        "blocking_findings": [],
    }


def _state() -> dict:
    return {
        "base_commit": BASE,
        "head_commit": HEAD,
        "head_tree": TREE,
        "diff_digest": DIFF,
    }


def _write_review(root: Path, receipt: dict, verdict: dict, prompt: bytes) -> Path:
    directory = root / receipt["dossier"]
    directory.mkdir(parents=True)
    (directory / "SOL-PROMPT.md").write_bytes(prompt)
    (directory / "sol.verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    (directory / "RECU.json").write_text(json.dumps(receipt), encoding="utf-8")
    return directory


def _manifest(tmp_path: Path, name: str = "S-sol") -> Path:
    path = tmp_path / "BINDING.txt"
    path.write_text(name + "\n", encoding="utf-8")
    return path


def test_sol_verifier_rejects_injected_prompt_even_when_hash_receipt_and_verdict_agree(tmp_path):
    prompt = b"injected prompt with attacker-controlled artifact"
    prompt_sha = hashlib.sha256(prompt).hexdigest()
    receipt = _receipt(prompt_sha256=prompt_sha)
    verdict = _verdict(prompt_sha256=prompt_sha)
    directory = tmp_path / "S-sol"
    directory.mkdir()
    (directory / "SOL-PROMPT.md").write_bytes(prompt)

    result = revue.verifier_recu(
        receipt,
        [verdict],
        _state(),
        review_dir=directory,
        runner=_runner,
        now=NOW,
    )

    assert result["result"] != "APPROVE"
    assert "prompt" in result["reason"].lower() or "artefact" in result["reason"].lower()


def test_sol_verifier_rejects_symlink_prompt(tmp_path):
    prompt = b"injected prompt"
    prompt_sha = hashlib.sha256(prompt).hexdigest()
    receipt = _receipt(prompt_sha256=prompt_sha)
    verdict = _verdict(prompt_sha256=prompt_sha)
    directory = tmp_path / "S-sol"
    directory.mkdir()
    target = tmp_path / "outside-prompt"
    target.write_bytes(prompt)
    (directory / "SOL-PROMPT.md").symlink_to(target)

    result = revue.verifier_recu(
        receipt,
        [verdict],
        _state(),
        review_dir=directory,
        runner=_runner,
        now=NOW,
    )

    assert result["result"] != "APPROVE"
    assert "symlink" in result["reason"].lower() or "prompt" in result["reason"].lower()


@pytest.mark.parametrize(
    ("reviewed_at", "date_heure"),
    [
        ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00"),
        ("2026-08-23T12:00:00+00:00", "2026-08-23T12:00:00+00:00"),
    ],
)
def test_current_sol_verifier_rejects_stale_or_future_timestamps(reviewed_at, date_heure, tmp_path):
    prompt = b"canonical"
    prompt_sha = hashlib.sha256(prompt).hexdigest()
    receipt = _receipt(
        reviewed_at=reviewed_at,
        date_heure=date_heure,
        prompt_sha256=prompt_sha,
    )
    verdict = _verdict(reviewed_at=reviewed_at, prompt_sha256=prompt_sha)
    directory = tmp_path / "S-sol"
    directory.mkdir()
    (directory / "SOL-PROMPT.md").write_bytes(prompt)

    result = revue.verifier_recu(
        receipt,
        [verdict],
        _state(),
        review_dir=directory,
        runner=_runner,
        now=NOW,
    )

    assert result["result"] != "APPROVE"
    assert any(
        marker in result["reason"].lower() for marker in ("périm", "timestamp", "futur")
    )


@pytest.mark.parametrize(
    "timestamp",
    ["2000-01-01T00:00:00+00:00", "2026-08-23T12:00:00+00:00"],
)
def test_current_sol_gate_rejects_stale_or_future_receipt(timestamp, tmp_path):
    prompt = CANONICAL_PROMPT
    prompt_sha = CANONICAL_SHA
    receipt = _receipt(
        reviewed_at=timestamp,
        date_heure=timestamp,
        prompt_sha256=prompt_sha,
    )
    verdict = _verdict(
        reviewed_at=timestamp,
        prompt_sha256=prompt_sha,
    )
    root = tmp_path / "reviews"
    _write_review(root, receipt, verdict, prompt)

    ok, report = gate.check(
        _manifest(tmp_path),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=_runner,
        now=NOW,
    )

    assert ok is False
    assert any("aucun reçu" in line or "périm" in line for line in report)


def test_sol_verifier_requires_exact_receipt_schema(tmp_path):
    prompt = b"canonical"
    prompt_sha = hashlib.sha256(prompt).hexdigest()
    receipt = _receipt(schema="recu-revue/1", prompt_sha256=prompt_sha)
    verdict = _verdict(prompt_sha256=prompt_sha)
    directory = tmp_path / "S-sol"
    directory.mkdir()
    (directory / "SOL-PROMPT.md").write_bytes(prompt)

    result = revue.verifier_recu(
        receipt,
        [verdict],
        _state(),
        review_dir=directory,
        runner=_runner,
        now=NOW,
    )

    assert result["result"] == "INVALIDE"
    assert "schema" in result["reason"]


def test_sol_archive_requires_exact_receipt_schema():
    with pytest.raises(ValueError, match="schema"):
        revue._validate_sol_archive_receipt(_receipt(schema="recu-revue/1"), _runner)


@pytest.mark.parametrize(
    "change",
    [
        {"modele": "GPT-5.6 Luna"},
        {"vendor": "anthropic"},
        {"provider_id": "GPT-5.6-Luna-Writer"},
        {"statut": "retire"},
        {"id": "sol_alias"},
    ],
)
def test_sol_verifier_rejects_noncanonical_active_sol_roster(monkeypatch, change):
    roles = [
        {
            "id": "luna_writer",
            "vendor": "openai",
            "provider_id": "GPT-5.6-Luna-Writer",
            "modele": "GPT-5.6 Luna",
            "statut": "actif",
        },
        {
            "id": "sol",
            "vendor": "openai",
            "provider_id": "GPT-5.6-Sol",
            "modele": "GPT-5.6 Sol",
            "statut": "actif",
        },
    ]
    roles[1].update(change)
    monkeypatch.setattr(revue, "_load_roles_yaml", lambda path: roles)

    result = revue.tally_sol_blind(
        [_verdict(prompt_sha256=hashlib.sha256(b"canonical").hexdigest())],
        expected={
            "candidate_diff_digest": DIFF,
            "diff_digest": DIFF,
            "base_commit": BASE,
            "reviewed_head_commit": HEAD,
            "reviewed_head_tree": TREE,
            "prompt_sha256": hashlib.sha256(b"canonical").hexdigest(),
            "reviewed_at": DATE,
        },
        codeurs=["luna_writer"],
    )

    assert result["result"] != "APPROVE"
    assert any(marker in result["reason"].lower() for marker in ("sol", "identit", "roster"))


def test_current_sol_verifier_rejects_negative_window(tmp_path):
    prompt = b"canonical"
    prompt_sha = hashlib.sha256(prompt).hexdigest()
    receipt = _receipt(prompt_sha256=prompt_sha)
    receipt["fenetre_heures"] = True
    verdict = _verdict(prompt_sha256=prompt_sha)
    directory = tmp_path / "S-sol"
    directory.mkdir()
    (directory / "SOL-PROMPT.md").write_bytes(prompt)

    result = revue.verifier_recu(
        receipt,
        [verdict],
        _state(),
        review_dir=directory,
        runner=_runner,
        now=NOW,
    )

    assert result["result"] != "APPROVE"
    assert "fenêtre" in result["reason"].lower() or "window" in result["reason"].lower()
