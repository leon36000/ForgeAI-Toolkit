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

import gate_git_ref


# SonarCloud pythonsecurity:S8705 (New Code, #449 — suppression sonar-project.properties e8,
# même famille que e6 sur gate_docs.py) : `cible` est un argument CLI arbitraire injecté tel quel
# dans un argv `python3 -m mypy`. Validée ci-dessous AVANT tout subprocess dans executer_mypy.
def _valider_cible(cible: str) -> None:
    """Refuse une cible mypy vide ou commençant par '-' (injection d'option subprocess)."""
    if not cible or cible.startswith("-"):
        raise ValueError(f"cible mypy invalide {cible!r} : refusee avant tout appel subprocess")


def executer_mypy(racine: Path, cible: str) -> str:
    """Lance `<interpréteur courant> -m mypy <cible> --config-file=` (cwd=racine),
    capture stdout+stderr, retourne le texte combiné. Utilise sys.executable, pas python3 en dur.
    Le `--config-file=` explicite empêche toute config mypy du dépôt (présente ou future)
    d'être silencieusement chargée — c'est une garantie d'intégrité de l'analyse elle-même.
    mypy sort avec un code non-nul QUAND IL TROUVE DES ERREURS DE TYPE — c'est le cas normal
    attendu, PAS une exception : ne jamais lever sur un exit code mypy non-nul en soi. Ne lever
    RuntimeError QUE si l'interpréteur est introuvable (FileNotFoundError sur sys.executable) ou
    si le module mypy est absent (message mypy indiquant l'absence du module) — dans ce cas
    message clair invitant à installer `mypy>=1.10`."""
    _valider_cible(cible)
    commande = [sys.executable, "-m", "mypy", cible, "--config-file="]
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
            "interpreteur Python introuvable (sys.executable) ; installer mypy>=1.10 "
            "(déjà en dev deps pyproject.toml, et à ajouter à requirements-ci.in / "
            "requirements-ci.txt)"
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
    SSI elle matche `^(chemin.py):\\d+: error:` ou `^(chemin.pyi):\\d+: error:` — ignorer les
    lignes `note:` (continuation d'une même erreur, mypy peut en émettre plusieurs par erreur) et
    la ligne de résumé finale (`Found N errors in M files...` / `Success: no issues found...`).
    Fichiers absents du résultat = 0 erreur (ne pas les lister)."""
    erreurs: dict[str, int] = {}
    pattern = re.compile(r"^(.+\.pyi?):\d+: error:")
    for ligne in sortie_mypy.splitlines():
        if ligne.startswith(("Found ", "Success: no issues found")):
            continue
        if ligne.startswith("note:"):
            continue
        correspondance = pattern.match(ligne)
        if correspondance:
            fichier = correspondance.group(1)
            erreurs[fichier] = erreurs.get(fichier, 0) + 1
    return erreurs


def fichiers_reels(racine: Path, cible: str) -> set[str]:
    """rglob('*.py') et rglob('*.pyi') sous racine/cible, retourne l'ensemble des chemins relatifs
    à `racine`, en POSIX (`/`, jamais `\\`), sous forme de chaînes (ex. "src/forgeai/cli.py"),
    incluant donc les stubs `.pyi`."""
    dossier = racine / cible
    if not dossier.exists():
        return set()
    if not dossier.is_dir():
        raise ValueError(f"cible mypy invalide {str(dossier)!r} : n'est pas un répertoire")
    fichiers: set[str] = set()
    for motif in ("*.py", "*.pyi"):
        for p in dossier.rglob(motif):
            if p.is_file():
                fichiers.add(p.relative_to(racine).as_posix())
    return fichiers


def _valider_borne(borne: Any, libelle: str) -> int:
    """Valide l'objet `borne` (dict avec `total_erreurs` int >= 0 non-bool) et retourne
    `total_erreurs`. Lève ValueError avec message explicite sinon."""
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
    return total_erreurs


def _valider_fichiers_proteges(fichiers_proteges: Any, libelle: str) -> list[str]:
    """Valide `fichiers_proteges` (liste de str sans doublon) et la retourne."""
    if not isinstance(fichiers_proteges, list) or not all(
        isinstance(f, str) for f in fichiers_proteges
    ):
        raise ValueError(f"{libelle}.fichiers_proteges doit etre une liste de chaines")
    if len(set(fichiers_proteges)) != len(fichiers_proteges):
        raise ValueError(f"{libelle}.fichiers_proteges contient des doublons")
    return fichiers_proteges


def _valider_dette(dette: Any, libelle: str) -> dict[str, int]:
    """Valide `dette` (dict str->int>0 non-bool) et la retourne."""
    if not isinstance(dette, dict):
        raise ValueError(f"{libelle}.dette doit etre un objet")
    for fichier, plafond in dette.items():
        if not isinstance(fichier, str):
            raise ValueError(f"{libelle}.dette contient une cle non chaine")
        if isinstance(plafond, bool) or not isinstance(plafond, int) or plafond <= 0:
            raise ValueError(
                f"{libelle}.dette[{fichier!r}] doit etre un entier strictement positif"
            )
    return dette


def _valider_classification(
    classification: Any, dette: dict[str, int], libelle: str
) -> dict[str, dict[str, int]]:
    """Valide la classification mypy optionnelle. Si absente ou null, retourne {}.

    Si présente : doit être un dict dont les clés correspondent exactement aux clés de `dette`.
    Pour chaque fichier, la valeur doit être un dict `code mypy -> compte`, chaque compte
    strictement positif non booléen, et la somme des comptes doit égaler la dette du fichier.
    Lève ValueError avec message explicite selon la violation (clés manquantes/en trop, valeur
    non positive, somme incohérente). La classification reste informationnelle.
    """
    if classification is None:
        return {}

    if not isinstance(classification, dict):
        raise ValueError(f"{libelle}.classification doit etre un objet")

    cle_classification = set(classification.keys())
    cle_dette = set(dette.keys())
    if cle_classification != cle_dette:
        manquantes = sorted(cle_dette - cle_classification)
        en_trop = sorted(cle_classification - cle_dette)
        details: list[str] = []
        if manquantes:
            details.append(f"manquantes pour {manquantes}")
        if en_trop:
            details.append(f"en trop pour {en_trop}")
        raise ValueError(
            f"{libelle}.classification : cles incoherentes avec dette ({', '.join(details)})"
        )

    for fichier, plafond in dette.items():
        comptes = classification[fichier]
        if not isinstance(comptes, dict):
            raise ValueError(
                f"{libelle}.classification[{fichier!r}] doit etre un objet"
            )
        for code, compte in comptes.items():
            if not isinstance(code, str):
                raise ValueError(
                    f"{libelle}.classification[{fichier!r}] contient un code non chaine"
                )
            if isinstance(compte, bool) or not isinstance(compte, int) or compte <= 0:
                raise ValueError(
                    f"{libelle}.classification[{fichier!r}][{code!r}] doit etre un "
                    "entier strictement positif"
                )
        total = sum(comptes.values())
        if total != plafond:
            raise ValueError(
                f"{libelle}.classification[{fichier!r}] : somme des codes ({total}) "
                f"incoherente avec dette ({plafond})"
            )

    return classification


def _valider_base(base: Any, libelle: str) -> dict[str, Any]:
    """Valide la structure : `version` (int), `borne.total_erreurs` (int >= 0, pas un bool),
    `fichiers_proteges` (liste de str, sans doublon), `dette` (dict str->int, toutes les valeurs
    > 0, pas de bool), `classification` optionnelle (dict cohérent avec `dette`). Valide
    l'invariant de disjonction ci-dessus. Lève ValueError avec message explicite sinon. Retourne
    `base` si valide."""
    if not isinstance(base, dict):
        raise ValueError(f"{libelle} doit etre un objet JSON")

    # version
    version = base.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"{libelle}.version doit etre un entier")

    # borne
    _valider_borne(base.get("borne"), libelle)

    # fichiers_proteges
    fichiers_proteges = _valider_fichiers_proteges(
        base.get("fichiers_proteges"), libelle
    )

    # dette
    dette = _valider_dette(base.get("dette"), libelle)

    # disjonction
    intersection = set(fichiers_proteges) & set(dette.keys())
    if intersection:
        raise ValueError(
            f"{libelle} : les fichiers {sorted(intersection)} sont a la fois "
            "dans fichiers_proteges et dans dette"
        )

    # classification (optionnelle, uniquement validée si présente)
    _valider_classification(base.get("classification"), dette, libelle)

    return base


def _anomalies_non_baselinees(
    reels: set[str],
    erreurs: dict[str, int],
    proteges: set[str],
    dette: dict[str, int],
) -> list[str]:
    """Règle 1 : fichier réel en erreur absent de la base (ni protégé ni en dette)."""
    resultat: list[str] = []
    for f in sorted(reels):
        n = erreurs.get(f, 0)
        if n > 0 and f not in proteges and f not in dette:
            resultat.append(
                f"fichier {f} en erreur ({n}) mais absent de la base (ni protege ni en dette) : "
                "baseliner explicitement ou corriger"
            )
    return resultat


def _anomalies_proteges(
    reels: set[str],
    erreurs: dict[str, int],
    proteges: set[str],
) -> list[str]:
    """Règle 2 : régression sur un fichier protégé, ou fichier protégé disparu."""
    resultat: list[str] = []
    for f in sorted(proteges):
        n = erreurs.get(f, 0)
        if n > 0:
            resultat.append(
                f"fichier protege {f} desormais en erreur ({n}) : regression interdite"
            )
        if f not in reels:
            resultat.append(f"fichier {f} protege mais absent du depot")
    return resultat


def _anomalies_dette(
    reels: set[str],
    erreurs: dict[str, int],
    dette: dict[str, int],
) -> list[str]:
    """Règle 3 : dette dépassée, fichier en dette disparu, ou fichier devenu propre."""
    resultat: list[str] = []
    for f, plafond in sorted(dette.items()):
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
    return resultat


def _anomalie_borne_totale(
    reels: set[str],
    erreurs: dict[str, int],
    borne: int,
) -> list[str]:
    """Règle 4 : borne totale inconditionnelle (liste de 0 ou 1 élément)."""
    total_actuel = sum(erreurs.get(f, 0) for f in reels)
    if total_actuel > borne:
        return [
            f"le total mypy est de {total_actuel} erreurs alors que la borne est fixee a {borne} : "
            "toute nouvelle erreur doit etre corrigee, jamais simplement re-baselinee (rebaser la "
            "borne exige de documenter la regression, pas de l'etendre)"
        ]
    return []


def _anomalies_reference(
    dette: dict[str, int],
    borne_totale: int,
    reference: dict[str, Any],
    proteges: set[str],
) -> list[str]:
    """Règle 5 : comparaison avec la base de référence — aucune croissance non justifiée
    (dette ou borne), protection permanente des fichiers_proteges, et interdiction de retirer
    silencieusement un fichier de la dette référencée sans le promouvoir aux fichiers_proteges."""
    resultat: list[str] = []
    ref_proteges = set(reference["fichiers_proteges"])
    ref_dette = reference["dette"]

    for f in sorted(ref_proteges):
        if f not in proteges:
            resultat.append(
                f"fichier {f} retire de la protection depuis la reference (etait dans "
                "fichiers_proteges) : la protection est permanente, jamais retiree"
            )

    for f in sorted(ref_dette):
        if f not in dette and f not in proteges:
            resultat.append(
                f"fichier {f} retire de la dette referencee sans etre promu aux fichiers proteges : "
                "suppression de tracking non justifiee"
            )

    for f, plafond in sorted(dette.items()):
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

    if borne_totale > reference["borne"]["total_erreurs"]:
        resultat.append(
            f"borne totale augmentee depuis la reference ({borne_totale} > "
            f"{reference['borne']['total_erreurs']}) : extension non justifiee"
        )

    return resultat


def anomalies(
    reels: set[str],
    erreurs: dict[str, int],
    base: dict[str, Any],
    base_reference: dict[str, Any] | None,
    neutralises: set[str] | None = None,
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
       extension non justifiée ; tout fichier protégé dans la référence doit rester protégé
       dans la base courante ; et tout fichier présent dans la dette de la référence doit
       demeurer suivi (soit en dette, soit promu aux fichiers_proteges) — toute disparition
       silencieuse du tracking est une anomalie (anti-contournement, mirrorant
       gate_docs._charger_base_reference_git).
    6. si `neutralises` est fourni : tout fichier protégé listé dans `neutralises` est signalé
       comme contenant une directive de neutralisation mypy (`# mypy: ignore-errors`) — la
       protection est compromise car mypy ne remontera aucune erreur sur ce fichier.

    Retourne la liste des messages d'anomalie (vide si aucune)."""
    base_validee = _valider_base(base, "base")
    reference_validee = (
        _valider_base(base_reference, "base de reference")
        if base_reference is not None
        else None
    )

    proteges = set(base_validee["fichiers_proteges"])
    dette = base_validee["dette"]
    resultat: list[str] = []

    resultat.extend(_anomalies_non_baselinees(reels, erreurs, proteges, dette))
    resultat.extend(_anomalies_proteges(reels, erreurs, proteges))
    resultat.extend(_anomalies_dette(reels, erreurs, dette))
    resultat.extend(
        _anomalie_borne_totale(reels, erreurs, base_validee["borne"]["total_erreurs"])
    )
    if reference_validee is not None:
        resultat.extend(
            _anomalies_reference(
                dette,
                base_validee["borne"]["total_erreurs"],
                reference_validee,
                proteges,
            )
        )
    if neutralises is not None:
        for f in sorted(neutralises):
            resultat.append(
                f"fichier protege {f} contient une directive mypy inline (# mypy: ...) : "
                "protection compromise, retirer la directive ou le fichier de fichiers_proteges"
            )

    return resultat


def _charger_json(chemin: Path, libelle: str) -> dict[str, Any]:
    """Charge et valide le JSON d'une base."""
    # SonarCloud pythonsecurity:S8707 (New Code, #449 — suppression sonar-project.properties e9,
    # même famille que e5/e7) : validé explicitement AVANT tout accès disque (is_file() ci-dessus),
    # plutôt que de se reposer uniquement sur l'OSError attrapée plus bas.
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


def _valider_chemin_rapport(chemin: str) -> Path:
    """Valide le chemin de sortie du rapport JSON : le parent doit exister."""
    chemin_resolu = Path(chemin).resolve()
    if not chemin_resolu.parent.is_dir():
        raise ValueError(
            f"répertoire parent introuvable pour --rapport-json {chemin!r}"
        )
    return chemin_resolu


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
            base_reference, message_reference = gate_git_ref.charger_base_reference_git(
                racine,
                chemin_base,
                arguments.base_ref_git,
                _valider_base,
            )

        if message_reference:
            print(message_reference)

        neutralises = fichiers_proteges_neutralises(racine, set(base["fichiers_proteges"]))
        rapport = anomalies(reels, erreurs, base, base_reference, neutralises=neutralises)

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
            chemin_rapport = _valider_chemin_rapport(arguments.rapport_json)
            rapport_json: dict[str, Any] = {
                "total_erreurs": total,
                "erreurs_par_fichier": {f: n for f, n in erreurs.items() if n > 0},
                "anomalies": rapport,
                "fichiers_proteges": n_proteges,
                "fichiers_en_dette": n_dette,
                "classification": base.get("classification", {}),
            }
            with open(chemin_rapport, "w", encoding="utf-8") as fh:
                json.dump(rapport_json, fh, indent=2)
                fh.write("\n")
    except (OSError, TypeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    return 1 if rapport else 0


# Correctif post-revue scellée #449 (round 6/7/8, REJECT de GPT-5.6-Terra-Pro) — `scripts/mypy_gate.py`
# (La fonction fichiers_proteges_neutralises et la regex sont définies ci-dessous, avant main)
# La recherche se fait sur les octets bruts (`read_bytes`) pour être indépendante de l'encodage
# déclaré du fichier (PEP-263) ; toute directive mypy inline étant purement ASCII, une regex bytes
# la détecte quel que soit l'encodage, contrairement à une lecture texte qui lèverait
# UnicodeDecodeError sur un fichier latin-1/cp1252 avec octets non UTF-8.
# Round 8 : la directive `# mypy:` est généralisée à TOUTE option mypy — un fichier protégé n'a
# jamais besoin d'une directive mypy inline, donc toute occurrence `# mypy: <...>` y est suspecte.
_DIRECTIVE_NEUTRALISATION = re.compile(rb"#\s*mypy:\s*\S")


def fichiers_proteges_neutralises(racine: Path, proteges: set[str]) -> set[str]:
    """Scanne le contenu de chaque fichier de `proteges` (qui existe dans `racine`) à la
    recherche de toute directive mypy inline `# mypy: <...>` (n'importe où dans le fichier,
    mypy ne l'exige pas en première ligne). Retourne l'ensemble des fichiers protégés
    contenant une telle directive — un fichier protégé n'a jamais besoin d'une directive mypy
    inline, donc toute occurrence est traitée comme suspecte par principe, quelle que soit
    l'option nommée, plutôt que d'énumérer des noms d'options spécifiques qui deviendraient
    vite obsolètes ou incomplets. La lecture est effectuée en octets bruts (`read_bytes()`),
    sans décodage, afin de rester indépendante de l'encodage déclaré du fichier (PEP-263) ;
    la directive étant composée uniquement de caractères ASCII, une recherche bytes la détecte
    toujours, même pour un fichier latin-1/cp1252 qui ferait échouer une lecture texte UTF-8.
    Fichier illisible ou absent : ignoré silencieusement (déjà couvert par une autre règle si
    le fichier a disparu)."""
    resultat: set[str] = set()
    for f in proteges:
        chemin = racine / f
        try:
            donnees = chemin.read_bytes()
        except OSError:
            continue
        if _DIRECTIVE_NEUTRALISATION.search(donnees):
            resultat.add(f)
    return resultat


if __name__ == "__main__":
    raise SystemExit(main())
