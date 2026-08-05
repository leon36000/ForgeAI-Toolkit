"""Régressions FIX-AUDIT-1b : garde fail-open exercé dans le processus couvert."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "reviews_gate.py"
MESSAGE_SUCCES = "GATE OK : toutes les revues liantes sont APPROVE 3/3."


def _charger_gate():
    spec = importlib.util.spec_from_file_location("reviews_gate", GATE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_defaut_fail_open_manifeste_vide_check_echoue_en_processus(
    tmp_path: Path,
) -> None:
    gate = _charger_gate()
    manifest = tmp_path / "BINDING.txt"
    manifest.write_text("", encoding="utf-8")
    reviews_root = tmp_path / "reviews"
    reviews_root.mkdir()

    ok, report = gate.check(manifest, reviews_root)

    assert ok is False
    assert any("vide ou absent" in ligne for ligne in report)


def test_defaut_fail_open_manifeste_absent_check_echoue_en_processus(
    tmp_path: Path,
) -> None:
    gate = _charger_gate()
    manifest = tmp_path / "BINDING.txt"
    reviews_root = tmp_path / "reviews"
    reviews_root.mkdir()

    ok, report = gate.check(manifest, reviews_root)

    assert ok is False
    assert any("vide ou absent" in ligne for ligne in report)


def test_defaut_fail_open_aucun_depouillement_ne_rapporte_pas_de_succes(
    tmp_path: Path,
) -> None:
    gate = _charger_gate()
    manifest = tmp_path / "BINDING.txt"
    manifest.write_text("", encoding="utf-8")
    reviews_root = tmp_path / "reviews"
    reviews_root.mkdir()

    ok, report = gate.check(manifest, reviews_root)

    assert ok is False
    assert all(MESSAGE_SUCCES not in ligne for ligne in report)
    assert all(not ligne.startswith("OK    ") for ligne in report)


def test_cas_nominal_trois_approbations_vendors_distincts_reussit(
    tmp_path: Path,
) -> None:
    gate = _charger_gate()
    reviews_root = tmp_path / "reviews"
    dossier_revue = reviews_root / "S-1"
    dossier_revue.mkdir(parents=True)
    manifest = tmp_path / "BINDING.txt"
    manifest.write_text("S-1\n", encoding="utf-8")
    prompt_sha256 = hashlib.sha256(b"prompt de revue neutre").hexdigest()
    date_heure = datetime.now(timezone.utc).isoformat()

    for index, reviewer_model in enumerate(
        ("DeepSeek-V4-Pro", "Gemini-3.1-Pro", "Qwen3.7-Max"),
        start=1,
    ):
        verdict = {
            "verdict": "APPROVE",
            "objections": [],
            "date_heure": date_heure,
            "prompt_sha256": prompt_sha256,
            "reviewer_model": reviewer_model,
        }
        (dossier_revue / f"reviewer-{index}.verdict.json").write_text(
            json.dumps(verdict),
            encoding="utf-8",
        )

    ok, report = gate.check(manifest, reviews_root)

    assert ok is True
    assert any("APPROVE 3/3 APPROVE" in ligne for ligne in report)
