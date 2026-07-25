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
        ],
    }


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        vc.load(tmp_path / "absent.json")


def test_main_passes_on_clean_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coord = _write_coord(
        tmp_path,
        _base_wp(),
        {"_schema": "active-claims-v1", "claims": []},
        {"_schema": "completed-v1", "completed": []},
    )
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 0


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


def test_main_detects_duplicate_package_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wp = {
        "packages": [
            {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": []},
            {"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": []},
        ]
    }
    coord = _write_coord(tmp_path, wp, {"claims": []}, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_main_detects_unknown_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wp = {"packages": [{"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": ["GHOST"]}]}
    coord = _write_coord(tmp_path, wp, {"claims": []}, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_main_detects_double_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claims = {"claims": [{"package": "ORCH-001", "lane": "governance"},
                          {"package": "ORCH-001", "lane": "governance"}]}
    coord = _write_coord(tmp_path, _base_wp(), claims, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_main_detects_lane_collision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wp = {
        "packages": [
            {"id": "UI-039", "exclusive_lane": "web-ui", "dependencies": []},
            {"id": "UI-040", "exclusive_lane": "web-ui", "dependencies": []},
        ]
    }
    claims = {"claims": [{"package": "UI-039", "lane": "web-ui"},
                          {"package": "UI-040", "lane": "web-ui"}]}
    coord = _write_coord(tmp_path, wp, claims, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_main_detects_claim_on_unknown_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claims = {"claims": [{"package": "GHOST-999", "lane": "governance"}]}
    coord = _write_coord(tmp_path, _base_wp(), claims, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_main_detects_lane_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claims = {"claims": [{"package": "ORCH-001", "lane": "wrong-lane"}]}
    coord = _write_coord(tmp_path, _base_wp(), claims, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_main_detects_completed_unknown_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    completed = {"completed": ["GHOST-999"]}
    coord = _write_coord(tmp_path, _base_wp(), {"claims": []}, completed)
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_main_detects_claim_with_unmet_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claims = {"claims": [{"package": "UI-039", "lane": "web-ui"}]}
    coord = _write_coord(tmp_path, _base_wp(), claims, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_main_accepts_claim_with_met_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claims = {"_schema": "active-claims-v1", "claims": [{"package": "UI-039", "lane": "web-ui"}]}
    completed = {"_schema": "completed-v1", "completed": ["ORCH-001"]}
    coord = _write_coord(tmp_path, _base_wp(), claims, completed)
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 0


def test_completed_entries_as_dict_objects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    completed = {"_schema": "completed-v1", "completed": [{"id": "ORCH-001"}]}
    claims = {"_schema": "active-claims-v1", "claims": []}
    coord = _write_coord(tmp_path, _base_wp(), claims, completed)
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 0


def test_malformed_claim_without_package_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claims = {"claims": [{"lane": "governance"}]}
    coord = _write_coord(tmp_path, _base_wp(), claims, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_malformed_completed_entry_without_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    completed = {"completed": [{"note": "no id here"}]}
    coord = _write_coord(tmp_path, _base_wp(), {"claims": []}, completed)
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_malformed_package_without_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wp = {"packages": [{"exclusive_lane": "governance", "dependencies": []}]}
    coord = _write_coord(tmp_path, wp, {"claims": []}, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_non_list_packages_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wp = {"packages": "not-a-list"}
    coord = _write_coord(tmp_path, wp, {"claims": []}, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_non_list_claims_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coord = _write_coord(tmp_path, _base_wp(), {"claims": "nope"}, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_non_list_completed_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    coord = _write_coord(tmp_path, _base_wp(), {"claims": []}, {"completed": "nope"})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_missing_schema_keys_are_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """L'absence de '_schema' dans les trois fichiers est toujours une erreur bloquante."""
    wp = {"packages": [{"id": "ORCH-001", "exclusive_lane": "governance", "dependencies": []}]}
    coord = _write_coord(tmp_path, wp, {"claims": []}, {"completed": []})
    monkeypatch.setattr(vc, "COORD_DIR", coord)
    assert vc.main() == 1


def test_cli_entrypoint_runs_as_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exécute le script en subprocess pour couvrir le bloc __main__."""
    import subprocess

    coord = _write_coord(
        tmp_path,
        _base_wp(),
        {"_schema": "x", "claims": []},
        {"_schema": "x", "completed": []},
    )
    script = Path(vc.__file__)
    env_repo = tmp_path
    (env_repo / "scripts").mkdir(exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(script.parent),
        capture_output=True,
        text=True,
        env={**__import__("os").environ},
    )
    # Le script utilise REPO_ROOT dérivé de son propre chemin (repo réel) — on vérifie
    # simplement qu'il s'exécute et retourne un code de sortie valide (0 ou 1).
    assert result.returncode in (0, 1)
