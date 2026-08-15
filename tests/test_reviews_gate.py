"""Gate `reviews-sealed` (déviation D9) — tests de la logique de blocage.

Vérifie que le gate BLOQUE si une revue liante n'est pas APPROVE 3/3, et PASSE sinon.
Réutilise le dépouillement déterministe (scripts/revue.py) via scripts/reviews_gate.py.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reviews_gate", REPO / "scripts" / "reviews_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SHA = "a" * 64
DATE = "2025-01-01T12:00:00+00:00"


def _verdict(vendor, verdict="APPROVE"):
    return {
        "vendor": vendor,
        "prompt_sha256": SHA,
        "verdict": verdict,
        "objections": [],
        "date_heure": DATE,
    }


def _make_review(root: Path, name: str, verdicts: list[dict]) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    for verdict in verdicts:
        (directory / f"{verdict['vendor']}.verdict.json").write_text(
            json.dumps(verdict), encoding="utf-8"
        )
    return directory


def _manifest(tmp_path: Path, lines: list[str]) -> Path:
    manifest = tmp_path / "BINDING.txt"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def _runner(command):
    if command[:3] == ["git", "merge-base", "--is-ancestor"]:
        return ""
    if command[:2] == ["git", "merge-base"]:
        return "b" * 40
    if command[:2] == ["git", "rev-parse"]:
        return ("d" * 40 if command[-1].endswith("^{tree}") else "c" * 40)
    if command[:3] == ["git", "diff", "--raw"]:
        return ""
    raise AssertionError(command)


def _receipt():
    return {
        "schema": "recu-revue/1",
        "dossier": "S",
        "issue": 434,
        "round": 1,
        "base_commit": "b" * 40,
        "head_commit": "c" * 40,
        "head_tree": "d" * 40,
        "diff_digest": __import__("hashlib").sha256(b"").hexdigest(),
        "prompt_sha256": SHA,
        "reviewers_attendus": ["deepseek", "gemini", "longcat"],
        "codeur": ["fable"],
        "resultat": "APPROVE",
        "date_heure": DATE,
        "fenetre_heures": 24,
    }


def test_gate_ok_si_toutes_approve(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-1", [_verdict("deepseek"), _verdict("gemini"), _verdict("longcat")])
    ok, report = gate.check(_manifest(tmp_path, ["S-1"]), root)
    assert ok is True and any("OK" in line for line in report)


def test_gate_bloque_si_reject(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-2", [_verdict("deepseek"), _verdict("gemini", "REJECT"), _verdict("longcat")])
    ok, report = gate.check(_manifest(tmp_path, ["S-2"]), root)
    assert ok is False and any("ECHEC" in line and "REJECT" in line for line in report)


def test_gate_bloque_si_moins_de_3_vendors(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-3", [_verdict("deepseek"), _verdict("gemini")])
    ok, report = gate.check(_manifest(tmp_path, ["S-3"]), root)
    assert ok is False and any("INVALIDE" in line for line in report)


def test_gate_bloque_si_dossier_absent(tmp_path):
    root = tmp_path / "reviews"
    root.mkdir()
    ok, report = gate.check(_manifest(tmp_path, ["S-INEXISTANT"]), root)
    assert ok is False and any("aucun verdict" in line for line in report)


def test_gate_ignore_commentaires_et_lignes_vides(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-4", [_verdict("deepseek"), _verdict("gemini"), _verdict("qwen37max")])
    ok, _ = gate.check(_manifest(tmp_path, ["# commentaire", "", "S-4", "  # autre"]), root)
    assert ok is True


def test_gate_traversee_chemin_rejetee(tmp_path):
    root = tmp_path / "reviews"
    root.mkdir()
    ok, report = gate.check(_manifest(tmp_path, ["../ailleurs"]), root)
    assert ok is False and any("chemin hors de reviews/" in line for line in report)


def test_mode_pr_echoue_sans_recu_couvrant(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S", [_verdict("deepseek"), _verdict("gemini"), _verdict("longcat")])
    ok, report = gate.check(
        _manifest(tmp_path, ["S"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
    )
    assert ok is False and any("aucun reçu ne couvre le changement courant" in line for line in report)


def test_mode_pr_reussit_avec_recu_valide(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini"), _verdict("longcat")]
    )
    (directory / "RECU.json").write_text(json.dumps(_receipt()), encoding="utf-8")
    ok, report = gate.check(
        _manifest(tmp_path, ["S"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
    )
    assert ok is True and any("reçu couvre le changement courant" in line for line in report)


def test_mode_archive_rejette_recu_commit_non_fusionne(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini"), _verdict("longcat")]
    )
    (directory / "RECU.json").write_text(json.dumps(_receipt()), encoding="utf-8")

    def non_ancestor(command):
        if command[:3] == ["git", "merge-base", "--is-ancestor"]:
            raise subprocess.CalledProcessError(1, command)
        return _runner(command)

    ok, report = gate.check(_manifest(tmp_path, ["S"]), root, mode="archive", runner=non_ancestor)
    assert ok is False and any("jamais fusionné" in line for line in report)


def test_mode_archive_recu_malforme_echoue_proprement(tmp_path):
    # Régression revue scellée RC1-004-PR497-v3 (objection mineure DeepSeek-V4-Pro) : un
    # RECU.json valide en JSON mais pas un objet (ex. une liste) levait TypeError non
    # attrapée sur receipt["head_commit"] — doit produire un échec contrôlé, jamais planter.
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini"), _verdict("longcat")]
    )
    (directory / "RECU.json").write_text("[]", encoding="utf-8")

    ok, report = gate.check(_manifest(tmp_path, ["S"]), root, mode="archive", runner=_runner)

    assert ok is False and any("reçu archive illisible" in line for line in report)


def test_defaut_sans_drapeau_comportement_inchange(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S", [_verdict("deepseek"), _verdict("gemini"), _verdict("longcat")])
    ok, report = gate.check(_manifest(tmp_path, ["S"]), root)
    assert ok is True and any("APPROVE" in line for line in report)


def test_manifeste_reel_du_depot_est_approve():
    ok, report = gate.check(REPO / "reviews" / "BINDING.txt", REPO / "reviews")
    assert ok is True, report
