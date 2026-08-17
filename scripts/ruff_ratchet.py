#!/usr/bin/env python3
"""Cliquet Ruff bloquant sur les règles « defaut_candidat » (RC1-020, #450, incrément 2).

L'incrément 1 a livré `scripts/ruff_report.py` : mesure et catégorisation informationnelles,
jamais bloquantes. Cet incrément livre le mécanisme de cliquet proprement dit — bloquant en CI —
mais UNIQUEMENT sur le sous-ensemble de règles classées `"categorie": "defaut_candidat"` dans
`governance/ruff-classification.json`. Ce sous-ensemble est dérivé dynamiquement à chaque
exécution (jamais codé en dur), pour rester synchronisé si un futur incrément reclasse un code.
`[tool.ruff.lint] select` dans `pyproject.toml` reste `["E9", "F"]`, inchangé.

Philosophie reprise de `scripts/mypy_gate.py` (#449, cliquet mypy en production) : baseline JSON
commitée (`governance/ruff-baseline.json`) avec borne totale + dette par fichier, et contrôle de
non-croissance contre une référence git (`origin/main` par défaut) via le module partagé
`gate_git_ref.py` — aucune réinvention de cette partie. Deux simplifications assumées par rapport
à mypy_gate : pas de liste `fichiers_proteges` séparée (un fichier absent de `dette` a
implicitement un plafond de 0 — même garantie, structure plus simple) et aucun suivi des
suppressions `# noqa` (hors périmètre explicite de cet incrément : ruff les applique nativement,
une ligne supprimée par `# noqa` n'apparaît simplement pas dans la sortie JSON de `ruff check`).
Une granularité en revanche ajoutée : la dette est bornée À LA FOIS par fichier (`dette`) ET par
couple (fichier, règle) (`classification`, champ OBLIGATOIRE ici — alors qu'il est optionnel et
seulement informationnel dans mypy_gate).

En fonctionnement normal, ce script ne fait que LIRE et VALIDER la baseline : il ne modifie
jamais de fichier source et n'appelle jamais `ruff --fix`. La SEULE exception est le mode de
maintenance explicite `--regenerer-baseline` (opération déclarée, review-visible via le diff git
du fichier généré, toujours suivie d'une revue humaine/scellée avant merge, jamais automatique
en CI), qui réécrit intégralement la baseline depuis une mesure fraîche — la baseline reste un
artefact commité, symétriquement à `Docs/BASELINE-MYPY.json` pour `mypy_gate.py`.

LIMITE RÉSIDUELLE ASSUMÉE (même nature que celle documentée dans `mypy_gate.py` pour
`type_ignore_lignes`) : la règle 4 (comparaison par couple fichier/règle) ne parcourt que les
couples déjà présents dans `classification` de la base — un couple retiré de `classification`
tout en gonflant artificiellement le plafond d'un AUTRE code du même fichier, pour absorber le
compte sans faire décroître `dette[fichier]`, échapperait à cette règle précise. Rule 2 (dette
totale par fichier) reste néanmoins le filet de sécurité : elle capture toute régression réelle
tant que le total mesuré dépasse le total baseliné. Fermer ce résidu exigerait une comparaison
par provenance (diff git réel), hors périmètre de cet incrément — et une telle manipulation du
JSON commité devrait de toute façon survivre à la revue scellée à 3 vendors sur le diff réel.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import gate_git_ref


def _charger_json(chemin: Path) -> dict[str, Any]:
    """Charge un fichier JSON (classification Ruff ou baseline) et garantit un objet JSON racine.

    Ré-implémentation locale volontairement identique à celle de `ruff_report.py` : les deux
    scripts restent indépendants l'un de l'autre, aucun import croisé.
    """
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError as erreur:
        raise ValueError(f"fichier JSON introuvable : {str(chemin)!r}") from erreur
    except (OSError, UnicodeError) as erreur:
        raise ValueError(f"fichier JSON illisible {str(chemin)!r} : {erreur}") from erreur
    except json.JSONDecodeError as erreur:
        raise ValueError(f"fichier JSON invalide {str(chemin)!r} : {erreur}") from erreur

    if not isinstance(contenu, dict):
        raise ValueError(f"le contenu de {str(chemin)!r} doit être un objet JSON")
    return contenu


def regles_defaut_candidat(classification_ruff: dict[str, Any]) -> list[str]:
    """Dérive dynamiquement, depuis le contenu déjà chargé de
    `governance/ruff-classification.json` (le dict Python, pas un chemin), la liste TRIÉE
    alphabétiquement des codes dont `regles[code]["categorie"] == "defaut_candidat"`. Lève
    ValueError si le résultat est vide (classification vide ou champ `regles` absent) : jamais de
    cliquet actif sur un ensemble de règles vide — ce serait un cliquet qui ne cliquette sur
    rien."""
    regles = classification_ruff.get("regles")
    resultat: list[str] = []
    if isinstance(regles, dict):
        for code, definition in regles.items():
            if (
                isinstance(code, str)
                and isinstance(definition, dict)
                and definition.get("categorie") == "defaut_candidat"
            ):
                resultat.append(code)
    resultat.sort()
    if not resultat:
        raise ValueError(
            "aucune regle categorisee 'defaut_candidat' dans la classification Ruff : "
            "le cliquet ne peut pas s'appliquer sur un ensemble de regles vide"
        )
    return resultat


def mesurer(racine: Path, regles: list[str]) -> list[dict[str, Any]]:
    """Exécute `ruff check --no-cache --output-format=json --select <regles> src scripts`
    (cwd=`racine`) et retourne les violations détectées. Quasiment identique à `mesurer()` de
    `ruff_report.py` (même gestion d'erreurs : ruff absent → RuntimeError, code de sortie hors
    0/1 → RuntimeError, JSON invalide → RuntimeError, sortie non-liste → RuntimeError), mais
    paramétrée par la liste `regles` reçue en argument — aucune constante globale figée au
    chargement du module. Les chemins absolus renvoyés par ruff (dépendants de la machine) sont
    normalisés en relatif POSIX à `racine`, pour une comparaison stable avec la baseline."""
    commande = [
        "ruff",
        "check",
        "--no-cache",
        "--output-format=json",
        "--select",
        ",".join(regles),
        "src",
        "scripts",
    ]

    try:
        resultat = subprocess.run(
            commande,
            cwd=str(racine),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as erreur:
        raise RuntimeError(
            "ruff est indisponible : vérifiez son installation et le PATH"
        ) from erreur
    except OSError as erreur:
        raise RuntimeError(f"impossible d'exécuter ruff : {erreur}") from erreur

    if resultat.returncode not in (0, 1):
        details = resultat.stderr.strip()
        suffixe = f" : {details}" if details else ""
        raise RuntimeError(
            f"ruff a échoué avec le code {resultat.returncode}{suffixe}"
        )

    try:
        violations = json.loads(resultat.stdout)
    except json.JSONDecodeError as erreur:
        details = resultat.stderr.strip()
        suffixe = f" ({details})" if details else ""
        raise RuntimeError(
            f"la sortie JSON de ruff est invalide{suffixe} : {erreur}"
        ) from erreur

    if not isinstance(violations, list) or not all(
        isinstance(violation, dict) for violation in violations
    ):
        raise RuntimeError("la sortie JSON de ruff doit être une liste de violations")

    racine_resolue = Path(racine).resolve()
    for violation in violations:
        chemin = violation.get("filename")
        if isinstance(chemin, str):
            try:
                violation["filename"] = (
                    Path(chemin).resolve().relative_to(racine_resolue).as_posix()
                )
            except ValueError:
                pass  # hors de racine (improbable) : conserve le chemin absolu tel quel

    return violations


def fichiers_reels(racine: Path) -> set[str]:
    """Retourne l'ensemble des fichiers `.py` RÉELLEMENT présents sous `racine/src` et
    `racine/scripts` (via rglob), en chemins relatifs POSIX à `racine` (ex. "src/forgeai/cli.py").
    Même esprit que `fichiers_reels()` de `mypy_gate.py`, mais uniquement `.py` — pas de stubs
    `.pyi`, sans objet pour Ruff. Un dossier absent est simplement ignoré."""
    fichiers: set[str] = set()
    for nom in ("src", "scripts"):
        dossier = racine / nom
        if not dossier.is_dir():
            continue
        for chemin in dossier.rglob("*.py"):
            if chemin.is_file():
                fichiers.add(chemin.relative_to(racine).as_posix())
    return fichiers


def agreger(
    violations: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Retourne `(dette, classification)` calculés depuis la liste de violations mesurées (format
    de sortie de `mesurer` : chaque violation a au moins `"filename"` et `"code"`).
    `dette[fichier]` = nombre total de violations (toutes règles confondues) sur ce fichier ;
    `classification[fichier][code]` = nombre de violations de ce code précis sur ce fichier.
    Représentation creuse : fichiers et codes à 0 violation sont absents des dicts (même
    convention que `ruff_report.py`)."""
    dette: dict[str, int] = {}
    classification: dict[str, dict[str, int]] = {}
    for violation in violations:
        fichier = violation.get("filename")
        code = violation.get("code")
        fichier_texte = fichier if isinstance(fichier, str) else "fichier_inconnu"
        code_texte = code if isinstance(code, str) else "code_inconnu"
        dette[fichier_texte] = dette.get(fichier_texte, 0) + 1
        comptes = classification.setdefault(fichier_texte, {})
        comptes[code_texte] = comptes.get(code_texte, 0) + 1
    return dette, classification


