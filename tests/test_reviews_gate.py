"""Gate `reviews-sealed` (déviation D9) — tests de la logique de blocage.

Vérifie que le gate BLOQUE si une revue liante n'est pas APPROVE 3/3, et PASSE sinon.
Réutilise le dépouillement déterministe (scripts/revue.py) via scripts/reviews_gate.py.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reviews_gate", REPO / "scripts" / "reviews_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SOL_PROMPT_BYTES = b""
SOL_SHA = ""
SHA = hashlib.sha256(b"historical multi-vendor prompt\n").hexdigest()
DATE = "2025-01-01T12:00:00+00:00"
SOL_NOW = datetime.fromisoformat("2026-08-22T12:00:00+00:00")


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
    if command[0] == "git" and "diff" in command and "--raw" in command:
        return ""
    if command[:8] == [
        "git",
        "-c",
        "core.attributesFile=",
        "-c",
        "diff.orderFile=scripts/coordination/__init__.py",
        "-c",
        "diff.suppressBlankEmpty=false",
        "diff",
    ]:
        return ""
    if command[:3] == ["git", "rev-parse", "--verify"]:
        ref = command[-1]
        if ref.endswith("^{tree}"):
            return "d" * 40
        return ref[: -len("^{commit}")] if ref.endswith("^{commit}") else ref
    if command[:2] == ["git", "rev-parse"]:
        return ("d" * 40 if command[-1].endswith("^{tree}") else "c" * 40)
    if command[:2] == ["git", "diff"]:
        return ""
    if command[:2] == ["git", "show"]:
        if command[-1].endswith(gate._load_revue()._SOL_CANONICAL_STORY_ID):
            return "# Story\n\n## Critères d’acceptation\n\n- [x] contrat\n\n## Limites\n"
        return gate._load_revue().TEMPLATE.read_text(encoding="utf-8")
    raise AssertionError(command)


SOL_PROMPT_BYTES, SOL_SHA = gate._load_revue()._canonical_sol_prompt(
    gate._load_revue()._SOL_CANONICAL_STORY_ID, "b" * 40, "c" * 40, runner=_runner
)
SOL_TEMPLATE_SHA = hashlib.sha256(
    gate._load_revue().TEMPLATE.read_bytes()
).hexdigest()
SOL_SDD_DIGEST = hashlib.sha256(b"").hexdigest()
SOL_MISSION_DIGEST = hashlib.sha256(b"").hexdigest()


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
        "sdd_diff_digest": SOL_SDD_DIGEST,
        "mission_diff_digest": SOL_MISSION_DIGEST,
        "prompt_sha256": SHA,
        "template_sha256": SOL_TEMPLATE_SHA,
        "reviewers_attendus": ["deepseek", "gemini_flash", "mimo"],
        "codeur": ["fable"],
        "resultat": "APPROVE",
        "date_heure": DATE,
        "fenetre_heures": 24,
    }


def _make_sol_blind_gate_review(
    root: Path,
    *,
    include_receipt_blocking_findings: bool = True,
    receipt_blocking_findings: list[dict] | None = None,
) -> Path:
    directory = _make_review(
        root,
        "S-sol",
        [
            {
                "vendor": "sol",
                "fresh_context": True,
                "blind": True,
                "reviewer_read_only": True,
                "reviewer_model": "GPT-5.6-Sol",
                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                "diff_digest": hashlib.sha256(b"").hexdigest(),
                "sdd_diff_digest": SOL_SDD_DIGEST,
                "mission_diff_digest": SOL_MISSION_DIGEST,
                "base_commit": "b" * 40,
                "reviewed_head_commit": "c" * 40,
                "reviewed_head_tree": "d" * 40,
                "prompt_sha256": SOL_SHA,
                "template_sha256": SOL_TEMPLATE_SHA,
                "verdict": "APPROVE",
                "blocking_findings": [],
                "reviewed_at": "2026-08-22T12:00:00+00:00",
            }
        ],
    )
    (directory / "SOL-PROMPT.md").write_bytes(SOL_PROMPT_BYTES)
    receipt = {
        "schema": "recu-revue/2",
        "mode": "sol_blind",
        "story": gate._load_revue()._SOL_CANONICAL_STORY_ID,
        "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
        "diff_digest": hashlib.sha256(b"").hexdigest(),
        "sdd_diff_digest": SOL_SDD_DIGEST,
        "mission_diff_digest": SOL_MISSION_DIGEST,
        "base_commit": "b" * 40,
        "head_commit": "c" * 40,
        "head_tree": "d" * 40,
        "reviewed_head_commit": "c" * 40,
        "reviewed_head_tree": "d" * 40,
        "prompt_sha256": SOL_SHA,
        "template_sha256": SOL_TEMPLATE_SHA,
        "dossier": "S-sol",
        "issue": 603,
        "round": 1,
        "reviewers_attendus": ["GPT-5.6-Sol"],
        "codeur": ["luna_writer"],
        "resultat": "APPROVE",
        "reviewed_at": "2026-08-22T12:00:00+00:00",
        "verdict": "APPROVE",
        "reviewer_model": "GPT-5.6-Sol",
        "date_heure": "2026-08-22T12:00:00+00:00",
        "fenetre_heures": 24,
    }
    if include_receipt_blocking_findings:
        receipt["blocking_findings"] = (
            [] if receipt_blocking_findings is None else receipt_blocking_findings
        )
    (directory / "RECU.json").write_text(json.dumps(receipt), encoding="utf-8")
    return directory


def test_gate_ok_si_toutes_approve(tmp_path):
    # RC1-010 (#440) lot 5d : reviews/ est intégralement migré vers evidence/reviews/ — le
    # repli bi-racine posé au lot 5a (une entrée liante pouvait vivre sous l'une OU l'autre
    # racine pendant la transition) est retiré, `reviews_root` désigne désormais une racine
    # unique et sans ambiguïté. `tmp_path / "reviews"` ci-dessous est un nom de dossier de test
    # arbitraire (transmis explicitement en paramètre) — sans rapport avec la racine par défaut
    # du CLI, qui pointe maintenant vers evidence/reviews/.
    root = tmp_path / "reviews"
    _make_review(root, "S-1", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")])
    ok, report = gate.check(_manifest(tmp_path, ["S-1"]), root)
    assert ok is True and any("OK" in line for line in report)


def test_gate_bloque_si_reject(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-2", [_verdict("deepseek"), _verdict("gemini_flash", "REJECT"), _verdict("mimo")])
    ok, report = gate.check(_manifest(tmp_path, ["S-2"]), root)
    assert ok is False and any("ECHEC" in line and "REJECT" in line for line in report)


def test_gate_bloque_si_moins_de_3_vendors(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-3", [_verdict("deepseek"), _verdict("gemini_flash")])
    ok, report = gate.check(_manifest(tmp_path, ["S-3"]), root)
    assert ok is False and any("INVALIDE" in line for line in report)


def test_gate_bloque_si_dossier_absent(tmp_path):
    root = tmp_path / "reviews"
    root.mkdir()
    ok, report = gate.check(_manifest(tmp_path, ["S-INEXISTANT"]), root)
    assert ok is False and any("aucun verdict" in line for line in report)


def test_gate_ignore_commentaires_et_lignes_vides(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S-4", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("qwen_37")])
    ok, _ = gate.check(_manifest(tmp_path, ["# commentaire", "", "S-4", "  # autre"]), root)
    assert ok is True


def test_gate_traversee_chemin_rejetee(tmp_path):
    root = tmp_path / "reviews"
    root.mkdir()
    ok, report = gate.check(_manifest(tmp_path, ["../ailleurs"]), root)
    assert ok is False and any("chemin hors de la racine de revues" in line for line in report)


def test_mode_pr_echoue_sans_recu_couvrant(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")])
    ok, report = gate.check(
        _manifest(tmp_path, ["S"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
    )
    assert ok is False and any("aucun reçu ne couvre le changement courant" in line for line in report)


def test_mode_pr_rejette_recu_multi_vendor_courant(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
    )
    (directory / "RECU.json").write_text(json.dumps(_receipt()), encoding="utf-8")
    ok, report = gate.check(
        _manifest(tmp_path, ["S"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
    )
    assert ok is False
    assert any("mode de politique requis" in line for line in report)


def test_mode_pr_rejette_un_recu_dune_autre_issue(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
    )
    (directory / "RECU.json").write_text(json.dumps(_receipt()), encoding="utf-8")
    ok, report = gate.check(
        _manifest(tmp_path, ["S"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=435,
        runner=_runner,
    )
    assert ok is False and any("mode de politique requis" in line for line in report)


def test_mode_archive_rejette_recu_commit_non_fusionne(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
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
        root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
    )
    (directory / "RECU.json").write_text("[]", encoding="utf-8")

    ok, report = gate.check(_manifest(tmp_path, ["S"]), root, mode="archive", runner=_runner)

    assert ok is False and any("reçu archive illisible" in line for line in report)


def test_mode_archive_recu_sol_commit_absent_echoue_proprement(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    missing_commit = "f" * 40
    receipt["head_commit"] = missing_commit
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    def missing_commit_runner(command):
        if command[:2] == ["git", "rev-parse"] and missing_commit in command[-1]:
            raise subprocess.CalledProcessError(128, command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        mode="archive",
        runner=missing_commit_runner,
    )

    assert ok is False
    assert any("reçu archive illisible" in line for line in report)


def test_mode_archive_accepte_recu_ancetre_valide(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
    )
    (directory / "RECU.json").write_text(json.dumps(_receipt()), encoding="utf-8")

    ok, report = gate.check(_manifest(tmp_path, ["S"]), root, mode="archive", runner=_runner)

    assert ok is True and any("APPROVE" in line for line in report)


def test_check_exiger_recu_sans_base_ref_echoue(tmp_path):
    root = tmp_path / "reviews"
    root.mkdir()
    ok, report = gate.check(_manifest(tmp_path, []), root, exiger_recu_courant=True)
    assert ok is False and any("base-ref" in line for line in report)


def test_check_mode_inconnu_echoue(tmp_path):
    root = tmp_path / "reviews"
    root.mkdir()
    ok, report = gate.check(_manifest(tmp_path, []), root, mode="bogus")
    assert ok is False and any("mode inconnu" in line for line in report)


def test_check_etat_git_inaccessible_echoue(tmp_path):
    root = tmp_path / "reviews"
    root.mkdir()

    def runner_qui_echoue(command):
        raise subprocess.CalledProcessError(1, command)

    ok, report = gate.check(
        _manifest(tmp_path, []),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=runner_qui_echoue,
    )
    # No receipt means there is no reason to resolve the PR Git state. The gate still fails,
    # but for the actionable missing-binding reason; Sol claims are validated locally before
    # any lazy Git resolution.
    assert ok is False and any("manifeste" in line for line in report)


def test_gate_verdict_illisible_echoue_proprement(tmp_path):
    root = tmp_path / "reviews"
    directory = root / "S"
    directory.mkdir(parents=True)
    (directory / "deepseek.verdict.json").write_text("{pas du json valide", encoding="utf-8")

    ok, report = gate.check(_manifest(tmp_path, ["S"]), root)

    assert ok is False and any("verdict illisible" in line for line in report)


def test_mode_pr_recu_illisible_echoue_proprement(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
    )
    (directory / "RECU.json").write_text("{pas du json valide", encoding="utf-8")

    ok, report = gate.check(
        _manifest(tmp_path, ["S"]), root, exiger_recu_courant=True, base_ref="origin/main", runner=_runner
    )

    assert ok is False and any("reçu illisible" in line for line in report)


def test_mode_pr_ignore_recu_historique_non_couvrant(tmp_path):
    # Régression #439/PR500 (dogfooding réel de #434 sur la PR suivante) : une entrée liante
    # DÉJÀ MERGÉE (ex. RC1-004-PR497-v5) porte un RECU.json valide pour SA PROPRE PR d'origine,
    # dont le base_commit ne correspondra plus jamais à l'état git courant d'une PR ultérieure
    # (origin/main a avancé). Ce n'est PAS une anomalie — c'est l'état normal et permanent de
    # toute entrée historique. Le mode PR ne doit échouer que si AUCUN reçu ne couvre le
    # changement courant, jamais parce qu'un reçu HISTORIQUE ne le couvre plus.
    root = tmp_path / "reviews"
    ancienne = _make_review(
        root, "S-ancienne", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
    )
    recu_ancien = _receipt()
    recu_ancien["base_commit"] = "e" * 40  # ne correspond plus au merge-base courant ("b"*40)
    (ancienne / "RECU.json").write_text(json.dumps(recu_ancien), encoding="utf-8")

    courante = _make_review(
        root, "S-courante", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
    )
    recu_courante_historique = _receipt()
    recu_courante_historique["base_commit"] = "e" * 40
    (courante / "RECU.json").write_text(
        json.dumps(recu_courante_historique), encoding="utf-8"
    )
    current_sol = _make_sol_blind_gate_review(root)

    ok, report = gate.check(
        _manifest(tmp_path, ["S-ancienne", "S-courante", current_sol.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=_runner,
        now=SOL_NOW,
    )

    assert ok is True, report
    assert any("reçu couvre le changement courant" in line for line in report)
    assert not any("ECHEC S-ancienne" in line for line in report)


def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
    root = tmp_path / "reviews"
    historical_prompt = SOL_PROMPT_BYTES.replace(b"b" * 40, b"a" * 40).replace(
        b"c" * 40, b"3" * 40
    )
    historical_prompt_sha = hashlib.sha256(historical_prompt).hexdigest()
    historical = _make_review(
        root,
        "S-ancienne-sol",
        [
            {
                "vendor": "sol",
                "fresh_context": True,
                "blind": True,
                "reviewer_read_only": True,
                "reviewer_model": "GPT-5.6-Sol",
                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                "diff_digest": hashlib.sha256(b"").hexdigest(),
                "base_commit": "a" * 40,
                "sdd_diff_digest": SOL_SDD_DIGEST,
                "mission_diff_digest": SOL_MISSION_DIGEST,
                "reviewed_head_commit": "3" * 40,
                "reviewed_head_tree": "d" * 40,
                "prompt_sha256": historical_prompt_sha,
                "template_sha256": SOL_TEMPLATE_SHA,
                "verdict": "APPROVE",
                "blocking_findings": [],
                "reviewed_at": "2000-01-01T00:00:00+00:00",
            }
        ],
    )
    (historical / "SOL-PROMPT.md").write_bytes(historical_prompt)
    (historical / "RECU.json").write_text(
        json.dumps(
            {
                "schema": "recu-revue/2",
                "mode": "sol_blind",
                "story": gate._load_revue()._SOL_CANONICAL_STORY_ID,
                "dossier": "S-ancienne-sol",
                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                "diff_digest": hashlib.sha256(b"").hexdigest(),
                "base_commit": "a" * 40,
                "sdd_diff_digest": SOL_SDD_DIGEST,
                "mission_diff_digest": SOL_MISSION_DIGEST,
                "head_commit": "c" * 40,
                "head_tree": "d" * 40,
                "reviewed_head_commit": "3" * 40,
                "reviewed_head_tree": "d" * 40,
                "prompt_sha256": historical_prompt_sha,
                "template_sha256": SOL_TEMPLATE_SHA,
                "issue": 603,
                "round": 1,
                "reviewers_attendus": ["GPT-5.6-Sol"],
                "codeur": ["luna_writer"],
                "resultat": "APPROVE",
                "reviewed_at": "2000-01-01T00:00:00+00:00",
                "verdict": "APPROVE",
                "blocking_findings": [],
                "reviewer_model": "GPT-5.6-Sol",
                "date_heure": "2000-01-01T00:00:00+00:00",
                "fenetre_heures": 24,
            }
        ),
        encoding="utf-8",
    )

    current = _make_review(
        root,
        "S-courante-sol",
        [
            {
                "vendor": "sol",
                "fresh_context": True,
                "blind": True,
                "reviewer_read_only": True,
                "reviewer_model": "GPT-5.6-Sol",
                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                "diff_digest": hashlib.sha256(b"").hexdigest(),
                "base_commit": "b" * 40,
                "reviewed_head_commit": "c" * 40,
                "reviewed_head_tree": "d" * 40,
                "prompt_sha256": SOL_SHA,
                "sdd_diff_digest": SOL_SDD_DIGEST,
                "mission_diff_digest": SOL_MISSION_DIGEST,
                "template_sha256": SOL_TEMPLATE_SHA,
                "verdict": "APPROVE",
                "blocking_findings": [],
                "reviewed_at": "2026-08-22T12:00:00+00:00",
            }
        ],
    )
    (current / "SOL-PROMPT.md").write_bytes(SOL_PROMPT_BYTES)
    (current / "RECU.json").write_text(
        json.dumps(
            {
                **_receipt(),
                    "schema": "recu-revue/2",
                    "mode": "sol_blind",
                    "story": gate._load_revue()._SOL_CANONICAL_STORY_ID,
                    "dossier": "S-courante-sol",
                    "issue": 603,
                "prompt_sha256": SOL_SHA,
                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                "reviewed_head_commit": "c" * 40,
                "reviewed_head_tree": "d" * 40,
                "reviewed_at": "2026-08-22T12:00:00+00:00",
                "verdict": "APPROVE",
                "blocking_findings": [],
                "reviewer_model": "GPT-5.6-Sol",
                "codeur": ["luna_writer"],
                "reviewers_attendus": ["GPT-5.6-Sol"],
                "date_heure": "2026-08-22T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    def historical_runner(command):
        if command[:2] == ["git", "merge-base"] and "a" * 40 in command:
            return "a" * 40
        if command[:2] == ["git", "rev-parse"] and "3" * 40 in command:
            return "d" * 40 if command[-1].endswith("^{tree}") else "3" * 40
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [historical.name, current.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=historical_runner,
        now=SOL_NOW,
    )

    assert ok is True, report
    assert any("info  S-ancienne-sol" in line for line in report)
    assert any("reçu couvre le changement courant" in line for line in report)


def test_mode_pr_historical_sol_tampering_is_blocking_even_with_current_receipt(tmp_path):
    root = tmp_path / "reviews"
    current = _make_sol_blind_gate_review(root)
    current.rename(root / "S-current-sol")
    current_receipt_path = root / "S-current-sol" / "RECU.json"
    current_receipt = json.loads(current_receipt_path.read_text(encoding="utf-8"))
    current_receipt["dossier"] = "S-current-sol"
    current_receipt_path.write_text(json.dumps(current_receipt), encoding="utf-8")

    historical = _make_sol_blind_gate_review(root)
    historical_receipt_path = historical / "RECU.json"
    historical_receipt = json.loads(historical_receipt_path.read_text(encoding="utf-8"))
    historical_receipt["dossier"] = historical.name
    historical_receipt["base_commit"] = "a" * 40
    historical_receipt["sdd_diff_digest"] = "0" * 64
    historical_receipt_path.write_text(json.dumps(historical_receipt), encoding="utf-8")

    ok, report = gate.check(
        _manifest(tmp_path, [historical.name, "S-current-sol"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("intrinsèquement invalide" in line for line in report)
    assert any("S-current-sol : reçu couvre" in line for line in report)


def test_mode_pr_recu_invalide_rapporte_raison(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_review(
        root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
    )
    recu = _receipt()
    recu["base_commit"] = "x" * 40
    (directory / "RECU.json").write_text(json.dumps(recu), encoding="utf-8")

    ok, report = gate.check(
        _manifest(tmp_path, ["S"]), root, exiger_recu_courant=True, base_ref="origin/main", runner=_runner
    )

    assert ok is False and any("reçu invalide" in line for line in report)


def test_main_argv_reussit_avec_manifeste_valide(monkeypatch, tmp_path, capsys):
    root = tmp_path / "reviews"
    _make_review(root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")])
    manifest = _manifest(tmp_path, ["S"])

    rc = gate.main(["--manifest", str(manifest), "--reviews-root", str(root)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "GATE OK" in out


def test_main_argv_echoue_avec_manifeste_invalide(monkeypatch, tmp_path, capsys):
    root = tmp_path / "reviews"
    root.mkdir()
    manifest = _manifest(tmp_path, ["S-INEXISTANT"])

    rc = gate.main(["--manifest", str(manifest), "--reviews-root", str(root)])

    assert rc == 1
    out = capsys.readouterr().out
    assert "GATE ECHOUÉ" in out


def test_defaut_sans_drapeau_comportement_inchange(tmp_path):
    root = tmp_path / "reviews"
    _make_review(root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")])
    ok, report = gate.check(_manifest(tmp_path, ["S"]), root)
    assert ok is True and any("APPROVE" in line for line in report)


def test_gate_dispatch_sol_blind_receipt_avec_un_seul_verdict(tmp_path):
    root = tmp_path / "reviews"
    _make_sol_blind_gate_review(root)

    ok, report = gate.check(
        _manifest(tmp_path, ["S-sol"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
        now=SOL_NOW,
    )

    assert ok is True, report
    assert not any("< 3" in line for line in report)
    assert any("APPROVE" in line for line in report)


def test_gate_sol_blind_sans_drapeau_reste_tally_only(tmp_path, monkeypatch):
    root = tmp_path / "reviews"
    _make_sol_blind_gate_review(root)
    revue = gate._load_revue()

    def _git_should_not_run(*args, **kwargs):
        raise AssertionError("le mode legacy ne doit pas relire les objets Git Sol")

    monkeypatch.setattr(revue, "_sol_expected_from_git", _git_should_not_run)
    monkeypatch.setattr(gate, "_load_revue", lambda: revue)

    ok, report = gate.check(_manifest(tmp_path, ["S-sol"]), root)

    assert ok is True, report
    assert any("Sol APPROVE" in line for line in report)


def test_gate_sol_blind_defaut_rejette_recu_incomplet(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("schema")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    ok, report = gate.check(_manifest(tmp_path, ["S-sol"]), root)

    assert ok is False
    assert any("schema" in line for line in report)


def test_gate_sol_blind_defaut_rejette_preuve_perimee(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["reviewed_at"] = "2000-01-01T00:00:00+00:00"
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["reviewed_at"] = verdict["reviewed_at"]
    receipt["date_heure"] = "2020-01-01T00:00:00+00:00"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    ok, report = gate.check(_manifest(tmp_path, ["S-sol"]), root)

    assert ok is False
    assert any("périmée" in line for line in report)


def test_mode_archive_rejette_incoherence_prompt_avant_objets_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["base_commit"] = "f" * 40
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["base_commit"] = "f" * 40
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, ["S-sol"]), root, mode="archive", runner=recording_runner
    )

    assert ok is False
    assert any("métadonnées du prompt" in line for line in report)
    assert not any(command[:3] == ["git", "rev-parse", "--verify"] for command in commands)


def test_mode_archive_rejette_date_future_avant_objets_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    # One minute is enough: the archive seal has no clock-skew grace period.
    receipt["date_heure"] = "2026-08-22T12:01:00+00:00"
    receipt["reviewed_at"] = receipt["date_heure"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["reviewed_at"] = receipt["reviewed_at"]
    verdict["date_heure"] = receipt["date_heure"]
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        mode="archive",
        runner=recording_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("date_heure du reçu futur" in line for line in report)
    assert not any(command[:3] == ["git", "rev-parse", "--verify"] for command in commands)


def test_mode_pr_rejette_incoherence_verdict_avant_acces_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["base_commit"] = "f" * 40
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=recording_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("base_commit du verdict différent" in line for line in report)
    assert not any(command[:2] == ["git", "merge-base"] for command in commands)


def test_mode_pr_rejette_schema_prompt_contradictoire_avant_acces_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    prompt_path = directory / "SOL-PROMPT.md"
    prompt = prompt_path.read_bytes()
    marker = "conforme à ce\nschéma :\n".encode("utf-8")
    before, separator, after = prompt.partition(marker)
    assert separator
    schema_line, newline, tail = after.partition(b"\n")
    schema = json.loads(schema_line.decode("utf-8"))
    schema["base_commit"] = "f" * 40
    prompt_path.write_bytes(
        before
        + separator
        + json.dumps(schema, ensure_ascii=False, sort_keys=True).encode("utf-8")
        + newline
        + tail
    )
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["prompt_sha256"] = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["prompt_sha256"] = receipt["prompt_sha256"]
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=recording_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("schéma Sol" in line for line in report)
    assert not any(command[:2] == ["git", "merge-base"] for command in commands)


def test_mode_pr_rejette_champ_schema_prompt_absent_avant_acces_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    prompt_path = directory / "SOL-PROMPT.md"
    prompt = prompt_path.read_bytes()
    marker = "conforme à ce\nschéma :\n".encode("utf-8")
    before, separator, after = prompt.partition(marker)
    assert separator
    schema_line, newline, tail = after.partition(b"\n")
    schema = json.loads(schema_line.decode("utf-8"))
    schema.pop("verdict")
    prompt_path.write_bytes(
        before
        + separator
        + json.dumps(schema, ensure_ascii=False, sort_keys=True).encode("utf-8")
        + newline
        + tail
    )
    prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["prompt_sha256"] = prompt_sha
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["prompt_sha256"] = prompt_sha
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=recording_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("verdict différent des métadonnées du schéma" in line for line in report)
    assert not any(command[:2] == ["git", "merge-base"] for command in commands)


def test_mode_pr_rejette_verdict_post_scellement_avant_acces_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["date_heure"] = "2026-08-22T12:15:00+00:00"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["date_heure"] = "2026-08-22T12:30:00+00:00"
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=recording_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("postérieure à date_heure" in line for line in report)
    assert not any(command[:2] == ["git", "merge-base"] for command in commands)


def test_mode_pr_rejette_identite_sol_noncanonique_avant_acces_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["reviewer_model"] = "Not-Sol"
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["reviewer_model"] = "Not-Sol"
    receipt["reviewers_attendus"] = ["Not-Sol"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=recording_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("non canonique" in line for line in report)
    assert not any(command[:2] == ["git", "merge-base"] for command in commands)


def test_mode_pr_rejette_contexte_sol_non_frais_avant_acces_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    verdict_path = next(directory.glob("*.verdict.json"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict["fresh_context"] = False
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=recording_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("fresh_context" in line for line in report)
    assert not any(command[:2] == ["git", "merge-base"] for command in commands)


def test_mode_pr_rejette_recu_sol_incomplet_sans_acces_git(tmp_path):
    root = tmp_path / "reviews"
    directory = _make_sol_blind_gate_review(root)
    receipt_path = directory / "RECU.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("schema")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    commands = []

    def recording_runner(command):
        commands.append(command)
        return _runner(command)

    ok, report = gate.check(
        _manifest(tmp_path, [directory.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=603,
        runner=recording_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("schema" in line for line in report)
    assert not any(command[:2] == ["git", "merge-base"] for command in commands)


def test_gate_dispatch_sol_blind_receipt_requires_blocking_findings(tmp_path):
    root = tmp_path / "reviews"
    _make_sol_blind_gate_review(root, include_receipt_blocking_findings=False)

    ok, report = gate.check(
        _manifest(tmp_path, ["S-sol"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("blocking_findings" in line for line in report)


def test_gate_dispatch_sol_blind_receipt_rejects_non_empty_blocking_findings(tmp_path):
    root = tmp_path / "reviews"
    _make_sol_blind_gate_review(
        root,
        receipt_blocking_findings=[{"severity": "critical", "description": "unsafe"}],
    )

    ok, report = gate.check(
        _manifest(tmp_path, ["S-sol"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
        now=SOL_NOW,
    )

    assert ok is False
    assert any("blocking_findings" in line for line in report)


def test_manifeste_reel_du_depot_est_approve():
    ok, report = gate.check(
        REPO / "evidence" / "reviews" / "BINDING.txt", REPO / "evidence" / "reviews"
    )
    assert ok is True, report
