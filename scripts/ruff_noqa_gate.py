#!/usr/bin/env python3
"""Cliquet sur les suppressions `# noqa: <code>` des règles « defaut_candidat » (RC1-020, #450, incrément 3b/3 — dernier).

Les incréments 1 et 2 (déjà mergés) ont livré `scripts/ruff_report.py` (mesure et
catégorisation informationnelles, jamais bloquantes) puis `scripts/ruff_ratchet.py` (cliquet
bloquant en CI sur les violations des règles `"categorie": "defaut_candidat"` de
`governance/ruff-classification.json`). Cet incrément livre un cliquet SÉPARÉ et INDÉPENDANT
sur les SUPPRESSIONS `# noqa: <code>` de ces mêmes règles : toute suppression doit porter une
justification ET une date de révision, LOCALEMENT dans le commentaire (pas de registre JSON
séparé — la justification vit au site de l'exception). Le sous-ensemble de règles surveillées
est dérivé dynamiquement de la classification à chaque exécution (jamais codé en dur), comme
dans `ruff_ratchet.py`, pour rester synchronisé si un futur incrément reclasse un code.

Indépendance mutuelle voulue avec le reste de la story : ce module n'importe NI
`ruff_ratchet` NI `ruff_report` (les fonctions communes `_charger_json`,
`regles_defaut_candidat` et `fichiers_reels` sont ré-implémentées localement, copie exacte du
comportement) ; il ne dépend que du module partagé `gate_git_ref.py` pour le contrôle de
non-croissance contre une référence git — aucune réinvention de cette partie.

Différence structurelle majeure avec `ruff_ratchet.py` : ce cliquet N'INVOQUE JAMAIS ruff —
aucun subprocess nulle part dans ce fichier. Ruff applique nativement les `# noqa` : une
violation supprimée n'apparaît tout simplement pas dans la sortie JSON de `ruff check`. Le
seul endroit où auditer les suppressions est donc le code source lui-même, lu directement
(`Path.read_text`).

Format exigé : `# noqa: <CODE>` suivi, n'importe où sur le reste de la même ligne, du motif
`(révision: YYYY-MM-DD)` (accent optionnel sur é : `(revision: 2026-08-17)` aussi accepté).
Exemple CONFORME : `# noqa: S310 — URL locale/LAN du socle (révision: 2027-02-17)`. Les
occurrences déjà présentes sur `origin/main` avec justification mais SANS date sont
grand-parentées dans la baseline, PAS corrigées dans cet incrément.

Philosophie reprise de `ruff_ratchet.py` (elle-même alignée sur `scripts/mypy_gate.py`,
#449) : baseline JSON commitée (`governance/ruff-noqa-baseline.json`) avec borne totale +
occurrences par fichier, et contrôle de non-croissance contre une référence git
(`origin/main` par défaut). Granularité PAR FICHIER SEULEMENT ici — pas de dimension par
règle, ce cliquet est volontairement plus simple. En fonctionnement normal, ce script ne fait
que LIRE et VALIDER la baseline : il ne modifie jamais de fichier source. La SEULE exception
est le mode de maintenance explicite `--regenerer-baseline` (opération déclarée,
review-visible via le diff git du fichier généré, toujours suivie d'une revue
humaine/scellée avant merge, jamais automatique en CI), qui réécrit intégralement la
baseline depuis une mesure fraîche.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import gate_git_ref

# Motif d'une suppression `# noqa: <CODE>` : le premier code capturé après `noqa:` est celui
# comparé aux règles surveillées (comparaison insensible à la casse du préfixe — ex. `s310`
# vaut `S310`). Un `# noqa` nu (sans code) n'est pas capturé par ce motif : il ne supprime
# pas un code defaut_candidat précis et reste hors du périmètre de ce cliquet.
MOTIF_CODE_NOQA: re.Pattern[str] = re.compile(r"#\s*noqa:\s*([A-Za-z]+\d+)")

# Motif de la date de révision exigée : `(révision: YYYY-MM-DD)`, accent optionnel sur é,
# espaces autour de `:` tolérés. Recherché sur la ligne ENTIÈRE (pas seulement après le
# noqa), pour rester simple et robuste.
MOTIF_DATE_REVISION: re.Pattern[str] = re.compile(
    r"\(r[ée]vision\s*:\s*\d{4}-\d{2}-\d{2}\)"
)


def _charger_json(chemin: Path) -> dict[str, Any]:
    """Charge un fichier JSON (classification Ruff ou baseline) et garantit un objet JSON racine.

    Ré-implémentation locale volontairement identique à celle de `ruff_ratchet.py` : les
    scripts de la story restent indépendants les uns des autres, aucun import croisé.
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
    ValueError si le résultat est vide (classification vide ou champ `regles` absent) : jamais
    de cliquet actif sur un ensemble de règles vide — ce serait un cliquet qui ne cliquette
    sur rien. Copie exacte du comportement de la fonction du même nom dans
    `ruff_ratchet.py`, ré-implémentée localement (indépendance mutuelle voulue)."""
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


def fichiers_reels(racine: Path) -> set[str]:
    """Retourne l'ensemble des fichiers `.py` RÉELLEMENT présents sous `racine/src` et
    `racine/scripts` (via rglob), en chemins relatifs POSIX à `racine` (ex.
    "src/forgeai/cli.py"). Copie exacte du comportement de la fonction du même nom dans
    `ruff_ratchet.py`, ré-implémentée localement : uniquement `.py` — pas de stubs `.pyi`,
    sans objet pour Ruff. Un dossier absent est simplement ignoré."""
    fichiers: set[str] = set()
    for nom in ("src", "scripts"):
        dossier = racine / nom
        if not dossier.is_dir():
            continue
        for chemin in dossier.rglob("*.py"):
            if chemin.is_file():
                fichiers.add(chemin.relative_to(racine).as_posix())
    return fichiers


def noqa_non_conformes(racine: Path, regles: list[str]) -> dict[str, int]:
    """Compte, par fichier, les suppressions `# noqa: <CODE>` NON CONFORMES visant une règle
    de `regles` — c'est-à-dire dépourvues du motif de date `(révision: YYYY-MM-DD)` (accent
    optionnel) sur la ligne.

    Lecture directe de chaque fichier de `fichiers_reels(racine)` via `Path.read_text` : ce
    cliquet n'invoque JAMAIS ruff ni aucun subprocess — ruff applique nativement les `# noqa`
    (une violation supprimée n'apparaît pas dans sa sortie JSON), donc le code source est le
    seul endroit où les suppressions peuvent être auditées.

    Pour chaque LIGNE de chaque fichier : recherche le motif `# noqa: <CODE>` ; si le code
    capturé (comparaison insensible à la casse du préfixe) appartient à `regles`, le motif de
    date est recherché sur la ligne ENTIÈRE (pas seulement après le noqa, pour rester simple
    et robuste). Absence du motif de date → une occurrence NON CONFORME de plus pour ce
    fichier. Retourne un dict `{fichier: nombre_occurrences_non_conformes}` en représentation
    creuse (fichiers à 0 absents). Un fichier illisible (`OSError`, `UnicodeError`) est ignoré
    silencieusement — pas d'exception propagée, cohérent avec le traitement des chemins hors
    racine dans `ruff_ratchet.py`."""
    codes_surveilles = {code.upper() for code in regles}
    resultat: dict[str, int] = {}
    for fichier in sorted(fichiers_reels(racine)):
        try:
            contenu = (racine / fichier).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        non_conformes = 0
        for ligne in contenu.splitlines():
            correspondance = MOTIF_CODE_NOQA.search(ligne)
            if correspondance is None:
                continue
            if correspondance.group(1).upper() not in codes_surveilles:
                continue
            if MOTIF_DATE_REVISION.search(ligne) is None:
                non_conformes += 1
        if non_conformes > 0:
            resultat[fichier] = non_conformes
    return resultat


def _valider_base(base: Any, libelle: str) -> dict[str, Any]:
    """Valide l'intégralité du schéma `ruff-noqa-baseline-v1` : `_schema` (chaîne EXACTEMENT
    égale à `"ruff-noqa-baseline-v1"` — contrat de versionnement du format), `version`
    (entier non booléen, ET EXACTEMENT égal à 1 — toute autre valeur entière signifie un
    format de baseline que ce script ne sait pas valider), `borne.total_occurrences` (entier
    >= 0 non booléen, et EXACTEMENT égal à la somme des plafonds de `occurrences` — aucune
    marge cachée : le piège classique Python où `bool` est une sous-classe de `int` est écarté
    en testant `isinstance(x, bool)` AVANT `isinstance(x, int)`), `occurrences` (dict chemin
    -> entier strictement positif non booléen, représentation creuse : un fichier à 0
    occurrence ne doit PAS y apparaître). `libelle` est un texte court (ex. "base locale",
    "base de reference") préfixant les messages pour distinguer quelle base a échoué. Lève
    ValueError avec message explicite si un invariant est violé. Retourne `base` si valide."""
    if not isinstance(base, dict):
        raise ValueError(f"{libelle} doit etre un objet JSON")

    if base.get("_schema") != "ruff-noqa-baseline-v1":
        raise ValueError(f"{libelle}._schema doit etre 'ruff-noqa-baseline-v1'")

    version = base.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"{libelle}.version doit etre un entier")
    if version != 1:
        raise ValueError(
            f"{libelle}.version doit etre 1 (schema ruff-noqa-baseline-v1), recu {version}"
        )

    borne = base.get("borne")
    if not isinstance(borne, dict):
        raise ValueError(f"{libelle} doit contenir un objet 'borne'")
    total_occurrences = borne.get("total_occurrences")
    if (
        isinstance(total_occurrences, bool)
        or not isinstance(total_occurrences, int)
        or total_occurrences < 0
    ):
        raise ValueError(
            f"{libelle}.borne.total_occurrences doit etre un entier positif ou nul"
        )

    occurrences = base.get("occurrences")
    if not isinstance(occurrences, dict):
        raise ValueError(f"{libelle}.occurrences doit etre un objet")
    for fichier, plafond in occurrences.items():
        if not isinstance(fichier, str):
            raise ValueError(f"{libelle}.occurrences contient une cle non chaine")
        if isinstance(plafond, bool) or not isinstance(plafond, int) or plafond <= 0:
            raise ValueError(
                f"{libelle}.occurrences[{fichier!r}] doit etre un entier strictement positif"
            )

    somme_occurrences = sum(occurrences.values())
    if total_occurrences != somme_occurrences:
        raise ValueError(
            f"{libelle}.borne.total_occurrences ({total_occurrences}) ne correspond pas a "
            f"la somme de occurrences ({somme_occurrences}) : aucune marge cachee n'est "
            "admise entre la borne totale et les occurrences par fichier"
        )

    return base


def construire_baseline(racine: Path, regles: list[str]) -> dict[str, Any]:
    """Construit une baseline `ruff-noqa-baseline-v1` COMPLÈTE depuis une mesure fraîche :
    appelle `noqa_non_conformes(racine, regles)` et retourne un dict conforme au schéma validé
    par `_valider_base` — `_schema`, `_description`, `version` (1), `borne.total_occurrences`
    (EXACTEMENT la somme de `occurrences`, sans aucune marge cachée) et `occurrences` (trié
    par clé fichier — les dicts Python conservent l'ordre d'insertion, donc le JSON sérialisé
    est déterministe et diff-stable).

    Fonction PURE : AUCUNE écriture disque ici — la sérialisation et l'écriture sont la
    responsabilité de l'appelant (`main`, mode `--regenerer-baseline`), afin que cette
    fonction reste directement testable."""
    occurrences = noqa_non_conformes(racine, regles)
    occurrences_triees = {
        fichier: occurrences[fichier] for fichier in sorted(occurrences)
    }
    return {
        "_schema": "ruff-noqa-baseline-v1",
        "_description": (
            "Baseline du cliquet noqa (justification + date de revision) sur les regles "
            "defaut_candidat, RC1-020 #450 increment 3b. Fichier GENERE par "
            "scripts/ruff_noqa_gate.py --regenerer-baseline : ne jamais editer a la main. "
            "Toute regeneration est une operation de maintenance declaree, review-visible "
            "via le diff git, toujours suivie d'une revue humaine/scellee avant merge."
        ),
        "version": 1,
        "borne": {"total_occurrences": sum(occurrences_triees.values())},
        "occurrences": occurrences_triees,
    }


def anomalies(
    mesure: dict[str, int],
    fichiers_reels: set[str],
    base_locale: dict[str, Any],
    base_reference: dict[str, Any] | None,
) -> list[str]:
    """Logique pure de comparaison — aucun I/O, aucun subprocess. Valide `base_locale` (et
    `base_reference` si fournie) via `_valider_base`, puis contrôle dans l'ordre (même esprit
    que `ruff_ratchet.py`, MAIS granularité PAR FICHIER SEULEMENT ici — pas de dimension par
    règle, ce cliquet est volontairement plus simple) :

    1. fichier réel avec occurrences non conformes (`mesure.get(fichier, 0) > 0`) mais absent
       de `base_locale["occurrences"]` (nouveau fichier en violation jamais baseliné) ;
    2. occurrences dépassées par fichier (régression vs le plafond baseliné) ;
    3. fichier baseliné mais désormais conforme (0 occurrence mesurée — doit être retiré, la
       base doit décroître, une amélioration totale ne passe pas silencieusement) ;
    4. borne totale inconditionnelle (`borne.total_occurrences`) ;
    5. si `base_reference` est fournie (`None` = référence non chargeable, ex. premier commit
       du mécanisme — PAS une erreur, la règle est alors entièrement ignorée) : aucun plafond
       de `occurrences` augmenté vs la référence pour un fichier présent dans les deux ; TOUT
       fichier de la `occurrences` locale ABSENT de celle de référence est une extension non
       justifiée (le plafond implicite de référence d'un fichier jamais vu est 0 — MÊME
       principe que `ruff_ratchet.py`, règle 6 : la dette décroît, jamais l'inverse) ; un
       fichier retiré de la référence n'est légitime que si son compte mesuré réel est 0
       (nettoyage cohérent), sinon retrait non justifié ; borne totale non augmentée vs la
       référence.

    Retourne la liste des messages d'anomalie (vide si aucune) — chaque message est une phrase
    française explicite et actionnable : quoi, valeurs concrètes, pourquoi c'est un
    problème."""
    base_validee = _valider_base(base_locale, "base locale")
    reference_validee = (
        _valider_base(base_reference, "base de reference")
        if base_reference is not None
        else None
    )

    occurrences_base = base_validee["occurrences"]
    borne_totale = base_validee["borne"]["total_occurrences"]
    resultat: list[str] = []

    # Règle 1 : fichier réel en violation absent de la base locale.
    for fichier in sorted(fichiers_reels):
        actuel = mesure.get(fichier, 0)
        if actuel > 0 and fichier not in occurrences_base:
            resultat.append(
                f"fichier {fichier} avec {actuel} occurrence(s) noqa non conforme(s) mais "
                "absent de la base locale : nouveau fichier en violation jamais baseline — "
                "ajouter une justification et une date de revision aux suppressions "
                "concernees, ou baseliner explicitement dans "
                "governance/ruff-noqa-baseline.json"
            )

    # Règles 2 et 3 : occurrences dépassées par fichier, ou fichier devenu conforme.
    for fichier, plafond in sorted(occurrences_base.items()):
        actuel = mesure.get(fichier, 0)
        if actuel > plafond:
            resultat.append(
                f"fichier {fichier} depasse son plafond d'occurrences noqa non conformes "
                f"baseline ({actuel} > {plafond}) : regression interdite"
            )
        elif actuel == 0:
            resultat.append(
                f"fichier {fichier} baseline mais desormais conforme : retirer ce fichier "
                "de la baseline (la base doit decroitre)"
            )

    # Règle 4 : borne totale inconditionnelle.
    total_mesure = sum(mesure.values())
    if total_mesure > borne_totale:
        resultat.append(
            f"le total des occurrences noqa non conformes est de {total_mesure} alors que "
            f"la borne est fixee a {borne_totale} : toute nouvelle suppression doit porter "
            "une justification et une date de revision, jamais simplement etre re-baselinee"
        )

    # Règle 5 : comparaison contre la référence git (non-croissance de la base elle-même).
    if reference_validee is not None:
        occurrences_ref = reference_validee["occurrences"]
        borne_ref = reference_validee["borne"]["total_occurrences"]

        for fichier, plafond in sorted(occurrences_base.items()):
            if fichier not in occurrences_ref:
                resultat.append(
                    f"fichier {fichier} ajoute a la baseline, absent de la base de "
                    "reference : extension non justifiee"
                )
            elif plafond > occurrences_ref[fichier]:
                resultat.append(
                    f"plafond baseline pour {fichier} augmente depuis la reference "
                    f"({plafond} > {occurrences_ref[fichier]}) : la base doit decroitre, "
                    "jamais s'etendre"
                )

        for fichier in sorted(occurrences_ref):
            if fichier not in occurrences_base:
                actuel = mesure.get(fichier, 0)
                if actuel > 0:
                    resultat.append(
                        f"fichier {fichier} retire de la base de reference alors qu'il "
                        f"presente encore {actuel} occurrence(s) non conforme(s) : retrait "
                        "non justifie — seul un fichier reellement devenu conforme (0 "
                        "occurrence mesuree) peut sortir de la base"
                    )

        if borne_totale > borne_ref:
            resultat.append(
                f"borne totale augmentee depuis la reference ({borne_totale} > "
                f"{borne_ref}) : extension non justifiee"
            )

    return resultat


def main(argv: list[str] | None = None) -> int:
    """Execute le gate de cliquet noqa (justification + date de revision). Retourne 0 si le
    cliquet est vert, 1 si au moins une anomalie est détectée ou si une erreur attendue
    survient (jamais de traceback brut qui fuite en CI). Avec `--regenerer-baseline`,
    régénère intégralement `governance/ruff-noqa-baseline.json` depuis une mesure fraîche
    (opération de maintenance déclarée, jamais automatique en CI), affiche une confirmation et
    retourne 0 (1 en cas d'erreur)."""
    parser = argparse.ArgumentParser(
        description=(
            "Controle le cliquet noqa (justification + date de revision) de ForgeAI."
        )
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
            "regenere governance/ruff-noqa-baseline.json depuis une mesure fraiche, puis "
            "quitte (operation de maintenance declaree, review-visible via le diff git, "
            "jamais automatique en CI)"
        ),
    )
    arguments = parser.parse_args(argv)

    racine = Path(arguments.racine)
    chemin_classification = racine / "governance" / "ruff-classification.json"
    chemin_base = racine / "governance" / "ruff-noqa-baseline.json"

    try:
        classification_ruff = _charger_json(chemin_classification)
        regles = regles_defaut_candidat(classification_ruff)
    except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    # Mode maintenance --regenerer-baseline : s'exécute AVANT tout chargement de l'ancienne
    # baseline — il la REMPLACE intégralement (le fichier n'a donc pas besoin d'exister pour
    # être (re)généré la première fois) et ne fait AUCUNE comparaison de non-croissance. Le
    # fichier généré reste un artefact commité, review-visible via le diff git, toujours
    # suivi d'une revue humaine/scellée avant merge. La baseline nouvellement construite est
    # validée par `_valider_base` AVANT sérialisation : `construire_baseline` est censée
    # toujours produire un schéma valide, mais cette validation supplémentaire est un filet
    # de sécurité peu coûteux — on n'écrit jamais sur disque une baseline qui échouerait à
    # la relecture.
    if arguments.regenerer_baseline:
        try:
            nouvelle_base = construire_baseline(racine, regles)
            _valider_base(nouvelle_base, "baseline regeneree")
            texte_base = json.dumps(nouvelle_base, indent=2, ensure_ascii=False) + "\n"
            chemin_base.write_text(texte_base, encoding="utf-8")
        except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
            print(str(erreur), file=sys.stderr)
            return 1
        print(
            f"Baseline regeneree dans {str(chemin_base)} : "
            f"{nouvelle_base['borne']['total_occurrences']} occurrence(s) noqa non "
            f"conforme(s) sur {len(nouvelle_base['occurrences'])} fichier(s) — a committer "
            "apres revue."
        )
        return 0

    # Référence git — aligné sur le comportement de `ruff_ratchet.py` (précédent #449 via
    # mypy_gate) : l'appel à `charger_base_reference_git` N'A PAS de try/except dédié qui
    # dégraderait silencieusement le contrôle de non-croissance ; il est couvert par le bloc
    # try/except de plus haut niveau ci-dessous, qui fait ÉCHOUER le gate (return 1) sur
    # toute VRAIE panne d'infrastructure (git indisponible → RuntimeError, JSON de la
    # référence invalide ou schéma non conforme → ValueError levée par `_valider_base` passé
    # en callback). Deux chemins bien distincts :
    # - absence LÉGITIME de la baseline à cette ref (premier commit du mécanisme) : retour
    #   NORMAL `(None, message)` de `charger_base_reference_git`, jamais d'exception —
    #   avertissement stderr et `base_reference = None`, le gate continue avec le seul
    #   contrôle local ;
    # - VRAIE panne : l'exception se propage jusqu'au try/except ci-dessous. Un simple
    #   avertissement suivi d'une continuation transformerait une panne réelle (ex.
    #   fetch-depth insuffisant en CI) en désactivation silencieuse de TOUT le contrôle de
    #   non-croissance — précisément le trou qu'une PR gonflant la baseline locale pourrait
    #   exploiter.
    try:
        base_locale = _valider_base(_charger_json(chemin_base), "base locale")
        base_reference: dict[str, Any] | None
        base_reference, message_reference = gate_git_ref.charger_base_reference_git(
            racine,
            chemin_base,
            arguments.base_ref_git,
            _valider_base,
        )
        if message_reference:
            print(f"Avertissement : {message_reference}", file=sys.stderr)
        mesure = noqa_non_conformes(racine, regles)
        reels = fichiers_reels(racine)
        rapport = anomalies(mesure, reels, base_locale, base_reference)
    except (OSError, UnicodeError, ValueError, RuntimeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    if rapport:
        for anomalie in rapport:
            print(f"ANOMALIE : {anomalie}", file=sys.stderr)
        return 1

    print("Cliquet noqa (justification + date de revision) : OK, aucune regression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
