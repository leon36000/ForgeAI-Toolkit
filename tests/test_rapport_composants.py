"""Tests du script ``scripts/rapport_composants.py`` (rapport supply-chain RC1).

Chaque test construit ses propres ``requirements-ci.txt``/``pyproject.toml``
factices dans ``tmp_path`` : aucun ne dépend des vrais fichiers de ce dépôt,
qui peuvent évoluer indépendamment du contrat verrouillé ici.
"""

from __future__ import annotations

import json
import sys
from email.message import Message
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rapport_composants as rc  # noqa: E402


def _ecrire_requirements(racine: Path, contenu: str) -> Path:
    """Écrit un ``requirements-ci.txt`` factice et retourne son chemin."""
    chemin = racine / "requirements-ci.txt"
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _ecrire_pyproject(
    racine: Path,
    nom: str = "projet-factice",
    version: str = "0.1.0",
    licence: str = "MIT",
) -> Path:
    """Écrit un ``pyproject.toml`` factice minimal mais valide."""
    chemin = racine / "pyproject.toml"
    chemin.write_text(
        f'[project]\nname = "{nom}"\nversion = "{version}"\nlicense = "{licence}"\n',
        encoding="utf-8",
    )
    return chemin


def _preparer_racine(
    racine: Path,
    requirements: str = "alpha-factice==1.0\n",
    nom: str = "projet-factice",
    version: str = "0.1.0",
    licence: str = "MIT",
) -> None:
    """Prépare une racine de dépôt factice complète pour les tests d'intégration."""
    _ecrire_requirements(racine, requirements)
    _ecrire_pyproject(racine, nom, version, licence)


def _fausses_metadonnees(champs: dict[str, str | list[str]]) -> Message:
    """Fabrique des métadonnées de paquet factices (API ``.get``/``.get_all``)."""
    message = Message()
    for cle, valeur in champs.items():
        valeurs = valeur if isinstance(valeur, list) else [valeur]
        for element in valeurs:
            message[cle] = element
    return message


