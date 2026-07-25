"""Tests unitaires pour simulate_orchestration.py (couverture ORCH-001)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from coordination import simulate_orchestration as so  # noqa: E402


def _packages() -> dict:
    return {
        "ORCH-001": {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": [], "status": "READY"},
        "UI-039": {"id": "UI-039", "exclusive_lane": "web-ui", "dependencies": ["ORCH-001"], "status": "READY_AFTER"},
        "UI-040": {"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": ["UI-039"], "status": "READY_AFTER"},
        "LAB-X": {"id": "LAB-X", "exclusive_lane": "lab", "dependencies": [], "status": "BLOCKED_LAB"},
    }


def test_build_completed() -> None:
    assert so.build_completed(["A", "B"]) == {"A", "B"}


def test_try_claim_unknown_package() -> None:
    ok, reason = so.try_claim("GHOST", _packages(), {}, set(), set())
    assert not ok
    assert "inconnu" in reason


def test_try_claim_double_claim() -> None:
    ok, reason = so.try_claim("ORCH-001", _packages(), {}, {"ORCH-001"}, set())
    assert not ok
    assert "Double claim" in reason


def test_try_claim_lane_collision() -> None:
    ok, reason = so.try_claim(
        "UI-040", _packages(), {"web-ui": "UI-039"}, {"UI-039"}, {"ORCH-001", "UI-039"}
    )
    assert not ok
    assert "Lane" in reason


def test_try_claim_missing_dependency() -> None:
    ok, reason = so.try_claim("UI-039", _packages(), {}, set(), set())
    assert not ok
    assert "Dépendance" in reason


def test_try_claim_stale_base() -> None:
    ok, reason = so.try_claim(
        "ORCH-001", _packages(), {}, set(), set(),
        origin_main="abc123", branch_base="deadbeef",
    )
    assert not ok
    assert "périmée" in reason


def test_try_claim_blocked_lab() -> None:
    ok, reason = so.try_claim("LAB-X", _packages(), {}, set(), set())
    assert not ok
    assert "BLOCKED_LAB" in reason


def test_try_claim_success() -> None:
    ok, reason = so.try_claim("ORCH-001", _packages(), {}, set(), set())
    assert ok
    assert reason == "OK"


def test_try_claim_success_after_dependency_completed() -> None:
    ok, _ = so.try_claim("UI-039", _packages(), {}, set(), {"ORCH-001"})
    assert ok


def test_run_simulations_all_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coord = tmp_path / "coordination"
    coord.mkdir()
    wp = {
        "packages": [
            {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": [], "status": "READY"},
            {"id": "UI-039", "exclusive_lane": "web-ui", "dependencies": ["ORCH-001"], "status": "READY_AFTER"},
            {"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": ["UI-039"], "status": "READY_AFTER"},
            {"id": "CAP-033A", "exclusive_lane": "capability-docs", "dependencies": ["HW-037"], "status": "READY_AFTER"},
            {"id": "OPS-031E", "exclusive_lane": "web-ui", "dependencies": ["OPS-031C", "UI-040"], "status": "READY_AFTER"},
            {"id": "DOC-032", "exclusive_lane": "documentation", "dependencies": ["CAP-033A", "OPS-031E", "UI-040"], "status": "READY_AFTER"},
        ]
    }
    (coord / "work-packages.json").write_text(json.dumps(wp), encoding="utf-8")
    monkeypatch.setattr(so, "COORD_DIR", coord)

    results = so.run_simulations()
    assert len(results) == 10
    for label, ok, _detail in results:
        assert ok, f"Simulation échouée: {label}"


def test_main_returns_zero_on_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    coord = tmp_path / "coordination"
    coord.mkdir()
    wp = {
        "packages": [
            {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": [], "status": "READY"},
            {"id": "UI-039", "exclusive_lane": "web-ui", "dependencies": ["ORCH-001"], "status": "READY_AFTER"},
            {"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": ["UI-039"], "status": "READY_AFTER"},
            {"id": "CAP-033A", "exclusive_lane": "capability-docs", "dependencies": ["HW-037"], "status": "READY_AFTER"},
            {"id": "OPS-031E", "exclusive_lane": "web-ui", "dependencies": ["OPS-031C", "UI-040"], "status": "READY_AFTER"},
            {"id": "DOC-032", "exclusive_lane": "documentation", "dependencies": ["CAP-033A", "OPS-031E", "UI-040"], "status": "READY_AFTER"},
        ]
    }
    (coord / "work-packages.json").write_text(json.dumps(wp), encoding="utf-8")
    monkeypatch.setattr(so, "COORD_DIR", coord)

    assert so.main() == 0
    out = capsys.readouterr().out
    assert "10/10 PASS" in out


def test_main_returns_one_when_a_simulation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Un work-packages.json incomplet (dépendances manquantes) fait échouer certaines
    simulations qui attendaient un succès, donc main() doit retourner 1."""
    coord = tmp_path / "coordination"
    coord.mkdir()
    wp = {"packages": [{"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": [], "status": "READY"}]}
    (coord / "work-packages.json").write_text(json.dumps(wp), encoding="utf-8")
    monkeypatch.setattr(so, "COORD_DIR", coord)

    assert so.main() == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.err
    assert "[FAIL]" in captured.out


def test_main_handles_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> list:
        raise RuntimeError("boom")

    monkeypatch.setattr(so, "run_simulations", _boom)
    assert so.main() == 1
