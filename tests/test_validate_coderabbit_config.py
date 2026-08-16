from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "governance"
    / "validate_coderabbit_config.py"
)
_spec = importlib.util.spec_from_file_location("validate_coderabbit_config", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
vcc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vcc)

REPO = Path(__file__).resolve().parents[1]


def _init_mini_repo_git(root: Path) -> None:
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Test Runner"],
        check=True,
        capture_output=True,
    )


def test_repo_reel_valide() -> None:
    assert vcc.erreurs(REPO) == []


def test_chemin_mort_detecte(tmp_path: Path) -> None:
    (tmp_path / ".coderabbit.yaml").write_text(
        "reviews:\n  path_filters:\n    - \"!archive/**\"\n",
        encoding="utf-8",
    )

    errs = vcc.erreurs(tmp_path)

    assert len(errs) >= 1
    assert any("chemin mort" in err and "archive" in err for err in errs)


def test_exclusion_hors_allowlist_detectee(tmp_path: Path) -> None:
    _init_mini_repo_git(tmp_path)
    canon_dir = tmp_path / "CANON"
    canon_dir.mkdir(parents=True, exist_ok=True)
    (canon_dir / "fichier.md").write_text("# Contenu\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)

    (tmp_path / ".coderabbit.yaml").write_text(
        "reviews:\n  path_filters:\n    - \"!CANON/**\"\n",
        encoding="utf-8",
    )

    errs = vcc.erreurs(tmp_path)

    assert any("non inventoriée" in err and "CANON" in err for err in errs)
    assert not any("chemin mort" in err for err in errs)


def test_config_conforme_est_valide(tmp_path: Path) -> None:
    _init_mini_repo_git(tmp_path)
    registres_dir = tmp_path / "evidence" / "registres"
    registres_dir.mkdir(parents=True, exist_ok=True)
    (registres_dir / "mission.jsonl").write_text('{"item": 1}\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)

    (tmp_path / ".coderabbit.yaml").write_text(
        "reviews:\n  path_filters:\n    - \"!evidence/registres/**\"\n",
        encoding="utf-8",
    )

    assert vcc.erreurs(tmp_path) == []


def test_repertoire_exclu_reconnait_motif_repertoire() -> None:
    assert vcc._repertoire_exclu("!archive/**") == "archive"
    assert vcc._repertoire_exclu("!evidence/registres/**") == "evidence/registres"
    assert vcc._repertoire_exclu("!governance/STATE-CURRENT.json") is None
    assert vcc._repertoire_exclu("src/forgeai/data/__init__.py") is None


def test_absence_toleree_jamais_signalee_morte(tmp_path: Path) -> None:
    (tmp_path / ".coderabbit.yaml").write_text(
        "reviews:\n  path_filters:\n    - \"!build/**\"\n",
        encoding="utf-8",
    )

    assert vcc.erreurs(tmp_path) == []


def test_main_exit0_sur_repo_reel() -> None:
    assert vcc.main(["--root", str(REPO)]) == 0


def test_main_exit1_et_message_sur_config_cassee(tmp_path: Path, capsys) -> None:
    (tmp_path / ".coderabbit.yaml").write_text(
        "reviews:\n  path_filters:\n    - \"!archive/**\"\n",
        encoding="utf-8",
    )

    code = vcc.main(["--root", str(tmp_path)])

    assert code == 1
    captured = capsys.readouterr()
    assert "ERREUR:" in captured.err


def test_chemin_present_mais_non_trackable_est_mort(tmp_path: Path) -> None:
    (tmp_path / "Vide").mkdir()
    (tmp_path / ".coderabbit.yaml").write_text(
        "reviews:\n  path_filters:\n    - \"!archive/**\"\n",
        encoding="utf-8",
    )

    errs = vcc.erreurs(tmp_path)

    assert any("chemin mort" in err and "archive" in err for err in errs)
