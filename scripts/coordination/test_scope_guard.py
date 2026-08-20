"""Tests unitaires pour scope_guard.py (correctif ORCH-001-civ, revue Gemini-3.1-Pro).

Le scénario clé (test_check_scope_ignores_other_claims_scope) reproduit exactement
le défaut rapporté en revue aveugle scellée : avec plusieurs claims concurrents actifs,
une PR ne doit être jugée que contre SON PROPRE claim (résolu par branche), jamais
contre les allowed_paths des autres claims actifs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from coordination import scope_guard as sg  # noqa: E402


def _pkg_by_id() -> dict:
    return {
        "ORCH-001": {
            "id": "ORCH-001",
            "allowed_paths": ["AGENTS.md", "coordination/**"],
            "forbidden_paths": ["build/**"],
        },
        "HW-037": {
            "id": "HW-037",
            "allowed_paths": ["src/forgeai/hardware/**"],
            "forbidden_paths": [],
        },
    }


CONCURRENT_CLAIMS = [
    {"package": "ORCH-001", "branch": "br-orch-001"},
    {"package": "HW-037", "branch": "br-hw-037"},
]


# ---------------------------------------------------------------------------
# matches_any
# ---------------------------------------------------------------------------

MATCHES_ANY_CASES = [
    pytest.param("AGENTS.md", ["AGENTS.md"], True, id="exact"),
    pytest.param("coordination/work-packages.json", ["coordination/**"], True, id="glob-double-star"),
    pytest.param("src/other.py", ["coordination/**"], False, id="hors-glob"),
    pytest.param("x.py", [], False, id="liste-vide"),
]


@pytest.mark.parametrize("path, patterns, expected", MATCHES_ANY_CASES)
def test_matches_any(path: str, patterns: list[str], expected: bool) -> None:
    assert sg.matches_any(path, patterns) is expected


# ---------------------------------------------------------------------------
# find_claim_for_branch
# ---------------------------------------------------------------------------
def test_find_claim_for_branch_found() -> None:
    claim = sg.find_claim_for_branch(CONCURRENT_CLAIMS, "br-orch-001")
    assert claim is not None
    assert claim["package"] == "ORCH-001"


def test_find_claim_for_branch_not_found() -> None:
    assert sg.find_claim_for_branch(CONCURRENT_CLAIMS, "branche-inconnue") is None


# ---------------------------------------------------------------------------
# check_scope — matrice de scénarios (le cœur du correctif)
# ---------------------------------------------------------------------------

CHECK_SCOPE_CASES = [
    pytest.param(
        ["coordination/work-packages.json"],
        {"package": "ORCH-001", "branch": "br-orch-001"},
        [],
        id="fichier-legitime-dans-allowed",
    ),
    pytest.param(
        ["src/forgeai/hardware/detect.py"],
        {"package": "ORCH-001", "branch": "br-orch-001"},
        ["HORS SCOPE"],
        id="fichier-hors-allowed-du-propre-claim",
    ),
    pytest.param(
        ["build/artifact.bin"],
        {"package": "ORCH-001", "branch": "br-orch-001"},
        ["INTERDIT"],
        id="fichier-dans-forbidden",
    ),
    pytest.param(
        ["src/forgeai/hardware/detect.py"],
        {"package": "HW-037", "branch": "br-hw-037"},
        [],
        id="claim-different-fichier-legitime-pour-lui",
    ),
]


@pytest.mark.parametrize("changed, claim, expected_substrs", CHECK_SCOPE_CASES)
def test_check_scope_matrix(changed: list[str], claim: dict, expected_substrs: list[str]) -> None:
    errors = sg.check_scope(changed, claim, _pkg_by_id())
    if not expected_substrs:
        assert errors == []
    else:
        assert len(errors) == 1
        assert all(s in errors[0] for s in expected_substrs)


def test_check_scope_ignores_other_claims_scope() -> None:
    """LE test qui reproduit le défaut de la revue : une PR ORCH-001 légitime ne
    doit JAMAIS être jugée contre les allowed_paths du claim HW-037 concurrent."""
    changed = ["coordination/work-packages.json"]
    claim = sg.find_claim_for_branch(CONCURRENT_CLAIMS, "br-orch-001")
    assert claim is not None
    errors = sg.check_scope(changed, claim, _pkg_by_id())
    assert errors == []


def test_check_scope_unknown_package() -> None:
    errors = sg.check_scope(["x.py"], {"package": "GHOST"}, _pkg_by_id())
    assert len(errors) == 1
    assert "package inconnu" in errors[0]


# ---------------------------------------------------------------------------
# main() — bootstrap / skip / fail / pass, via monkeypatch de COORD_DIR
# ---------------------------------------------------------------------------
def _write_coord(tmp_path: Path, claims: list[dict] | None, packages: dict | None) -> Path:
    coord = tmp_path / "coordination"
    coord.mkdir()
    if packages is not None:
        (coord / "work-packages.json").write_text(
            json.dumps({"packages": list(packages.values())}), encoding="utf-8"
        )
    if claims is not None:
        (coord / "active-claims.json").write_text(json.dumps({"claims": claims}), encoding="utf-8")
    return coord


@pytest.fixture(autouse=True)
def _stable_budget_for_main_tests(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Les tests main historiques isolent le contrôle de claims du budget Git réel."""
    if request.node.name.startswith("test_main_"):
        monkeypatch.setattr(
            sg,
            "collect_scope_metrics",
            lambda *_args, **_kwargs: _small_metrics(),
        )