def construire_baseline(racine: Path, regles: list[str]) -> dict[str, Any]:
    """Construit une baseline `ruff-baseline-v1` COMPLÈTE depuis une mesure fraîche : appelle
    `mesurer(racine, regles)` puis `agreger(...)`, et retourne un dict conforme au schéma validé
    par `_valider_base` — `_schema`, `_description`, `version` (1), `regles_activees` (triées
    alphabétiquement), `borne.total_violations` (EXACTEMENT la somme de `dette`, sans aucune
    marge cachée), `dette` (triée par clé fichier) et `classification` (triée par clé fichier,
    puis par clé code à l'intérieur de chaque fichier — les dicts Python conservent l'ordre
    d'insertion, donc le JSON sérialisé est déterministe et diff-stable).

    AUCUN I/O fichier ici : la fonction n'écrit jamais `governance/ruff-baseline.json`
    elle-même — la sérialisation et l'écriture sont la responsabilité de l'appelant (`main`,
    mode `--regenerer-baseline`), afin que cette fonction reste directement testable. Seul I/O
    indirect : le subprocess `ruff check` invoqué par `mesurer`."""
    violations = mesurer(racine, regles)
    dette, classification = agreger(violations)
    dette_triee = {fichier: dette[fichier] for fichier in sorted(dette)}
    classification_triee = {
        fichier: {code: classification[fichier][code] for code in sorted(classification[fichier])}
        for fichier in sorted(classification)
    }
    return {
        "_schema": "ruff-baseline-v1",
        "_description": (
            "Baseline du cliquet Ruff (regles defaut_candidat), RC1-020 #450. Fichier GENERE "
            "par scripts/ruff_ratchet.py --regenerer-baseline : ne jamais editer a la main. "
            "Toute regeneration est une operation de maintenance declaree, review-visible via "
            "le diff git, toujours suivie d'une revue humaine/scellee avant merge."
        ),
        "version": 1,
        "regles_activees": sorted(regles),
        "borne": {"total_violations": sum(dette_triee.values())},
        "dette": dette_triee,
        "classification": classification_triee,
    }


