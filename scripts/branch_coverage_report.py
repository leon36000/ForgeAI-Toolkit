#!/usr/bin/env python3
"""Mesure et rapporte les branches manquantes par fonction, sans bloquer la CI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def mesurer(racine: Path, sortie_json: Path) -> dict[str, Any]:
    """Exécute pytest avec la mesure de couverture des branches."""
    commande = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--cov=src/forgeai",
        "--cov-branch",
        f"--cov-report=json:{sortie_json}",
    ]

    try:
        resultat = subprocess.run(
            commande,
            cwd=str(racine),
            capture_output=True,
            text=True,
            check=False,
            timeout=1200,
        )
    except FileNotFoundError as erreur:
        raise RuntimeError(
            "pytest est indisponible : vérifiez son installation et le PATH"
        ) from erreur
    except subprocess.TimeoutExpired as erreur:
        raise RuntimeError(
            "pytest a dépassé le délai de 1200s — abandon plutôt que de bloquer la CI"
        ) from erreur
    except OSError as erreur:
        raise RuntimeError(f"impossible d'exécuter pytest : {erreur}") from erreur

    if resultat.returncode not in (0, 1):
        details = resultat.stderr.strip() or resultat.stdout.strip()[-2000:]
        suffixe = f" : {details}" if details else ""
        raise RuntimeError(
            f"pytest a échoué avec le code {resultat.returncode}{suffixe}"
        )

    if resultat.returncode == 1:
        # Non bloquant par conception (voir docstring module) : le job `tests` séparé est déjà
        # le gate qui bloque sur les échecs de test. On avertit seulement, pour que le rapport
        # de branches ne soit pas lu comme fiable à 100% si la mesure sous-jacente est partielle.
        print(
            "ATTENTION : au moins un test a échoué pendant cette mesure — le rapport de "
            "couverture de branches peut être basé sur une exécution partielle.",
            file=sys.stderr,
        )

    if not sortie_json.exists():
        raise RuntimeError(f"le fichier de couverture est absent : {sortie_json}")

    try:
        contenu = json.loads(sortie_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erreur:
        raise RuntimeError(
            f"le fichier JSON de couverture est invalide {str(sortie_json)!r} : {erreur}"
        ) from erreur
    except (OSError, UnicodeError) as erreur:
        raise RuntimeError(
            f"le fichier de couverture est illisible {str(sortie_json)!r} : {erreur}"
        ) from erreur

    if not isinstance(contenu, dict):
        raise RuntimeError("le rapport de couverture JSON doit être un objet")

    meta = contenu.get("meta", {})
    if not isinstance(meta, dict) or meta.get("branch_coverage") is not True:
        raise RuntimeError(
            "la mesure de couverture de branches n'a pas été activée par pytest-cov"
        )

    return contenu


def extraire_fonctions_incompletes(
    donnees: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extrait les fonctions présentant des branches manquantes."""
    fichiers = donnees.get("files")
    if not isinstance(fichiers, dict):
        return []

    fonctions_incompletes: list[dict[str, Any]] = []

    for chemin, fichier in fichiers.items():
        if not isinstance(fichier, dict):
            continue

        fonctions = fichier.get("functions", {})
        if not isinstance(fonctions, dict):
            continue

        for nom, fonction in fonctions.items():
            if not isinstance(fonction, dict):
                continue

            resume = fonction.get("summary", {})
            if not isinstance(resume, dict):
                continue

            branches_totales = resume.get("num_branches", 0)
            branches_manquantes = resume.get("missing_branches", 0)

            if branches_totales == 0 or branches_manquantes == 0:
                continue

            lignes_manquantes = fonction.get("missing_lines", [])
            if not isinstance(lignes_manquantes, list):
                lignes_manquantes = []

            nom_fonction = "<module>" if nom == "" else nom
            fonctions_incompletes.append(
                {
                    "fichier": chemin,
                    "fonction": nom_fonction,
                    "ligne_debut": fonction.get("start_line"),
                    "branches_manquantes": branches_manquantes,
                    "branches_totales": branches_totales,
                    "pourcentage_branches": resume.get(
                        "percent_branches_covered", 0.0
                    ),
                    "lignes_manquantes": list(lignes_manquantes),
                }
            )

    fonctions_incompletes.sort(
        key=lambda fonction: (
            -fonction["branches_manquantes"],
            fonction["pourcentage_branches"],
            fonction["fichier"],
            fonction["fonction"],
        )
    )
    return fonctions_incompletes


def _afficher_rapport(
    donnees: dict[str, Any],
    fonctions_incompletes: list[dict[str, Any]],
) -> None:
    """Affiche le résumé global et les fonctions aux branches incomplètes."""
    totaux = donnees.get("totals", {})
    if not isinstance(totaux, dict):
        totaux = {}

    def valeur(cle: str) -> Any:
        return totaux[cle] if cle in totaux else "n/d"

    print("Rapport de couverture de branches")
    print(
        "Lignes : "
        f"{valeur('num_statements')} totales, "
        f"{valeur('missing_lines')} manquantes "
        f"({valeur('percent_covered')}%)"
    )
    print(
        "Branches : "
        f"{valeur('num_branches')} totales, "
        f"{valeur('missing_branches')} manquantes "
        f"({valeur('percent_branches_covered')}%)"
    )

    if not fonctions_incompletes:
        print("Aucune fonction avec des branches manquantes.")
        return

    for fonction in fonctions_incompletes:
        pourcentage = fonction["pourcentage_branches"]
        print(
            f"- {fonction['fichier']}::{fonction['fonction']} "
            f"(ligne {fonction['ligne_debut']}) : "
            f"{fonction['branches_manquantes']}/{fonction['branches_totales']} "
            f"branches manquantes ({pourcentage:.1f}%)"
        )


def main(argv: list[str] | None = None) -> int:
    """Exécute la mesure et affiche le rapport de couverture des branches."""
    parser = argparse.ArgumentParser(
        description="Mesure les branches manquantes par fonction."
    )
    parser.add_argument("--racine", default=".", help="racine du dépôt")
    parser.add_argument(
        "--sortie-json",
        default="branch-coverage.json",
        help="chemin du rapport JSON de couverture",
    )
    arguments = parser.parse_args(argv)

    racine = Path(arguments.racine)
    sortie_json = Path(arguments.sortie_json)
    if not sortie_json.is_absolute():
        sortie_json = racine / sortie_json

    try:
        donnees = mesurer(racine, sortie_json)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    fonctions_incompletes = extraire_fonctions_incompletes(donnees)
    _afficher_rapport(donnees, fonctions_incompletes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
