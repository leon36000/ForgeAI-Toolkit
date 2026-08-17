#!/usr/bin/env python3
"""Mesure et rapporte les violations Ruff candidates sans bloquer la CI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ruff_mesure


_CHEMIN_CLASSIFICATION = (
    Path(__file__).resolve().parent.parent / "governance" / "ruff-classification.json"
)


def _charger_json(chemin: Path) -> dict[str, Any]:
    """Charge le fichier de classification Ruff."""
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError as erreur:
        raise ValueError(f"classification Ruff introuvable : {str(chemin)!r}") from erreur
    except (OSError, UnicodeError) as erreur:
        raise ValueError(
            f"classification Ruff illisible {str(chemin)!r} : {erreur}"
        ) from erreur
    except json.JSONDecodeError as erreur:
        raise ValueError(
            f"classification Ruff JSON invalide {str(chemin)!r} : {erreur}"
        ) from erreur

    if not isinstance(contenu, dict):
        raise ValueError("la classification Ruff doit être un objet JSON")
    return contenu


def _selection_depuis_classification(chemin: Path) -> list[str]:
    """Retourne les familles candidates définies par la classification."""
    classification = _charger_json(chemin)
    selection = classification.get("_familles_candidates")
    if (
        not isinstance(selection, list)
        or not selection
        or not all(isinstance(famille, str) and famille for famille in selection)
    ):
        raise ValueError(
            "la classification Ruff doit contenir une liste non vide "
            "'_familles_candidates' de chaînes non vides"
        )
    return selection


SELECTION = _selection_depuis_classification(_CHEMIN_CLASSIFICATION)


def mesurer(racine: Path) -> list[dict[str, Any]]:
    """Exécute Ruff et retourne les violations détectées. Délègue à la fonction partagée
    `ruff_mesure.mesurer_violations` (extraite pour éliminer une duplication avec `mesurer()` de
    `ruff_ratchet.py`, Quality Gate SonarCloud #572 — les deux modules restent indépendants l'un
    de l'autre, ni l'un ni l'autre ne s'importe, chacun dépend de cette infrastructure commune,
    même principe que `gate_git_ref.py`)."""
    return ruff_mesure.mesurer_violations(racine, SELECTION)


def classifier(
    violations: list[dict[str, Any]],
    classification: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Regroupe les violations par catégorie, code et fichier."""
    categories: dict[str, dict[str, Any]] = {
        "defaut_candidat": {
            "total": 0,
            "par_code": {},
            "fichiers": {},
        },
        "dette": {
            "total": 0,
            "par_code": {},
            "fichiers": {},
        },
        "non_classe": {
            "total": 0,
            "par_code": {},
            "fichiers": {},
        },
        "style": {
            "total": 0,
            "par_code": {},
            "fichiers": {},
        },
    }

    regles = classification.get("regles", {})
    if not isinstance(regles, dict):
        regles = {}

    for violation in violations:
        code = violation.get("code")
        fichier = violation.get("filename")
        code_texte = code if isinstance(code, str) else "code_inconnu"
        fichier_texte = fichier if isinstance(fichier, str) else "fichier_inconnu"

        definition = regles.get(code_texte)
        categorie = (
            definition.get("categorie")
            if isinstance(definition, dict)
            else "non_classe"
        )
        if categorie not in categories:
            categorie = "non_classe"

        donnees = categories[categorie]
        donnees["total"] += 1

        par_code = donnees["par_code"]
        par_code[code_texte] = par_code.get(code_texte, 0) + 1

        fichiers = donnees["fichiers"]
        fichiers[fichier_texte] = fichiers.get(fichier_texte, 0) + 1

    for donnees in categories.values():
        donnees["par_code"] = dict(sorted(donnees["par_code"].items()))
        donnees["fichiers"] = [
            {"fichier": fichier, "occurrences": nombre}
            for fichier, nombre in sorted(
                donnees["fichiers"].items(),
                key=lambda element: (-element[1], element[0]),
            )[:10]
        ]

    return categories


def _afficher_rapport(rapport: dict[str, dict[str, Any]]) -> None:
    """Affiche le rapport dans l'ordre de priorité demandé."""
    print("Rapport Ruff — mesure des règles candidates")

    for categorie in ("defaut_candidat", "dette", "non_classe", "style"):
        donnees = rapport[categorie]
        print()
        print(f"Catégorie : {categorie}")
        print(f"Total : {donnees['total']}")
        print("Violations par code :")

        par_code = donnees["par_code"]
        if par_code:
            for code, nombre in par_code.items():
                print(f"- {code} : {nombre}")
        else:
            print("- aucune")

        print("10 fichiers les plus touchés :")
        fichiers = donnees["fichiers"]
        if fichiers:
            for element in fichiers:
                print(f"- {element['fichier']} : {element['occurrences']}")
        else:
            print("- aucun")


def main(argv: list[str] | None = None) -> int:
    """Exécute la mesure et affiche le rapport Ruff."""
    parser = argparse.ArgumentParser(
        description="Mesure les violations Ruff candidates sans bloquer la CI."
    )
    parser.add_argument("--racine", default=".", help="racine du dépôt")
    arguments = parser.parse_args(argv)

    racine = Path(arguments.racine)
    chemin_classification = racine / "governance" / "ruff-classification.json"

    try:
        classification = _charger_json(chemin_classification)
    except (OSError, UnicodeError, ValueError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    try:
        violations = mesurer(racine)
    except (OSError, RuntimeError, ValueError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    rapport = classifier(violations, classification)
    _afficher_rapport(rapport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