def _valider_regles_activees(regles_activees: Any, libelle: str) -> list[str]:
    """Valide `regles_activees` (liste non vide de chaînes non vides, sans doublon, triée
    alphabétiquement) et la retourne. Lève ValueError avec message explicite sinon."""
    if not isinstance(regles_activees, list) or not regles_activees:
        raise ValueError(
            f"{libelle}.regles_activees doit etre une liste non vide de chaines"
        )
    if not all(isinstance(code, str) and code for code in regles_activees):
        raise ValueError(
            f"{libelle}.regles_activees doit etre une liste de chaines non vides"
        )
    if len(set(regles_activees)) != len(regles_activees):
        raise ValueError(f"{libelle}.regles_activees contient des doublons")
    if regles_activees != sorted(regles_activees):
        raise ValueError(
            f"{libelle}.regles_activees doit etre triee alphabetiquement"
        )
    return regles_activees


def _valider_borne(borne: Any, libelle: str) -> int:
    """Valide l'objet `borne` (dict avec `total_violations` int >= 0 non-bool — le piège
    classique Python où `bool` est une sous-classe de `int` est écarté en testant
    `isinstance(x, bool)` AVANT `isinstance(x, int)`) et retourne `total_violations`."""
    if not isinstance(borne, dict):
        raise ValueError(f"{libelle} doit contenir un objet 'borne'")
    total_violations = borne.get("total_violations")
    if (
        isinstance(total_violations, bool)
        or not isinstance(total_violations, int)
        or total_violations < 0
    ):
        raise ValueError(
            f"{libelle}.borne.total_violations doit etre un entier positif ou nul"
        )
    return total_violations


