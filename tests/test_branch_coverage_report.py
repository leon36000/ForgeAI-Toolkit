from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
BASELINE_PATH = REPO_ROOT / "governance" / "branch-coverage-baseline.json"

sys.path.insert(0, str(SCRIPTS_DIR))
import branch_coverage_report  # noqa: E402


def test_baseline_json_valide_et_seuil_initial_defini() -> None:
    """Preuve que le critère « seuil global initial depuis une mesure fraîche » (#451) est
    réellement livré : le fichier existe, est un JSON valide, et le seuil est un nombre issu
    d'une mesure (pas un placeholder)."""
    contenu = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    assert contenu["_schema"] == "branch-coverage-baseline-v1"
    mesure = contenu["mesure_fraiche"]
    assert isinstance(mesure["num_branches"], int) and mesure["num_branches"] > 0
    assert isinstance(mesure["percent_branches_covered"], float)
    seuil = contenu["seuil_global_initial_branches_pct"]
    assert isinstance(seuil, float)
    # Le seuil doit être EXACTEMENT la mesure fraîche (pas de marge arbitraire inventée).
    assert seuil == mesure["percent_branches_covered"]


def test_mesurer_bout_en_bout_sur_mini_projet_jetable(tmp_path: Path) -> None:
    paquet = tmp_path / "src" / "forgeai"
    paquet.mkdir(parents=True)
    (paquet / "__init__.py").write_text("", encoding="utf-8")
    (paquet / "exemple.py").write_text(
        "def f(x):\n"
        "    if x:\n"
        "        return 1\n"
        "    return 2\n",
        encoding="utf-8",
    )
    dossier_tests = tmp_path / "tests"
    dossier_tests.mkdir()
    (dossier_tests / "test_exemple.py").write_text(
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "from forgeai.exemple import f\n"
        "def test_f_vrai():\n"
        "    assert f(True) == 1\n",
        encoding="utf-8",
    )
    sortie = tmp_path / "coverage.json"

    donnees = branch_coverage_report.mesurer(tmp_path, sortie)

    assert donnees["meta"]["branch_coverage"] is True
    assert sortie.exists()
    fonctions = branch_coverage_report.extraire_fonctions_incompletes(donnees)
    assert any(fonction["fonction"] == "f" for fonction in fonctions)