def test_main_skips_when_coordination_files_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    assert sg.main() == 0
    output = capsys.readouterr().out
    assert "PASS — budget quantitatif" in output
    assert "SKIP" in output


def test_main_skips_when_no_active_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_coord(tmp_path, claims=[], packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    assert sg.main() == 0
    output = capsys.readouterr().out
    assert "PASS — budget quantitatif" in output
    assert "aucun claim actif" in output


def test_main_skips_when_no_changed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(sg, "get_changed_files", lambda _base_ref="origin/main", _head_ref="HEAD": [])
    assert sg.main() == 0
    assert "aucun fichier modifié" in capsys.readouterr().out


def test_main_skips_when_branch_has_no_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(
        sg, "get_changed_files", lambda _base_ref="origin/main", _head_ref="HEAD": ["README.md"]
    )
    monkeypatch.setattr(sg, "current_branch", lambda: "branche-hors-coordination")
    assert sg.main() == 0
    assert "aucun claim actif ne correspond" in capsys.readouterr().out


def test_main_passes_for_own_claim_despite_concurrent_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test d'intégration bout-en-bout : 2 claims, la PR respecte SON claim."""
    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(
        sg,
        "get_changed_files",
        lambda _base_ref="origin/main", _head_ref="HEAD": ["coordination/work-packages.json"],
    )
    monkeypatch.setattr(sg, "current_branch", lambda: "br-orch-001")
    assert sg.main() == 0
    assert "PASS" in capsys.readouterr().out


def test_main_fails_on_forbidden_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(
        sg, "get_changed_files", lambda _base_ref="origin/main", _head_ref="HEAD": ["build/artifact.bin"]
    )
    monkeypatch.setattr(sg, "current_branch", lambda: "br-orch-001")
    assert sg.main() == 1
    assert "INTERDIT" in capsys.readouterr().err


def test_get_changed_files_raises_on_git_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def _boom(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "git diff")

    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.raises(subprocess.CalledProcessError):
        sg.get_changed_files()


def test_main_fail_on_git_diff_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import subprocess

    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")

    def _boom(_base_ref: str = "origin/main", _head_ref: str = "HEAD"):
        raise subprocess.CalledProcessError(1, "git diff")

    monkeypatch.setattr(sg, "get_changed_files", _boom)
    assert sg.main() == 1
    assert "git diff impossible" in capsys.readouterr().err


def test_current_branch_prefers_github_head_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_HEAD_REF", "pr-branch-from-actions")
    assert sg.current_branch() == "pr-branch-from-actions"


def test_current_branch_falls_back_to_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    import subprocess

    class _Result:
        stdout = "local-branch\n"

    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: _Result())
    assert sg.current_branch() == "local-branch"


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sg.load(tmp_path / "absent.json")


