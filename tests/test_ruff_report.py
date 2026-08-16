from __future__ import annotations

import json
import subprocess
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


def test_charger_json_fichier_absent(tmp_path: Path) -> None:
    chemin = tmp_path / "absent.json"

    with pytest.raises(ValueError, match="classification Ruff introuvable"):
        ruff_report._charger_json(chemin)


def test_charger_json_fichier_illisible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chemin = tmp_path / "illisible.json"
    chemin.write_text("{}", encoding="utf-8")

    def lecture_interdite(
        _self: Path,
        *,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        raise PermissionError("permission refusée")

    monkeypatch.setattr(Path, "read_text", lecture_interdite)

    with pytest.raises(ValueError, match="classification Ruff illisible"):
        ruff_report._charger_json(chemin)


def test_charger_json_json_malforme(tmp_path: Path) -> None:
    chemin = tmp_path / "invalide.json"
    chemin.write_text("ceci n'est pas du JSON", encoding="utf-8")

    with pytest.raises(ValueError, match="classification Ruff JSON invalide"):
        ruff_report._charger_json(chemin)


def test_charger_json_json_valide_mais_pas_objet(tmp_path: Path) -> None:
    chemin = tmp_path / "liste.json"
    chemin.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="doit être un objet JSON"):
        ruff_report._charger_json(chemin)


@pytest.mark.parametrize(
    "contenu",
    [
        {},
        {"_familles_candidates": []},
        {"_familles_candidates": ["B", ""]},
        {"_familles_candidates": ["B", 1]},
        {"_familles_candidates": "B"},
    ],
)
def test_selection_classification_invalide(
    tmp_path: Path,
    contenu: dict[str, object],
) -> None:
    chemin = tmp_path / "classification.json"
    chemin.write_text(json.dumps(contenu), encoding="utf-8")

    with pytest.raises(ValueError, match="_familles_candidates"):
        ruff_report._selection_depuis_classification(chemin)


def test_mesurer_ruff_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ruff_absent(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("ruff")

    monkeypatch.setattr(ruff_report.subprocess, "run", ruff_absent)

    with pytest.raises(RuntimeError, match="ruff est indisponible"):
        ruff_report.mesurer(tmp_path)


def test_mesurer_erreur_systeme(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def execution_impossible(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        raise OSError("exécution impossible")

    monkeypatch.setattr(ruff_report.subprocess, "run", execution_impossible)

    with pytest.raises(RuntimeError, match="impossible d'exécuter ruff"):
        ruff_report.mesurer(tmp_path)


def test_mesurer_code_ruff_inattendu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["ruff"],
        returncode=2,
        stdout="",
        stderr="erreur ruff",
    )
    monkeypatch.setattr(ruff_report.subprocess, "run", lambda *args, **kwargs: resultat)

    with pytest.raises(RuntimeError, match="code 2"):
        ruff_report.mesurer(tmp_path)


def test_mesurer_sortie_json_invalide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["ruff"],
        returncode=1,
        stdout="pas du JSON",
        stderr="",
    )
    monkeypatch.setattr(ruff_report.subprocess, "run", lambda *args, **kwargs: resultat)

    with pytest.raises(RuntimeError, match="sortie JSON de ruff est invalide"):
        ruff_report.mesurer(tmp_path)


@pytest.mark.parametrize("sortie", ["{}", "[1, 2]"])
def test_mesurer_sortie_json_structure_invalide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sortie: str,
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["ruff"],
        returncode=0,
        stdout=sortie,
        stderr="",
    )
    monkeypatch.setattr(ruff_report.subprocess, "run", lambda *args, **kwargs: resultat)

    with pytest.raises(
        RuntimeError,
        match="sortie JSON de ruff doit être une liste de violations",
    ):
        ruff_report.mesurer(tmp_path)


def test_mesurer_normalise_les_chemins_et_conserve_un_chemin_externe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chemin_interne = tmp_path / "src" / "module.py"
    chemin_interne.parent.mkdir()
    chemin_interne.write_text("", encoding="utf-8")
    chemin_externe = Path("/tmp/fichier-ruff-externe.py")

    resultat = subprocess.CompletedProcess(
        args=["ruff"],
        returncode=0,
        stdout=json.dumps(
            [
                {"code": "B904", "filename": str(chemin_interne)},
                {"code": "S101", "filename": str(chemin_externe)},
                {"code": "F401", "filename": 123},
            ]
        ),
        stderr="",
    )
    monkeypatch.setattr(ruff_report.subprocess, "run", lambda *args, **kwargs: resultat)

    violations = ruff_report.mesurer(tmp_path)

    assert violations[0]["filename"] == "src/module.py"
    assert violations[1]["filename"] == str(chemin_externe)
    assert violations[2]["filename"] == 123


def test_classifier_gere_les_violations_incompletes_et_categories_inconnues() -> None:
    violations = [
        {"code": 101, "filename": None},
        {"code": "X999", "filename": "src/inconnu.py"},
    ]
    classification = {
        "regles": {
            "X999": {"categorie": "categorie_inconnue"},
        }
    }

    rapport = ruff_report.classifier(violations, classification)

    assert rapport["non_classe"]["total"] == 2
    assert rapport["non_classe"]["par_code"] == {
        "code_inconnu": 1,
        "X999": 1,
    }


def test_afficher_rapport_affiche_les_sections_vides(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rapport = {
        categorie: {
            "total": 0,
            "par_code": {},
            "fichiers": [],
        }
        for categorie in (
            "defaut_candidat",
            "dette",
            "non_classe",
            "style",
        )
    }

    ruff_report._afficher_rapport(rapport)
    sortie = capsys.readouterr().out

    lignes = sortie.splitlines()
    assert lignes.count("- aucune") == 4
    assert lignes.count("- aucun") == 4


def test_main_retourne_1_si_classification_absente(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code_retour = ruff_report.main(["--racine", str(tmp_path)])
    erreur = capsys.readouterr().err

    assert code_retour == 1
    assert "classification Ruff introuvable" in erreur


def test_main_retourne_1_si_mesurer_echoue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chemin_classification = tmp_path / "governance" / "ruff-classification.json"
    chemin_classification.parent.mkdir()
    chemin_classification.write_text(
        json.dumps({"_familles_candidates": ["B"], "regles": {}}),
        encoding="utf-8",
    )

    def mesure_en_echec(_racine: Path) -> list[dict[str, object]]:
        raise RuntimeError("échec de mesure")

    monkeypatch.setattr(ruff_report, "mesurer", mesure_en_echec)

    code_retour = ruff_report.main(["--racine", str(tmp_path)])
    erreur = capsys.readouterr().err

    assert code_retour == 1
    assert "échec de mesure" in erreur
