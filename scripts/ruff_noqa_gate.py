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
seul endroit où auditer les suppressions est donc le code source lui-même, lu directement en
octets bruts (`Path.read_bytes`) puis découpé en tokens typés par la stdlib `tokenize`.

Format contrôlé : une directive noqa porteuse d'un code surveillé — un COMMENTAIRE Python (au
sens `tokenize.COMMENT`) en fin d'une ligne de code réel, puisque c'est là et SEULEMENT là
que ruff l'applique — suivie, sur le reste de la même ligne, d'une justification NON VIDE
et du motif `(révision: YYYY-MM-DD)` (accent optionnel sur é : `(revision: 2026-08-17)` aussi
accepté), la date devant être calendairement VALIDE (pas seulement de forme `AAAA-MM-JJ` :
`2027-99-99` est rejetée). La justification est un texte LIBRE : n'importe quel texte non
vide entre la fin de la liste des codes et le début du motif de date est accepté, quel que
soit le caractère utilisé pour l'introduire ; seule une « justification » réduite, une fois
dépouillée, à des espaces et séparateurs de ponctuation seuls (`-`, `—`, `:`, `,` — voir
`CARACTERES_SEPARATEURS_JUSTIFICATION`) est considérée ABSENTE et rend le commentaire non
conforme, même avec une date. Le tiret cadratin `—` employé dans les exemples de la présente
documentation est un simple style illustratif recommandé, PAS une exigence syntaxique du
contrôle. Exemple CONFORME (sur une ligne de code) :
`x = urlopen(url)  # noqa: S310 — URL locale/LAN du socle (révision: 2027-02-17)`. Les
occurrences déjà présentes sur `origin/main` avec justification mais SANS date sont
grand-parentées dans la baseline, PAS corrigées dans cet incrément.

Distinction essentielle du scanner : une VRAIE directive noqa est un COMMENTAIRE Python — un
token `COMMENT` au sens de la stdlib `tokenize` — jamais un littéral de chaîne contenant un
texte ressemblant. Le scan repose donc sur `tokenize.tokenize` (PEP-263-aware, lecture en
octets bruts) et ne traite QUE les tokens de type `tokenize.COMMENT` : un token `STRING`
(littéral de chaîne, docstring en position code, f-string — par exemple une affectation dont
la valeur est un littéral documentant le format attendu) contenant une sous-chaîne identique
à une directive est ignoré par construction — il est structurellement impossible de le
confondre avec un vrai commentaire, quel que soit son contenu textuel. C'est exactement le
précédent déjà résolu et en production de `scripts/mypy_gate.py` (fonction
`_lignes_avec_commentaire_reel`, « Round 17 » de la revue #449) : même problème (distinguer
un vrai commentaire d'un texte similaire dans un littéral), même solution — aucune
heuristique de texte brut. Un filtre du type « la ligne commence par `#` » ne suffirait PAS :
une ligne de code réel peut contenir un littéral de chaîne portant un texte de directive sans
qu'aucune violation ne soit réellement supprimée. Sans ce filtre structurel, le scanner
compterait de fausses suppressions et s'auditerait lui-même (les exemples littéraux de la
présente docstring sont des tokens STRING : jamais examinés).