def _valider_dette(dette: Any, libelle: str) -> dict[str, int]:
    """Valide `dette` (dict chemin -> entier strictement positif, jamais un booléen) et la
    retourne. Un fichier à 0 violation ne doit PAS apparaître dans `dette` (représentation
    creuse) — d'où l'exigence de stricte positivité."""
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


def _valider_coherence_borne_dette(
    total_violations: int, dette: dict[str, int], libelle: str
) -> None:
    """Vérifie que `borne.total_violations` est EXACTEMENT égale à la somme des plafonds de
    `dette` (correctif post-revue : sans cette égalité, une borne gonflée au-dessus de la somme
    réelle des plafonds offrirait une marge cachée capable d'absorber de nouvelles violations
    sans jamais déclencher la règle 5 de `anomalies`). Lève ValueError avec message explicite
    en cas d'écart."""
    somme_dette = sum(dette.values())
    if total_violations != somme_dette:
        raise ValueError(
            f"{libelle}.borne.total_violations ({total_violations}) ne correspond pas a la "
            f"somme de dette ({somme_dette}) : aucune marge cachee n'est admise entre la "
            "borne totale et la dette par fichier"
        )


def _valider_classification(
    classification: Any,
    dette: dict[str, int],
    regles_activees: list[str],
    libelle: str,
) -> dict[str, dict[str, int]]:
    """Valide la `classification` (champ OBLIGATOIRE ici, contrairement à mypy_gate où elle est
    optionnelle et informationnelle : c'est la structure PRIMAIRE de la borne, exigée par la
    story — baseline décroissante, bornée par règle ET chemin). Invariants : dict
    `chemin -> {code -> entier strictement positif non booléen}` ; les clés de `classification`
    sont EXACTEMENT les clés de `dette` (ni plus ni moins) ; pour chaque fichier, la somme des
    comptes égale EXACTEMENT `dette[fichier]` ; et chaque code apparaissant dans
    `classification` est déclaré dans `regles_activees` (aucune règle fantôme non déclarée)."""
    if not isinstance(classification, dict):
        raise ValueError(f"{libelle}.classification doit etre un objet")

    cles_classification = set(classification.keys())
    cles_dette = set(dette.keys())
    if cles_classification != cles_dette:
        manquantes = sorted(cles_dette - cles_classification)
        en_trop = sorted(cles_classification - cles_dette)
        details: list[str] = []
        if manquantes:
            details.append(f"manquantes pour {manquantes}")
        if en_trop:
            details.append(f"en trop pour {en_trop}")
        raise ValueError(
            f"{libelle}.classification : cles incoherentes avec dette ({', '.join(details)})"
        )

    regles_declarees = set(regles_activees)
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
            if code not in regles_declarees:
                raise ValueError(
                    f"{libelle}.classification[{fichier!r}][{code!r}] : regle absente de "
                    "regles_activees (regle fantome non declaree)"
                )
        total = sum(comptes.values())
        if total != plafond:
            raise ValueError(
                f"{libelle}.classification[{fichier!r}] : somme des codes ({total}) "
                f"incoherente avec dette ({plafond})"
            )

    return classification