def _par_nom(rapport: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Indexe les composants d'un rapport par nom pour des assertions directes."""
    composants = rapport["composants"]
    assert isinstance(composants, list)
    return {composant["nom"]: composant for composant in composants}


def test_parser_requirements_paquets_simples_tries_alphabetiquement(
    tmp_path: Path,
) -> None:
    chemin = _ecrire_requirements(
        tmp_path,
        "# lockfile factice\n"
        "pytest==8.3.3\n"
        "\n"
        "build==1.2.2.post1\n"
        "mypy==1.11.2\n",
    )

    assert rc._parser_requirements(chemin) == [
        ("build", "1.2.2.post1"),
        ("mypy", "1.11.2"),
        ("pytest", "8.3.3"),
    ]


def test_parser_requirements_tri_insensible_a_la_casse(tmp_path: Path) -> None:
    chemin = _ecrire_requirements(tmp_path, "ruff==0.6.0\nPyYAML==6.0.2\n")

    assert rc._parser_requirements(chemin) == [
        ("PyYAML", "6.0.2"),
        ("ruff", "0.6.0"),
    ]


def test_parser_requirements_marqueur_environnement_ignore(tmp_path: Path) -> None:
    chemin = _ecrire_requirements(
        tmp_path,
        "colorama==0.4.6 ; sys_platform == 'win32'\n",
    )

    assert rc._parser_requirements(chemin) == [("colorama", "0.4.6")]


def test_parser_requirements_lignes_de_hash_de_continuation_ignorees(
    tmp_path: Path,
) -> None:
    chemin = _ecrire_requirements(
        tmp_path,
        "pytest==8.3.3 \\\n"
        "    --hash=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "    --hash=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        "ruff==0.6.0 \\\n"
        "    --hash=sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\n",
    )

    assert rc._parser_requirements(chemin) == [
        ("pytest", "8.3.3"),
        ("ruff", "0.6.0"),
    ]


def test_parser_requirements_meme_nom_versions_differentes_conserve(
    tmp_path: Path,
) -> None:
    chemin = _ecrire_requirements(
        tmp_path,
        "rpds-py==0.20.0 ; python_version < '3.10'\n"
        "rpds-py==0.22.3 ; python_version >= '3.10'\n",
    )

    assert rc._parser_requirements(chemin) == [
        ("rpds-py", "0.20.0"),
        ("rpds-py", "0.22.3"),
    ]


def test_parser_requirements_doublon_strict_dedupe(tmp_path: Path) -> None:
    chemin = _ecrire_requirements(
        tmp_path,
        "pytest==8.3.3\n"
        "ruff==0.6.0\n"
        "pytest==8.3.3\n",
    )

    assert rc._parser_requirements(chemin) == [
        ("pytest", "8.3.3"),
        ("ruff", "0.6.0"),
    ]


def test_parser_requirements_fichier_vide_retourne_liste_vide(tmp_path: Path) -> None:
    chemin = _ecrire_requirements(tmp_path, "")

    assert rc._parser_requirements(chemin) == []


def test_parser_requirements_fichier_introuvable_leve_value_error_avec_chemin(
    tmp_path: Path,
) -> None:
    chemin = tmp_path / "absent.txt"

    with pytest.raises(ValueError) as excinfo:
        rc._parser_requirements(chemin)

    assert "requirements introuvable" in str(excinfo.value)
    assert str(chemin) in str(excinfo.value)


def test_licence_installee_paquet_reel_retourne_chaine_non_vide() -> None:
    licence = rc._licence_installee("pytest")

    assert isinstance(licence, str)
    assert licence


def test_licence_installee_paquet_inexistant_retourne_message_sans_lever() -> None:
    licence = rc._licence_installee("ce-paquet-nexiste-vraiment-pas-du-tout-12345")

    assert licence == "licence inconnue (paquet non installé dans cet environnement)"


def test_licence_installee_license_expression_est_prioritaire() -> None:
    fausses = _fausses_metadonnees(
        {
            "License-Expression": "MIT",
            "Classifier": "License :: OSI Approved :: Apache Software License",
            "License": "Apache-2.0",
        }
    )

    with mock.patch.object(rc.importlib.metadata, "metadata", return_value=fausses):
        assert rc._licence_installee("paquet-factice") == "MIT"


def test_licence_installee_repli_sur_classifier_license() -> None:
    fausses = _fausses_metadonnees(
        {
            "Classifier": [
                "Development Status :: 5 - Production/Stable",
                "License :: OSI Approved :: MIT License",
            ],
        }
    )

    with mock.patch.object(rc.importlib.metadata, "metadata", return_value=fausses):
        assert rc._licence_installee("paquet-factice") == "OSI Approved :: MIT License"


def test_licence_installee_repli_sur_champ_license_brut() -> None:
    fausses = _fausses_metadonnees({"License": "BSD-3-Clause"})

    with mock.patch.object(rc.importlib.metadata, "metadata", return_value=fausses):
        assert rc._licence_installee("paquet-factice") == "BSD-3-Clause"


def test_licence_installee_metadonnees_vides_retourne_licence_inconnue() -> None:
    fausses = _fausses_metadonnees({})

    with mock.patch.object(rc.importlib.metadata, "metadata", return_value=fausses):
        assert (
            rc._licence_installee("paquet-factice")
            == "licence inconnue (métadonnées absentes)"
        )


def test_licence_installee_license_unknown_vaut_metadonnees_absentes() -> None:
    fausses = _fausses_metadonnees({"License": "UNKNOWN"})

    with mock.patch.object(rc.importlib.metadata, "metadata", return_value=fausses):
        assert (
            rc._licence_installee("paquet-factice")
            == "licence inconnue (métadonnées absentes)"
        )


def test_construire_rapport_structure_schema_compteur_et_tri(tmp_path: Path) -> None:
    _preparer_racine(
        tmp_path,
        requirements="zeta-factice==1.0\nAlpha-factice==2.0\n",
    )

    rapport = rc.construire_rapport(tmp_path)

    assert rapport["_schema"] == "rapport-composants-v1"
    assert isinstance(rapport["_description"], str)
    assert rapport["_description"]
    assert rapport["nombre_composants"] == len(rapport["composants"])
    noms = [composant["nom"] for composant in rapport["composants"]]
    assert noms == sorted(noms, key=str.lower)


def test_construire_rapport_paquets_requirements_source_requirements(
    tmp_path: Path,
) -> None:
    _preparer_racine(
        tmp_path,
        requirements="alpha-factice==1.0\nbeta-factice==2.0\n",
    )

    rapport = rc.construire_rapport(tmp_path)
    par_nom = _par_nom(rapport)

    assert par_nom["alpha-factice"]["version"] == "1.0"
    assert par_nom["alpha-factice"]["source"] == "requirements-ci.txt"
    assert par_nom["beta-factice"]["version"] == "2.0"
    assert par_nom["beta-factice"]["source"] == "requirements-ci.txt"


def test_construire_rapport_entree_build_toujours_presente(tmp_path: Path) -> None:
    _preparer_racine(tmp_path, requirements="alpha-factice==1.0\n")

    rapport = rc.construire_rapport(tmp_path)
    par_nom = _par_nom(rapport)

    assert par_nom["build"]["version"] == "1.2.2.post1"
    assert (
        par_nom["build"]["source"]
        == "artefact-distribue.yml (installation directe, hors requirements-ci.txt)"
    )


def test_construire_rapport_entree_pyproject_hooks_toujours_presente(
    tmp_path: Path,
) -> None:
    """Fermeture des dépendances directes de build (round 6 de revue scellée,
    #454) : packaging est déjà couvert par requirements-ci.txt (non dupliqué,
    voir test dédié ci-dessous) ; pyproject_hooks est la seule dépendance
    directe inconditionnelle de build absente du lockfile — doit apparaître.
    Version/licence en dur (round 8) : épinglées explicitement dans
    artefact-distribue.yml au même titre que build, jamais introspectées —
    aucun mock nécessaire, valeurs identiques quel que soit l'hôte de test.
    """
    _preparer_racine(tmp_path, requirements="alpha-factice==1.0\n")

    rapport = rc.construire_rapport(tmp_path)
    par_nom = _par_nom(rapport)

    assert par_nom["pyproject_hooks"]["version"] == "1.2.0"
    assert par_nom["pyproject_hooks"]["licence"] == "OSI Approved :: MIT License"
    assert (
        par_nom["pyproject_hooks"]["source"]
        == "artefact-distribue.yml (installation directe, hors requirements-ci.txt)"
    )


def test_construire_rapport_packaging_du_lockfile_non_duplique_par_la_fermeture(
    tmp_path: Path,
) -> None:
    """packaging est AUSSI une dépendance directe de build (comme
    pyproject_hooks), mais déjà présente dans requirements-ci.txt — la
    fermeture ne doit pas en ajouter une 2e entrée en double.
    """
    _preparer_racine(tmp_path, requirements="packaging==26.3\n")

    rapport = rc.construire_rapport(tmp_path)

    occurrences = [c for c in rapport["composants"] if c["nom"] == "packaging"]
    assert len(occurrences) == 1
    assert occurrences[0]["source"] == "requirements-ci.txt"


def test_construire_rapport_entree_projet_lue_depuis_pyproject(tmp_path: Path) -> None:
    _preparer_racine(
        tmp_path,
        requirements="",
        nom="mon-produit",
        version="2.3.4",
        licence="Apache-2.0",
    )

    rapport = rc.construire_rapport(tmp_path)
    par_nom = _par_nom(rapport)

    entree = par_nom["mon-produit"]
    assert entree["version"] == "2.3.4"
    assert entree["licence"] == "Apache-2.0"
    assert "pyproject.toml" in entree["source"]


def test_construire_rapport_requirements_vide_compte_build_hooks_et_projet(
    tmp_path: Path,
) -> None:
    _preparer_racine(tmp_path, requirements="")

    rapport = rc.construire_rapport(tmp_path)

    assert rapport["nombre_composants"] == 3
    assert {composant["nom"] for composant in rapport["composants"]} == {
        "build",
        "pyproject_hooks",
        "projet-factice",
    }


def test_main_succes_retourne_zero_imprime_et_ecrit_json_exact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _preparer_racine(
        tmp_path,
        requirements="alpha-factice==1.0\nbeta-factice==2.0\n",
    )

    code_retour = rc.main(["--racine", str(tmp_path)])
    capture = capsys.readouterr()

    attendu = rc.construire_rapport(tmp_path)
    chemin_sortie = tmp_path / "composants-rc1.json"

    assert code_retour == 0
    assert capture.err == ""
    assert str(chemin_sortie) in capture.out
    assert f"({attendu['nombre_composants']} composant(s))" in capture.out
    assert chemin_sortie.is_file()
    assert json.loads(chemin_sortie.read_text(encoding="utf-8")) == attendu


def test_main_sortie_personnalisee_ecrite_au_chemin_demande(tmp_path: Path) -> None:
    _preparer_racine(tmp_path, requirements="")

    code_retour = rc.main(
        ["--racine", str(tmp_path), "--sortie", "rapport-personnalise.json"]
    )

    assert code_retour == 0
    assert (tmp_path / "rapport-personnalise.json").is_file()
    assert not (tmp_path / "composants-rc1.json").exists()


def test_main_racine_sans_requirements_retourne_1_sans_creer_de_fichier(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code_retour = rc.main(["--racine", str(tmp_path)])
    capture = capsys.readouterr()

    assert code_retour == 1
    assert "requirements introuvable" in capture.err
    assert not (tmp_path / "composants-rc1.json").exists()


def test_main_deux_appels_successifs_produisent_un_fichier_byte_identique(
    tmp_path: Path,
) -> None:
    _preparer_racine(
        tmp_path,
        requirements="alpha-factice==1.0\nbeta-factice==2.0\n",
    )
    chemin_sortie = tmp_path / "composants-rc1.json"

    assert rc.main(["--racine", str(tmp_path)]) == 0
    premier = chemin_sortie.read_bytes()

    assert rc.main(["--racine", str(tmp_path)]) == 0
    second = chemin_sortie.read_bytes()

    assert premier == second


def test_charger_pyproject_toml_invalide_leve_value_error(tmp_path: Path) -> None:
    chemin = tmp_path / "pyproject.toml"
    chemin.write_text("[project\nname = INVALIDE\n", encoding="utf-8")

    with pytest.raises(ValueError, match="TOML invalide"):
        rc._charger_pyproject(chemin)


def test_charger_pyproject_introuvable_leve_value_error_avec_chemin(
    tmp_path: Path,
) -> None:
    chemin = tmp_path / "absent.toml"

    with pytest.raises(ValueError, match="introuvable"):
        rc._charger_pyproject(chemin)


def test_entree_projet_table_project_absente_leve(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.autre]\nvaleur = 1\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="table 'project'"):
        rc._entree_projet(tmp_path)


def test_entree_projet_nom_absent_leve(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "0.1.0"\nlicense = "MIT"\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="'project.name'"):
        rc._entree_projet(tmp_path)


def test_entree_projet_version_absente_leve(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nlicense = "MIT"\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="'project.version'"):
        rc._entree_projet(tmp_path)


def test_entree_projet_licence_absente_leve(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="'project.license'"):
        rc._entree_projet(tmp_path)


def test_entrees_backend_build_setuptools_contrainte_declaree_non_resolue(
    tmp_path: Path,
) -> None:
    """Round 9 de revue scellée (#454) : [build-system].requires DOIT être
    inventorié, mais un build PEP 517 isolé ne fige aucune version résolue —
    la contrainte déclarée est rapportée telle quelle, jamais devinée.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=68"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "x"\nversion = "0.1.0"\nlicense = "MIT"\n',
        encoding="utf-8",
    )

    entrees = rc._entrees_backend_build(tmp_path)

    assert len(entrees) == 1
    assert entrees[0]["nom"] == "setuptools"
    assert ">=68" in entrees[0]["version"]
    assert "non résolue" in entrees[0]["version"]
    assert entrees[0]["source"] == (
        "pyproject.toml [build-system].requires (backend PEP 517)"
    )


def test_entrees_backend_build_sans_contrainte_de_version(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["wheel"]\n'
        '[project]\nname = "x"\nversion = "0.1.0"\nlicense = "MIT"\n',
        encoding="utf-8",
    )

    entrees = rc._entrees_backend_build(tmp_path)

    assert entrees[0]["nom"] == "wheel"
    assert "aucune contrainte déclarée" in entrees[0]["version"]


def test_entrees_backend_build_plusieurs_entrees_toutes_incluses(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=68", "wheel"]\n'
        '[project]\nname = "x"\nversion = "0.1.0"\nlicense = "MIT"\n',
        encoding="utf-8",
    )

    entrees = rc._entrees_backend_build(tmp_path)

    assert {entree["nom"] for entree in entrees} == {"setuptools", "wheel"}


def test_entrees_backend_build_section_absente_retourne_liste_vide(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\nlicense = "MIT"\n',
        encoding="utf-8",
    )

    assert rc._entrees_backend_build(tmp_path) == []


def test_entrees_backend_build_requires_vide_retourne_liste_vide(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = []\n'
        '[project]\nname = "x"\nversion = "0.1.0"\nlicense = "MIT"\n',
        encoding="utf-8",
    )

    assert rc._entrees_backend_build(tmp_path) == []


def test_entrees_backend_build_requires_type_invalide_retourne_liste_vide(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = "setuptools"\n'
        '[project]\nname = "x"\nversion = "0.1.0"\nlicense = "MIT"\n',
        encoding="utf-8",
    )

    assert rc._entrees_backend_build(tmp_path) == []


def test_entrees_backend_build_pyproject_absent_retourne_liste_vide(
    tmp_path: Path,
) -> None:
    assert rc._entrees_backend_build(tmp_path) == []


def test_construire_rapport_backend_build_inclus_dans_inventaire_complet(
    tmp_path: Path,
) -> None:
    _ecrire_requirements(tmp_path, "alpha-factice==1.0\n")
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=68"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "projet-factice"\nversion = "0.1.0"\nlicense = "MIT"\n',
        encoding="utf-8",
    )

    rapport = rc.construire_rapport(tmp_path)
    par_nom = _par_nom(rapport)

    assert "setuptools" in par_nom
    assert ">=68" in par_nom["setuptools"]["version"]


def test_main_erreur_ecriture_retourne_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _preparer_racine(tmp_path)

    with mock.patch.object(
        rc.Path, "write_text", side_effect=OSError("disque plein (simulé)")
    ):
        code_retour = rc.main(["--racine", str(tmp_path)])

    capture = capsys.readouterr()
    assert code_retour == 1
    assert "impossible d'écrire" in capture.err


def test_main_sortie_absolue_rejetee_sans_ecrire_ni_contourner_la_racine(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Path("/a") / "/b" == Path("/b") (stdlib) : sans garde-fou, --sortie absolu
    écrirait hors de --racine en silence, contrairement au contrat annoncé par --help
    ("relatif à --racine") — revue scellée round 1, objection GPT-5.6-Terra-Pro."""
    _preparer_racine(tmp_path)
    cible_hors_racine = tmp_path.parent / "ne-doit-jamais-exister.json"

    code_retour = rc.main(
        ["--racine", str(tmp_path), "--sortie", str(cible_hors_racine)]
    )

    capture = capsys.readouterr()
    assert code_retour == 1
    assert "s'en évade" in capture.err
    assert not cible_hors_racine.exists()


def test_main_sortie_relative_avec_remontee_rejetee_sans_ecrire_hors_racine(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """is_absolute() seul (round 1) ne détecte pas une remontée ".." qui reste
    syntaxiquement relative mais s'évade de --racine une fois résolue — revue
    scellée round 2, objections convergentes DeepSeek-V4-Pro-0813 et Qwen3.8-2.4T."""
    _preparer_racine(tmp_path)
    cible_hors_racine = tmp_path.parent / "ne-doit-jamais-exister-non-plus.json"
    sortie_relative_evasive = f"../{cible_hors_racine.name}"

    code_retour = rc.main(
        ["--racine", str(tmp_path), "--sortie", sortie_relative_evasive]
    )

    capture = capsys.readouterr()
    assert code_retour == 1
    assert "s'en évade" in capture.err
    assert not cible_hors_racine.exists()


def test_parser_requirements_extras_pep508_ignores_nom_et_version_extraits(
    tmp_path: Path,
) -> None:
    """`paquet[extra1,extra2]==version` (extras PEP 508) doit rester détecté — le
    lockfile réel de ce dépôt n'en contient pas aujourd'hui (vérifié empiriquement),
    mais rien n'exclut qu'un futur ajout en introduise — revue scellée round 2,
    objections convergentes DeepSeek-V4-Pro-0813 et Qwen3.8-2.4T."""
    chemin = _ecrire_requirements(
        tmp_path, "requests[security,socks]==2.28.0\n"
    )

    resultat = rc._parser_requirements(chemin)

    assert resultat == [("requests", "2.28.0")]
