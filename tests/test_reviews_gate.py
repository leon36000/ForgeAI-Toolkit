"""Gate `reviews-sealed` (déviation D9) — tests de la logique de blocage.

Vérifie que le gate BLOQUE si une revue liante n'est pas APPROVE 3/3, et PASSE sinon.
Réutilise le dépouillement déterministe (scripts/revue.py) via scripts/reviews_gate.py.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reviews_gate", REPO / "scripts" / "reviews_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SHA = "a" * 64


def _verdict(vendor, verdict="APPROVE"):
    return {"vendor": vendor, "prompt_sha256": SHA, "verdict": verdict, "objections": []}


def _make_review(root: Path, name: str, verdicts: list[dict]) -> None:
    d = root / name
    d.mkdir(parents=True)
    for v in verdicts:
        (d / f"{v['vendor']}.verdict.json").write_text(json.dumps(v), encoding="utf-8")


def _manifest(tmp_path: Path, lines: list[str]) -> Path:
    m = tmp_path / "BINDING.txt"
    m.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return m


def test_gate_ok_si_toutes_approve(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-1", [_verdict("deepseek"), _verdict("gemini"), _verdict("longcat")])
    ok, report = gate.check(_manifest(tmp_path, ["S-1"]), root)
    assert ok is True and any("OK" in r for r in report)


def test_gate_bloque_si_reject(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-2", [_verdict("deepseek"), _verdict("gemini", "REJECT"),
                               _verdict("longcat")])
    ok, report = gate.check(_manifest(tmp_path, ["S-2"]), root)
    assert ok is False and any("ECHEC" in r and "REJECT" in r for r in report)


def test_gate_bloque_si_moins_de_3_vendors(tmp_path):
    root = tmp_path / "reviews"
    # deepseek + gemini seulement → tally INVALIDE (< 3 vendors)
    _make_review(root, "S-3", [_verdict("deepseek"), _verdict("gemini")])
    ok, report = gate.check(_manifest(tmp_path, ["S-3"]), root)
    assert ok is False


def test_gate_bloque_si_dossier_absent(tmp_path):
    root = tmp_path / "reviews"
    root.mkdir()
    ok, report = gate.check(_manifest(tmp_path, ["S-INEXISTANT"]), root)
    assert ok is False and any("aucun verdict" in r for r in report)


def test_gate_ignore_commentaires_et_lignes_vides(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-4", [_verdict("deepseek"), _verdict("gemini"), _verdict("qwen37max")])
    ok, _ = gate.check(_manifest(tmp_path, ["# commentaire", "", "S-4", "  # autre"]), root)
    assert ok is True


def test_manifeste_reel_du_depot_est_approve():
    # le manifeste versionné doit toujours pointer des revues APPROVE (sinon main est cassé)
    ok, report = gate.check(REPO / "reviews" / "BINDING.txt", REPO / "reviews")
    assert ok is True, report
