#!/usr/bin/env python3
"""Cliquet de documentation des sous-commandes CLI ForgeAI."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

import gate_git_ref

_REF_GIT_VALIDE = gate_git_ref.REF_GIT_VALIDE
_valider_ref_git = gate_git_ref.valider_ref_git


def _arbre_et_porteur(chemin_cli: Path) -> tuple[ast.AST, str]:
    """Lit la CLI, parse son AST et trouve le porteur des sous-commandes de premier niveau."""
    try:
        source = chemin_cli.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as erreur:
        raise ValueError(f"CLI illisible {str(chemin_cli)!r} : {erreur}") from erreur

    try:
        arbre = ast.parse(source, filename=str(chemin_cli))
    except SyntaxError as erreur:
        raise ValueError(f"CLI invalide {str(chemin_cli)!r} : {erreur}") from erreur

    porteur: str | None = None
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Assign) or not isinstance(noeud.value, ast.Call):
            continue
        fonction = noeud.value.func
        if isinstance(fonction, ast.Attribute) and fonction.attr == "add_subparsers":
            cible = noeud.targets[0]
            if isinstance(cible, ast.Name):
                porteur = cible.id
                break

    if porteur is None:
        raise ValueError(
            f"aucun add_subparsers trouve dans {str(chemin_cli)!r} : la structure de la CLI a "
            "change, le gate ne peut pas conclure et refuse de verdir par defaut"
        )

    return arbre, porteur


def sous_commandes(chemin_cli: Path) -> list[str]:
    """Extrait par AST les sous-commandes declarees par add_parser."""
    arbre, porteur = _arbre_et_porteur(chemin_cli)

    # Seules les sous-commandes de PREMIER NIVEAU comptent : la documentation est reperee par la
    # chaine « forgeai <cmd> », qui ne peut par construction jamais correspondre a une commande
    # imbriquee (« forgeai node prepare » n'est pas « forgeai prepare »). Compter les imbriquees
    # produirait des anomalies systematiques et indefendables — 42 au lieu de 21 ici.
    #
    # Le porteur du premier niveau est DERIVE, jamais code en dur : on repere la variable
    # affectee par `add_subparsers(...)` sur l'objet `ArgumentParser` racine, c'est-a-dire le
    # PREMIER `add_subparsers` du fichier. Renommer la variable dans cli.py reste donc sans effet.
    resultat: set[str] = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        fonction = noeud.func
        if not isinstance(fonction, ast.Attribute) or fonction.attr != "add_parser":
            continue
        if not isinstance(fonction.value, ast.Name) or fonction.value.id != porteur:
            continue
        if not noeud.args:
            continue

        premier_argument = noeud.args[0]
        if isinstance(premier_argument, ast.Constant) and isinstance(
            premier_argument.value, str
        ):
            resultat.add(premier_argument.value)

    return sorted(resultat)


def _inventaire_cli(chemin_cli: Path) -> dict[str, dict[str, Any]]:
    """Inventorie les sous-commandes directes et options des parseurs de premier niveau."""
    try:
        arbre, porteur = _arbre_et_porteur(chemin_cli)
    except ValueError as erreur:
        if str(erreur).startswith("aucun add_subparsers trouve"):
            raise ValueError(
                f"aucun add_subparsers trouve dans {str(chemin_cli)!r} : la structure de la CLI a "
                "change, le rapport ne peut pas conclure"
            ) from erreur
        raise

    parseurs: dict[str, str] = {}
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Assign) or not isinstance(noeud.value, ast.Call):
            continue
        fonction = noeud.value.func
        if (
            not isinstance(fonction, ast.Attribute)
            or fonction.attr != "add_parser"
            or not isinstance(fonction.value, ast.Name)
            or fonction.value.id != porteur
            or not noeud.value.args
            or not isinstance(noeud.value.args[0], ast.Constant)
            or not isinstance(noeud.value.args[0].value, str)
        ):
            continue
        cible = noeud.targets[0]
        if isinstance(cible, ast.Name):
            parseurs[cible.id] = noeud.value.args[0].value

    resultat: dict[str, dict[str, Any]] = {}
    for variable, commande in parseurs.items():
        sous_porteurs: set[str] = set()
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Assign) or not isinstance(noeud.value, ast.Call):
                continue
            fonction = noeud.value.func
            if (
                isinstance(fonction, ast.Attribute)
                and fonction.attr == "add_subparsers"
                and isinstance(fonction.value, ast.Name)
                and fonction.value.id == variable
            ):
                cible = noeud.targets[0]
                if isinstance(cible, ast.Name):
                    sous_porteurs.add(cible.id)

        sous_commandes_directes: set[str] = set()
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            fonction = noeud.func
            if (
                not isinstance(fonction, ast.Attribute)
                or fonction.attr != "add_parser"
                or not isinstance(fonction.value, ast.Name)
                or fonction.value.id not in sous_porteurs
                or not noeud.args
            ):
                continue
            premier_argument = noeud.args[0]
            if isinstance(premier_argument, ast.Constant) and isinstance(
                premier_argument.value, str
            ):
                sous_commandes_directes.add(premier_argument.value)

        nombre_options = 0
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            fonction = noeud.func
            if (
                not isinstance(fonction, ast.Attribute)
                or fonction.attr != "add_argument"
                or not isinstance(fonction.value, ast.Name)
                or fonction.value.id != variable
            ):
                continue
            nombre_options += sum(
                isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
                and argument.value.startswith("--")
                for argument in noeud.args
            )

        resultat[commande] = {
            "sous_commandes": sorted(sous_commandes_directes),
            "options": nombre_options,
        }

    return resultat


def commandes_documentees(racine: Path) -> set[str]:
    """Retourne les commandes dont la forme ``forgeai X`` est documentee."""
    chemin_cli = racine / "src" / "forgeai" / "cli.py"
    commandes = sous_commandes(chemin_cli)

    chemins: set[Path] = set()
    for nom in ("README.md", "AGENTS.md", "MASTER-PLAN.md", "CLAUDE.md"):
        chemin = racine / nom
        if chemin.is_file():
            chemins.add(chemin)

    for dossier in ("Docs", "CANON"):
        chemin_dossier = racine / dossier
        if chemin_dossier.exists() and not chemin_dossier.is_dir():
            raise ValueError(f"dossier documentaire invalide {str(chemin_dossier)!r}")
        if chemin_dossier.is_dir():
            chemins.update(
                chemin
                for chemin in chemin_dossier.rglob("*.md")
                if chemin.is_file()
            )

    contenu = ""
    for chemin in sorted(chemins):
        try:
            contenu += "\n" + chemin.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as erreur:
            raise ValueError(
                f"documentation illisible {str(chemin)!r} : {erreur}"
            ) from erreur

    return {commande for commande in commandes if f"forgeai {commande}" in contenu}


def _valider_base(base: Any, libelle: str) -> dict[str, Any]:
    """Valide la structure minimale d'une base de cliquet."""
    if not isinstance(base, dict):
        raise ValueError(f"{libelle} doit etre un objet JSON")

    commandes = base.get("commandes")
    borne = base.get("borne")

    if not isinstance(commandes, list) or not all(
        isinstance(commande, str) for commande in commandes
    ):
        raise ValueError(f"{libelle} doit contenir une liste de commandes")

    if len(set(commandes)) != len(commandes):
        raise ValueError(f"{libelle} contient des commandes en double")

    if not isinstance(borne, dict):
        raise ValueError(f"{libelle} doit contenir un objet 'borne'")

    nombre_commandes = borne.get("nombre_commandes")
    if (
        isinstance(nombre_commandes, bool)
        or not isinstance(nombre_commandes, int)
        or nombre_commandes < 0
    ):
        raise ValueError(
            f"{libelle}.borne.nombre_commandes doit etre un entier positif ou nul"
        )

    return base