# ---------------------------------------------------------------------------
# #578 — budget quantitatif de branche + coupe-circuit des rounds de revue
# ---------------------------------------------------------------------------
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


def _runaway_metrics() -> dict[str, int]:
    return {
        "ahead": 24,
        "behind": 50,
        "changed_files": 25,
        "substantive_churn": 11950,
        "max_file_churn": 5007,
        "tests_churn": 5007,
        "story_churn": 4220,
        "generated_churn": 202651,
    }


def test_quantitative_scope_accepts_small_pr() -> None:
    ok, report = sg.evaluate_scope(_small_metrics())
    assert ok is True, report


def test_quantitative_scope_blocks_rc1015_runaway_profile() -> None:
    ok, report = sg.evaluate_scope(_runaway_metrics())
    assert ok is False
    text = "\n".join(report)
    for signal in ("ahead", "behind", "substantive", "fichier", "tests", "story", "généré"):
        assert signal in text


def test_review_rounds_1_and_2_are_automatic() -> None:
    assert sg.review_round_policy(1) == (True, "AUTO")
    assert sg.review_round_policy(2) == (True, "AUTO")


def test_review_round_3_requires_explicit_replan() -> None:
    assert sg.review_round_policy(3, replanned=False)[0] is False
    assert sg.review_round_policy(3, replanned=True) == (True, "REPLAN")


def test_review_round_4_plus_are_always_rejected() -> None:
    assert sg.review_round_policy(4, replanned=True)[0] is False
    assert sg.review_round_policy(120, replanned=True)[0] is False


def test_collect_scope_metrics_parses_numstat_and_separates_generated() -> None:
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

    metrics = sg.collect_scope_metrics("origin/main", "HEAD", runner=runner)
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


def test_collect_scope_metrics_refuse_les_diff_binaire_non_mesurables() -> None:
    def runner(command: list[str]) -> str:
        if command[:3] == ["git", "rev-list", "--count"]:
            return "0\n"
        if command[:3] == ["git", "diff", "--numstat"]:
            return "-\t-\tassets/blob.bin\n"
        raise AssertionError(command)

    with pytest.raises(ValueError, match="binaire"):
        sg.collect_scope_metrics("origin/main", "HEAD", runner=runner)


def test_quantitative_guard_does_not_depend_on_archived_claim() -> None:
    ok, _ = sg.evaluate_scope(_small_metrics())
    assert ok is True
    assert sg.find_claim_for_branch([], "feature/sans-claim-json") is None


def test_get_changed_files_respecte_le_head_ref_demande(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(sg, "_run_git", lambda command: commands.append(command) or "a.py\n")

    assert sg.get_changed_files("origin/main", "refs/pull/597/head") == ["a.py"]
    assert commands == [["git", "diff", "--name-only", "origin/main...refs/pull/597/head"]]


def test_main_budget_blocks_before_legacy_claim_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(
        sg,
        "collect_scope_metrics",
        lambda *_args, **_kwargs: _runaway_metrics(),
    )
    assert sg.main([]) == 1
    captured = capsys.readouterr()
    assert "budget quantitatif" in captured.err
    assert "behind" in captured.err


def test_main_round4_stops_before_legacy_claim_logic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    assert sg.main(["--round", "4", "--replanned"]) == 1
    assert "round" in capsys.readouterr().err.lower()


def test_main_round3_with_replan_can_continue_to_legacy_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    assert sg.main(["--round", "3", "--replanned"]) == 0
    output = capsys.readouterr().out
    assert "REPLAN" in output
    assert "SKIP" in output


def test_main_metric_failure_is_fail_closed_before_legacy_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import subprocess

    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")

    def _boom(*_args, **_kwargs):
        raise subprocess.CalledProcessError(128, "git rev-list")

    monkeypatch.setattr(sg, "collect_scope_metrics", _boom)
    assert sg.main([]) == 1
    assert "mesure Git impossible" in capsys.readouterr().err
