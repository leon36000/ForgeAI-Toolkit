#!/usr/bin/env python3
"""Partage de la validation et du chargement d'une base de cliquet depuis une référence git.

Extrait depuis `gate_docs.py` et `mypy_gate.py` (correctif SonarCloud #449) pour supprimer la
duplication. Ce module est en dessous des deux gates dans le graphe de dépendances : il ne
connaît aucun des schémas JSON des bases spécialisées. La validation du JSON est donc injectée
par l'appelant via `valider_base`.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

# SonarCloud pythonsecurity:S8705 (New Code, issue #385) : `--base-ref-git` est un argument
# CLI arbitraire injecté tel quel dans un argv `git`. En usage CI réel, gates.yml le fixe à
# "origin/main" (non attaquable), mais le script reste un outil général invocable avec
# n'importe quelle valeur — un ref commençant par "-" serait interprété comme une OPTION git
# (injection d'argument, ex. "--upload-pack=...") plutôt que comme un nom de référence.
REF_GIT_VALIDE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]*$")


def valider_ref_git(ref: str) -> None:
    """Refuse tout ref commençant par '-' (injection d'option git) ou contenant un
    caractère hors de l'ensemble attendu pour un nom de référence git."""
    if not ref or ref.startswith("-") or not REF_GIT_VALIDE.match(ref):
        raise ValueError(f"reference git invalide {ref!r} : refusee avant tout appel git")


def charger_base_reference_git(
    racine: Path,
    chemin_base: Path,
    ref: str,
    valider_base: Callable[[Any, str], dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    """Charge la base depuis une référence git déjà résolue.

    `valider_base` est la fonction de validation du schéma JSON de la base spécialisée
    (`_valider_base` de `gate_docs` ou de `mypy_gate`). Ce module partagé ne doit pas
    dépendre d'un schéma particulier.
    """
    valider_ref_git(ref)  # AVANT tout subprocess : refuse une injection d'option git
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

    return valider_base(contenu, "base de reference git"), ""