Distinction complémentaire, AU SEIN des tokens COMMENT : une ligne de COMMENTAIRE PUR (rien
avant le `#` sur la ligne physique sauf des espaces/tabulations d'indentation — typiquement
un exemple de syntaxe documenté dans une docstring ou un commentaire explicatif autonome)
n'est JAMAIS une vraie suppression, puisque Ruff n'applique un `# noqa` qu'à la ligne de code
que le commentaire termine. De tels commentaires sont ignorés COMPLÈTEMENT, même si leur
texte ressemble exactement à une directive conforme. Ce filtre n'exige AUCUN re-découpage
texte du fichier : chaque `TokenInfo` porte nativement `tok.line` (la ligne physique source
complète, déjà décodée) et `tok.start[1]` (l'offset 0-based du `#` dans cette ligne) — voir
`noqa_non_conformes`.

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
import io
import json
import re
import sys
import tokenize
from datetime import date
from pathlib import Path
from typing import Any

import gate_git_ref

# Motif d'une suppression noqa codifiée : capture la LISTE COMPLÈTE des codes après
# `noqa:` (syntaxe native ruff, codes séparés par virgules), pas seulement le premier. Le
# groupe capturé est ensuite découpé sur les virgules pour obtenir les codes individuels
# (comparaison insensible à la casse du préfixe). Un commentaire noqa nu (sans code) n'est
# pas capturé par ce motif : il ne supprime pas un code defaut_candidat précis et reste hors
# du périmètre de ce cliquet. Ce motif n'est appliqué qu'aux tokens COMMENT issus de
# `tokenize` ET précédés de code réel sur leur ligne physique — voir les filtres
# structurels de `noqa_non_conformes` : un texte identique dans un littéral de chaîne ou
# dans une ligne de commentaire pur n'est jamais examiné. Le flag `re.IGNORECASE` couvre le
# mot-clé de suppression lui-même, insensible à la casse côté Ruff (vérifié empiriquement sur
# ruff 0.15.20 : la variante toute en majuscules supprime une violation exactement comme la
# variante toute en minuscules) — le contrôle doit donc détecter la directive quelle que soit
# sa casse pour ne jamais sous-compter une suppression réelle (le préfixe des codes
# `[A-Za-z]+\d+` couvre déjà les deux casses et la comparaison finale se fait via `.upper()`,
# aucun autre ajustement nécessaire de ce côté). Aucun exemple littéral du mot-clé n'est cité
# ici : le faire, précédé d'un second symbole dièse sur cette ligne, serait lui-même interprété
# par Ruff comme une tentative de directive et émettrait un avertissement parasite, sans
# rapport avec le cliquet lui-même — piège rencontré et évité en écrivant ce commentaire.
MOTIF_CODE_NOQA: re.Pattern[str] = re.compile(
    r"#\s*noqa:\s*([A-Za-z]+\d+(?:\s*,\s*[A-Za-z]+\d+)*)",
    re.IGNORECASE,
)

# Motif de la date de révision exigée : `(révision: YYYY-MM-DD)`, accent optionnel sur é,
# espaces autour de `:` tolérés. Recherché dans le commentaire APRÈS la fin du match des
# codes (paramètre de position `search(chaine, pos)` dans `noqa_non_conformes`), afin qu'un
# motif de date situé AVANT la directive dans le même commentaire ne soit pas pris pour la
# date exigée après les codes. Le groupe capturé est la chaîne de date brute `AAAA-MM-JJ` :
# la forme regex seule ne suffit pas (une date calendaire impossible comme `2027-99-99`
# passerait), elle est donc ensuite validée calendairement via `datetime.date.fromisoformat`
# dans `noqa_non_conformes` — une date invalide est traitée comme une date ABSENTE
# (commentaire non conforme), jamais comme une exception qui remonte.
MOTIF_DATE_REVISION: re.Pattern[str] = re.compile(
    r"\(r[ée]vision\s*:\s*(\d{4}-\d{2}-\d{2})\)"
)

# Caractères dépouillés aux extrémités de la justification candidate pour décider si elle est
# non vide : espaces et séparateurs de ponctuation seuls (`-`, `—`, `:`, `,`). Une
# « justification » réduite à ces seuls caractères (par exemple une suppression dont le texte
# entre les codes et la date ne contient qu'un tiret cadratin) n'est PAS une justification :
# le commentaire est non conforme même avec une date. À l'inverse, TOUT autre contenu non
# vide est une justification valide : le texte est libre, aucun séparateur précis n'est
# exigé (le tiret cadratin des exemples de documentation est un simple style illustratif
# recommandé, pas une règle du contrôle).
CARACTERES_SEPARATEURS_JUSTIFICATION: str = " \t\r\n\f\v-—:,"


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
    """Compte, par fichier, les commentaires de suppression portant au moins un code de
    `regles` et NON CONFORMES — c'est-à-dire dépourvus soit d'une date de révision
    `(révision: YYYY-MM-DD)` (accent optionnel) calendairement VALIDE placée APRÈS la liste
    des codes, soit d'une justification NON VIDE entre la liste des codes et le motif de
    date. La justification est un texte LIBRE : n'importe quel contenu non vide y fait foi,
    quel que soit le caractère qui l'introduit — le tiret cadratin `—` des exemples de la
    documentation est un simple style illustratif recommandé, PAS une exigence syntaxique
    du contrôle (seule une « justification » réduite, une fois dépouillée, aux espaces et
    séparateurs de ponctuation listés dans `CARACTERES_SEPARATEURS_JUSTIFICATION` est
    considérée absente).

    MÉCANIQUE DE SCAN — `tokenize`, jamais de découpage texte brut de lignes. Chaque fichier
    de `fichiers_reels(racine)` est lu en OCTETS BRUTS (`Path.read_bytes`, PAS
    `Path.read_text` : `tokenize` a besoin d'octets pour respecter l'encodage déclaré
    PEP-263) puis découpé en tokens typés via
    `tokenize.tokenize(io.BytesIO(contenu_brut).readline)`. SEULS les tokens de type
    `tokenize.COMMENT` sont examinés : un token `STRING` (littéral de chaîne, docstring en
    position code, f-string) contenant un texte ressemblant à une directive n'est JAMAIS
    examiné — il est structurellement impossible de le confondre avec un vrai commentaire,
    quel que soit son contenu textuel. Précédent déjà résolu et en production :
    `scripts/mypy_gate.py`, fonction `_lignes_avec_commentaire_reel` (« Round 17 » de la
    revue #449) — même problème exact pour les directives mypy, même solution, aucune
    heuristique de texte brut. Ce cliquet n'invoque JAMAIS ruff ni aucun subprocess : ruff
    applique nativement les suppressions (une violation supprimée n'apparaît pas dans sa
    sortie JSON), donc le code source est le seul endroit où elles peuvent être auditées.

    Pour chaque token COMMENT (`tok.string` est le commentaire COMPLET, du `#` jusqu'à la
    fin de la ligne physique — inutile de re-découper la ligne source, et une directive, sa
    justification et sa date ne peuvent être que dans le commentaire lui-même, jamais avant
    le `#`) :

    0. FILTRE « COMMENTAIRE PUR », appliqué AVANT toute autre logique : `tok.line` est la
       ligne physique SOURCE COMPLÈTE (déjà décodée en `str`) où le token commence, et
       `tok.start[1]` l'offset (0-based) du caractère `#` dans cette ligne — deux
       informations natives du `TokenInfo`, sans ré-ouvrir ni re-découper le fichier. Si
       `tok.line[:tok.start[1]].strip()` est VIDE (rien avant le `#` sauf des
       espaces/tabulations d'indentation), le commentaire est un commentaire PUR
       (documentaire/explicatif autonome, typiquement un exemple de syntaxe) : Ruff
       n'applique un `# noqa` qu'à la ligne de code que le commentaire termine, donc un
       tel commentaire n'est JAMAIS une vraie suppression, même si son texte ressemble
       exactement à une directive conforme — il est ignoré COMPLÈTEMENT, exactement comme
       s'il n'avait aucune correspondance. Sinon (du code réel précède le `#`, même
       partiellement, par exemple `x = 1  # noqa: ...` ou `x = 1; y = 2  # noqa: ...`), la
       conformité est vérifiée normalement ;
    1. recherche du motif de suppression `MOTIF_CODE_NOQA` (liste native ruff de codes
       séparés par virgules, capturée EN ENTIER puis découpée sur les virgules) ; si AUCUN
       des codes (comparaison insensible à la casse du préfixe) n'appartient à `regles`, le
       commentaire est hors périmètre et ignoré ; sinon sa conformité est vérifiée UNE SEULE
       FOIS pour le commentaire entier (un seul commentaire de suppression, une seule
       justification/date pour TOUS les codes qu'il supprime — pas une vérification par code
       individuel) ;
    2. le motif de date est recherché UNIQUEMENT dans la portion du commentaire qui SUIT la
       fin du match des codes — via le paramètre de position
       `MOTIF_DATE_REVISION.search(tok.string, correspondance.end())` — afin qu'un motif de
       date apparaissant AVANT la directive dans le même commentaire (situation artificielle
       mais possible) ne soit pas confondu avec la date exigée APRÈS les codes ; absence →
       commentaire NON CONFORME ;
    3. si le motif de date est trouvé, la chaîne capturée `AAAA-MM-JJ` est validée
       CALENDAIREMENT via `datetime.date.fromisoformat` : une date impossible (par exemple
       mois 99) lève `ValueError`, interceptée ici — le commentaire est alors traité comme
       SI la date était absente (NON CONFORME), jamais comme une exception qui remonte. La
       validation de non-expiration (date dans le futur, horizon de révision) reste
       explicitement hors périmètre de cet incrément ;
    4. si la date est présente ET valide, la sous-chaîne comprise ENTRE la fin du match des
       codes et le début du motif de date est extraite ; dépouillée des espaces ET des
       séparateurs de ponctuation seuls (`-`, `—`, `:`, `,`), si elle est VIDE →
       justification absente → commentaire NON CONFORME, même avec une date.

    Gestion des erreurs : un fichier illisible (`OSError` à la lecture) OU non tokenizable
    (`tokenize.TokenError`, `SyntaxError`, `IndentationError`, `UnicodeDecodeError`,
    `ValueError` — syntaxe invalide, encodage déclaré invalide, etc.) est traité comme
    n'ayant AUCUNE occurrence non conforme (on passe au fichier suivant) — jamais
    d'exception propagée, cohérent avec le traitement des chemins hors racine dans
    `ruff_ratchet.py` et avec `_lignes_avec_commentaire_reel` de `scripts/mypy_gate.py`.

    Retourne un dict `{fichier: nombre_occurrences_non_conformes}` en représentation creuse
    (fichiers à 0 absents), comptage par COMMENTAIRE : un commentaire non conforme compte
    pour 1 occurrence, quel que soit le nombre de codes surveillés qu'il supprime (au plus un
    commentaire par ligne physique en Python, donc équivalent à un comptage par ligne)."""
    codes_surveilles = {code.upper() for code in regles}
    resultat: dict[str, int] = {}
    for fichier in sorted(fichiers_reels(racine)):
        try:
            contenu_brut = (racine / fichier).read_bytes()
        except OSError:
            continue
        non_conformes = 0
        try:
            for tok in tokenize.tokenize(io.BytesIO(contenu_brut).readline):
                # Seuls les vrais commentaires Python sont examinés : un token STRING (ou
                # tout autre type) contenant un texte ressemblant à une directive n'est
                # jamais concerné, structurellement.
                if tok.type != tokenize.COMMENT:
                    continue
                # Filtre « commentaire pur » : `tok.line` est la ligne physique source
                # complète où le token commence et `tok.start[1]` l'offset (0-based) du
                # caractère `#` dans cette ligne. Si rien ne précède le `#` sauf des
                # espaces/tabulations d'indentation, c'est un commentaire
                # documentaire/explicatif autonome — jamais une vraie suppression Ruff,
                # qui ne s'applique qu'à la ligne de code qu'elle termine — donc ignoré
                # COMPLÈTEMENT, même si son texte ressemble exactement à une directive.
                if not tok.line[: tok.start[1]].strip():
                    continue
                correspondance = MOTIF_CODE_NOQA.search(tok.string)
                if correspondance is None:
                    continue
                codes_ligne = re.split(r"\s*,\s*", correspondance.group(1))
                if not any(code.upper() in codes_surveilles for code in codes_ligne):
                    continue
                correspondance_date = MOTIF_DATE_REVISION.search(
                    tok.string, correspondance.end()
                )
                if correspondance_date is None:
                    non_conformes += 1
                    continue
                try:
                    date.fromisoformat(correspondance_date.group(1))
                except ValueError:
                    # Date calendaire impossible (ex. 2027-99-99) : traitée comme une date
                    # ABSENTE — commentaire non conforme, jamais d'exception propagée.
                    non_conformes += 1
                    continue
                justification = tok.string[
                    correspondance.end() : correspondance_date.start()
                ]
                if not justification.strip(CARACTERES_SEPARATEURS_JUSTIFICATION):
                    non_conformes += 1
        except (
            tokenize.TokenError,
            SyntaxError,
            IndentationError,
            UnicodeDecodeError,
            ValueError,
        ):
            # Fichier non tokenizable (syntaxe invalide, encodage déclaré invalide, etc.) :
            # traité comme n'ayant AUCUNE occurrence non conforme, jamais d'exception
            # propagée — même comportement que pour un fichier illisible.
            continue
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
