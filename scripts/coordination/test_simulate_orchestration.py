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


def _full_wp_packages() -> list[dict]:
    """Jeu de packages couvrant toutes les branches de run_simulations()."""
    return [
        {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": [], "status": "READY"},
        {"id": "UI-039", "exclusive_lane": "web-ui", "dependencies": ["ORCH-001"], "status": "READY_AFTER"},
        {"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": ["UI-039"], "status": "READY_AFTER"},
        {"id": "CAP-033A", "exclusive_lane": "capability-docs", "dependencies": ["HW-037"], "status": "READY_AFTER"},
        {"id": "OPS-031E", "exclusive_lane": "web-ui", "dependencies": ["OPS-031C", "UI-040"], "status": "READY_AFTER"},
        {"id": "DOC-032", "exclusive_lane": "documentation", "dependencies": ["CAP-033A", "OPS-031E", "UI-040"], "status": "READY_AFTER"},
    ]


def _write_wp(tmp_path: Path, packages: list[dict]) -> Path:
    coord = tmp_path / "coordination"
    coord.mkdir()
    (coord / "work-packages.json").write_text(json.dumps({"packages": packages}), encoding="utf-8")
    return coord


def test_build_completed() -> None:
    assert so.build_completed(["A", "B"]) == {"A", "B"}


# ---------------------------------------------------------------------------
# try_claim(): une matrice paramétrée couvre chaque branche de rejet/acceptation
# sans dupliquer la structure d'appel entre les tests.
# ---------------------------------------------------------------------------

TRY_CLAIM_CASES = [
    pytest.param("GHOST", {}, set(), set(), {}, False, "inconnu", id="package-inconnu"),
    pytest.param("ORCH-001", {}, {"ORCH-001"}, set(), {}, False, "Double claim", id="double-claim"),
    pytest.param(
        "UI-040", {"web-ui": "UI-039"}, {"UI-039"}, {"ORCH-001", "UI-039"}, {}, False, "Lane",
        id="collision-lane",
    ),
    pytest.param("UI-039", {}, set(), set(), {}, False, "Dépendance", id="dependance-manquante"),
    pytest.param(
        "ORCH-001", {}, set(), set(),
        {"origin_main": "abc123", "branch_base": "deadbeef"}, False, "périmée",
        id="base-perimee",
    ),
    pytest.param("LAB-X", {}, set(), set(), {}, False, "BLOCKED_LAB", id="package-bloque-lab"),
    pytest.param("ORCH-001", {}, set(), set(), {}, True, "OK", id="claim-reussi-sans-deps"),
    pytest.param("UI-039", {}, set(), {"ORCH-001"}, {}, True, None, id="claim-reussi-deps-completees"),
]


@pytest.mark.parametrize(
    "pkg_id, active_claims, active_pkgs, completed, extra_kwargs, expected_ok, expected_substr",
    TRY_CLAIM_CASES,
)
def test_try_claim_matrix(
    pkg_id: str,
    active_claims: dict,
    active_pkgs: set,
    completed: set,
    extra_kwargs: dict,
    expected_ok: bool,
    expected_substr: str | None,
) -> None:
    ok, reason = so.try_claim(pkg_id, _packages(), active_claims, active_pkgs, completed, **extra_kwargs)
    assert ok is expected_ok
    if expected_substr is not None:
        assert expected_substr in reason


def test_run_simulations_all_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coord = _write_wp(tmp_path, _full_wp_packages())
    monkeypatch.setattr(so, "COORD_DIR", coord)

    results = so.run_simulations()
    assert len(results) == 10
    for label, ok, _detail in results:
        assert ok, f"Simulation échouée: {label}"


def test_main_returns_zero_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    coord = _write_wp(tmp_path, _full_wp_packages())
    monkeypatch.setattr(so, "COORD_DIR", coord)

    assert so.main() == 0
    assert "10/10 PASS" in capsys.readouterr().out


def test_main_returns_one_when_a_simulation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Un work-packages.json incomplet (dépendances manquantes) fait échouer certaines
    simulations qui attendaient un succès, donc main() doit retourner 1."""
    coord = _write_wp(tmp_path, _full_wp_packages()[:1])  # ne garde que ORCH-001
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
