#!/usr/bin/env python3
"""Cliquet mypy progressif par module (RC1-019, #449) — src/forgeai en clone propre.

Lot 1 : construit le mécanisme, ne corrige aucune des erreurs existantes. Mesure de référence
(Docs/BASELINE-MYPY.json, mypy 2.1.0/2.3.1 identiques sur ce dépôt) : 134 erreurs sur 12 fichiers,
74 fichiers déjà propres protégés à zéro tolérance. Objectif final : dette à zéro, tout
`src/forgeai` sous protection — chaque lot de correction fait décroître `dette` (jamais l'inverse)
jusqu'à ce qu'un fichier bascule dans `fichiers_proteges`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Copié depuis gate_docs.py — validation anti-injection pour --base-ref-git
_REF_GIT_VALIDE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]*$")


def _valider_ref_git(ref: str) -> None:
    """Refuse tout ref commençant par '-' (injection d'option git) ou contenant un
    caractère hors de l'ensemble attendu pour un nom de référence git."""
    if not ref or ref.startswith("-") or not _REF_GIT_VALIDE.match(ref):
        raise ValueError(f"reference git invalide {ref!r} : refusee avant tout appel git")


def executer_mypy(racine: Path, cible: str) -> str:
    """Lance `python3 -m mypy <cible> --ignore-missing-imports` (cwd=racine), capture
    stdout+stderr, retourne le texte combiné. mypy sort avec un code non-nul QUAND IL TROUVE DES
    ERREURS DE TYPE — c'est le cas normal attendu, PAS une exception : ne jamais lever sur un
    exit code mypy non-nul en soi. Ne lever RuntimeError QUE si le module mypy est absent
    (FileNotFoundError sur l'exécutable python, ou le message mypy indiquant l'absence du
    module) — dans ce cas message clair invitant à installer `mypy>=1.10`."""
    commande = ["python3", "-m", "mypy", cible, "--ignore-missing-imports"]
    try:
        resultat = subprocess.run(
            commande,
            cwd=str(racine),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as erreur:
        raise RuntimeError(
            "python3 introuvable ; installer mypy>=1.10 (déjà en dev deps pyproject.toml, "
            "et à ajouter à requirements-ci.in / requirements-ci.txt)"
        ) from erreur

    sortie = resultat.stdout + resultat.stderr
    if "No module named mypy" in sortie or "No module named 'mypy'" in sortie:
        raise RuntimeError(
            "mypy n'est pas installé ; installer mypy>=1.10 (déjà en dev deps pyproject.toml, "
            "et à ajouter à requirements-ci.in / requirements-ci.txt)"
        )
    return sortie


def erreurs_par_fichier(sortie_mypy: str) -> dict[str, int]:
    """Parse le texte de sortie mypy, retourne {chemin_fichier: nombre_erreurs}. Une ligne compte
    SSI elle matche `^(chemin.py):\\d+: error:` — ignorer les lignes `note:` (continuation d'une
    même erreur, mypy peut en émettre plusieurs par erreur) et la ligne de résumé finale
    (`Found N errors in M files...` / `Success: no issues found...`). Fichiers absents du
    résultat = 0 erreur (ne pas les lister)."""
    erreurs: dict[str, int] = {}
    pattern = re.compile(r"^(.+\.py):\d+: error:")
    for ligne in sortie_mypy.splitlines():
        if ligne.startswith("Found ") or ligne.startswith("Success: no issues found"):
            continue
        if ligne.startswith("note:"):
            continue
        correspondance = pattern.match(ligne)
        if correspondance:
            fichier = correspondance.group(1)
            erreurs[fichier] = erreurs.get(fichier, 0) + 1
    return erreurs


def fichiers_reels(racine: Path, cible: str) -> set[str]:
    """rglob('*.py') sous racine/cible, retourne l'ensemble des chemins relatifs à `racine`, en
    POSIX (`/`, jamais `\\`), sous forme de chaînes (ex. "src/forgeai/cli.py")."""
    dossier = racine / cible
    if not dossier.exists():
        return set()
    if not dossier.is_dir():
        raise ValueError(f"cible mypy invalide {str(dossier)!r} : n'est pas un répertoire")
    return {
        p.relative_to(racine).as_posix()
        for p in dossier.rglob("*.py")
        if p.is_file()
    }


def _valider_base(base: Any, libelle: str) -> dict[str, Any]:
    """Valide la structure : `version` (int), `borne.total_erreurs` (int >= 0, pas un bool),
    `fichiers_proteges` (liste de str, sans doublon), `dette` (dict str->int, toutes les valeurs
    > 0, pas de bool). Valide l'invariant de disjonction ci-dessus. Lève ValueError avec message
    explicite sinon. Retourne `base` si valide."""
    if not isinstance(base, dict):
        raise ValueError(f"{libelle} doit etre un objet JSON")

    # version
    version = base.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"{libelle}.version doit etre un entier")

    # borne
    borne = base.get("borne")
    if not isinstance(borne, dict):
        raise ValueError(f"{libelle} doit contenir un objet 'borne'")
    total_erreurs = borne.get("total_erreurs")
    if (
        isinstance(total_erreurs, bool)
        or not isinstance(total_erreurs, int)
        or total_erreurs < 0
    ):
        raise ValueError(
            f"{libelle}.borne.total_erreurs doit etre un entier positif ou nul"
        )

    # fichiers_proteges
    fichiers_proteges = base.get("fichiers_proteges")
    if not isinstance(fichiers_proteges, list) or not all(
        isinstance(f, str) for f in fichiers_proteges
    ):
        raise ValueError(f"{libelle}.fichiers_proteges doit etre une liste de chaines")
    if len(set(fichiers_proteges)) != len(fichiers_proteges):
        raise ValueError(f"{libelle}.fichiers_proteges contient des doublons")

    # dette
    dette = base.get("dette")
    if not isinstance(dette, dict):
        raise ValueError(f"{libelle}.dette doit etre un objet")
    for fichier, plafond in dette.items():
        if not isinstance(fichier, str):
            raise ValueError(f"{libelle}.dette contient une cle non chaine")
        if isinstance(plafond, bool) or not isinstance(plafond, int) or plafond <= 0:
            raise ValueError(
                f"{libelle}.dette[{fichier!r}] doit etre un entier strictement positif"
            )

    # disjonction
    intersection = set(fichiers_proteges) & set(dette.keys())
    if intersection:
        raise ValueError(
            f"{libelle} : les fichiers {sorted(intersection)} sont a la fois "
            "dans fichiers_proteges et dans dette"
        )

    return base


def anomalies(
    reels: set[str],
    erreurs: dict[str, int],
    base: dict[str, Any],
    base_reference: dict[str, Any] | None,
) -> list[str]:
    """Logique pure de comparaison — aucun I/O, aucun subprocess. Valide `base` (et
    `base_reference` si fourni) via `_valider_base`, puis contrôle dans l'ordre :

    1. fichier réel en erreur absent de la base (ni protégé ni en dette) ;
    2. régression sur un fichier protégé (zéro tolérance), ou fichier protégé disparu ;
    3. dette dépassée sur un fichier baseliné, fichier en dette disparu, ou fichier en dette
       redevenu propre (doit alors être retiré — amélioration partielle tolérée, totale ne l'est
       pas silencieusement) ;
    4. borne totale inconditionnelle (mêmes garanties que la borne de gate_docs.py — ne dépend
       d'aucun argument optionnel) ;
    5. si `base_reference` est fourni : toute dette ou borne supérieure à la référence est une
       extension non justifiée (anti-contournement, mirrorant
       gate_docs._charger_base_reference_git).

    Retourne la liste des messages d'anomalie (vide si aucune)."""
    base_validee = _valider_base(base, "base")
    reference_validee = (
        _valider_base(base_reference, "base de reference")
        if base_reference is not None
        else None
    )

    commandes_proteges = set(base_validee["fichiers_proteges"])
    commandes_dette = base_validee["dette"]
    resultat: list[str] = []

    # 1. Nouveau fichier en erreur non baseliné
    for f in sorted(reels):
        n = erreurs.get(f, 0)
        if n > 0 and f not in commandes_proteges and f not in commandes_dette:
            resultat.append(
                f"fichier {f} en erreur ({n}) mais absent de la base (ni protege ni en dette) : "
                "baseliner explicitement ou corriger"
            )

    # 2. Fichiers protégés
    for f in sorted(commandes_proteges):
        n = erreurs.get(f, 0)
        if n > 0:
            resultat.append(
                f"fichier protege {f} desormais en erreur ({n}) : regression interdite"
            )
        if f not in reels:
            resultat.append(f"fichier {f} protege mais absent du depot")

    # 3. Dette
    for f, plafond in sorted(commandes_dette.items()):
        if f not in reels:
            resultat.append(f"fichier {f} baselineé en dette mais absent du depot")
        else:
            actuel = erreurs.get(f, 0)
            if actuel > plafond:
                resultat.append(
                    f"fichier {f} depasse sa dette baselinee ({actuel} > {plafond}) : regression"
                )
            elif actuel == 0:
                resultat.append(
                    f"fichier {f} baselineé en dette mais desormais propre : retirer de la dette "
                    "(la base doit decroitre)"
                )

    # 4. Borne totale inconditionnelle
    borne = base_validee["borne"]["total_erreurs"]
    total_actuel = sum(erreurs.get(f, 0) for f in reels)
    if total_actuel > borne:
        resultat.append(
            f"le total mypy est de {total_actuel} erreurs alors que la borne est fixee a {borne} : "
            "toute nouvelle erreur doit etre corrigee, jamais simplement re-baselinee (rebaser la "
            "borne exige de documenter la regression, pas de l'etendre)"
        )

    # 5. Comparaison avec la référence
    if reference_validee is not None:
        ref_proteges = set(reference_validee["fichiers_proteges"])
        ref_dette = reference_validee["dette"]

        for f, plafond in sorted(commandes_dette.items()):
            if f in ref_dette and plafond > ref_dette[f]:
                resultat.append(
                    f"dette baselinee pour {f} augmentee depuis la reference ({plafond} > "
                    f"{ref_dette[f]}) : la base doit decroitre, jamais s'etendre"
                )
            if f not in ref_dette and f not in ref_proteges:
                resultat.append(
                    f"fichier {f} ajoute a la dette baselinee, absent de la base de reference : "
                    "extension non justifiee"
                )

        if base_validee["borne"]["total_erreurs"] > reference_validee["borne"]["total_erreurs"]:
            resultat.append(
                f"borne totale augmentee depuis la reference ({base_validee['borne']['total_erreurs']} > "
                f"{reference_validee['borne']['total_erreurs']}) : extension non justifiee"
            )

    return resultat


def _charger_json(chemin: Path, libelle: str) -> dict[str, Any]:
    """Charge et valide le JSON d'une base."""
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
    """Charge la base depuis une reference git deja resolue."""
    _valider_ref_git(ref)  # AVANT tout subprocess : refuse une injection d'option git
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=str(racine),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as erreur:
        raise RuntimeError(
            f"git indisponible pour la reference {ref!r} ; "
            "le job CI doit utiliser fetch-depth: 0."
        ) from erreur
    except subprocess.CalledProcessError as erreur:
        raise RuntimeError(
            f"reference git {ref!r} inaccessible ; "
            "le job CI doit utiliser fetch-depth: 0."
        ) from erreur

    try:
        chemin_git = chemin_base.resolve().relative_to(racine.resolve()).as_posix()
    except ValueError as erreur:
        raise ValueError(
            f"base {str(chemin_base)!r} hors de la racine git {str(racine)!r}"
        ) from erreur

    try:
        resultat = subprocess.run(
            ["git", "show", f"{ref}:{chemin_git}"],
            cwd=str(racine),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as erreur:
        raise RuntimeError(
            "git indisponible pour lire la base de reference ; "
            "le job CI doit utiliser fetch-depth: 0."
        ) from erreur
    except subprocess.CalledProcessError:
        return (
            None,
            "base de reference absente a cette ref : le controle de "
            "non-croissance est inapplicable (premiere introduction).",
        )

    try:
        contenu = json.loads(resultat.stdout)
    except (json.JSONDecodeError, UnicodeError) as erreur:
        raise ValueError(
            f"base de reference git JSON invalide {chemin_git!r} sur {ref!r} : "
            f"{erreur}"
        ) from erreur

    return _valider_base(contenu, "base de reference git"), ""


def main(argv: list[str] | None = None) -> int:
    """Execute le gate de cliquet mypy progressif."""
    parser = argparse.ArgumentParser(
        description="Controle le cliquet mypy progressif de ForgeAI."
    )
    parser.add_argument("--racine", default=".", help="racine du depot")
    parser.add_argument(
        "--base",
        default="Docs/BASELINE-MYPY.json",
        help="base JSON du cliquet mypy",
    )
    parser.add_argument(
        "--cible",
        default="src/forgeai",
        help="cible mypy (chemin relatif a --racine)",
    )
    parser.add_argument(
        "--base-ref-git",
        metavar="REF",
        help="reference git de la base pour le controle de non-croissance",
    )
    parser.add_argument(
        "--rapport-json",
        metavar="CHEMIN",
        help="chemin du rapport JSON machine a ecrire (optionnel)",
    )
    arguments = parser.parse_args(argv)

    racine = Path(arguments.racine)
    chemin_base = Path(arguments.base)
    if not chemin_base.is_absolute():
        chemin_base = racine / chemin_base

    try:
        base = _charger_json(chemin_base, "base")
        sortie_mypy = executer_mypy(racine, arguments.cible)
        erreurs = erreurs_par_fichier(sortie_mypy)
        reels = fichiers_reels(racine, arguments.cible)

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

        rapport = anomalies(reels, erreurs, base, base_reference)
    except (OSError, TypeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    total = sum(erreurs.get(f, 0) for f in reels)
    n_dette = len(base["dette"])
    n_proteges = len(base["fichiers_proteges"])
    for anomalie in rapport:
        print(anomalie)
    print(
        f"— {total} erreur(s) mypy sur {n_dette} fichier(s) en dette (borne "
        f"{base['borne']['total_erreurs']}), {n_proteges} fichier(s) proteges a zero tolerance"
    )

    if arguments.rapport_json:
        rapport_json: dict[str, Any] = {
            "total_erreurs": total,
            "erreurs_par_fichier": {f: n for f, n in erreurs.items() if n > 0},
            "anomalies": rapport,
            "fichiers_proteges": n_proteges,
            "fichiers_en_dette": n_dette,
        }
        with open(arguments.rapport_json, "w", encoding="utf-8") as fh:
            json.dump(rapport_json, fh, indent=2)
            fh.write("\n")

    return 1 if rapport else 0


if __name__ == "__main__":
    raise SystemExit(main())
