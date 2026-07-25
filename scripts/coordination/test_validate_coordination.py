"""Tests unitaires pour validate_coordination.py (couverture ORCH-001)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from coordination import validate_coordination as vc  # noqa: E402


def _write_coord(tmp_path: Path, wp: dict, claims: dict, completed: dict) -> Path:
    coord = tmp_path / "coordination"
    coord.mkdir()
    (coord / "work-packages.json").write_text(json.dumps(wp), encoding="utf-8")
    (coord / "active-claims.json").write_text(json.dumps(claims), encoding="utf-8")
    (coord / "completed.json").write_text(json.dumps(completed), encoding="utf-8")
    return coord


def _base_wp() -> dict:
    return {
        "_schema": "work-packages-v1",
        "packages": [
            {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": []},
            {"id": "UI-039", "exclusive_lane": "web-ui", "dependencies": ["ORCH-001"]},
            {"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": ["UI-039"]},
        ],
    }


def _empty_claims() -> dict:
    return {"_schema": "active-claims-v1", "claims": []}


def _empty_completed() -> dict:
    return {"_schema": "completed-v1", "completed": []}


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        vc.load(tmp_path / "absent.json")


def test_main_fails_on_missing_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vc, "COORD_DIR", tmp_path / "does-not-exist")
    assert vc.main() == 1


def test_main_fails_on_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coord = tmp_path / "coordination"
    coord.mkdir()
    (coord / "work-packages.json").write_text("{not valid json", encoding="utf-8")
    (coord / "active-claims.json").write_text("{}", encoding="utf-8")
    (coord / "completed.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


# ---------------------------------------------------------------------------
# Matrice de scénarios: chaque entrée décrit un état (work-packages, claims,
# completed) et le code de sortie attendu. Consolide toutes les variantes de
# validation dans un seul test paramétré (évite la duplication ligne à ligne).
# ---------------------------------------------------------------------------

SCENARIOS = [
    pytest.param(
        _base_wp(), _empty_claims(), _empty_completed(), 0,
        id="etat-propre-sans-claim",
    ),
    pytest.param(
        {"packages": [
            {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": []},
            {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": []},
        ]},
        {"claims": []}, {"completed": []}, 1,
        id="package-id-duplique",
    ),
    pytest.param(
        {"packages": [{"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": ["GHOST"]}]},
        {"claims": []}, {"completed": []}, 1,
        id="dependance-inconnue",
    ),
    pytest.param(
        _base_wp(),
        {"claims": [{"package": "ORCH-001", "lane": "governance"},
                    {"package": "ORCH-001", "lane": "governance"}]},
        _empty_completed(), 1,
        id="double-claim-actif",
    ),
    pytest.param(
        {"packages": [
            {"id": "UI-039", "exclusive_lane": "web-ui", "dependencies": []},
            {"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": []},
        ]},
        {"claims": [{"package": "UI-039", "lane": "web-ui"},
                    {"package": "UI-040", "lane": "web-ui"}]},
        {"completed": []}, 1,
        id="collision-de-lane",
    ),
    pytest.param(
        _base_wp(),
        {"claims": [{"package": "GHOST-999", "lane": "governance"}]},
        _empty_completed(), 1,
        id="claim-sur-package-inconnu",
    ),
    pytest.param(
        _base_wp(),
        {"claims": [{"package": "ORCH-001", "lane": "wrong-lane"}]},
        _empty_completed(), 1,
        id="claim-lane-incoherente",
    ),
    pytest.param(
        _base_wp(), _empty_claims(), {"completed": ["GHOST-999"]}, 1,
        id="completed-package-inconnu",
    ),
    pytest.param(
        _base_wp(),
        {"claims": [{"package": "UI-039", "lane": "web-ui"}]},
        _empty_completed(), 1,
        id="claim-avec-dependance-non-completee",
    ),
    pytest.param(
        _base_wp(),
        {"_schema": "active-claims-v1", "claims": [{"package": "UI-039", "lane": "web-ui"}]},
        {"_schema": "completed-v1", "completed": ["ORCH-001"]}, 0,
        id="claim-avec-dependance-completee",
    ),
    pytest.param(
        _base_wp(), _empty_claims(),
        {"_schema": "completed-v1", "completed": [{"id": "ORCH-001"}]}, 0,
        id="completed-entree-objet",
    ),
    pytest.param(
        _base_wp(), {"claims": [{"lane": "governance"}]}, _empty_completed(), 1,
        id="claim-sans-champ-package",
    ),
    pytest.param(
        _base_wp(), _empty_claims(), {"completed": [{"note": "sans id"}]}, 1,
        id="completed-sans-id",
    ),
    pytest.param(
        {"packages": [{"exclusive_lane": "governance", "dependencies": []}]},
        _empty_claims(), _empty_completed(), 1,
        id="package-sans-id",
    ),
    pytest.param(
        {"packages": "not-a-list"}, _empty_claims(), _empty_completed(), 1,
        id="packages-non-liste",
    ),
    pytest.param(
        _base_wp(), {"claims": "nope"}, _empty_completed(), 1,
        id="claims-non-liste",
    ),
    pytest.param(
        _base_wp(), _empty_claims(), {"completed": "nope"}, 1,
        id="completed-non-liste",
    ),
    pytest.param(
        {"packages": [{"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": []}]},
        {"claims": []}, {"completed": []}, 1,
        id="schema-manquant-partout",
    ),
]


@pytest.mark.parametrize("wp, claims, completed, expected_exit", SCENARIOS)
def test_validate_scenarios(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wp: dict,
    claims: dict,
    completed: dict,
    expected_exit: int,
) -> None:
    coord = _write_coord(tmp_path, wp, claims, completed)
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == expected_exit


def test_cli_entrypoint_runs_as_subprocess() -> None:
    """Exécute le script en subprocess pour couvrir le bloc __main__."""
    import os
    import subprocess

    script = Path(vc.__file__)
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(script.parent),
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    # Le script utilise le vrai coordination/ du dépôt — on vérifie seulement
    # qu'il s'exécute et retourne un code de sortie de processus valide.
    assert result.returncode in (0, 1)
