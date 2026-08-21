#!/usr/bin/env python3
"""Campagne de mutation ciblée et bloquante pour les gardes du rate limiter.

Chaque mutation est volontaire, bornée à un site de décision critique et exécutée dans une
copie temporaire du paquet ``src``. Une mutation qui laisse la suite ciblée verte est un
mutant survivant : le rapport le conserve comme disposition ``FAIL`` et la commande retourne
un code non nul. Le job CI peut donc prouver que supprimer une garde importante rend le job
rouge, sans modifier le worktree ni dépendre d'un état de mutation persistant.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mutation:
    identifiant: str
    fichier: str
    avant: str
    apres: str
    contrat: str


def _metadonnees_rapport(mutation: Mutation) -> dict[str, str]:
    """Sélectionne les métadonnées utiles sans recopier le texte muté."""
    return {
        "identifiant": mutation.identifiant,
        "fichier": mutation.fichier,
        "contrat": mutation.contrat,
    }


MUTATIONS = (
    Mutation(
        "loopback-bypass-inverse",
        "src/forgeai/web/ratelimit.py",
        "if is_loopback:",
        "if not is_loopback:",
        "une requête loopback saine reste exemptée du bucket global",
    ),
    Mutation(
        "lockout-seuil-strict",
        "src/forgeai/web/ratelimit.py",
        'if len(state["failures"]) >= self.auth_max:',
        'if len(state["failures"]) > self.auth_max:',
        "le seuil auth_max arme le lockout dès le dernier échec requis",
    ),
    Mutation(
        "zero-rate-max-autorise",
        "src/forgeai/web/ratelimit.py",
        "if self.rate_max <= 0:",
        "if self.rate_max < 0:",
        "rate_max nul refuse toujours le trafic distant sans division par zéro",
    ),
)


def _copie_de_test(racine: Path, mutation: Mutation) -> Path:
    travail = Path(tempfile.mkdtemp(prefix="forgeai-mutation-"))
    try:
        shutil.copytree(
            racine / "src",
            travail / "src",
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
        )
        shutil.copytree(racine / "tests", travail / "tests", ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", "*.pyc"
        ))
        # Rejoue la configuration pytest du dépôt pour que la copie conserve les mêmes
        # options de découverte et de warnings que la suite principale.
        for nom in ("pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg", "conftest.py"):
            source = racine / nom
            if source.is_file():
                shutil.copy2(source, travail / nom)
        cible = travail / mutation.fichier
        contenu = cible.read_text(encoding="utf-8")
        occurrences = contenu.count(mutation.avant)
        if occurrences != 1:
            raise RuntimeError(
                f"{mutation.identifiant}: site de mutation non unique ({occurrences})"
            )
        cible.write_text(contenu.replace(mutation.avant, mutation.apres, 1), encoding="utf-8")
        return travail
    except Exception:
        shutil.rmtree(travail, ignore_errors=True)
        raise


def executer_mutation(racine: Path, mutation: Mutation, timeout: int = 180) -> dict[str, object]:
    travail = _copie_de_test(racine, mutation)
    try:
        environnement = os.environ.copy()
        chemins_python = [str(travail / "src")]
        ancien_pythonpath = environnement.get("PYTHONPATH")
        if ancien_pythonpath:
            chemins_python.append(ancien_pythonpath)
        environnement["PYTHONPATH"] = os.pathsep.join(chemins_python)
        try:
            resultat = subprocess.run(  # noqa: S603 — commande et arguments constants, copie temporaire contrôlée (révision: 2026-08-21)
                [sys.executable, "-m", "pytest", "-q", "tests/test_ratelimit.py"],
                cwd=travail,
                env=environnement,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                **_metadonnees_rapport(mutation),
                "statut": "runner-error",
                "disposition": "FAIL: délai dépassé du runner pytest",
                "code_retour": None,
                "sortie_tail": f"pytest a dépassé le délai configuré ({timeout}s)",
            }
        # pytest code 1 signifie qu'un test a échoué : le mutant est effectivement tué.
        # Les autres codes non nuls signalent une erreur du runner (usage, interruption,
        # erreur interne ou absence de tests) et doivent faire échouer la campagne, jamais
        # être transformés en preuve de mutation efficace.
        if resultat.returncode == 0:
            statut = "survived"
            disposition = "FAIL: mutant survivant"
        elif resultat.returncode == 1:
            statut = "killed"
            disposition = "PASS"
        else:
            statut = "runner-error"
            disposition = f"FAIL: erreur du runner pytest ({resultat.returncode})"
        return {
            **_metadonnees_rapport(mutation),
            "statut": statut,
            "disposition": disposition,
            "code_retour": resultat.returncode,
            "sortie_tail": (
                "pytest a réussi; sortie omise"
                if resultat.returncode == 0
                else f"pytest a échoué (code {resultat.returncode}); sortie omise"
            ),
        }
    finally:
        shutil.rmtree(travail, ignore_errors=True)


def campagne(racine: Path) -> dict[str, object]:
    resultats = []
    for mutation in MUTATIONS:
        try:
            resultats.append(executer_mutation(racine, mutation))
        except Exception:
            # Une erreur de préparation (source absente, site non unique, copie illisible)
            # est une panne de campagne, pas un mutant tué; elle doit néanmoins rester dans
            # le rapport pour que l'artefact CI soit exploitable.
            resultats.append(
                {
                    **_metadonnees_rapport(mutation),
                    "statut": "runner-error",
                    "disposition": "FAIL: erreur de préparation de la campagne",
                    "code_retour": None,
                    "sortie_tail": "échec lors de la préparation d'un mutant",
                }
            )
    survivants = [r for r in resultats if r["statut"] == "survived"]
    erreurs_runner = [r for r in resultats if r["statut"] == "runner-error"]
    return {
        "_schema": "mutation-gate-v1",
        "cible": "src/forgeai/web/ratelimit.py",
        "mutants": resultats,
        "total": len(resultats),
        "tues": sum(r["statut"] == "killed" for r in resultats),
        "survivants": len(survivants),
        "erreurs_runner": len(erreurs_runner),
        "statut": "PASS" if not survivants and not erreurs_runner else "FAIL",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--racine", type=Path, default=Path("."))
    parser.add_argument("--sortie-json", type=Path)
    args = parser.parse_args(argv)
    rapport = campagne(args.racine.resolve())
    texte = json.dumps(rapport, ensure_ascii=False, indent=2) + "\n"
    if args.sortie_json:
        sortie = args.sortie_json if args.sortie_json.is_absolute() else args.racine / args.sortie_json
        sortie.parent.mkdir(parents=True, exist_ok=True)
        sortie.write_text(texte, encoding="utf-8")
    print(texte, end="")
    return 0 if rapport["statut"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
