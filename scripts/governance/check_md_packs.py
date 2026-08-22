#!/usr/bin/env python3
"""Validateur de clôtures de blocs de code Markdown pour les packs de revue (RC1-011, #441).

Périmètre volontairement étroit : structure des fences de code uniquement (pas markdownlint —
importer une dépendance violerait `dependencies=[]` stdlib pur du produit). Deux règles :

  R1 (exacte)      : un bloc ouvert par une ligne fence (```/~~~) n'est jamais refermé avant la
                      fin du fichier. C'est une convention DE CE DÉPÔT (les packs sont des
                      documents de preuve, un bloc non refermé signale presque toujours une
                      concaténation accidentelle) — CommonMark, lui, ferme implicitement un
                      fence ouvert à EOF ; R1 est donc plus strict que la spec, pas une
                      implémentation de la spec.

  R2 (heuristique) : une ligne qui a la FORME d'une ouverture de fence (même caractère marqueur,
                      longueur >= 3, PORTANT une chaîne d'info après le marqueur) est rencontrée
                      alors qu'un bloc est déjà ouvert avec un marqueur de longueur >= à la
                      sienne. Une ligne de clôture CommonMark ne porte JAMAIS de chaîne d'info :
                      une telle ligne ne peut donc structurellement jamais fermer le bloc en
                      cours — c'est un signal fiable de "deuxième section qui aurait dû fermer
                      la première d'abord".

Restriction CommonMark supplémentaire modélisée : la chaîne d'info d'une fence à BACKTICKS ne
peut contenir aucun backtick (spec §4.5 — restriction absente pour les fences à TILDES, où un
backtick dans l'info est un caractère de contenu ordinaire). Une ligne qui la viole n'est ni une
ouverture ni une fermeture valides : simple contenu, jamais candidate à R1/R2. Sans cette
vérification, un document valide comme ` ```text\n```foo`\n``` ` (ligne centrale : longueur et
marqueur suffisants, mais backtick dans l'info) serait signalé R2 à tort.

Usage :
  check_md_packs.py [--racine DIR] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def analyser(texte: str) -> list[dict]:
    """Retourne la liste des défauts de clôture de fence dans `texte` (vide = sain).

    Chaque défaut : {"regle": "R1"|"R2", "ligne": <1-based, ligne d'OUVERTURE du bloc fautif>}.
    """
    defauts: list[dict] = []
    bloc_ouvert: dict | None = None  # {"marqueur": str, "longueur": int, "ligne": int}

    for numero, ligne in enumerate(texte.splitlines(), start=1):
        match = _FENCE_RE.match(ligne)
        if match is None:
            continue
        marqueurs = match.group(1)
        marqueur_char = marqueurs[0]
        longueur = len(marqueurs)
        # Le reste de la ligne est extrait par découpage simple, pas par un groupe de capture
        # `(.*)$` terminal — un tel groupe combiné à l'alternance ci-dessus est un motif à
        # risque de backtracking super-linéaire pour un moteur regex classique.
        reste = ligne[match.end():]
        # `chaine_info` (stricte, ASCII espace/tabulation uniquement) sert à juger si la ligne
        # PEUT FERMER : CommonMark n'autorise après une fence de clôture que des espaces/
        # tabulations ASCII (spec §4.5), pas la classe Unicode complète de `str.isspace()` (qui
        # inclut par ex. U+00A0 NBSP). `.strip()` nu traiterait à tort une ligne fence+NBSP comme
        # une clôture valide (bug réel corrigé, trouvé par revue scellée GPT-5.6-Terra-Pro,
        # RC1-011 round 13).
        chaine_info = reste.strip(" \t")
        # `info_r2` (heuristique, Unicode complet) sert UNIQUEMENT à juger si la ligne ressemble
        # à une VRAIE annotation de langage (motif R2) — un résidu Unicode non-imprimable comme
        # NBSP n'en est pas une ; ne pas la confondre avec `chaine_info` évite un R2 parasite sur
        # exactement le même contre-exemple (seul R1 doit être rapporté : le bloc ne ferme pas,
        # mais rien ne ressemble à une tentative de réouverture).
        info_r2 = reste.strip()

        # CommonMark : la chaîne d'info d'une fence à BACKTICKS ne peut contenir aucun backtick
        # (restriction absente pour les fences à tildes — un backtick y est un caractère de
        # contenu ordinaire). Une ligne qui viole cette règle n'est structurellement NI une
        # ouverture NI une clôture valides : simple contenu, ignorée comme si elle n'avait pas
        # matché le motif de fence du tout (ne modifie jamais bloc_ouvert).
        if marqueur_char == "`" and "`" in chaine_info:
            continue

        if bloc_ouvert is None:
            # Nouvelle ouverture (avec ou sans chaîne d'info — les deux sont valides ici).
            bloc_ouvert = {"marqueur": marqueur_char, "longueur": longueur, "ligne": numero}
            continue

        # Un bloc est déjà ouvert : cette ligne peut-elle le FERMER ?
        # CommonMark : même caractère, longueur >= à l'ouverture, AUCUNE chaîne d'info.
        peut_fermer = (
            marqueur_char == bloc_ouvert["marqueur"]
            and longueur >= bloc_ouvert["longueur"]
            and not chaine_info
        )
        if peut_fermer:
            bloc_ouvert = None
            continue

        # Ne peut pas fermer. Si elle A une chaîne d'info ET un marqueur de longueur >= à
        # l'ouverture (donc structurellement CAPABLE de fermer si seule sa chaîne d'info ne
        # l'en empêchait pas), c'est une NOUVELLE ouverture ratée (R2) — la ligne de clôture
        # réellement attendue n'a jamais été écrite entre les deux. Une ligne de longueur
        # INFÉRIEURE à l'ouverture ne peut structurellement jamais interagir avec elle (même
        # avec une chaîne d'info) : c'est du simple contenu imbriqué, cas légitime (```` peut
        # contenir des ``` à l'intérieur, quelle que soit leur chaîne d'info).
        #
        # bloc_ouvert n'est SCIEMMENT PAS réassigné à la pseudo-ouverture : CommonMark ne permet
        # pas l'imbrication de fences de même famille de marqueur — cette ligne reste du CONTENU
        # du bloc initial, qui doit rester fermable par un futur closeur valide pour SA PROPRE
        # longueur. Réassigner casserait la fermeture d'un bloc initial plus court par un closeur
        # plus court que la pseudo-ouverture mais toujours >= au bloc initial (ex. `python``` /
        # `````lang` / ` ``` ` : la 3e ligne ferme valablement le bloc de 3 backticks ouvert en
        # 1re ligne, quel que soit le R2 signalé sur la 2e — bug réel corrigé, trouvé par revue
        # scellée GPT-5.6-Terra-Pro, RC1-011 round 10).
        if info_r2 and longueur >= bloc_ouvert["longueur"] and marqueur_char == bloc_ouvert["marqueur"]:
            defauts.append({"regle": "R2", "ligne": bloc_ouvert["ligne"]})
            # Pas de `continue` : fin naturelle du corps de boucle (bloc_ouvert n'est pas
            # réassigné, rien d'autre à sauter avant la prochaine itération).

        # Sinon (marqueur plus court/imbriqué, ou marqueur différent) : simple contenu du bloc
        # ouvert, ignoré (fin naturelle de l'itération).

    if bloc_ouvert is not None:
        defauts.append({"regle": "R1", "ligne": bloc_ouvert["ligne"]})

    return defauts


def scanner(racine: Path) -> dict[str, list[dict]]:
    """Scanne récursivement `racine` pour les documents Markdown de preuve.

    Les prompts générés `SOL-PROMPT.md` sont exclus : ils contiennent le diff brut canonique,
    donc peuvent embarquer des fences imbriquées qui ne sont pas une structure de pack à valider.
    Les autres documents Markdown, notamment `pack.md` et `REVIEW-PACK.md`, restent entièrement
    soumis au scanner.

    N'utilise PAS git (Path.rglob uniquement) : doit fonctionner dans un clone/extraction sans
    .git (vérification "extraction dans un clone propre" du critère de l'issue #441).
    """
    resultats: dict[str, list[dict]] = {}
    for chemin in sorted(racine.rglob("*.md")):
        if chemin.name == "SOL-PROMPT.md":
            continue
        try:
            texte = chemin.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        defauts = analyser(texte)
        resultats[str(chemin)] = defauts
    return resultats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--racine", default=".", help="répertoire à scanner récursivement")
    ap.add_argument("--json", action="store_true", help="sortie JSON plutôt que texte")
    args = ap.parse_args(argv)

    racine = Path(args.racine).resolve()
    resultats = scanner(racine)
    defaillants = {chemin: defauts for chemin, defauts in resultats.items() if defauts}

    if args.json:
        print(json.dumps(defaillants, ensure_ascii=False, indent=2))
    else:
        if not defaillants:
            print(f"check_md_packs : OK ({len(resultats)} fichier(s) .md scannés, 0 défaut)")
        else:
            print(f"check_md_packs : {len(defaillants)} fichier(s) à clôture de fence invalide")
            for chemin, defauts in sorted(defaillants.items()):
                for defaut in defauts:
                    print(f"  {chemin}:{defaut['ligne']} — {defaut['regle']}")

    return 1 if defaillants else 0


if __name__ == "__main__":
    raise SystemExit(main())