def anomalies(
    reelles: Any,
    documentees: Any,
    base: Any,
    base_reference: Any,
) -> list[str]:
    """Controle la dette documentaire contre la base et sa reference."""
    base_validee = _valider_base(base, "base")
    reference_validee = (
        _valider_base(base_reference, "base de reference")
        if base_reference is not None
        else None
    )

    commandes_reelles = set(reelles)
    commandes_documentees_set = set(documentees)
    commandes_base = set(base_validee["commandes"])
    resultat: list[str] = []

    for commande in sorted(commandes_reelles - commandes_documentees_set - commandes_base):
        resultat.append(f"commande {commande} ni documentee ni baselinee")

    # BORNE — inconditionnelle. Elle etait imbriquee dans le bloc `base_reference`, donc muette
    # sans `--base-ref-git` : il suffisait alors d'ajouter la commande a la base pour faire passer
    # la PR, c'est-a-dire exactement le contournement que la borne existe pour fermer. La borne
    # est une propriete AUTOPORTANTE (comparer le total courant au total fige) : elle ne depend
    # d'aucune reference git, donc elle ne doit dependre d'aucun argument optionnel.
    borne = base_validee["borne"]["nombre_commandes"]
    if len(commandes_reelles) > borne:
        resultat.append(
            f"la CLI compte {len(commandes_reelles)} sous-commandes alors que la base est bornee "
            f"a {borne} : toute commande ajoutee depuis doit etre DOCUMENTEE, jamais baselinee "
            "(rebaser la borne exige de documenter la dette, pas de l'etendre)"
        )

    if reference_validee is not None:
        commandes_reference = set(reference_validee["commandes"])
        ajouts_base = commandes_base - commandes_reference

        for commande in sorted(ajouts_base):
            resultat.append(
                f"commande {commande} presente dans la base mais absente de la "
                "base de reference"
            )

    for commande in sorted(commandes_base - commandes_reelles):
        resultat.append(f"commande {commande} baselinee mais absente de la CLI")

    for commande in sorted(commandes_base & commandes_documentees_set):
        resultat.append(
            f"commande {commande} baselinee mais desormais documentee"
        )

    return resultat