def _valider_base(base: Any, libelle: str) -> dict[str, Any]:
    """Valide l'intégralité du schéma `ruff-baseline-v1` : `version` (entier non booléen),
    `regles_activees` (liste non vide de chaînes non vides, sans doublon, triée
    alphabétiquement), `borne.total_violations` (entier >= 0 non booléen, et EXACTEMENT égal à
    la somme des plafonds de `dette` — aucune marge cachée), `dette` (dict chemin -> entier
    strictement positif non booléen), `classification` (obligatoire, clés exactement celles de
    `dette`, somme par fichier égale à `dette[fichier]`, aucun code hors de `regles_activees`).
    `libelle` est un texte court (ex. "base locale", "base de reference") permettant à
    l'appelant de distinguer quelle base a échoué. Lève ValueError avec message explicite si un
    invariant est violé. Retourne `base` si valide."""
    if not isinstance(base, dict):
        raise ValueError(f"{libelle} doit etre un objet JSON")

    version = base.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"{libelle}.version doit etre un entier")

    regles_activees = _valider_regles_activees(base.get("regles_activees"), libelle)
    total_violations = _valider_borne(base.get("borne"), libelle)
    dette = _valider_dette(base.get("dette"), libelle)
    _valider_coherence_borne_dette(total_violations, dette, libelle)
    _valider_classification(base.get("classification"), dette, regles_activees, libelle)

    return base


