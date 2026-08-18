"""Régressions #578 : coupe-circuit anti branche/revue runaway."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "reviews_gate", REPO / "scripts" / "reviews_gate.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _small_metrics() -> dict[str, int]:
    return {
        "ahead": 3,
        "behind": 2,
        "changed_files": 12,
        "substantive_churn": 850,
        "max_file_churn": 280,
        "tests_churn": 340,
        "story_churn": 120,
        "generated_churn": 900,
    }


def test_scope_guard_accepte_une_petite_pr():
    ok, report = gate.evaluate_scope(_small_metrics())
    assert ok is True, report


def test_scope_guard_bloque_le_profil_runaway_rc1_015():
    metrics = {
        "ahead": 24,
        "behind": 50,
        "changed_files": 25,
        "substantive_churn": 11950,
        "max_file_churn": 5007,
        "tests_churn": 5007,
        "story_churn": 4220,
        "generated_churn": 202651,
    }
    ok, report = gate.evaluate_scope(metrics)
    assert ok is False
    texte = "\n".join(report)
    for signal in ("ahead", "behind", "substantive", "fichier", "tests", "story", "généré"):
        assert signal in texte


def test_rounds_1_et_2_sont_automatiques():
    assert gate.review_round_policy(1) == (True, "AUTO")
    assert gate.review_round_policy(2) == (True, "AUTO")


def test_round_3_exige_un_replan_explicite():
    assert gate.review_round_policy(3, replanned=False)[0] is False
    assert gate.review_round_policy(3, replanned=True) == (True, "REPLAN")


def test_round_4_et_plus_sont_toujours_refuses():
    assert gate.review_round_policy(4, replanned=True)[0] is False
    assert gate.review_round_policy(120, replanned=True)[0] is False


def test_collecte_scope_parse_numstat_et_separe_genere():
    def runner(command: list[str]) -> str:
        if command[:3] == ["git", "rev-list", "--count"]:
            return "4\n" if command[-1] == "origin/main..HEAD" else "6\n"
        if command[:3] == ["git", "diff", "--numstat"]:
            return (
                "20\t10\tsrc/forgeai/a.py\n"
                "50\t5\ttests/test_a.py\n"
                "30\t0\tstories/S.md\n"
                "500\t400\tgovernance/path-classification.json\n"
                "2\t1\tevidence/reviews/S/x.verdict.json\n"
            )
        raise AssertionError(command)

    metrics = gate.collect_scope_metrics("origin/main", "HEAD", runner=runner)
    assert metrics == {
        "ahead": 4,
        "behind": 6,
        "changed_files": 5,
        "substantive_churn": 115,
        "max_file_churn": 55,
        "tests_churn": 55,
        "story_churn": 30,
        "generated_churn": 903,
    }
