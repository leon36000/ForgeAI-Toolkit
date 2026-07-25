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


def test_main_skips_when_coordination_files_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    assert sg.main() == 0
    assert "SKIP" in capsys.readouterr().out


def test_main_skips_when_no_active_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_coord(tmp_path, claims=[], packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    assert sg.main() == 0
    assert "aucun claim actif" in capsys.readouterr().out


def test_main_skips_when_no_changed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(sg, "get_changed_files", lambda base_ref="origin/main": [])
    assert sg.main() == 0
    assert "aucun fichier modifié" in capsys.readouterr().out


def test_main_skips_when_branch_has_no_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(sg, "get_changed_files", lambda base_ref="origin/main": ["README.md"])
    monkeypatch.setattr(sg, "current_branch", lambda: "branche-hors-coordination")
    assert sg.main() == 0
    assert "aucun claim actif ne correspond" in capsys.readouterr().out


def test_main_passes_for_own_claim_despite_concurrent_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test d'intégration bout-en-bout du correctif via main(): 2 claims actifs, la PR
    ne touche que des fichiers dans le périmètre de SON claim (ORCH-001)."""
    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(
        sg, "get_changed_files", lambda base_ref="origin/main": ["coordination/work-packages.json"]
    )
    monkeypatch.setattr(sg, "current_branch", lambda: "br-orch-001")
    assert sg.main() == 0
    assert "PASS" in capsys.readouterr().out


def test_main_fails_on_forbidden_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_coord(tmp_path, claims=CONCURRENT_CLAIMS, packages=_pkg_by_id())
    monkeypatch.setattr(sg, "COORD_DIR", tmp_path / "coordination")
    monkeypatch.setattr(sg, "get_changed_files", lambda base_ref="origin/main": ["build/artifact.bin"])
    monkeypatch.setattr(sg, "current_branch", lambda: "br-orch-001")
    assert sg.main() == 1
    assert "INTERDIT" in capsys.readouterr().err


def test_get_changed_files_raises_on_git_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def _boom(*args, **kwargs):
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

    def _boom(base_ref: str = "origin/main"):
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

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
    assert sg.current_branch() == "local-branch"


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sg.load(tmp_path / "absent.json")
