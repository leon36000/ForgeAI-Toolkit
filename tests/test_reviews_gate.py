"""Gate `reviews-sealed` (déviation D9) — tests de la logique de blocage.

Vérifie que le gate BLOQUE si une revue liante n'est pas APPROVE 3/3, et PASSE sinon.
Réutilise le dépouillement déterministe (scripts/revue.py) via scripts/reviews_gate.py.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reviews_gate", REPO / "scripts" / "reviews_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SOL_PROMPT_BYTES = b"stored Sol prompt\n"
SHA = hashlib.sha256(SOL_PROMPT_BYTES).hexdigest()
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
    if command[:3] == ["git", "diff", "--raw"]:
        return ""
    if command[:3] == ["git", "rev-parse", "--verify"]:
        ref = command[-1]
        if ref.endswith("^{tree}"):
            return "d" * 40
        return ref[: -len("^{commit}")] if ref.endswith("^{commit}") else ref
    if command[:2] == ["git", "rev-parse"]:
        return ("d" * 40 if command[-1].endswith("^{tree}") else "c" * 40)
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
        "reviewers_attendus": ["deepseek", "gemini_flash", "mimo"],
        "codeur": ["fable"],
        "resultat": "APPROVE",
        "date_heure": DATE,
        "fenetre_heures": 24,
    }


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


def test_mode_pr_reussit_avec_recu_valide(tmp_path):
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
    assert ok is True and any("reçu couvre le changement courant" in line for line in report)


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
    assert ok is False and any("différent de la PR" in line for line in report)


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
    assert ok is False and any("état git courant inaccessible" in line for line in report)


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
    (courante / "RECU.json").write_text(json.dumps(_receipt()), encoding="utf-8")

    ok, report = gate.check(
        _manifest(tmp_path, ["S-ancienne", "S-courante"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
    )

    assert ok is True, report
    assert any("reçu couvre le changement courant" in line for line in report)
    assert not any("ECHEC S-ancienne" in line for line in report)


def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
    root = tmp_path / "reviews"
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
                "reviewed_head_commit": "3" * 40,
                "reviewed_head_tree": "4" * 40,
                "prompt_sha256": SHA,
                "verdict": "APPROVE",
                "blocking_findings": [],
                "reviewed_at": "2026-08-22T12:00:00+00:00",
            }
        ],
    )
    (historical / "SOL-PROMPT.md").write_bytes(SOL_PROMPT_BYTES)
    (historical / "RECU.json").write_text(
        json.dumps(
            {
                "schema": "recu-revue/2",
                "mode": "sol_blind",
                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                "diff_digest": hashlib.sha256(b"").hexdigest(),
                "base_commit": "a" * 40,
                "head_commit": "c" * 40,
                "head_tree": "d" * 40,
                "reviewed_head_commit": "3" * 40,
                "reviewed_head_tree": "4" * 40,
                "prompt_sha256": SHA,
                "dossier": "S-ancienne-sol",
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
                "prompt_sha256": SHA,
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
                "mode": "sol_blind",
                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                "reviewed_head_commit": "c" * 40,
                "reviewed_head_tree": "d" * 40,
                "reviewed_at": "2026-08-22T12:00:00+00:00",
                "verdict": "APPROVE",
                "reviewer_model": "GPT-5.6-Sol",
                "codeur": ["luna_writer"],
                "reviewers_attendus": ["GPT-5.6-Sol"],
            }
        ),
        encoding="utf-8",
    )

    ok, report = gate.check(
        _manifest(tmp_path, [historical.name, current.name]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        expected_issue=434,
        runner=_runner,
    )

    assert ok is True, report
    assert any("info  S-ancienne-sol" in line for line in report)
    assert any("reçu couvre le changement courant" in line for line in report)


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
                "base_commit": "b" * 40,
                "reviewed_head_commit": "c" * 40,
                "reviewed_head_tree": "d" * 40,
                "prompt_sha256": SHA,
                "verdict": "APPROVE",
                "blocking_findings": [],
                "reviewed_at": "2026-08-22T12:00:00+00:00",
            }
        ],
    )
    (directory / "SOL-PROMPT.md").write_bytes(SOL_PROMPT_BYTES)
    (directory / "RECU.json").write_text(
        json.dumps(
            {
                "schema": "recu-revue/2",
                "mode": "sol_blind",
                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                "diff_digest": hashlib.sha256(b"").hexdigest(),
                "base_commit": "b" * 40,
                "head_commit": "c" * 40,
                "head_tree": "d" * 40,
                "reviewed_head_commit": "c" * 40,
                "reviewed_head_tree": "d" * 40,
                "prompt_sha256": SHA,
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
        ),
        encoding="utf-8",
    )

    ok, report = gate.check(
        _manifest(tmp_path, ["S-sol"]),
        root,
        exiger_recu_courant=True,
        base_ref="origin/main",
        runner=_runner,
    )

    assert ok is True, report
    assert not any("< 3" in line for line in report)
    assert any("APPROVE" in line for line in report)


def test_manifeste_reel_du_depot_est_approve():
    ok, report = gate.check(
        REPO / "evidence" / "reviews" / "BINDING.txt", REPO / "evidence" / "reviews"
    )
    assert ok is True, report