def _charger_json(chemin: Path, libelle: str) -> dict[str, Any]:
    """Charge et valide le JSON d'une base."""
    # SonarCloud pythonsecurity:S8707 (New Code, issue #385) : valider explicitement AVANT
    # tout accès disque, plutot que de se reposer uniquement sur l'OSError attrapee plus bas.
    if not chemin.is_file():
        raise ValueError(f"{libelle} introuvable ou n'est pas un fichier regulier : {str(chemin)!r}")
    try:
        texte = chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as erreur:
        raise ValueError(f"{libelle} illisible {str(chemin)!r} : {erreur}") from erreur

    try:
        contenu = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise ValueError(f"{libelle} JSON invalide {str(chemin)!r} : {erreur}") from erreur

    return _valider_base(contenu, libelle)


def _charger_base_reference_git(
    racine: Path,
    chemin_base: Path,
    ref: str,
) -> tuple[dict[str, Any] | None, str]:
    """Charge la base depuis une reference git deja resolue (délègue à gate_git_ref,
    partagé avec mypy_gate.py — voir #449)."""
    return gate_git_ref.charger_base_reference_git(racine, chemin_base, ref, _valider_base)


def main(argv: list[str] | None = None) -> int:
    """Execute le gate de documentation des commandes CLI."""
    parser = argparse.ArgumentParser(
        description="Controle le cliquet de documentation des commandes ForgeAI."
    )
    parser.add_argument("--racine", default=".", help="racine du depot")
    parser.add_argument(
        "--base",
        default="Docs/BASELINE-CLI-DOC.json",
        help="base JSON des commandes tolerees",
    )
    parser.add_argument(
        "--base-ref-git",
        metavar="REF",
        help="reference git de la base pour le controle de non-croissance",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="affiche le rapport de couverture documentaire",
    )
    arguments = parser.parse_args(argv)

    racine = Path(arguments.racine)
    chemin_base = Path(arguments.base)
    if not chemin_base.is_absolute():
        chemin_base = racine / chemin_base

    if arguments.report:
        try:
            reelles = sous_commandes(racine / "src" / "forgeai" / "cli.py")
            documentees = commandes_documentees(racine)
            inventaire = _inventaire_cli(racine / "src" / "forgeai" / "cli.py")
        except (OSError, TypeError, ValueError, RuntimeError) as erreur:
            print(str(erreur), file=sys.stderr)
            return 1

        commandes_reelles = set(reelles)
        commandes_documentees_set = set(documentees)
        non_documentees = sorted(commandes_reelles - commandes_documentees_set)
        total = len(commandes_reelles)
        # documentees est un sous-ensemble de reelles par construction, donc le nombre documente
        # ne peut pas depasser le total et le pourcentage reste borne.
        couverture = (len(commandes_documentees_set) / total * 100) if total else 100.0

        print("Rapport de couverture documentaire")
        print(f"Total de commandes : {total}")
        print(f"Commandes documentées : {len(commandes_documentees_set)}")
        print(f"Commandes non documentées : {len(non_documentees)}")
        print("Liste des commandes non documentées :")
        for commande in non_documentees:
            print(f"- {commande}")
        print("Inventaire des commandes :")
        for commande in reelles:
            details = inventaire.get(
                commande,
                {"sous_commandes": [], "options": 0},
            )
            sous_commandes_directes = details["sous_commandes"]
            liste_sous_commandes = (
                ", ".join(sous_commandes_directes)
                if sous_commandes_directes
                else "aucune"
            )
            print(
                f"- forgeai {commande} : sous-commandes directes : "
                f"{liste_sous_commandes} ; options déclarées : {details['options']}"
            )
        print(f"Pourcentage de couverture : {couverture:.2f} %")
        return 0

    try:
        base = _charger_json(chemin_base, "base")
        reelles = sous_commandes(racine / "src" / "forgeai" / "cli.py")
        documentees = commandes_documentees(racine)

        base_reference: dict[str, Any] | None = None
        message_reference = ""
        if arguments.base_ref_git:
            base_reference, message_reference = _charger_base_reference_git(
                racine,
                chemin_base,
                arguments.base_ref_git,
            )

        if message_reference:
            print(message_reference)

        rapport = anomalies(reelles, documentees, base, base_reference)
    except (OSError, TypeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    commandes_base = set(base["commandes"])
    commandes_reelles = set(reelles)
    commandes_documentees_set = set(documentees)
    tolerees = len(
        (commandes_reelles - commandes_documentees_set) & commandes_base
    )
    nouvelles = len(
        commandes_reelles - commandes_documentees_set - commandes_base
    )

    for anomalie in rapport:
        print(anomalie)
    print(
        f"— {tolerees} commande(s) tolerees par la base, "
        f"{nouvelles} nouvelle(s)"
    )
    return 1 if rapport else 0


if __name__ == "__main__":
    raise SystemExit(main())
