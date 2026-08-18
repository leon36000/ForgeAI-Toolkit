#!/usr/bin/env python3
"""Génère le rapport des composants utilisés pour CONSTRUIRE les artefacts RC1.

Pourquoi ce script : l'audit supply-chain EXT-029 exige la liste exhaustive des
paquets Python (versions + licences) mobilisés pour construire les artefacts
distribués RC1 (wheel/sdist) — et non celles du produit livré, qui reste stdlib
pure (``dependencies = []`` dans ``pyproject.toml``). Trois sources, vérifiées
empiriquement : ``requirements-ci.txt`` (lockfile à empreintes couvrant tout
l'outillage CI/test/lint) ; ``build==1.2.2.post1`` (installé en direct dans
``.github/workflows/artefact-distribue.yml``, hors lockfile) ET la fermeture de
SES dépendances directes propres (``pyproject_hooks`` — ``packaging`` est aussi
une dépendance directe de ``build`` mais déjà couverte par le lockfile, non
dupliquée — vérifié via l'API PyPI ``requires_dist`` de la version exacte
épinglée, pas supposé) ; le projet lui-même. Le rapport est non bloquant : il
documente, il ne gate pas — même philosophie que ``scripts/ruff_report.py``.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any

# Repli non normalisé en ValueError (contrairement aux erreurs gérées dans
# _charger_pyproject ci-dessous) : ce ModuleNotFoundError ne peut survenir que si
# tomli est ABSENT sur Python <3.11, un scénario hors de l'environnement supporté
# de ce script — requirements-ci.txt (lockfile CI à empreintes) garantit tomli
# comme dépendance transitive de mypy, donc toujours présent quand ce script
# tourne dans l'environnement pour lequel il est conçu (revue scellée round 4,
# objection mineure non retenue pour ce motif).
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


# Motif d'une ligne de paquet pip-compile : ``nom==version``, éventuellement suivi
# d'un marqueur d'environnement ``; ...`` et/ou d'un ``\`` de continuation vers les
# lignes ``--hash=sha256:...`` (ignorées car non ancrées en début de ligne).
_MOTIF_PAQUET = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([^\s;\\]+)")


def _parser_requirements(chemin: Path) -> list[tuple[str, str]]:
    """Parse le lockfile pip-compile et retourne les couples (nom, version) triés.

    Pourquoi une déduplication sur (nom, version) strictement identique : le
    lockfile peut lister le MÊME paquet sous deux versions distinctes avec des
    marqueurs d'environnement disjoints (ex. ``rpds-py``) — les deux versions
    participent réellement au build selon la plateforme et doivent toutes deux
    figurer au rapport. Seul un doublon exact est éliminé. Le tri par nom
    (insensible à la casse) garantit une sortie déterministe et diff-stable.
    """
    try:
        contenu = chemin.read_text(encoding="utf-8")
    except FileNotFoundError as erreur:
        raise ValueError(f"requirements introuvable : {str(chemin)!r}") from erreur
    except (OSError, UnicodeError) as erreur:
        raise ValueError(
            f"requirements illisible {str(chemin)!r} : {erreur}"
        ) from erreur

    vues: set[tuple[str, str]] = set()
    paquets: list[tuple[str, str]] = []
    for ligne in contenu.splitlines():
        correspondance = _MOTIF_PAQUET.match(ligne)
        if correspondance is None:
            continue
        entree = (correspondance.group(1), correspondance.group(2))
        if entree in vues:
            continue
        vues.add(entree)
        paquets.append(entree)

    paquets.sort(key=lambda element: element[0].lower())
    return paquets


def _licence_installee(nom: str) -> str:
    """Extrait la licence d'un paquet installé, sans jamais deviner.

    Pourquoi cet ordre de préférence (vérifié empiriquement sur ce dépôt) :
    ``License-Expression`` (PEP 639, SPDX moderne) est le seul champ exposé par
    ruff/pytest/mypy, tandis que pyyaml n'expose que le classifier historique —
    les deux niveaux sont donc nécessaires. Le champ ``License`` brut sert de
    dernier recours mais vaut souvent ``UNKNOWN``. Mieux vaut un « licence
    inconnue » honnête qu'une licence inventée : un rapport d'audit qui devine
    donne une illusion de conformité.
    """
    try:
        metadonnees = importlib.metadata.metadata(nom)
    except importlib.metadata.PackageNotFoundError:
        return "licence inconnue (paquet non installé dans cet environnement)"

    expression = metadonnees.get("License-Expression")
    if expression:
        return expression

    for classifier in metadonnees.get_all("Classifier", []):
        if classifier.startswith("License :: "):
            return classifier[len("License :: "):]

    licence_brute = metadonnees.get("License", "")
    if licence_brute.strip() and licence_brute.strip().upper() != "UNKNOWN":
        return licence_brute

    return "licence inconnue (métadonnées absentes)"


def _charger_pyproject(chemin: Path) -> dict[str, Any]:
    """Charge ``pyproject.toml`` en normalisant toute erreur en ``ValueError``.

    Pourquoi normaliser : ``main`` ne capture que ``ValueError`` (lecture) et
    ``OSError`` (écriture) — convertir ici garantit qu'aucun traceback brut ne
    fuite, quelle que soit la panne (fichier absent, illisible, TOML invalide).
    """
    try:
        with chemin.open("rb") as flux:
            return tomllib.load(flux)
    except FileNotFoundError as erreur:
        raise ValueError(f"pyproject.toml introuvable : {str(chemin)!r}") from erreur
    except OSError as erreur:
        raise ValueError(
            f"pyproject.toml illisible {str(chemin)!r} : {erreur}"
        ) from erreur
    except tomllib.TOMLDecodeError as erreur:
        raise ValueError(
            f"pyproject.toml TOML invalide {str(chemin)!r} : {erreur}"
        ) from erreur


def _entree_projet(racine: Path) -> dict[str, Any]:
    """Construit l'entrée du produit livré lui-même, lue depuis ``pyproject.toml``.

    Pourquoi valider chaque champ : le tri final porte sur ``nom.lower()`` — un
    champ absent ou d'un type inattendu (ex. ``license`` en sous-objet
    ``{text = ...}`` au lieu de la chaîne SPDX directe attendue ici) y
    provoquerait un ``AttributeError`` brut. Échouer tôt en ``ValueError`` avec
    un message explicite vaut mieux qu'un rapport silencieusement faussé.
    """
    donnees = _charger_pyproject(racine / "pyproject.toml")
    projet = donnees.get("project")
    if not isinstance(projet, dict):
        raise ValueError("pyproject.toml : table 'project' absente ou invalide")

    nom = projet.get("name")
    version = projet.get("version")
    licence = projet.get("license")
    if not isinstance(nom, str) or not nom:
        raise ValueError("pyproject.toml : champ 'project.name' absent ou invalide")
    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml : champ 'project.version' absent ou invalide")
    if not isinstance(licence, str) or not licence:
        raise ValueError(
            "pyproject.toml : champ 'project.license' absent ou invalide "
            "(chaîne SPDX directe attendue)"
        )

    return {
        "nom": nom,
        "version": version,
        "licence": licence,
        "source": "pyproject.toml (produit livré, dependencies=[] — stdlib pure)",
    }


def construire_rapport(racine: Path) -> dict[str, Any]:
    """Construit le rapport complet des composants (fonction pure, aucune écriture).

    Pourquoi trois sources : le lockfile ``requirements-ci.txt`` couvre tout
    l'outillage CI/test/lint ; ``build`` est l'unique outil externe installé hors
    lockfile (épinglé en dur dans ``artefact-distribue.yml``) et c'est lui qui
    construit RÉELLEMENT les artefacts — SA PROPRE fermeture de dépendances
    directes est incluse (``pyproject_hooks``, absente du lockfile ;
    ``packaging`` aussi mais déjà présente donc non dupliquée) pour que
    l'inventaire ne s'arrête pas à l'outil épinglé lui-même ; le projet lui-même
    figure pour mémoire afin de rappeler que le produit livré n'embarque aucune
    dépendance runtime. Le tri final par nom (insensible à la casse) rend la
    sortie déterministe.
    """
    composants: list[dict[str, Any]] = [
        {
            "nom": nom,
            "version": version,
            "licence": _licence_installee(nom),
            "source": "requirements-ci.txt",
        }
        for nom, version in _parser_requirements(racine / "requirements-ci.txt")
    ]
    composants.append(
        {
            "nom": "build",
            "version": "1.2.2.post1",
            "licence": _licence_installee("build"),
            "source": "artefact-distribue.yml (installation directe, hors requirements-ci.txt)",
        }
    )
    # Fermeture des dépendances DIRECTES de build==1.2.2.post1 (requires_dist PyPI,
    # vérifié empiriquement 2026-08-18) : packaging>=19.1 (inconditionnelle, déjà
    # couverte par requirements-ci.txt — pas dupliquée ici) + pyproject_hooks
    # (inconditionnelle, absente du lockfile — ajoutée ci-dessous) + 3 dépendances
    # CONDITIONNELLES qui ne s'appliquent PAS à l'environnement réel de construction
    # (ubuntu-latest, Python 3.12, artefact-distribue.yml) : colorama exige
    # os_name=="nt" (Windows), importlib-metadata exige python_full_version<"3.10.2",
    # tomli exige python_version<"3.11" — aucune des trois n'est vraie ici. packaging
    # et pyproject_hooks n'ont eux-mêmes AUCUNE dépendance propre (vérifié PyPI) :
    # fermeture complète à ce niveau, pas un arrêt arbitraire.
    #
    # Round 8 de revue scellée (#454) : une introspection dynamique (comme pour
    # build ci-dessus, dont seule la LICENCE reste introspectée) ne rapporte
    # rien d'utile dans le job CI réel (rapport-composants, gates.yml) qui
    # n'installe ni build ni pyproject_hooks — l'inventaire publié aurait donc
    # « version/licence inconnue » pour un composant réellement mobilisé par la
    # construction. Corrigé en épinglant EXPLICITEMENT pyproject_hooks==1.2.0
    # dans artefact-distribue.yml (même job qui installe build), rendant cette
    # version aussi vérifiable/reproductible que celle de build lui-même —
    # valeur ci-dessous COPIÉE de ce pin, jamais introspectée ni devinée.
    composants.append(
        {
            "nom": "pyproject_hooks",
            "version": "1.2.0",
            "licence": "OSI Approved :: MIT License",
            "source": "artefact-distribue.yml (installation directe, hors requirements-ci.txt)",
        }
    )
    composants.append(_entree_projet(racine))

    composants.sort(key=lambda composant: composant["nom"].lower())

    return {
        "_schema": "rapport-composants-v1",
        "_description": (
            "Composants (paquets Python, versions et licences) utilisés pour "
            "CONSTRUIRE les artefacts distribués RC1 (wheel/sdist) : outillage "
            "de CI/dev/build uniquement. Le produit livré reste stdlib pure "
            "(dependencies = [] dans pyproject.toml) — rien de tout cela n'est "
            "une dépendance runtime du produit. La licence vaut « licence "
            "inconnue » lorsque le paquet n'est pas installé dans "
            "l'environnement d'exécution de ce script ou que ses métadonnées "
            "n'exposent aucune information de licence."
        ),
        "nombre_composants": len(composants),
        "composants": composants,
    }


def main(argv: list[str] | None = None) -> int:
    """Génère le rapport JSON des composants RC1 et l'écrit sous ``--racine``."""
    parser = argparse.ArgumentParser(
        description=(
            "Génère le rapport JSON des composants utilisés pour construire "
            "les artefacts distribués RC1 (rapport non bloquant)."
        )
    )
    parser.add_argument("--racine", default=".", help="racine du dépôt")
    parser.add_argument(
        "--sortie",
        default="composants-rc1.json",
        help=(
            "fichier de sortie du rapport JSON (relatif à --racine, ou absolu à "
            "condition de rester sous --racine une fois résolu)"
        ),
    )
    arguments = parser.parse_args(argv)

    racine = Path(arguments.racine)

    # Deux façons distinctes de contourner « --sortie relatif à --racine » (revue scellée
    # round 2, DeepSeek-V4-Pro-0813 et Qwen3.8-2.4T convergents), vérifiées empiriquement
    # toutes les deux : (1) Path("/a") / "/b" == Path("/b") — un opérande ABSOLU à droite de
    # l'opérateur pathlib « / » écrase silencieusement le côté gauche ; (2) un chemin RELATIF
    # contenant des remontées ".." (ex. "../../etc/passwd") reste accepté par is_absolute()
    # mais s'évade de --racine une fois résolu. Le SEUL garde-fou fiable contre les deux
    # est de comparer le chemin RÉSOLU final à la racine résolue via is_relative_to() (stdlib
    # ≥3.9) — is_absolute() seul (round 1) ne couvrait que le premier cas.
    chemin = racine / arguments.sortie
    if not chemin.resolve().is_relative_to(racine.resolve()):
        print(
            f"--sortie doit rester à l'intérieur de --racine, reçu un chemin qui s'en évade : "
            f"{arguments.sortie!r}",
            file=sys.stderr,
        )
        return 1

    try:
        rapport = construire_rapport(racine)
    except ValueError as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    # sort_keys=False : l'ordre des clés du dict est volontairement choisi dans
    # construire_rapport (schéma, description, compteur, liste) — ne pas le retrier.
    contenu = json.dumps(rapport, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    try:
        chemin.write_text(contenu, encoding="utf-8")
    except OSError as erreur:
        print(
            f"impossible d'écrire le rapport {str(chemin)!r} : {erreur}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Rapport composants généré : {chemin} "
        f"({rapport['nombre_composants']} composant(s))."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