def test_mesurer_pytest_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def pytest_absent(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("pytest")

    monkeypatch.setattr(branch_coverage_report.subprocess, "run", pytest_absent)

    with pytest.raises(RuntimeError, match="pytest est indisponible"):
        branch_coverage_report.mesurer(tmp_path, tmp_path / "coverage.json")


def test_mesurer_erreur_systeme(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def execution_impossible(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        raise OSError("exécution impossible")

    monkeypatch.setattr(
        branch_coverage_report.subprocess,
        "run",
        execution_impossible,
    )

    with pytest.raises(RuntimeError, match="impossible d'exécuter pytest"):
        branch_coverage_report.mesurer(tmp_path, tmp_path / "coverage.json")


def test_mesurer_code_pytest_inattendu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=2,
        stdout="",
        stderr="erreur pytest",
    )
    monkeypatch.setattr(
        branch_coverage_report.subprocess,
        "run",
        lambda *args, **kwargs: resultat,
    )

    with pytest.raises(RuntimeError, match="code 2"):
        branch_coverage_report.mesurer(tmp_path, tmp_path / "coverage.json")


def test_mesurer_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout_depasse(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=1200)

    monkeypatch.setattr(branch_coverage_report.subprocess, "run", timeout_depasse)

    with pytest.raises(RuntimeError, match="délai de 1200s"):
        branch_coverage_report.mesurer(tmp_path, tmp_path / "coverage.json")


def test_mesurer_avertit_sur_stderr_si_des_tests_ont_echoue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=1,
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(
        branch_coverage_report.subprocess,
        "run",
        lambda *args, **kwargs: resultat,
    )
    sortie = tmp_path / "coverage.json"
    sortie.write_text(
        json.dumps({"meta": {"branch_coverage": True}, "files": {}, "totals": {}}),
        encoding="utf-8",
    )

    donnees = branch_coverage_report.mesurer(tmp_path, sortie)
    erreur = capsys.readouterr().err

    assert donnees == {"meta": {"branch_coverage": True}, "files": {}, "totals": {}}
    assert "au moins un test a échoué" in erreur


def test_mesurer_fichier_de_couverture_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=0,
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(
        branch_coverage_report.subprocess,
        "run",
        lambda *args, **kwargs: resultat,
    )
    sortie = tmp_path / "coverage.json"

    with pytest.raises(RuntimeError, match="fichier de couverture est absent"):
        branch_coverage_report.mesurer(tmp_path, sortie)


def test_mesurer_json_invalide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=0,
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(
        branch_coverage_report.subprocess,
        "run",
        lambda *args, **kwargs: resultat,
    )
    sortie = tmp_path / "coverage.json"
    sortie.write_text("ceci n'est pas du JSON", encoding="utf-8")

    with pytest.raises(RuntimeError, match="JSON de couverture est invalide"):
        branch_coverage_report.mesurer(tmp_path, sortie)


@pytest.mark.parametrize("contenu", ["[]", '"texte"', "null"])
def test_mesurer_json_valide_mais_pas_un_objet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contenu: str,
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=0,
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(
        branch_coverage_report.subprocess,
        "run",
        lambda *args, **kwargs: resultat,
    )
    sortie = tmp_path / "coverage.json"
    sortie.write_text(contenu, encoding="utf-8")

    with pytest.raises(RuntimeError, match="doit être un objet"):
        branch_coverage_report.mesurer(tmp_path, sortie)


@pytest.mark.parametrize(
    "contenu",
    [
        {"meta": {"branch_coverage": False}, "files": {}, "totals": {}},
        {"files": {}, "totals": {}},
        {"meta": {}, "files": {}, "totals": {}},
        {"meta": {"branch_coverage": "true"}, "files": {}, "totals": {}},
    ],
)
def test_mesurer_couverture_de_branches_non_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contenu: dict[str, object],
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=0,
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(
        branch_coverage_report.subprocess,
        "run",
        lambda *args, **kwargs: resultat,
    )
    sortie = tmp_path / "coverage.json"
    sortie.write_text(json.dumps(contenu), encoding="utf-8")

    with pytest.raises(RuntimeError, match="n'a pas été activée"):
        branch_coverage_report.mesurer(tmp_path, sortie)


def test_mesurer_fichier_illisible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultat = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=0,
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(
        branch_coverage_report.subprocess,
        "run",
        lambda *args, **kwargs: resultat,
    )
    sortie = tmp_path / "coverage.json"
    sortie.write_text(
        json.dumps({"meta": {"branch_coverage": True}}),
        encoding="utf-8",
    )

    def lecture_interdite(
        _self: Path,
        *,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        raise PermissionError("permission refusée")

    monkeypatch.setattr(Path, "read_text", lecture_interdite)

    with pytest.raises(RuntimeError, match="illisible"):
        branch_coverage_report.mesurer(tmp_path, sortie)


@pytest.mark.parametrize("donnees", [{}, {"files": []}, {"files": None}])
def test_extraire_sans_fichiers_ou_avec_fichiers_invalides(
    donnees: dict[str, object],
) -> None:
    assert branch_coverage_report.extraire_fonctions_incompletes(donnees) == []


def test_extraire_ignore_fichier_invalide_et_traite_les_autres() -> None:
    donnees: dict[str, Any] = {
        "files": {
            "invalide.py": [],
            "valide.py": {
                "functions": {
                    "fonction": {
                        "summary": {
                            "num_branches": 2,
                            "missing_branches": 1,
                            "percent_branches_covered": 50.0,
                        },
                        "start_line": 3,
                        "missing_lines": [5],
                    }
                }
            },
        }
    }

    fonctions = branch_coverage_report.extraire_fonctions_incompletes(donnees)

    assert len(fonctions) == 1
    assert fonctions[0]["fichier"] == "valide.py"
    assert fonctions[0]["fonction"] == "fonction"


@pytest.mark.parametrize(
    "fichier",
    [
        {},
        {"functions": []},
        {"functions": None},
    ],
)
def test_extraire_ignore_functions_absentes_ou_invalides(
    fichier: dict[str, object],
) -> None:
    donnees = {"files": {"exemple.py": fichier}}

    assert branch_coverage_report.extraire_fonctions_incompletes(donnees) == []


def test_extraire_ignore_fonction_dont_la_valeur_n_est_pas_un_dict() -> None:
    donnees: dict[str, Any] = {
        "files": {
            "exemple.py": {
                "functions": {
                    "invalide": [],
                    "valide": {
                        "summary": {
                            "num_branches": 1,
                            "missing_branches": 1,
                            "percent_branches_covered": 0.0,
                        }
                    },
                }
            }
        }
    }

    fonctions = branch_coverage_report.extraire_fonctions_incompletes(donnees)

    assert [fonction["fonction"] for fonction in fonctions] == ["valide"]


def test_extraire_ignore_summary_non_dict() -> None:
    donnees: dict[str, Any] = {
        "files": {
            "exemple.py": {
                "functions": {
                    "sans_resume": {},
                    "resume_invalide": {"summary": []},
                    "valide": {
                        "summary": {
                            "num_branches": 1,
                            "missing_branches": 1,
                            "percent_branches_covered": 0.0,
                        }
                    },
                }
            }
        }
    }

    fonctions = branch_coverage_report.extraire_fonctions_incompletes(donnees)

    assert [fonction["fonction"] for fonction in fonctions] == ["valide"]


@pytest.mark.parametrize(
    "resume",
    [
        {"num_branches": 0, "missing_branches": 0},
        {"num_branches": 2, "missing_branches": 0},
    ],
)
def test_extraire_omet_fonctions_sans_branches_manquantes(
    resume: dict[str, int],
) -> None:
    donnees: dict[str, Any] = {
        "files": {
            "exemple.py": {
                "functions": {
                    "fonction": {
                        "summary": resume,
                    }
                }
            }
        }
    }

    assert branch_coverage_report.extraire_fonctions_incompletes(donnees) == []


def test_extraire_convertit_le_nom_de_module_et_normalise_missing_lines() -> None:
    donnees: dict[str, Any] = {
        "files": {
            "module.py": {
                "functions": {
                    "": {
                        "summary": {
                            "num_branches": 3,
                            "missing_branches": 1,
                            "percent_branches_covered": 66.666,
                        },
                        "start_line": 1,
                    },
                    "fonction": {
                        "summary": {
                            "num_branches": 2,
                            "missing_branches": 1,
                            "percent_branches_covered": 50.0,
                        },
                        "missing_lines": "5",
                    },
                }
            }
        }
    }

    fonctions = branch_coverage_report.extraire_fonctions_incompletes(donnees)

    # Les deux entrées ont 1 branche manquante (égalité) ; le départage se fait par
    # pourcentage_branches CROISSANT (pire couverture d'abord) : "fonction" (50.0%) précède
    # "<module>" (66.666%) — cohérent avec test_extraire_trie_par_branches_manquantes_puis_pourcentage.
    assert fonctions[0]["fonction"] == "fonction"
    assert fonctions[0]["lignes_manquantes"] == []
    assert fonctions[1]["fonction"] == "<module>"
    assert fonctions[1]["lignes_manquantes"] == []


def test_extraire_conserve_missing_lines_quand_c_est_une_liste() -> None:
    donnees: dict[str, Any] = {
        "files": {
            "exemple.py": {
                "functions": {
                    "fonction": {
                        "summary": {
                            "num_branches": 2,
                            "missing_branches": 1,
                            "percent_branches_covered": 25.0,
                        },
                        "missing_lines": [4, 7],
                    }
                }
            }
        }
    }

    fonctions = branch_coverage_report.extraire_fonctions_incompletes(donnees)

    assert fonctions[0]["lignes_manquantes"] == [4, 7]


def test_extraire_trie_par_branches_manquantes_puis_pourcentage() -> None:
    donnees: dict[str, Any] = {
        "files": {
            "exemple.py": {
                "functions": {
                    "deux_branches": {
                        "summary": {
                            "num_branches": 5,
                            "missing_branches": 2,
                            "percent_branches_covered": 60.0,
                        }
                    },
                    "trois_branches": {
                        "summary": {
                            "num_branches": 8,
                            "missing_branches": 3,
                            "percent_branches_covered": 70.0,
                        }
                    },
                    "trois_branches_moins_couverte": {
                        "summary": {
                            "num_branches": 8,
                            "missing_branches": 3,
                            "percent_branches_covered": 40.0,
                        }
                    },
                    "une_branche": {
                        "summary": {
                            "num_branches": 2,
                            "missing_branches": 1,
                            "percent_branches_covered": 10.0,
                        }
                    },
                }
            }
        }
    }

    fonctions = branch_coverage_report.extraire_fonctions_incompletes(donnees)

    assert [fonction["fonction"] for fonction in fonctions] == [
        "trois_branches_moins_couverte",
        "trois_branches",
        "deux_branches",
        "une_branche",
    ]


def test_afficher_rapport_totaux_absents(
    capsys: pytest.CaptureFixture[str],
) -> None:
    branch_coverage_report._afficher_rapport({}, [])
    sortie = capsys.readouterr().out

    assert "Lignes : n/d totales, n/d manquantes (n/d%)" in sortie
    assert "Branches : n/d totales, n/d manquantes (n/d%)" in sortie


def test_afficher_rapport_totaux_type_invalide(
    capsys: pytest.CaptureFixture[str],
) -> None:
    branch_coverage_report._afficher_rapport({"totals": ["pas un dict"]}, [])
    sortie = capsys.readouterr().out

    assert "Lignes : n/d totales, n/d manquantes (n/d%)" in sortie
    assert "Branches : n/d totales, n/d manquantes (n/d%)" in sortie


def test_afficher_rapport_totaux_incomplets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    donnees = {"totals": {"num_statements": 10}}
    branch_coverage_report._afficher_rapport(donnees, [])
    sortie = capsys.readouterr().out

    assert "Lignes : 10 totales, n/d manquantes (n/d%)" in sortie
    assert "Branches : n/d totales, n/d manquantes (n/d%)" in sortie


def test_afficher_rapport_sans_fonction_incomplete(
    capsys: pytest.CaptureFixture[str],
) -> None:
    donnees = {
        "totals": {
            "num_statements": 10,
            "missing_lines": 2,
            "percent_covered": 80.0,
            "num_branches": 4,
            "missing_branches": 1,
            "percent_branches_covered": 75.0,
        }
    }

    branch_coverage_report._afficher_rapport(donnees, [])
    sortie = capsys.readouterr().out

    assert sortie.splitlines()[-1] == "Aucune fonction avec des branches manquantes."


def test_afficher_rapport_avec_fonctions_incompletes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fonctions = [
        {
            "fichier": "src/forgeai/module.py",
            "fonction": "calculer",
            "ligne_debut": 12,
            "branches_manquantes": 2,
            "branches_totales": 5,
            "pourcentage_branches": 60.0,
            "lignes_manquantes": [15],
        },
        {
            "fichier": "src/forgeai/autre.py",
            "fonction": "<module>",
            "ligne_debut": 1,
            "branches_manquantes": 1,
            "branches_totales": 3,
            "pourcentage_branches": 66.666,
            "lignes_manquantes": [],
        },
    ]

    branch_coverage_report._afficher_rapport({}, fonctions)
    sortie = capsys.readouterr().out

    assert "src/forgeai/module.py" in sortie
    assert "calculer" in sortie
    assert "2/5 branches manquantes" in sortie
    assert "src/forgeai/autre.py" in sortie
    assert "<module>" in sortie
    assert "1/3 branches manquantes" in sortie


def test_main_retourne_1_si_mesurer_echoue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mesure_en_echec(
        _racine: Path,
        _sortie_json: Path,
    ) -> dict[str, Any]:
        raise RuntimeError("échec simulé")

    monkeypatch.setattr(branch_coverage_report, "mesurer", mesure_en_echec)

    code_retour = branch_coverage_report.main(["--racine", str(tmp_path)])
    erreur = capsys.readouterr().err

    assert code_retour == 1
    assert "échec simulé" in erreur


def test_main_affiche_les_fonctions_incompletes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    donnees = {
        "meta": {"branch_coverage": True},
        "files": {
            "src/forgeai/a.py": {
                "functions": {
                    "premiere": {
                        "start_line": 4,
                        "summary": {
                            "num_branches": 4,
                            "missing_branches": 1,
                            "percent_branches_covered": 75.0,
                        },
                    }
                }
            },
            "src/forgeai/b.py": {
                "functions": {
                    "complete": {
                        "start_line": 2,
                        "summary": {
                            "num_branches": 2,
                            "missing_branches": 0,
                            "percent_branches_covered": 100.0,
                        },
                    },
                    "seconde": {
                        "start_line": 8,
                        "summary": {
                            "num_branches": 5,
                            "missing_branches": 3,
                            "percent_branches_covered": 40.0,
                        },
                    },
                }
            },
        },
        "totals": {
            "num_statements": 20,
            "missing_lines": 4,
            "percent_covered": 80.0,
            "num_branches": 11,
            "missing_branches": 4,
            "percent_branches_covered": 63.6,
        },
    }

    def mesure_fixe(
        _racine: Path,
        _sortie_json: Path,
    ) -> dict[str, Any]:
        return donnees

    monkeypatch.setattr(branch_coverage_report, "mesurer", mesure_fixe)

    code_retour = branch_coverage_report.main(["--racine", str(tmp_path)])
    sortie = capsys.readouterr().out

    assert code_retour == 0
    assert "src/forgeai/a.py" in sortie
    assert "premiere" in sortie
    assert "src/forgeai/b.py" in sortie
    assert "seconde" in sortie
    assert "complete" not in sortie


def test_main_joint_sortie_json_relative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments_recus: list[tuple[Path, Path]] = []

    def mesure_capturee(racine: Path, sortie_json: Path) -> dict[str, Any]:
        arguments_recus.append((racine, sortie_json))
        return {"files": {}, "totals": {}}

    monkeypatch.setattr(branch_coverage_report, "mesurer", mesure_capturee)

    code_retour = branch_coverage_report.main(
        [
            "--racine",
            "/un/chemin",
            "--sortie-json",
            "relatif.json",
        ]
    )

    assert code_retour == 0
    assert arguments_recus == [
        (Path("/un/chemin"), Path("/un/chemin/relatif.json"))
    ]


def test_main_conserve_sortie_json_absolue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments_recus: list[tuple[Path, Path]] = []

    def mesure_capturee(racine: Path, sortie_json: Path) -> dict[str, Any]:
        arguments_recus.append((racine, sortie_json))
        return {"files": {}, "totals": {}}

    monkeypatch.setattr(branch_coverage_report, "mesurer", mesure_capturee)

    code_retour = branch_coverage_report.main(
        [
            "--racine",
            "/un/chemin",
            "--sortie-json",
            "/ailleurs/rapport.json",
        ]
    )

    assert code_retour == 0
    assert arguments_recus == [
        (Path("/un/chemin"), Path("/ailleurs/rapport.json"))
    ]


def test_main_utilise_la_racine_par_defaut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments_recus: list[tuple[Path, Path]] = []

    def mesure_capturee(racine: Path, sortie_json: Path) -> dict[str, Any]:
        arguments_recus.append((racine, sortie_json))
        return {"files": {}, "totals": {}}

    monkeypatch.setattr(branch_coverage_report, "mesurer", mesure_capturee)

    code_retour = branch_coverage_report.main([])

    assert code_retour == 0
    assert arguments_recus == [(Path("."), Path("branch-coverage.json"))]