def anomalies(
    mesure_dette: dict[str, int],
    mesure_classification: dict[str, dict[str, int]],
    fichiers_reels: set[str],
    regles_courantes: list[str],
    base_locale: dict[str, Any],
    base_reference: dict[str, Any] | None,
) -> list[str]:
    """Logique pure de comparaison — aucun I/O, aucun subprocess. Valide `base_locale` (et
    `base_reference` si fournie) via `_valider_base`, puis contrôle dans l'ordre :

    0. cohérence des règles : `regles_activees` de la baseline doit correspondre EXACTEMENT
       (aux tris près) aux règles `defaut_candidat` réellement dérivées de la classification
       courante (`regles_courantes`) — sinon la baseline est périmée et doit être régénérée,
       même si tous les comptes sont verts ;
    1. fichier réel en violation absent de la base locale (nouveau fichier jamais baseliné) ;
    2. dette dépassée par fichier (régression vs le plafond baseliné) ;
    3. fichier baseliné en dette mais désormais propre (doit être retiré — la base doit
       décroître, une amélioration totale ne passe pas silencieusement) ;
    4. dette dépassée par couple (fichier, règle) — granularité fine : une hausse d'un code
       compensée par la baisse d'un autre code sur le MÊME fichier est détectée ici, même si le
       total du fichier (règle 2) n'a pas augmenté ;
    5. borne totale inconditionnelle (`borne.total_violations`) ;
    6. si `base_reference` est fournie (`None` = référence non chargeable, ex. premier commit du
       mécanisme — PAS une erreur) : aucun plafond de `dette` augmenté vs la référence pour un
       fichier présent dans les deux ; TOUT fichier de la `dette` locale ABSENT de la `dette`
       de référence est une extension non justifiée (le plafond implicite de référence d'un
       fichier jamais vu est 0 — philosophie mypy_gate : la dette décroît, jamais l'inverse) ;
       un fichier retiré de la `dette` de référence n'est légitime que si son décompte réel
       actuel est 0 (nettoyage cohérent), sinon retrait non justifié ; aucun compte
       `classification[fichier][code]` augmenté vs la référence pour un couple présent dans les
       deux, et TOUT couple (fichier, code) local ABSENT de la référence est une extension non
       justifiée ; `borne.total_violations` non augmentée vs la référence.

    Retourne la liste des messages d'anomalie (vide si aucune) — chaque message est une phrase
    française explicite et actionnable : quoi, valeurs concrètes, pourquoi c'est un problème."""
    base_validee = _valider_base(base_locale, "base locale")
    reference_validee = (
        _valider_base(base_reference, "base de reference")
        if base_reference is not None
        else None
    )

    dette_base = base_validee["dette"]
    classification_base = base_validee["classification"]
    borne_totale = base_validee["borne"]["total_violations"]
    resultat: list[str] = []

    # Règle 0 : les règles activées de la baseline doivent refléter la classification courante.
    regles_baseline_triees = sorted(base_validee["regles_activees"])
    regles_courantes_triees = sorted(regles_courantes)
    if regles_baseline_triees != regles_courantes_triees:
        resultat.append(
            f"les regles activees de la baseline ({regles_baseline_triees}) ne correspondent "
            f"plus aux regles defaut_candidat actuelles de la classification "
            f"({regles_courantes_triees}) : regenerer governance/ruff-baseline.json"
        )

    # Règle 1 : fichier réel en violation absent de la base locale.
    for fichier in sorted(fichiers_reels):
        actuel = mesure_dette.get(fichier, 0)
        if actuel > 0 and fichier not in dette_base:
            resultat.append(
                f"fichier {fichier} en violation ({actuel}) mais absent de la base locale : "
                "nouveau fichier en violation jamais baseline — baseliner explicitement dans "
                "governance/ruff-baseline.json ou corriger les violations"
            )

    # Règles 2 et 3 : dette dépassée par fichier, ou fichier devenu propre.
    for fichier, plafond in sorted(dette_base.items()):
        actuel = mesure_dette.get(fichier, 0)
        if actuel > plafond:
            resultat.append(
                f"fichier {fichier} depasse sa dette baselinee ({actuel} > {plafond}) : "
                "regression interdite"
            )
        elif actuel == 0:
            resultat.append(
                f"fichier {fichier} baseline en dette mais desormais propre : retirer ce "
                "fichier de la dette et de la classification (la base doit decroitre)"
            )

    # Règle 4 : dette dépassée par couple (fichier, règle).
    for fichier, comptes in sorted(classification_base.items()):
        comptes_mesures = mesure_classification.get(fichier, {})
        for code, plafond in sorted(comptes.items()):
            actuel = comptes_mesures.get(code, 0)
            if actuel > plafond:
                resultat.append(
                    f"fichier {fichier} : regle {code} en hausse ({actuel} > {plafond} "
                    "baseline) : regression sur ce code precis, meme si le total du fichier "
                    "est stable ou en baisse"
                )

    # Règle 5 : borne totale inconditionnelle.
    total_mesure = sum(mesure_dette.values())
    if total_mesure > borne_totale:
        resultat.append(
            f"le total des violations defaut_candidat est de {total_mesure} alors que la "
            f"borne est fixee a {borne_totale} : toute nouvelle violation doit etre corrigee, "
            "jamais simplement re-baselinee"
        )

    # Règle 6 : comparaison contre la référence git (non-croissance de la base elle-même).
    if reference_validee is not None:
        dette_ref = reference_validee["dette"]
        classification_ref = reference_validee["classification"]
        borne_ref = reference_validee["borne"]["total_violations"]

        for fichier, plafond in sorted(dette_base.items()):
            if fichier not in dette_ref:
                resultat.append(
                    f"fichier {fichier} ajoute a la dette baselinee, absent de la base de "
                    "reference : extension non justifiee"
                )
            elif plafond > dette_ref[fichier]:
                resultat.append(
                    f"dette baselinee pour {fichier} augmentee depuis la reference "
                    f"({plafond} > {dette_ref[fichier]}) : la base doit decroitre, jamais "
                    "s'etendre"
                )

        for fichier in sorted(dette_ref):
            if fichier not in dette_base:
                actuel = mesure_dette.get(fichier, 0)
                if actuel > 0:
                    resultat.append(
                        f"fichier {fichier} retire de la dette de reference alors qu'il "
                        f"presente encore {actuel} violation(s) : retrait non justifie — "
                        "seul un fichier reellement devenu propre (0 violation mesuree) peut "
                        "sortir de la base"
                    )

        for fichier, comptes in sorted(classification_base.items()):
            comptes_ref = classification_ref.get(fichier, {})
            for code, plafond in sorted(comptes.items()):
                if code not in comptes_ref:
                    resultat.append(
                        f"fichier {fichier} : regle {code} ajoutee a la classification "
                        "baselinee, absente de la base de reference : extension non justifiee"
                    )
                elif plafond > comptes_ref[code]:
                    resultat.append(
                        f"classification baselinee pour {fichier}[{code}] augmentee depuis "
                        f"la reference ({plafond} > {comptes_ref[code]}) : la base doit "
                        "decroitre, jamais s'etendre"
                    )

        if borne_totale > borne_ref:
            resultat.append(
                f"borne totale augmentee depuis la reference ({borne_totale} > {borne_ref}) : "
                "extension non justifiee"
            )

    return resultat


