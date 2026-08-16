from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
CLASSIFICATION_PATH = REPO_ROOT / "governance" / "ruff-classification.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

sys.path.insert(0, str(SCRIPTS_DIR))
import ruff_report  # noqa: E402


def test_classification_json_valide() -> None:
    contenu = json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))

    assert isinstance(contenu, dict)
    assert "_familles_candidates" in contenu
    assert "regles" in contenu
    assert isinstance(contenu["regles"], dict)
    assert contenu["regles"]


def test_s101_classe_style_b904_classe_defaut_candidat() -> None:
    contenu = json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))
    regles = contenu["regles"]

    assert regles["S101"]["categorie"] == "style"
    assert regles["B904"]["categorie"] == "defaut_candidat"


def test_ruff_report_exit_0_sur_vrai_depot() -> None:
    code_retour = ruff_report.main(["--racine", str(REPO_ROOT)])

    assert code_retour == 0


def test_rapport_contient_les_4_categories(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code_retour = ruff_report.main(["--racine", str(REPO_ROOT)])
    sortie = capsys.readouterr().out

    assert code_retour == 0
    for categorie in ("defaut_candidat", "dette", "style", "non_classe"):
        assert categorie in sortie


def test_pyproject_select_inchange() -> None:
    contenu = PYPROJECT_PATH.read_text(encoding="utf-8")

    assert 'select = ["E9", "F"]' in contenu