def main(argv: list[str] | None = None) -> int:
    """Execute le gate de cliquet Ruff (règles defaut_candidat). Retourne 0 si le cliquet est
    vert, 1 si au moins une anomalie est détectée ou si une erreur attendue survient (jamais de
    traceback brut qui fuite en CI). Avec `--regenerer-baseline`, régénère intégralement
    `governance/ruff-baseline.json` depuis une mesure fraîche (opération de maintenance
    déclarée, jamais automatique en CI), affiche un résumé et retourne 0 (1 en cas d'erreur)."""
    parser = argparse.ArgumentParser(
        description="Controle le cliquet Ruff (regles defaut_candidat) de ForgeAI."
    )
    parser.add_argument("--racine", default=".", help="racine du depot")
    parser.add_argument(
        "--base-ref-git",
        default="origin/main",
        metavar="REF",
        help="reference git de la base pour le controle de non-croissance",
    )
    parser.add_argument(
        "--regenerer-baseline",
        action="store_true",
        help=(
            "regenere governance/ruff-baseline.json depuis une mesure fraiche, puis quitte "
            "(operation de maintenance declaree, review-visible via le diff git, jamais "
            "automatique en CI)"
        ),
    )
    arguments = parser.parse_args(argv)

    racine = Path(arguments.racine)
    chemin_classification = racine / "governance" / "ruff-classification.json"
    chemin_base = racine / "governance" / "ruff-baseline.json"

    try:
        classification_ruff = _charger_json(chemin_classification)
        regles = regles_defaut_candidat(classification_ruff)
    except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    # Mode maintenance --regenerer-baseline : s'exécute AVANT tout chargement de l'ancienne
    # baseline — il la REMPLACE intégralement (le fichier n'a donc pas besoin d'exister pour
    # être (re)généré la première fois) et ne fait AUCUNE comparaison de non-croissance. Le
    # fichier généré reste un artefact commité, review-visible via le diff git, toujours suivi
    # d'une revue humaine/scellée avant merge.
    if arguments.regenerer_baseline:
        try:
            nouvelle_base = construire_baseline(racine, regles)
            texte_base = json.dumps(nouvelle_base, indent=2, ensure_ascii=False) + "\n"
            chemin_base.write_text(texte_base, encoding="utf-8")
        except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
            print(str(erreur), file=sys.stderr)
            return 1
        print(
            f"Baseline regeneree dans {str(chemin_base)} : "
            f"{nouvelle_base['borne']['total_violations']} violation(s) defaut_candidat "
            f"sur {len(nouvelle_base['dette'])} fichier(s) — a committer apres revue."
        )
        return 0

    try:
        base_locale = _valider_base(_charger_json(chemin_base), "base locale")
    except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    # Référence git : JAMAIS bloquante. Absente à cette ref (premier commit du mécanisme) ou
    # inaccessible (fetch-depth insuffisant, git indisponible) : avertissement sur stderr et
    # base_reference = None — le contrôle de non-croissance est alors simplement inapplicable.
    base_reference: dict[str, Any] | None = None
    try:
        base_reference, message_reference = gate_git_ref.charger_base_reference_git(
            racine,
            chemin_base,
            arguments.base_ref_git,
            _valider_base,
        )
        if message_reference:
            print(f"Avertissement : {message_reference}", file=sys.stderr)
    except (OSError, ValueError, RuntimeError) as erreur:
        print(
            f"Avertissement : reference git {arguments.base_ref_git!r} inutilisable "
            f"({erreur}) : controle de non-croissance inapplicable.",
            file=sys.stderr,
        )
        base_reference = None

    try:
        violations = mesurer(racine, regles)
        reels = fichiers_reels(racine)
        mesure_dette, mesure_classification = agreger(violations)
        rapport = anomalies(
            mesure_dette,
            mesure_classification,
            reels,
            regles,
            base_locale,
            base_reference,
        )
    except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    if rapport:
        for anomalie in rapport:
            print(f"ANOMALIE : {anomalie}", file=sys.stderr)
        return 1

    print("Cliquet Ruff (defaut_candidat) : OK, aucune régression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
