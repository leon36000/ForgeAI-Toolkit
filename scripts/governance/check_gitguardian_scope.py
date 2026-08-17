#!/usr/bin/env python3
"""Valide le périmètre de `.gitguardian.yaml` (RC1-015, #445).

Contexte : `.gitguardian.yaml` excluait globalement `**/*.md` du scan de secrets GitGuardian —
prompts, rapports, revues et documents pouvaient donc contenir des valeurs sensibles sans jamais
être analysés. Ce script vérifie STRUCTURELLEMENT que cette exclusion globale n'est jamais
réintroduite, sans dépendre de `ggshield` (outil de dev optionnel, non installé par défaut —
`dependencies=[]` stdlib pur du produit, voir `scripts/governance/capabilities.py`) ni de PyYAML
(même contrainte, vérifiée dépôt entier : aucun script sous `scripts/` n'importe de dépendance
non-stdlib — convention délibérée, pas une restriction ad hoc à ce seul fichier).

Distinction clé : une exclusion GLOBALE (`**/*.md`, `*.md` nu — couvre TOUT le dépôt) est
interdite. Une exclusion BORNÉE à un sous-arbre précis (ex. `evidence/reviews/**/*.md`, artefacts
de revue scellés historiques dont les octets sont dans la préimage d'un `prompt_sha256` — voir
RC1-011/#441) ou un chemin de fixture individuel reste acceptable si présente et justifiée.

Complexité assumée (Sentinelle Grok-4.6, round 37 RC1-015 — traité, pas ignoré) : ce fichier a
grandi d'un analyseur ligne par ligne minimal vers ~20 regex couvrant ancres/alias, fusions
`<<:`, mappings/listes flow imbriqués et scalaires bloc, au fil d'une longue campagne de revue
aveugle scellée (3 vendors distincts, `civ_review.py`) — décompte exact des rounds et des tests
dans `stories/RC1-015.md`, qui reste la source à jour plutôt qu'un chiffre figé ici. Ce n'est PAS
une accumulation non maîtrisée de rustines : CHAQUE règle a été ajoutée en réponse à une
reproduction YAML concrète, vérifiée
empiriquement contre PyYAML AVANT correctif (jamais par supposition), avec un test de
non-régression dédié — `tests/test_rc1015_gitguardian_scope.py` documente et fige chaque cas.
L'alternative (dépendre de PyYAML) romprait la convention `dependencies=[]` du dépôt
pour ce seul script ; elle a été explicitement examinée et écartée (voir `stories/RC1-015.md`,
addendum round 37). La surface de faux négatifs reste structurellement bornée par construction :
un scan par motifs ne peut jamais couvrir TOUTE la grammaire YAML — c'est pourquoi `gitleaks`
(gate CI indépendante de CE fichier, vérifiée depuis toujours séparément) reste le filet de
dernier recours SPÉCIFIQUEMENT pour le risque que ce cliquet structurel adresse (contournement
de l'exclusion Markdown) : si ce cliquet manque un cas, `gitleaks` scanne le contenu réel
indépendamment de `.gitguardian.yaml`. Ce script n'est qu'un cliquet complémentaire sur UNE
seule config, pas un remplacement d'un parseur YAML conforme, ni une affirmation de préséance
générale sur GitGuardian — voir `Docs/reference/secrets-scanning.md` pour la distinction entre
détecteurs (portées et garanties différentes, aucun des deux ne remplace l'autre).

Usage :
  check_gitguardian_scope.py [--fichier .gitguardian.yaml]
"""
from __future__ import annotations

import argparse
import re
import sys
from fractions import Fraction
from pathlib import Path

# Jeu de caractères d'un nom d'ancre/alias YAML — large volontairement (spec YAML 6.9.2 :
# ns-anchor-char = ns-char - c-flow-indicator, n'exclut QUE les indicateurs flow `,[]{}` et les
# blancs). PyYAML restreint en interne à `[A-Za-z0-9_-]` (son propre code source le documente :
# « The specification does not restrict characters for anchors and aliases... we restrict
# aliases to numbers and ASCII letters » — un choix de désambiguïsation PyYAML, PAS une
# exigence du spec). Round 20 (RC1-015) : s'aligner sur la restriction PyYAML aurait laissé un
# nom d'ancre contenant un point (`&md.glob`, valide selon le spec, potentiellement accepté par
# le parseur réel de GitGuardian même si PyYAML le refuse) non résolu. Bornes retenues ici :
# le jeu de terminateurs reconnu par le scanner PyYAML (`?:,]}%@\``) plus quelques caractères
# d'indicateur/ouverture exclus par prudence pour cet analyseur (`[{&*#'"`).
_CARACTERE_ANCRE = r"[^\s?:,\]}%@`\x00\[{&*#'\"]"

# Propriétés de nœud YAML optionnelles (ancre `&nom` et/ou tag `!nom`) pouvant précéder la
# valeur d'une clé mapping — le spec autorise les DEUX ordres (ancre puis tag, ou tag puis
# ancre ; vérifié empiriquement contre PyYAML, round 20/28). Round 29 (RC1-015) : `ignored_paths`
# elle-même peut porter un TAG explicite (`ignored_paths: !!seq`), pas seulement une ancre
# (rounds 26/27) — `_LIGNE_CLE`/`_LIGNE_CLE_FLOW_OUVERTE` partagent désormais ce même fragment
# que `_LIGNE_CLE_SECRET` (round 28) au lieu de ne tolérer qu'une ancre.
_PROPRIETES_NOEUD = r"(?:&\S+\s*!\S+\s*|!\S+\s*&\S+\s*|&\S+\s*|!\S+\s*)?"

# Round 36 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : le NOM d'une clé
# YAML peut être écrit NU ou entre guillemets (doubles/simples) — sémantiquement indiscernable
# pour tout parseur YAML conforme (vérifié empiriquement contre PyYAML : `"ignored_paths":` et
# `ignored_paths:` produisent la MÊME clé).
_CLE_IGNORED_PATHS_NOM = r'(?:"ignored_paths"|\'ignored_paths\'|ignored_paths)'
_CLE_SECRET_NOM = r'(?:"secret"|\'secret\'|secret)'  # proof:allow — clé de schéma YAML, pas un secret réel

# Round 40 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : les alternatives
# littérales ci-dessus (round 36) ne reconnaissaient qu'une orthographe guillemetée EXACTE — une
# clé double-guillemets contenant un échappement YAML valide (`"ignored\u005fpaths"`, où
# `\u005f` décode en `_`) est pourtant sémantiquement identique à `ignored_paths` pour tout
# parseur conforme (vérifié empiriquement contre PyYAML), mais aucune regex littérale ne peut
# couvrir l'espace infini des échappements équivalents. `_NOM_CLE_QUELCONQUE` capture le nom de
# clé BRUT (nu, guillemets simples — sans échappements en YAML —, ou guillemets doubles — AVEC
# échappements) sans présumer de sa valeur ; `_decoder_nom_cle()` le décode (réutilise
# `_decoder_echappements_yaml`, déjà utilisée pour les VALEURS depuis les rounds 7/10) pour
# comparaison à la cible ("ignored_paths"/"secret") au niveau appelant, plutôt que d'essayer
# d'énumérer les orthographes équivalentes dans la regex elle-même. Remplace les 6 regexes
# `_LIGNE_CLE*`/`_LIGNE_SECRET_*` (round 36) par une forme structurelle PARTAGÉE entre les deux
# clés (indentée pour `ignored_paths`, non indentée pour `secret`, toujours au niveau racine) —
# réduction du nombre de regexes distinctes en plus de la correction du bug (répond aussi à
# l'objection Sentinelle round 37 sur la complexité). Portée : formes BLOC uniquement — la
# recherche de clé DANS un mapping flow (`_CLE_IGNORED_PATHS_DANS_FLOW`, round 32+) reste hors
# périmètre (même limite assumée que le round 36 pour la tolérance aux guillemets simples, non
# encore rapportée pour les échappements).
_NOM_CLE_QUELCONQUE = r'(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\])*)\'|([^\s:#][^:#]*?))'


def _decoder_nom_cle(
    m: re.Match,
    indice_premier_groupe: int,
    ancres: dict[str, str | list[str]] | None = None,
) -> str:
    """Décode le nom de clé capturé par `_NOM_CLE_QUELCONQUE` (3 groupes à partir de
    `indice_premier_groupe` : guillemets doubles décodés, guillemets simples littéral, ou nu) —
    round 40 (RC1-015).

    Round 80 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la branche NUE
    capture aussi bien un nom littéral (`ignored_paths`) qu'un ALIAS utilisé comme NOM DE CLÉ
    (`*k`, où `&k` ancre la chaîne `"ignored_paths"` ailleurs dans le fichier) — YAML valide,
    vérifié empiriquement contre PyYAML : `? *k\\n:` (ou même `*k:` sans `?`) résout la clé vers
    la valeur de l'ancre. La comparaison littérale à `"ignored_paths"`/`"secret"` échouait alors
    systématiquement pour cette forme. `ancres` (optionnel, `None` par défaut — comportement
    inchangé pour tout appelant qui ne le fournit pas) permet désormais de résoudre un alias
    NU dont la valeur ancrée est un SCALAIRE (une liste/dict n'a pas de sens comme nom de clé
    ici) — sinon, repli sur le texte brut (`*k` littéral), comportement identique à avant.
    """
    if m.group(indice_premier_groupe) is not None:
        return _decoder_echappements_yaml(m.group(indice_premier_groupe))
    if m.group(indice_premier_groupe + 1) is not None:
        return m.group(indice_premier_groupe + 1)
    brut = m.group(indice_premier_groupe + 2)
    if ancres:
        match_alias = _REF_ALIAS.match(brut)
        if match_alias:
            valeur_ancree = ancres.get(match_alias.group(1))
            if isinstance(valeur_ancree, str):
                return valeur_ancree
    return brut


# Forme INDENTÉE (`ignored_paths`, jamais à la racine) : groupe 1 = indentation, groupes 2-4 =
# nom de clé (`_decoder_nom_cle(m, 2)`), dernier groupe = comment/alias selon la forme.
_LIGNE_CLE = re.compile(r"^(\s*)" + _NOM_CLE_QUELCONQUE + r"\s*:\s*" + _PROPRIETES_NOEUD + r"(#.*)?$")
_LIGNE_CLE_FLOW_OUVERTE = re.compile(
    r"^(\s*)" + _NOM_CLE_QUELCONQUE + r"\s*:\s*" + _PROPRIETES_NOEUD + r"\["
)
_LIGNE_CLE_ALIAS = re.compile(
    r"^(\s*)" + _NOM_CLE_QUELCONQUE + r"\s*:\s*\*(" + _CARACTERE_ANCRE + r"+)\s*(#.*)?$"
)
# Round 42 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : syntaxe YAML de clé
# EXPLICITE (indicateur `?`, spec 8.2.1) — la clé et son séparateur `:` peuvent être sur des
# lignes DISTINCTES (`? ignored_paths\n:` au lieu de `ignored_paths:`), forme rare mais valide
# et supportée par PyYAML (vérifié empiriquement). Portée initialement bornée au nom de clé
# inline après `?` (pas sur une ligne séparée) — non traité faute de reproduction rapportée sur
# une clé multi-lignes.
#
# Round 46 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la limite documentée à la fin
# du round 42 (« pas de valeur inline après `:` ») est comblée — une valeur peut légitimement
# suivre le séparateur `:` sur la MÊME ligne (`: [*alias]`, `: *alias`), pas seulement sur les
# lignes suivantes. `_LIGNE_VALEUR_EXPLICITE_FLOW_OUVERTE`/`_LIGNE_VALEUR_EXPLICITE_ALIAS`
# reconnaissent ces deux formes ; `_LIGNE_VALEUR_EXPLICITE` (`:` seul) reste le cas où la valeur
# vit sur les lignes suivantes (round 42, inchangé). Scalaire nu/guillemeté inline après `:` hors
# périmètre faute de reproduction rapportée sur cette forme spécifique.
#
# Round 50 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la clé RACINE elle-même
# (round 49 : reconnue en syntaxe explicite) peut porter une valeur MAPPING FLOW inline après son
# séparateur `:` (`? secret\n: {ignored_paths: [*md]}`) — symétrique à `_LIGNE_SECRET_FLOW_OUVERTE`
# (round 32) pour la forme bloc classique. `_LIGNE_VALEUR_EXPLICITE_SECRET_FLOW_OUVERTE`
# reconnaît cette forme.
# Round 51 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `_LIGNE_VALEUR_EXPLICITE`
# (`:` seul, valeur bloc sur les lignes suivantes) n'acceptait aucune propriété de nœud (ancre
# et/ou tag) entre le séparateur `:` et le commentaire optionnel — symétrique à ce que
# `_PROPRIETES_NOEUD` tolère déjà pour toutes les formes `clé: <properties>?` depuis les rounds
# 26-29. Un séparateur `: &nom` (ancre sur la valeur bloc qui suit) n'était donc pas reconnu.
#
# Round 52 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : le même défaut affectait
# `_LIGNE_VALEUR_EXPLICITE_FLOW_OUVERTE` (`: [`, round 46) — `: &nom [...]` n'était pas reconnu,
# alors que `_LIGNE_CLE_FLOW_OUVERTE`/`_LIGNE_SECRET_FLOW_OUVERTE` (formes bloc classiques)
# tolèrent déjà `_PROPRIETES_NOEUD` avant `[`/`{`. Élargi symétriquement, ainsi que
# `_LIGNE_VALEUR_EXPLICITE_SECRET_FLOW_OUVERTE` (`: {`, round 50, même défaut vérifié
# proactivement). `_LIGNE_VALEUR_EXPLICITE_ALIAS` (`: *nom`) reste SANS cette tolérance —
# vérifié empiriquement que `&nom *autre` (ancre précédant directement un alias) est un
# ParserError PyYAML, pas une forme YAML valide : aucune propriété ne peut précéder un alias.
#
# Round 53 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : les rounds 51-52 corrigeaient
# le côté VALEUR (`:`) du séparateur explicite — `_LIGNE_CLE_EXPLICITE` (le côté CLÉ, `?`)
# souffrait du même défaut symétrique, jamais corrigé : aucune propriété de nœud entre `?` et le
# nom de clé (`? !!str secret`, tag sur la clé explicite elle-même). Élargi de la même façon.
_LIGNE_CLE_EXPLICITE = re.compile(
    r"^(\s*)\?\s*" + _PROPRIETES_NOEUD + _NOM_CLE_QUELCONQUE + r"\s*(#.*)?$"
)
_LIGNE_VALEUR_EXPLICITE = re.compile(r"^(\s*):\s*" + _PROPRIETES_NOEUD + r"(#.*)?$")
_LIGNE_VALEUR_EXPLICITE_ALIAS = re.compile(r"^(\s*):\s*\*(" + _CARACTERE_ANCRE + r"+)\s*(#.*)?$")
_LIGNE_VALEUR_EXPLICITE_FLOW_OUVERTE = re.compile(r"^(\s*):\s*" + _PROPRIETES_NOEUD + r"\[")
_LIGNE_VALEUR_EXPLICITE_SECRET_FLOW_OUVERTE = re.compile(r"^(\s*):\s*" + _PROPRIETES_NOEUD + r"\{")
_LIGNE_ITEM = re.compile(r'^(\s*)-\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))\s*(#.*)?$')
# Round 111 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : miroir manqué de
# `_LIGNE_CLE_BLOC` (round 12) — un item de LISTE portant une ancre directement sur son scalaire
# bloc (`- &a >-\n  **/*.md`, forme YAML valide, vérifiée empiriquement : PyYAML résout
# `secret.ignored_paths` en `['**/*.md']`) n'était reconnu NI par cette regex (qui n'autorisait
# qu'un TAG optionnel avant l'indicateur `[|>]`, pas une ANCRE) NI par `_LIGNE_ITEM` (qui exige
# qu'il ne reste que `\s*(#.*)?$` après le premier jeton nu — `&a` — alors qu'il reste `>-` avant
# la fin de ligne). `verifier()` concluait à tort à la conformité.
#
# Round 112 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro, via
# DeepSeek-V4-Pro-0813) : le correctif round 111 (`(?:&\S+\s+)?(?:!\S*\s+)?`) réintroduisait
# EXACTEMENT le défaut d'ordre déjà résolu par `_PROPRIETES_NOEUD` (round 20/28, voir sa
# docstring : « le spec autorise les DEUX ordres, ancre puis tag OU tag puis ancre ») — un ordre
# unique (ancre PUIS tag) codé en dur, alors que `!!str &a >-` (tag PUIS ancre, YAML valide,
# vérifié empiriquement : PyYAML résout la même liste `['**/*.md']`) reste non reconnu. Reprend
# donc directement `_PROPRIETES_NOEUD` (déjà correcte, déjà partagée par `_LIGNE_CLE`/
# `_LIGNE_CLE_FLOW_OUVERTE`/`_LIGNE_SECRET_FLOW_OUVERTE`) au lieu de réinventer un fragment ad hoc
# — élimine la classe entière de bugs d'ordre, pas seulement le cas signalé. `_LIGNE_CLE_BLOC`
# (round 12, JAMAIS migrée vers `_PROPRIETES_NOEUD`) souffrait du MÊME défaut symétrique côté
# CLÉ (`secret.ignored_paths: !!str &a >-` non reconnu, vérifié empiriquement AVANT ce round) —
# corrigée proactivement en même temps, même fragment partagé.
#
# Seul `.group(1)` (indentation) est consommé par les 3 appelants de `_LIGNE_ITEM_BLOC`
# (`_lignes_contenu_bloc`, `_consommer_sequence_ancree`, `parser_ignored_paths`) — `_PROPRIETES_
# NOEUD` ne capture rien (groupe non capturant), aucun décalage d'index pour les appelants
# existants, ici ou pour `_LIGNE_CLE_BLOC`.
_LIGNE_ITEM_BLOC = re.compile(
    r"^(\s*)-\s*" + _PROPRIETES_NOEUD + r"([|>])(?:[+-][1-9]|[1-9][+-]|[+-]|[1-9])?\s*(#.*)?$"
)
_LIGNE_ITEM_ALIAS = re.compile(r"^(\s*)-\s*\*(" + _CARACTERE_ANCRE + r"+)\s*(#.*)?$")
_CHAINE_DOUBLE_GUILLEMETS = re.compile(r'"((?:[^"\\]|\\.)*)"', re.DOTALL)
_CHAINE_SIMPLE_GUILLEMETS = re.compile(r"'((?:[^'\\])*)'")
_ECHAPPEMENT_YAML = re.compile(
    r"\\(?:u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|U[0-9a-fA-F]{8}|/|\\|\n[ \t]*)"
)
# Round 44 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : le nom de clé
# nu `[^\s:#-][^:#]*` ne reconnaît pas une clé GUILLEMETÉE contenant un `:` littéral
# (`"note: benign": |-`) — le `:` interne, rencontré avant le vrai séparateur, faisait échouer
# la reconnaissance de la ligne comme porteuse d'un scalaire bloc, laissant son contenu
# (potentiellement une fausse hiérarchie `secret.ignored_paths`) hors de `lignes_exclues`.
# Réutilise `_NOM_CLE_QUELCONQUE` (round 40) — seule l'indentation (groupe 1) est consommée par
# l'appelant (`_lignes_contenu_bloc`), le nom de clé lui-même n'a pas besoin d'être décodé ici
# (cette fonction n'a pas besoin de savoir QUELLE clé porte le scalaire, seulement qu'il y en a
# UNE, quelle que soit sa forme).
#
# Round 112 (RC1-015, correctif proactif — même défaut symétrique que `_LIGNE_ITEM_BLOC`,
# corrigé le même round par bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : le fragment
# ad hoc `(?:&\S+\s+)?(?:!\S*\s+)?` codait en dur l'ordre ancre-PUIS-tag, alors que YAML autorise
# aussi tag-PUIS-ancre (`secret.ignored_paths: !!str &a >-`, vérifié empiriquement AVANT ce
# round : non reconnu, `verifier()` concluait à tort à la conformité ; PyYAML résout pourtant la
# même chaîne `'**/*.md'`). Reprend `_PROPRIETES_NOEUD` (round 20/28, déjà correcte pour les
# DEUX ordres) au lieu du fragment ad hoc — aucun groupe capturant ajouté, aucun décalage
# d'index pour l'appelant existant.
_LIGNE_CLE_BLOC = re.compile(
    r"^(\s*)" + _NOM_CLE_QUELCONQUE + r"\s*:\s*" + _PROPRIETES_NOEUD + r"([|>])(?:[+-][1-9]|[1-9][+-]|[+-]|[1-9])?\s*(#.*)?$"
)
# Forme NON INDENTÉE (`secret`, toujours à la racine, colonne 0) : groupes 1-3 = nom de clé
# (`_decoder_nom_cle(m, 1)`), dernier groupe = comment/alias selon la forme.
_LIGNE_CLE_SECRET = re.compile(  # proof:allow — identifiant de variable, pas un secret réel
    r"^" + _NOM_CLE_QUELCONQUE + r"\s*:\s*" + _PROPRIETES_NOEUD + r"(#.*)?$"
)  # proof:allow — clé de schéma YAML, pas un secret réel
_LIGNE_SECRET_ALIAS = re.compile(  # proof:allow — identifiant de variable, pas un secret réel
    r"^" + _NOM_CLE_QUELCONQUE + r"\s*:\s*\*(" + _CARACTERE_ANCRE + r"+)\s*(#.*)?$"
)  # proof:allow — clé de schéma YAML, pas un secret réel
_LIGNE_FUSION = re.compile(r"^(\s*)<<\s*:\s*\*(" + _CARACTERE_ANCRE + r"+)\s*(#.*)?$")
# Round 56 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la clé de FUSION
# YAML (round 31) peut référencer PLUSIEURS ancres via une LISTE flow (`<<: [*a, *b]`) — forme
# valide de l'extension `tag:yaml.org,2002:merge` (vérifiée empiriquement contre PyYAML), pas
# seulement un alias unique (`<<: *nom`, seule forme couverte jusqu'ici). `_LIGNE_FUSION` exigeait
# `\*` immédiatement après `:`, ne matchant donc jamais `[`.
_LIGNE_FUSION_FLOW_OUVERTE = re.compile(r"^(\s*)<<\s*:\s*\[")
# Round 56 (suite, gap symétrique proactif — même extension `tag:yaml.org,2002:merge`, vérifiée
# empiriquement contre PyYAML) : la « séquence de nœuds mapping » que permet la fusion peut aussi
# s'écrire en style BLOC plutôt qu'en liste flow — `<<:\n  - *a\n  - *b` résout identiquement à
# `<<: [*a, *b]`. `_LIGNE_FUSION_FLOW_OUVERTE`/`_LIGNE_FUSION` ne couvrent ni l'un ni l'autre :
# la valeur de `<<:` y est vide (rien après les deux-points sur la même ligne), les ancres vivant
# sur les lignes suivantes, plus indentées, comme des items `- *nom` (réutilise `_LIGNE_ITEM_ALIAS`,
# déjà en place pour `ignored_paths` lui-même).
_LIGNE_FUSION_VALEUR_VIDE = re.compile(r"^(\s*)<<\s*:\s*(#.*)?$")
_LIGNE_SECRET_FLOW_OUVERTE = re.compile(  # proof:allow — identifiant de variable, pas un secret réel
    r"^" + _NOM_CLE_QUELCONQUE + r"\s*:\s*" + _PROPRIETES_NOEUD + r"\{"
)  # proof:allow — clé de schéma YAML, pas un secret réel
# Round 41 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la limite assumée à
# la fin du round 40 est comblée — cette regex utilise désormais une capture générique de nom de
# clé (au lieu de `_CLE_IGNORED_PATHS_NOM`, littéral seulement), avec le décodage/comparaison
# fait par l'appelant (`_resoudre_ignored_paths_dans_mapping_flow`) après le filtrage par
# spans/profondeur déjà en place (rounds 33/35/37) — la boundary guillemet (round 37 :
# `position == g_debut` = candidat guillemeté légitime) reste correcte quelle que soit la forme
# du nom capturé, le décodage n'intervenant qu'APRÈS ce filtrage structurel.
#
# `_NOM_CLE_QUELCONQUE` (round 40) n'est PAS réutilisable ici tel quel : cette regex est utilisée
# NON ANCRÉE (`finditer` sur le contenu ENTIER d'un mapping flow, round 32+), contrairement aux
# formes bloc du round 40 qui sont ancrées à `^` un début de ligne. Son alternative nue
# (`[^\s:#][^:#]*?`) exclut seulement `:`/`#` — trouvé RÉEL (bug proactif, en vérifiant ce
# correctif) : sans exclure aussi les indicateurs flow (`,[]{}`), un candidat nu peut engloutir
# du texte à travers une frontière d'item flow (virgule, crochet) et masquer la vraie clé qui le
# suit. `_NOM_CLE_QUELCONQUE_FLOW` exclut en plus ces indicateurs dans son alternative nue —
# les formes guillemetées restent partagées avec `_NOM_CLE_QUELCONQUE` (un guillemet peut
# légitimement contenir `,[]{}` en tant que caractères littéraux du nom).
# Round 85 (RC1-015, finding réfuté avec preuve — revue scellée GPT-5.6-Terra-Pro) : le finding
# évoquait un nom de clé `ignored_paths` double-guillemets réparti sur PLUSIEURS lignes (via
# continuation échappée `\` + saut de ligne) au sein d'un mapping FLOW, non couvert par
# `_NOM_CLE_QUELCONQUE_FLOW` (compilée sans `re.DOTALL`, contrairement à `_CHAINE_DOUBLE_GUILLEMETS`).
# La reproduction fournie était elle-même invalide YAML — vérifié EMPIRIQUEMENT, avant tout
# correctif, que PyYAML rejette catégoriquement TOUT nom de clé double/simple-guillemets
# multi-ligne au sein d'un mapping FLOW, quelle que soit la syntaxe exacte (avec ou sans
# continuation échappée, avec ou sans espace de fold) — `ParserError: while parsing a flow
# mapping, expected ',' or '}'` dans TOUS les cas testés. Plus surprenant encore, un nom de clé
# multi-ligne échoue AUSSI en syntaxe BLOC classique (`mapping values are not allowed here`) —
# SEULE la forme EXPLICITE (`? "nom\\n"\n:`) le supporte, déjà correctement gérée depuis les
# rounds 58/63 (`_decoder_cle_explicite_multiligne`). Voir
# `test_pyyaml_reel_refute_nom_de_cle_multiligne_dans_mapping_flow` pour la preuve exécutable.
# Aucune construction YAML valide ne peut donc exploiter cette forme dans un mapping flow —
# `_NOM_CLE_QUELCONQUE_FLOW` reste délibérément sans `re.DOTALL`.
_NOM_CLE_QUELCONQUE_FLOW = r'(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\])*)\'|([^\s:#,\[\]{}]+?))'
_CLE_IGNORED_PATHS_DANS_FLOW = re.compile(
    _NOM_CLE_QUELCONQUE_FLOW + r"\s*:\s*" + _PROPRIETES_NOEUD
)
# Round 59 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : miroir de
# `_CLE_IGNORED_PATHS_DANS_FLOW` mais pour la clé de FUSION `<<` (round 31) recherchée AU SEIN
# d'un mapping flow — un mapping flow ancré, référencé par `secret` (round 30/57), peut lui-même
# fusionner un AUTRE mapping ancré via `<<` (`cfg: &cfg {<<: *md}`), sans qu'aucun mécanisme
# existant ne le résolve. Pas de nom de clé générique nécessaire ici (`<<` est un littéral fixe,
# contrairement à `ignored_paths`), donc pas de dépendance à `_NOM_CLE_QUELCONQUE_FLOW`.
_CLE_FUSION_DANS_FLOW = re.compile(r"<<\s*:\s*")
_DEF_ANCRE = re.compile(r"&(" + _CARACTERE_ANCRE + r"+)")
_REF_ALIAS = re.compile(r"^\*(" + _CARACTERE_ANCRE + r"+)$")
_REF_ALIAS_PARTIEL = re.compile(r"^\*(" + _CARACTERE_ANCRE + r"+)")
_BLOC_ANCRE = re.compile(r"^([|>])(?:[+-][1-9]|[1-9][+-]|[+-]|[1-9])?\s*(#.*)?$")
_TAG_YAML = re.compile(r"^!\S*\s+")
# Round 48 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : un `&nom` peut
# apparaître à l'intérieur d'un scalaire NU déjà commencé (`note: foo&md safe`) sans être une
# propriété de nœud — vérifié empiriquement contre PyYAML : `&` ne démarre une ancre que s'il
# est à la position de DÉBUT d'une valeur (juste après `clé:`+blanc, `-`+blanc, un tag+blanc, ou
# en tout début de ligne), jamais au milieu d'un scalaire déjà en cours. Ce fragment décrit
# EXACTEMENT ces préfixes légitimes ; un candidat `&` dont le préfixe de ligne (tout ce qui le
# précède) ne matche PAS entièrement ce fragment est ignoré — la table d'ancres n'est alors plus
# écrasée à tort par un `&nom` textuel sans rapport.
#
# Round 54 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : une clé EXPLICITE ARBITRAIRE
# (`? nom\n: &ancre …`, pas seulement `secret`/`ignored_paths` — `_construire_table_ancres`
# balaie TOUT le fichier, round 12) porte son ancre sur une ligne de séparateur `:` SEUL, sans
# aucun nom de clé sur cette même ligne (le nom a déjà été consommé par la ligne `?` précédente).
# `_PREFIXE_AVANT_ANCRE` ne reconnaissait pas ce préfixe (`:` seul, sans clé avant) comme une
# position de début de valeur légitime. Ajouté comme alternative dédiée.
#
# Round 65 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : une ancre peut porter une clé
# À L'INTÉRIEUR d'un mapping FLOW (`holder: { paths: &paths [*base] }`) — le préfixe complet
# (`holder: { paths: `) ne correspondait à AUCUNE alternative existante (toutes exigent une
# UNIQUE clé depuis le début de ligne, jamais une clé EXTÉRIEURE suivie d'un `{` ouvrant avant la
# clé locale). Élargi pour tolérer un préfixe EXTÉRIEUR arbitraire se terminant par `{` ou `,`
# (frontière d'entrée de mapping flow, quelle que soit sa profondeur d'imbrication — seule la
# frontière LOCALE immédiatement avant `clé:` importe, pas l'historique complet de nesting).
# Limite assumée (comme `_decouper_liste_flow`, round 39) : ce préfixe extérieur n'est pas
# vérifié contre les spans guillemetés qui le précèdent — un `{`/`,` littéral à l'intérieur d'une
# chaîne AVANT la clé locale pourrait en théorie déclencher cette alternative à tort ; non
# rencontré empiriquement, hors périmètre du finding vérifié ici.
#
# Round 114 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : deux préfixes
# légitimes de début de valeur manquaient encore. (1) Une ancre peut porter directement la
# VALEUR d'une clé EXPLICITE, sur la ligne `?` elle-même (`? &paths >-\n  **/*.md\n: value`,
# distinct du round 54 où l'ancre était sur la ligne `:` séparée) — YAML valide, vérifié
# empiriquement : PyYAML résout `{'**/*.md': 'value', ...}`, et référencer `*paths` dans
# `secret.ignored_paths` réintroduit une exclusion RÉELLE non détectée (`verifier()` concluait à
# tort `ok=True` avant ce correctif). (2) Une ancre peut porter un item de liste IMBRIQUÉE
# (`- - &paths >-`, plusieurs tirets consécutifs) — seul UN tiret unique était reconnu.
# `-\s+` élargi en `(?:-\s+)+` (un ou plusieurs), nouvelle alternative `\?\s+` ajoutée pour le
# préfixe clé explicite. Aucun groupe capturant ajouté (les deux ajouts sont non capturants),
# aucun décalage d'index pour l'appelant (`_construire_table_ancres`, seul usage).
_PREFIXE_AVANT_ANCRE = re.compile(
    r"^\s*(?:(?:-\s+)+|\?\s+|:\s*|(?:.*[{,]\s*)?" + _NOM_CLE_QUELCONQUE + r"\s*:\s*)?(?:!\S+\s+)?$"
)
# Round 57 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la clé `secret`
# réduite à un alias direct `*cfg` (round 30, ou fusionnée via `<<: *cfg`, round 31/56) compose
# avec `cfg: &cfg {ignored_paths: [...]}` (round 32, mapping FLOW porté par l'ancre elle-même)
# sans que cette composition soit résolue — `_construire_table_ancres` exclut explicitement les
# ancres sur un mapping entier de son périmètre (round 12), et le pré-passage round 32 ne
# cherchait `{` qu'après la clé littérale `secret`, jamais après une ancre nommée différemment.
# Reconnaît ce qui suit un nom d'ancre valide (tag optionnel inclus, même ordre que
# `_PROPRIETES_NOEUD`) quand cela ouvre un mapping flow.
_SUITE_ANCRE_FLOW_OUVERTE = re.compile(r"^\s*(?:!\S+\s*)?\{")


def _position_fusion(
    position_base: int | float | Fraction, index_jeton: int
) -> int | float | Fraction:
    """Position EFFECTIVE d'un élément d'une fusion-LISTE (`<<: [*a, *b, …]`), à l'index
    `index_jeton` (0 = premier élément), dérivée de `position_base` (position de la ligne `<<:`
    ou du mapping flow racine portant la fusion) — round 100/101/102/103 (RC1-015).

    Round 100 : chaque élément recevait `position_base - index_jeton` (décalage ENTIER) pour
    reproduire la préséance YAML merge-key (le premier élément de la liste gagne). Round 101
    (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : ce décalage entier peut entrer en
    COLLISION avec la position RÉELLE (entière elle aussi) d'un contenu totalement indépendant
    ailleurs dans le document (ex. une occurrence antérieure de la clé racine `secret`) —
    `position_base - 1` peut coïncider EXACTEMENT avec la ligne de ce contenu tiers, faussant le
    départage `position > meilleur_trouve_ligne` (jamais à égalité) au profit de l'ordre de
    balayage plutôt que de la sémantique YAML. Corrigé round 101 en décalant par une fraction
    (`index_jeton / DIVISEUR_FIXE`) — mais avec un DIVISEUR FIXE, la garantie ne tenait que pour
    `index_jeton < DIVISEUR_FIXE` : round 102 (bug réel trouvé par revue scellée
    GPT-5.6-Terra-Pro) — à `index_jeton == DIVISEUR_FIXE` PILE, la fraction vaut EXACTEMENT 1,
    recréant la collision que round 101 prétendait éliminer (`_position_fusion(10, 1_000_000)
    == 9`, PAS strictement `> 9`).

    Round 102 : diviseur DYNAMIQUE `index_jeton + 1` (au lieu d'une constante fixe), calculé en
    arithmétique FLOTTANTE (`float`, `/`). Round 103 (bug réel trouvé par revue scellée
    GPT-5.6-Terra-Pro) : la garantie « `index_jeton / (index_jeton + 1)` mathématiquement `< 1`
    pour TOUT `index_jeton` » est FAUSSE en arithmétique FLOTTANTE IEEE-754 (précision finie,
    ~15-17 chiffres significatifs) — pour un `index_jeton` suffisamment grand (`>= 10**16`
    environ), la division flottante s'ARRONDIT à `1.0` pile, recréant la collision. Vérifié
    empiriquement AVANT correctif : `_position_fusion(10, 10**20) == 9.0` (PAS strictement
    `> 9`), alors que le test round 101/102 ne couvrait que jusqu'à `10**12` (jamais assez grand
    pour révéler la perte de précision).

    Round 103 : remplace la division FLOTTANTE par `fractions.Fraction` (stdlib pur,
    `dependencies=[]` respecté) — arithmétique RATIONNELLE EXACTE, AUCUNE perte de précision
    possible quelle que soit l'ampleur de `index_jeton` (contrairement à `float`, une `Fraction`
    représente exactement n'importe quel rapport de deux entiers, aussi grands soient-ils).
    `Fraction(index_jeton, index_jeton + 1) < 1` est donc VRAIMENT garanti pour TOUT
    `index_jeton >= 0`, sans aucune approximation numérique — la propriété mathématique visée
    depuis le round 102 est enfin RÉELLEMENT sans exception, pas seulement en théorie idéalisée.
    Comparaisons (`>`) avec des positions `int`/`float` ordinaires ailleurs dans ce fichier
    restent correctes : `Fraction` implémente nativement les opérateurs de comparaison avec les
    autres types numériques Python, sans conversion avec perte.
    """
    if index_jeton == 0:
        return position_base
    return position_base - Fraction(index_jeton, index_jeton + 1)


def _remplacer_un_echappement(match: re.Match) -> str:
    jeton = match.group(0)
    if jeton == "\\/":
        return "/"
    if jeton == "\\\\":
        return "\\"
    if jeton.startswith("\\\n"):
        # Continuation de ligne échappée (scalaire double-guillemets multi-ligne) : le saut de
        # ligne ET l'indentation de tête de la ligne suivante sont retirés, sans espace de
        # remplacement — round 11, voir docstring de _decoder_echappements_yaml.
        return ""
    # \uNNNN / \xNN / \UNNNNNNNN (N = chiffre hex) : délégué à unicode_escape sur le SEUL
    # jeton matché (jamais sur la valeur entière — voir _decoder_echappements_yaml).
    return jeton.encode("utf-8", "backslashreplace").decode("unicode_escape")


def _decoder_echappements_yaml(valeur: str) -> str:
    """Décode les échappements `\\uNNNN`/`\\xNN`/`\\UNNNNNNNN` (N = chiffre hex) et `\\/` d'une
    valeur YAML entre guillemets DOUBLES (les guillemets simples YAML ne supportent AUCUN
    échappement — un backslash y reste littéral, jamais décodé).

    Substitution ATOMIQUE jeton-par-jeton en un seul passage gauche-à-droite (`re.sub` sur
    `_ECHAPPEMENT_YAML`, jamais un `.replace("\\/", "/")` naïf après coup) : un `\\\\` authentique
    (backslash échappé) consomme exactement ses 2 caractères et redevient un unique `\\`, ce qui
    laisse un `/` qui le suivrait comme jeton SÉPARÉ à l'itération suivante — sans ce découpage
    atomique, une valeur `\\\\/x` (backslash littéral puis slash littéral) serait indistinguable
    d'un authentique `\\/x` (slash échappé) après une simple substitution textuelle post-hoc.

    Bugs réels corrigés, trouvés par revue scellée GPT-5.6-Terra-Pro :
    - round 7 : `"**/*\\u002emd"` est sémantiquement `**/*.md` pour tout parseur YAML conforme
      (`\\u002e` = `.`), donc réintroduirait l'exclusion globale sans être reconnu par une
      comparaison sur le texte brut non décodé.
    - round 10 : `"**\\/*.md"` est sémantiquement `**/*.md` (`\\/` est un échappement YAML valide
      d'un `/` littéral — vérifié empiriquement contre PyYAML : `yaml.safe_load` le résout bien
      en `/`), mais l'ancienne implémentation fondée sur `str.encode(...).decode("unicode_escape")`
      sur la valeur ENTIÈRE ne reconnaît pas `\\/` (absent du jeu d'échappements Python), le
      laissant tel quel — `verifier()` concluait alors à tort à la conformité.
    - round 11 : un scalaire double-guillemets peut s'étendre sur PLUSIEURS lignes physiques via
      une continuation de ligne échappée (`\\` immédiatement suivi d'un saut de ligne) — le saut
      de ligne ET l'indentation de tête de la ligne suivante sont alors retirés SANS espace de
      remplacement (vérifié empiriquement contre PyYAML). `_ECHAPPEMENT_YAML` reconnaît désormais
      ce jeton (`\\\n[ \t]*`) en plus des échappements mono-ligne.

    Retombe sur la valeur brute si le décodage échoue (séquence invalide) plutôt que de lever
    une exception ; un jeton `\\uNNNN` mal formé (moins de 4 chiffres hex valides) ne matche
    simplement pas `_ECHAPPEMENT_YAML` et reste tel quel dans le résultat, sans jamais lever.
    """
    try:
        return _ECHAPPEMENT_YAML.sub(_remplacer_un_echappement, valeur)
    except (UnicodeDecodeError, UnicodeEncodeError):
        return valeur


def _consommer_scalaire_bloc(lignes: list[str], depart: int, indentation_item: int) -> tuple[str, int]:
    """Consomme les lignes de contenu d'un scalaire YAML bloc (`|` littéral ou `>` replié)
    démarrant à `depart`, plus indentées que `indentation_item` (colonne du tiret `-`).

    Retourne (valeur_jointe, index de la première ligne NON consommée). Jointure simplifiée
    (littéral → `\\n`, replié → espace, lignes vides ignorées) : suffisante pour détecter un
    glob interdit reconstitué sur une ou plusieurs lignes de contenu, sans modéliser l'intégralité
    des règles de pliage YAML (hors périmètre — un glob légitime ne contient jamais de ligne
    vide interne).
    """
    morceaux: list[str] = []
    i = depart
    while i < len(lignes):
        suite = lignes[i]
        suite_nue = suite.strip()
        if suite_nue:
            indentation_suite = len(suite) - len(suite.lstrip(" "))
            if indentation_suite <= indentation_item:
                break
            morceaux.append(suite_nue)
        i += 1
    return " ".join(morceaux), i


def _lignes_contenu_bloc(lignes: list[str]) -> set[int]:
    """Indices des lignes qui sont le CONTENU d'un scalaire bloc `clé: |`/`clé: >` (mapping,
    éventuellement ancrée/taguée — `_LIGNE_CLE_BLOC`) OU `- |`/`- >` (item de liste,
    `_LIGNE_ITEM_BLOC`), PARTOUT dans le fichier — pas seulement dans `ignored_paths`.

    Bug réel trouvé par revue scellée GPT-5.6-Terra-Pro (RC1-015 round 18) : la recherche flow
    globale (`_LIGNE_CLE_FLOW_OUVERTE.search()` sur le texte entier) peut matcher du texte qui
    N'EST PAS une vraie clé YAML, mais le CONTENU d'un scalaire bloc d'une clé sans rapport
    (`note: |-\\n  ignored_paths: [safe]`) — ce texte est un simple littéral au sein d'un autre
    scalaire, pas de la structure YAML. Sans exclusion, le parseur retourne cette fausse liste et
    n'examine JAMAIS la vraie liste `secret.ignored_paths`, masquant une réintroduction réelle
    portée par ailleurs (ex. un alias résolu vers `**/*.md`). Cette fonction identifie ces lignes
    de contenu pour que la recherche structurelle (clé `ignored_paths:`, flow ou bloc) les
    ignore systématiquement.
    """
    exclues: set[int] = set()
    i = 0
    n = len(lignes)
    while i < n:
        ligne = lignes[i]
        match_cle_bloc = _LIGNE_CLE_BLOC.match(ligne)
        if match_cle_bloc:
            indentation = len(match_cle_bloc.group(1))
            _, j = _consommer_scalaire_bloc(lignes, i + 1, indentation)
            exclues.update(range(i + 1, j))
            i = j
            continue
        match_item_bloc = _LIGNE_ITEM_BLOC.match(ligne)
        if match_item_bloc:
            indentation = len(match_item_bloc.group(1))
            _, j = _consommer_scalaire_bloc(lignes, i + 1, indentation)
            exclues.update(range(i + 1, j))
            i = j
            continue
        i += 1
    return exclues


def _trouver_definition_ancre_valide(ligne: str) -> list[re.Match]:
    """TOUS les candidats `&nom` valides sur `ligne` (dans l'ordre d'apparition) : hors chaîne
    guillemetée, hors commentaire, précédé d'un préfixe de position-de-valeur légitime
    (`_PREFIXE_AVANT_ANCRE`) — round 59 (RC1-015). Factorisé de la même logique de filtrage,
    jusqu'ici DUPLIQUÉE deux fois (`_construire_table_ancres`, rounds 23-25 ; le pré-passage
    round 57 dans `parser_ignored_paths`), pour éviter une TROISIÈME duplication ici (round 59).
    Un nouveau besoin de repérer une définition d'ancre valide en dehors de
    `_construire_table_ancres` (qui exclut délibérément les ancres-mapping de son périmètre,
    round 12) justifie enfin l'extraction — `_construire_table_ancres` elle-même n'est PAS
    refactorée pour la réutiliser (fonction à l'historique de revue déjà long, rounds 12-25 :
    risque de régression non justifié par ce seul correctif).

    Round 74 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro — même finding que
    le correctif `_construire_table_ancres` de ce round) : retournait auparavant seulement le
    PREMIER candidat valide (`return candidat` dès la première itération). Une ligne flow peut
    porter PLUSIEURS ancres (`{ bruit: &bruit 1, cfg: &cfg {ignored_paths: [*md]} }`) — les
    deux appelants cherchent un nom PRÉCIS parmi un ensemble connu (`noms_alias_racine`/
    `position_alias_racine`) ; si ce nom n'est pas le PREMIER candidat de sa ligne, il n'était
    jamais examiné, laissant une clé racine dupliquée passer inaperçue. Reproduction vérifiée
    empiriquement contre PyYAML (voir
    `test_construire_table_ancres_deux_ancres_meme_ligne_flow` et
    `test_pre_passage_round57_trouve_ancre_precedee_par_autre_ancre_meme_ligne`). Retourne
    désormais la liste COMPLÈTE des candidats valides — les appelants itèrent et filtrent par
    nom eux-mêmes, au lieu de recevoir un candidat unique déjà présupposé pertinent.

    Round 75 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la détection de
    commentaire ci-dessous traitait tout `#` non guillemeté comme un début de commentaire, sans
    vérifier le caractère PRÉCÉDENT — contrairement à la règle YAML déjà correctement appliquée
    par `_spans_commentaires` (round 38) : `#` ne démarre un commentaire que séparé du contenu
    précédent (`_CARACTERES_PRECEDENT_COMMENTAIRE`) ; à l'intérieur d'un scalaire nu SANS
    séparation (`note: foo#bar`), il fait partie de la valeur littérale. Reproduction vérifiée
    empiriquement contre PyYAML : un `#` interne à un scalaire, AVANT une ancre légitime
    (`&paths`) sur la même ligne, faisait perdre `position_commentaire` trop tôt, écartant
    ensuite `&paths` comme s'il était dans un commentaire. Corrigé en appliquant la MÊME règle
    de bord que `_spans_commentaires`.
    """
    spans_guillemets = [sp.span() for sp in _CHAINE_DOUBLE_GUILLEMETS.finditer(ligne)]
    spans_guillemets += [sp.span() for sp in _CHAINE_SIMPLE_GUILLEMETS.finditer(ligne)]
    position_commentaire = None
    for j, caractere in enumerate(ligne):
        if any(g_debut <= j < g_fin for g_debut, g_fin in spans_guillemets):
            continue
        if caractere == "#" and (j == 0 or ligne[j - 1] in _CARACTERES_PRECEDENT_COMMENTAIRE):
            position_commentaire = j
            break
    candidats_valides = []
    for candidat in _DEF_ANCRE.finditer(ligne):
        debut = candidat.start()
        if position_commentaire is not None and debut >= position_commentaire:
            continue
        if any(g_debut <= debut < g_fin for g_debut, g_fin in spans_guillemets):
            continue
        if not _PREFIXE_AVANT_ANCRE.match(ligne[:debut]):
            continue
        candidats_valides.append(candidat)
    return candidats_valides


def _construire_table_ancres(
    texte: str, lignes: list[str], lignes_exclues: set[int] | None = None
) -> dict[str, str | list[str]]:
    """Construit une table `{nom_ancre: valeur_résolue}` en balayant l'INTÉGRALITÉ du fichier.

    Bug réel trouvé par revue scellée GPT-5.6-Terra-Pro (RC1-015 round 12) : une ancre YAML
    (`&nom`) définie AILLEURS dans le fichier, référencée par alias (`*nom`) au sein de
    `ignored_paths`, réintroduit sémantiquement l'exclusion globale sans qu'aucun littéral
    `**/*.md` n'apparaisse dans le contexte `ignored_paths` lui-même — ni l'analyseur structurel
    ni le filet de chaînes guillemetées ne peuvent voir un alias sans résoudre les ancres.

    Portée volontairement bornée à ce qu'un alias référencé depuis `ignored_paths` peut pointer :
    scalaire bloc ancré, chaîne guillemetée ancrée, ou scalaire nu ancré, sur la même ligne que
    l'ancre — un TAG YAML explicite (`!!str`, `!local`, …) peut précéder l'un ou l'autre et est
    ignoré avant résolution (round 15 : `&nom !!str >-` stockait `"!!str >-"` littéralement,
    empêchant `_BLOC_ANCRE` de reconnaître l'indicateur de scalaire bloc juste après). Ne
    modélise PAS les ancres sur une correspondance (mapping) entière EN GÉNÉRAL, ni un alias
    pointant vers un autre alias — hors du périmètre de cette fonction, ciblée sur la résolution
    de VALEURS (scalaires/séquences), pas de mappings. Les cas d'ascendance de `secret` via un
    mapping entier (alias direct round 30, fusion `<<: *nom` round 31) sont traités par des
    mécanismes séparés (`_noms_ancres_aliasees_secret`, `_noms_ancres_fusionnees_dans_secret`)
    — cette docstring affirmait autrefois que les fusions étaient hors périmètre ; ce n'est plus
    exact pour le cas spécifique de la fusion DANS `secret` (round 31 l'a fermé), même si la
    résolution de fusions dans un contexte général reste hors périmètre.

    Round 23 : un `&nom` apparaissant À L'INTÉRIEUR d'une chaîne guillemetée ORDINAIRE (texte
    littéral, pas une vraie définition d'ancre) écrasait à tort une ancre légitime définie plus
    tôt dans le fichier — `note: "&md safe"` n'est PAS une redéfinition de `&md`, YAML l'ignore
    entièrement (guillemets = texte littéral, aucune syntaxe spéciale interprétée dedans). Chaque
    candidat `&nom` est désormais vérifié contre les spans de chaînes guillemetées de sa propre
    ligne ; le premier candidat HORS de tout span guillemeté est retenu, les autres ignorés.
    Round 24 : même bug pour un `&nom` apparaissant dans un COMMENTAIRE (`# &md safe`) — la
    position du premier `#` non guillemeté de la ligne est calculée, tout candidat à cette
    position ou après est ignoré. Round 25 (trouvé PROACTIVEMENT, même famille de bug que les
    rounds 23/24) : un `&nom` apparaissant dans le CONTENU d'un scalaire bloc d'une AUTRE clé
    (`note: |-\n  &md safe`) souffrait de la même confusion — `lignes_exclues` (calculé par
    `_lignes_contenu_bloc`, déjà utilisé pour la recherche de `ignored_paths`) est désormais
    passé à cette fonction et toute ligne qu'il contient est ignorée pour la recherche d'ancres.

    Round 62 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : une ancre portant une
    SÉQUENCE FLOW sur la même ligne (`paths: &paths [*md]`) était stockée comme une chaîne
    LITTÉRALE brute (`"[*md]"`, branche de repli scalaire round 12) plutôt que résolue comme
    une liste — un alias direct vers cette ancre (`ignored_paths: *paths`) réintroduisait alors
    sémantiquement l'exclusion globale portée par `*md` sans jamais être détecté, vérifié
    empiriquement contre PyYAML. Corrigé en ajoutant `texte` comme paramètre (pour pouvoir
    appeler `_trouver_fermeture_flow`/`_decouper_liste_flow`/`_resoudre_jeton_item`, déjà en
    place pour `ignored_paths: [...]` lui-même, rounds 12/17) et une branche dédiée AVANT le
    repli scalaire, déclenchée quand `reste` ouvre une liste flow.

    Round 94 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : une ancre de
    scalaire GUILLEMETÉ (double ou simple) portée par une clé D'UN MAPPING FLOW, suivie de la
    fermeture `}` de ce mapping sur la MÊME ligne (`holder: { paths: &paths "**/*.md" }`),
    n'était PAS résolue — la condition exigeait `m_double.end() == len(reste)` (rien d'autre du
    tout après la valeur), alors que `reste` inclut la fermeture `}` du mapping englobant. Un
    correctif intermédiaire (round 94, `_SUITE_ANCRE_CLOTURE_FLOW_VALIDE`, retiré au round 95)
    élargissait la suite tolérée aux seuls indicateurs de fermeture/séparation flow — mais
    laissait un FAUX NÉGATIF résiduel dès que du contenu RÉEL (clé sœur d'une enveloppe
    extérieure) suivait sur la même ligne (`outer: { holder: { paths: &paths "**/*.md" },
    other: 1 }`), confirmé par revue scellée round 95.

    Round 95 (RC1-015, MÊME famille de bug, reproduction étendue par revue scellée
    GPT-5.6-Terra-Pro) : correctif définitif — le filtrage de la suite après la valeur est
    RETIRÉ ENTIÈREMENT. `_CHAINE_DOUBLE_GUILLEMETS.match(reste)`/`_CHAINE_SIMPLE_GUILLEMETS.
    match(reste)` ancrent déjà la recherche en POSITION 0 de `reste` (`re.Match.match`, pas
    `.search`) : si `reste[0]` n'est pas un guillemet, aucun match ne se produit — mais dès
    qu'un match se produit, `m.group(1)` est SANS AMBIGUÏTÉ le premier jeton de `reste`, donc la
    valeur RÉELLE de l'ancre, INDÉPENDAMMENT de ce qui suit (fermeture flow, virgule, clé sœur,
    ou même du YAML invalide au-delà — dans tous les cas hors du périmètre de ce cliquet, dont
    la responsabilité s'arrête à ne jamais laisser passer une exclusion RÉELLE, pas à valider la
    syntaxe globale du fichier). Aucune condition sur la suite n'est donc plus nécessaire ni
    justifiée : la retirer ferme définitivement toute la famille de faux négatifs des rounds
    94/95, sans risque de nouvelle fausse acceptation identifié empiriquement (310+ tests dédiés
    couvrant les formes déjà connues, tous verts après ce retrait).
    """
    if lignes_exclues is None:
        lignes_exclues = set()
    ancres: dict[str, str | list[str]] = {}
    i = 0
    while i < len(lignes):
        if i in lignes_exclues:
            i += 1
            continue
        ligne = lignes[i]
        spans_guillemetes = [sp.span() for sp in _CHAINE_DOUBLE_GUILLEMETS.finditer(ligne)]
        spans_guillemetes += [sp.span() for sp in _CHAINE_SIMPLE_GUILLEMETS.finditer(ligne)]
        position_commentaire = None
        for j, caractere in enumerate(ligne):
            if any(g_debut <= j < g_fin for g_debut, g_fin in spans_guillemetes):
                continue
            # Round 75 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `#`
            # ne démarre un commentaire QUE s'il est séparé du contenu précédent (même règle
            # que `_spans_commentaires`, round 38) — à l'intérieur d'un scalaire nu SANS
            # séparation (`note: foo#bar`), il fait partie de la valeur littérale. Vérifié
            # empiriquement contre PyYAML : sans cette vérification, un `#` interne à un
            # scalaire précédant une ancre légitime sur la même ligne fixait
            # `position_commentaire` trop tôt, écartant ensuite cette ancre à tort.
            if caractere == "#" and (j == 0 or ligne[j - 1] in _CARACTERES_PRECEDENT_COMMENTAIRE):
                position_commentaire = j
                break
        # Round 74 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : collecte
        # TOUS les candidats `&nom` valides de la ligne (pas seulement le premier) — un mapping
        # flow peut porter PLUSIEURS ancres sur la même ligne physique
        # (`{ safe: &safe x, paths: &paths [*md] }`) ; s'arrêter au premier candidat via
        # `break` (comportement pré-round-74) empêchait l'enregistrement de toute ancre
        # ULTÉRIEURE sur cette même ligne, y compris une ancre portant elle-même
        # `ignored_paths` (via alias indirect) — reproduction vérifiée empiriquement contre
        # PyYAML. Pour une ligne à candidat UNIQUE (l'écrasante majorité des cas, dont TOUS les
        # tests des rounds 12-73), le comportement est BYTE-POUR-BYTE identique à avant : la
        # même liste de filtres (commentaire, guillemets, `_PREFIXE_AVANT_ANCRE`) produit le
        # même candidat unique, `limite_suivante` vaut `None`, et `segment`/`reste` couvrent
        # exactement `ligne[m.end():]` comme avant.
        candidats_valides = []
        for candidat in _DEF_ANCRE.finditer(ligne):
            debut = candidat.start()
            if position_commentaire is not None and debut >= position_commentaire:
                continue
            if any(g_debut <= debut < g_fin for g_debut, g_fin in spans_guillemetes):
                continue
            if not _PREFIXE_AVANT_ANCRE.match(ligne[:debut]):
                continue
            candidats_valides.append(candidat)
        if not candidats_valides:
            i += 1
            continue

        ligne_deplacee = False
        for index_candidat, m in enumerate(candidats_valides):
            nom = m.group(1)
            limite_suivante = (
                candidats_valides[index_candidat + 1].start()
                if index_candidat + 1 < len(candidats_valides)
                else None
            )
            segment = ligne[m.end() : limite_suivante] if limite_suivante is not None else ligne[m.end() :]
            reste = segment.strip()
            match_tag = _TAG_YAML.match(reste)
            if match_tag:
                reste = reste[match_tag.end():].strip()
            match_bloc = _BLOC_ANCRE.match(reste)
            if match_bloc:
                # Un indicateur de scalaire bloc consomme le reste de la ligne par
                # construction YAML — aucun autre candidat valide ne peut structurellement le
                # suivre sur cette même ligne physique ; sûr de sortir de la boucle interne.
                indentation_ancre = len(ligne) - len(ligne.lstrip(" "))
                valeur, i = _consommer_scalaire_bloc(lignes, i + 1, indentation_ancre)
                ancres[nom] = valeur
                ligne_deplacee = True
                break
            if reste.startswith('"'):
                # Round 96 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) :
                # une chaîne double-guillemets YAML valide peut s'étendre sur PLUSIEURS lignes
                # physiques via une continuation de ligne échappée (`\` immédiatement suivi
                # d'un saut de ligne) — exactement le même mécanisme déjà couvert pour un NOM
                # DE CLÉ explicite multiligne (round 58, `_decoder_cle_explicite_multiligne`),
                # jamais branché ici pour la VALEUR d'une ancre. `_CHAINE_DOUBLE_GUILLEMETS.
                # match(reste)` (ligne SEULE) ne pouvait donc jamais voir le guillemet fermant
                # situé sur la ligne suivante. Vérifié empiriquement contre PyYAML AVANT
                # correctif : `defaults: &md "**/*.\` + saut de ligne + `  md"` résout bien en
                # `**/*.md`. Même correctif que round 58 : `_CHAINE_DOUBLE_GUILLEMETS` (déjà
                # compilée en mode DOTALL) appliquée à `texte` depuis la position ABSOLUE du
                # guillemet ouvrant — capable nativement de franchir des sauts de ligne.
                position_guillemet = ligne.index('"', m.end())
                absolu = _position_debut_ligne(lignes, i) + position_guillemet
                m_double = _CHAINE_DOUBLE_GUILLEMETS.match(texte, absolu)
                if m_double:
                    ancres[nom] = _decoder_echappements_yaml(m_double.group(1))
                    sauts_ligne = texte.count("\n", absolu, m_double.end())
                    if sauts_ligne:
                        i += sauts_ligne
                        ligne_deplacee = True
                        break
                    continue
            m_simple = _CHAINE_SIMPLE_GUILLEMETS.match(reste)
            if m_simple:
                ancres[nom] = m_simple.group(1)
                continue
            if reste.startswith("["):
                # Round 62 : ancre portant une séquence FLOW sur la même ligne
                # (`&paths [*md]`) — réutilise `_trouver_fermeture_flow`/`_decouper_liste_flow`/
                # `_resoudre_jeton_item` (rounds 12/17) sur `texte` plutôt que sur `ligne`
                # seule, la liste flow pouvant légitimement s'étendre sur plusieurs lignes
                # physiques (round 17).
                position_crochet = ligne.index("[", m.end())
                absolu = _position_debut_ligne(lignes, i) + position_crochet + 1
                contenu = _trouver_fermeture_flow(texte, absolu, "]")
                ancres[nom] = [_resoudre_jeton_item(t, ancres) for t in _decouper_liste_flow(contenu)]
                sauts_ligne = texte.count("\n", absolu, absolu + len(contenu) + 1)
                if sauts_ligne:
                    # La liste s'étend sur plusieurs lignes physiques — tout candidat
                    # ULTÉRIEUR sur la ligne d'OUVERTURE appartient en réalité au contenu de
                    # cette liste (déjà résolu ci-dessus). `i += sauts_ligne` (SANS `+1`, bug
                    # réel proactivement trouvé et corrigé en vérifiant ce correctif round 74,
                    # AVANT tout dispatch de revue) atterrit EXACTEMENT sur la ligne de
                    # FERMETURE (`sauts_ligne` = nombre de sauts de ligne jusqu'à la position
                    # du `]` inclus) — la boucle externe la réexamine alors FRAÎCHEMENT depuis
                    # son début, découvrant toute ancre qui suivrait la fermeture sur cette
                    # même ligne physique (`], paths: &paths [...] }`). Un `+= sauts_ligne + 1`
                    # sauterait cette ligne de fermeture entièrement, la rendant invisible à
                    # toute recherche d'ancre ultérieure — vérifié empiriquement contre PyYAML.
                    i += sauts_ligne
                    ligne_deplacee = True
                    break
                continue
            if not reste:
                # Round 25 : rien après l'ancre sur cette ligne (`defaults: &md`) — l'ancre
                # porte potentiellement une SÉQUENCE (liste) entière, pas un scalaire, si les
                # lignes suivantes, plus indentées, sont des items de liste.
                indentation_ancre = len(ligne) - len(ligne.lstrip(" "))
                items, j = _consommer_sequence_ancree(lignes, i + 1, indentation_ancre, ancres)
                if items:
                    ancres[nom] = items
                    i = j
                    ligne_deplacee = True
                    break
                continue
            if reste:
                if limite_suivante is not None:
                    # Round 74 : `segment` a été borné à `limite_suivante` (début du candidat
                    # SUIVANT), donc `reste` peut encore porter le préfixe clé-flow de ce
                    # candidat (`x, paths: `) — tronque au DERNIER séparateur flow (`,`) trouvé
                    # avant cette limite, laissant la vraie valeur scalaire. Si aucune virgule
                    # n'est trouvée (combinaison non couverte par la reproduction vérifiée),
                    # conserve `reste` tel quel — comportement conservateur, pas de régression
                    # sur un cas non testé.
                    position_virgule = reste.rfind(",")
                    if position_virgule != -1:
                        reste = reste[:position_virgule].strip()
                ancres[nom] = reste
        if not ligne_deplacee:
            i += 1
    return ancres


def _consommer_sequence_ancree(
    lignes: list[str], depart: int, indentation_ancre: int, ancres: dict[str, str | list[str]]
) -> tuple[list[str], int]:
    """Consomme les items d'une séquence YAML (liste) ANCRÉE démarrant à `depart`, plus
    indentée que `indentation_ancre` (colonne de la clé portant l'ancre). Réutilise la même
    reconnaissance d'item que la boucle principale de `parser_ignored_paths` (scalaire bloc,
    alias, guillemeté/nu) — bug réel trouvé par revue scellée GPT-5.6-Terra-Pro (RC1-015 round
    25) : `secret.ignored_paths: *md` (alias DIRECT, sans crochets ni tiret, comme valeur de la
    clé elle-même) où `&md` ancre une séquence entière (`defaults: &md\n  - >-\n    **/*.md`)
    n'était résolu par aucun mécanisme existant — les ancres ne portaient jusqu'ici que des
    scalaires. Retourne une liste VIDE (pas de séquence) si aucun item n'est trouvé.
    """
    items: list[str] = []
    i = depart
    while i < len(lignes):
        ligne = lignes[i]
        ligne_nue = ligne.strip()
        if not ligne_nue or ligne_nue.startswith("#"):
            i += 1
            continue
        indentation_ligne = len(ligne) - len(ligne.lstrip(" "))
        if indentation_ligne <= indentation_ancre:
            break
        match_bloc = _LIGNE_ITEM_BLOC.match(ligne)
        if match_bloc and len(match_bloc.group(1)) > indentation_ancre:
            valeur, i = _consommer_scalaire_bloc(lignes, i + 1, len(match_bloc.group(1)))
            items.append(valeur)
            continue
        match_alias = _LIGNE_ITEM_ALIAS.match(ligne)
        if match_alias and len(match_alias.group(1)) > indentation_ancre:
            valeur_ancree = ancres.get(match_alias.group(2), "*" + match_alias.group(2))
            if isinstance(valeur_ancree, list):
                items.extend(valeur_ancree)
            else:
                items.append(valeur_ancree)
            i += 1
            continue
        match_item = _LIGNE_ITEM.match(ligne)
        if match_item and len(match_item.group(1)) > indentation_ancre:
            valeur_double = match_item.group(2)
            if valeur_double is not None:
                valeur = _decoder_echappements_yaml(valeur_double)
            else:
                valeur = match_item.group(3)
                if valeur is None:
                    valeur = match_item.group(4)
            items.append(valeur)
            i += 1
            continue
        break
    return items, i


def _position_debut_ligne(lignes: list[str], indice: int) -> int:
    """Position absolue (caractères) du début de `lignes[indice]` dans le texte reconstruit —
    round 46 (RC1-015). Suppose un séparateur `\\n` unique entre chaque ligne (même convention
    que les boucles de recherche flow existantes, rounds 32+, qui accumulent `len(ligne) + 1`).
    Utilisée pour retrouver la position absolue d'une valeur INLINE après le séparateur `:`
    d'une clé explicite (round 42), afin d'appeler `_trouver_fermeture_flow` sur le texte
    complet plutôt que sur la seule ligne.

    Round 86 (RC1-015, finding réfuté avec preuve — revue scellée GPT-5.6-Terra-Pro) : le
    finding évoquait un fichier `.gitguardian.yaml` en fins de ligne CRLF (`\\r\\n`), où
    `lignes = texte.splitlines()` retirerait les DEUX caractères `\\r\\n` par ligne alors que
    cette fonction (et les boucles `offset += len(ligne) + 1` de `parser_ignored_paths`)
    suppose un séparateur d'UN SEUL caractère — un décalage d'un octet par ligne précédente
    désynchroniserait alors les positions absolues calculées de celles réellement présentes
    dans `texte`. Vérifié EMPIRIQUEMENT (avant tout correctif) : `Path.read_text()` (les DEUX
    appels de ce fichier, `parser_ignored_paths`/`verifier`, aucun des deux ne passe de
    paramètre `newline`) utilise le mode « universal newlines » par défaut de Python, qui
    NORMALISE SILENCIEUSEMENT `\\r\\n` ET `\\r` seul en `\\n` DÈS LA LECTURE — `texte` ne peut
    donc JAMAIS contenir de caractère `\\r`, quelle que soit la convention de fin de ligne
    RÉELLE du fichier sur disque. L'hypothèse du finding (« `texte` contient des `\\r\\n`
    littéraux ») est donc STRUCTURELLEMENT IMPOSSIBLE, pas seulement mal reproduite — vérifié
    avec un fichier écrit en octets bruts CRLF/CR-seul/mixte, relu via `Path.read_text()`, dont
    le résultat ne contient aucun `\\r` dans tous les cas. Voir
    `test_read_text_normalise_toujours_les_fins_de_ligne_avant_analyse`.
    """
    return sum(len(l) + 1 for l in lignes[:indice])


def _trouver_fermeture_flow(texte: str, depart: int, fermant: str = "]") -> str:
    """Depuis `depart` (juste après le `[` — ou `{`, round 32 — ouvrant d'une collection YAML
    flow), trouve le caractère `fermant` NON guillemeté et NON imbriqué correspondant dans
    `texte` — en respectant les guillemets (un `fermant` à l'intérieur d'une chaîne guillemetée
    n'est pas une fermeture) — et retourne le contenu entre les deux.

    Opère sur le TEXTE COMPLET (pas ligne par ligne) : une collection flow YAML valide peut
    s'étendre sur plusieurs lignes physiques (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro,
    RC1-015 round 17 : `ignored_paths: [\\n    *md\\n  ]` — le round 12 ne reconnaissait que la
    forme sur UNE seule ligne). Si aucune fermeture n'est trouvée, retourne le texte jusqu'à la
    fin (fichier malformé — hors périmètre de lever une erreur ici, `verifier()` ne trouvera
    simplement rien à signaler dans ce contenu incomplet). Round 32 : généralisée à `}` (mapping
    flow, `fermant="}"`) en plus de `]` (liste flow) — même logique de respect des guillemets.

    Round 34 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : le mapping
    `secret` en syntaxe flow peut contenir une collection flow IMBRIQUÉE (`{other: {x: safe},
    ignored_paths: [*md]}`) AVANT `ignored_paths` — sans suivi de profondeur, le premier `}` non
    guillemeté rencontré (celui de la collection imbriquée, PAS celui du mapping `secret`
    lui-même) était pris à tort pour la fermeture recherchée, tronquant le contenu examiné et
    masquant la vraie clé `ignored_paths` plus loin. Vérifié empiriquement contre PyYAML :
    `secret.ignored_paths` résout bien en `['**/*.md']` (via l'alias) dans ce cas. Un compteur
    de profondeur est désormais tenu pour TOUTE ouverture (`{` ou `[`) rencontrée après `depart`
    — la fermeture recherchée n'est retenue qu'à profondeur 0 (aucune collection imbriquée
    encore ouverte), toute fermeture à profondeur > 0 décrémente simplement le compteur.

    Round 39 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : un COMMENTAIRE interne au
    mapping flow (légitime sur plusieurs lignes, round 33) peut lui-même contenir un `}`/`]`
    littéral (`# } commentaire`) — sans reconnaissance des commentaires, ce caractère était pris
    à tort pour la fermeture recherchée, tronquant le contenu avant la vraie clé. Vérifié
    empiriquement contre PyYAML : le commentaire est entièrement ignoré, `secret.ignored_paths`
    résout normalement. Même règle de détection qu'`_spans_commentaires` (round 38,
    `_CARACTERES_PRECEDENT_COMMENTAIRE`) : un `#` non guillemeté, séparé du contenu précédent,
    fait sauter le scan jusqu'au saut de ligne suivant sans compter ses caractères internes.
    """
    dans_double = False
    dans_simple = False
    profondeur = 0
    i = depart
    while i < len(texte):
        c = texte[i]
        if dans_double:
            if c == "\\" and i + 1 < len(texte):
                i += 2
                continue
            if c == '"':
                dans_double = False
            i += 1
            continue
        if dans_simple:
            if c == "'":
                dans_simple = False
            i += 1
            continue
        if c == '"':
            dans_double = True
        elif c == "'":
            dans_simple = True
        elif c == "#" and (i == 0 or texte[i - 1] in _CARACTERES_PRECEDENT_COMMENTAIRE):
            fin_ligne = texte.find("\n", i)
            i = len(texte) if fin_ligne == -1 else fin_ligne
            continue
        elif c in "{[":
            profondeur += 1
        elif c in "}]":
            if profondeur == 0:
                return texte[depart:i]
            profondeur -= 1
        i += 1
    return texte[depart:]


def _decouper_liste_flow(contenu: str) -> list[str]:
    """Découpe le contenu d'une liste YAML "flow" (entre crochets) par virgules de PREMIER
    niveau, en respectant les guillemets (une virgule à l'intérieur d'une chaîne guillemetée
    n'est pas un séparateur). Suffisant pour `ignored_paths` : jamais de crochets/accolades
    imbriqués dans un chemin ou un alias.

    Round 39 (RC1-015, trouvé proactivement en vérifiant le correctif du même round sur
    `_trouver_fermeture_flow`) : une liste flow multi-lignes (round 17) peut légitimement
    contenir un COMMENTAIRE sur une de ses lignes internes (`[\\n  # note\\n  *md\\n]`) —
    vérifié empiriquement contre PyYAML, le commentaire est entièrement ignoré. Sans
    reconnaissance des commentaires ici, son texte (y compris une éventuelle virgule ou
    accolade qu'il contiendrait) était incorporé tel quel dans le jeton en cours. Même règle de
    détection qu'`_spans_commentaires`/`_trouver_fermeture_flow` (round 38/39,
    `_CARACTERES_PRECEDENT_COMMENTAIRE`).
    """
    jetons: list[str] = []
    courant: list[str] = []
    dans_double = False
    dans_simple = False
    i = 0
    while i < len(contenu):
        c = contenu[i]
        if dans_double:
            courant.append(c)
            if c == "\\" and i + 1 < len(contenu):
                courant.append(contenu[i + 1])
                i += 2
                continue
            if c == '"':
                dans_double = False
            i += 1
            continue
        if dans_simple:
            courant.append(c)
            if c == "'":
                dans_simple = False
            i += 1
            continue
        if c == '"':
            dans_double = True
            courant.append(c)
        elif c == "'":
            dans_simple = True
            courant.append(c)
        elif c == "#" and (i == 0 or contenu[i - 1] in _CARACTERES_PRECEDENT_COMMENTAIRE):
            fin_ligne = contenu.find("\n", i)
            i = len(contenu) if fin_ligne == -1 else fin_ligne
            continue
        elif c == ",":
            jetons.append("".join(courant).strip())
            courant = []
        else:
            courant.append(c)
        i += 1
    dernier = "".join(courant).strip()
    if dernier:
        jetons.append(dernier)
    return jetons


def _resoudre_jeton_item(jeton: str, ancres: dict[str, str | list[str]]) -> str:
    """Résout un jeton d'item `ignored_paths` (flow ou alias de bloc) en sa valeur : alias
    (`*nom`, via `ancres` — inchangé si l'alias est indéfini), chaîne guillemetée (décodée pour
    les guillemets doubles), ou scalaire nu tel quel.

    Si `ancres[nom]` est une LISTE (ancre de séquence, round 25 — voir
    `_consommer_sequence_ancree`), retombe sur le jeton brut : un item de bloc/flow référençant
    un alias de séquence entière comme SIMPLE ITEM (pas comme valeur directe de `ignored_paths`,
    couverte séparément par `_LIGNE_CLE_ALIAS`) est une forme YAML dégénérée hors du périmètre
    ciblé de ce cliquet.
    """
    if not jeton:
        return jeton
    m_alias = _REF_ALIAS.match(jeton)
    if m_alias:
        valeur = ancres.get(m_alias.group(1), jeton)
        return jeton if isinstance(valeur, list) else valeur
    m_double = _CHAINE_DOUBLE_GUILLEMETS.match(jeton)
    if m_double and m_double.end() == len(jeton):
        return _decoder_echappements_yaml(m_double.group(1))
    m_simple = _CHAINE_SIMPLE_GUILLEMETS.match(jeton)
    if m_simple and m_simple.end() == len(jeton):
        return m_simple.group(1)
    return jeton


def _spans_guillemets(texte: str) -> list[tuple[int, int]]:
    """Spans des chaînes guillemetées (doubles/simples) de `texte` — factorisé du calcul commun
    à `_spans_exclus_recherche_cle` (round 33) et à `_resoudre_ignored_paths_dans_mapping_flow`
    (round 37, RC1-015) : ce dernier a besoin de distinguer un candidat qui COMMENCE exactement
    à l'ouverture d'un guillemet (donc consommé comme clé guillemetée légitime par sa propre
    regex, round 36) d'un candidat strictement À L'INTÉRIEUR d'une chaîne guillemetée existante
    (occurrence factice de texte, round 33) — un traitement uniforme des deux (round 36 seul)
    excluait à tort toute clé `"ignored_paths"` guillemetée dans un mapping flow.
    """
    spans = [sp.span() for sp in _CHAINE_DOUBLE_GUILLEMETS.finditer(texte)]
    spans += [sp.span() for sp in _CHAINE_SIMPLE_GUILLEMETS.finditer(texte)]
    return spans


# Caractères qui, immédiatement AVANT un `#` non guillemeté, permettent à celui-ci de démarrer
# un commentaire — round 38 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro).
# Vérifié empiriquement contre le SCANNER de PyYAML (source `scan_plain` : un `#` rencontré en
# cours de scalaire nu n'est PAS un terminateur — seul `scan_to_next_token`, appelé entre deux
# jetons déjà complets, transforme un `#` en commentaire) puis confirmé comportementalement
# (`yaml.safe_load`) : `#` démarre un commentaire s'il est précédé d'un blanc (espace/tabulation),
# d'un indicateur structurel flow (`{[,}]:`), ou s'il est en tout début de `texte`/de ligne (`\n`
# juste avant). Un `#` précédé de tout AUTRE caractère (lettre, chiffre, etc.) fait partie d'un
# scalaire nu ordinaire — `foo#bar` est la valeur littérale `foo#bar`, jamais `foo` suivi d'un
# commentaire.
_CARACTERES_PRECEDENT_COMMENTAIRE = frozenset(" \t\n{}[],:")


def _spans_commentaires(texte: str, spans_guillemets: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Spans des commentaires de `texte` : un `#` non guillemeté (d'après `spans_guillemets`)
    s'étend jusqu'au saut de ligne suivant (ou la fin de `texte` si aucun) — round 33 (RC1-015).
    Contrairement aux guillemets, AUCUNE exemption de bord n'est accordée pour les commentaires :
    un candidat de clé commençant pile au `#` d'ouverture n'est jamais une clé légitime (`#`
    n'est le premier caractère d'aucune forme de clé reconnue par cet analyseur).

    Round 38 : un `#` non guillemeté n'est PAS systématiquement un commentaire — bug réel trouvé
    par revue scellée GPT-5.6-Terra-Pro. En YAML, `#` ne démarre un commentaire que s'il est
    séparé du contenu précédent (blanc, indicateur structurel, ou début de ligne/texte) ; à
    l'intérieur d'un scalaire nu SANS séparation (`note: foo#bar`), il fait partie de la valeur
    littérale. Un `#` précédé d'un caractère hors `_CARACTERES_PRECEDENT_COMMENTAIRE` n'ouvre
    donc plus de span — la vraie clé `ignored_paths` qui le suit sur la même ligne physique
    n'est ainsi plus masquée à tort.
    """
    spans = []
    i = 0
    while i < len(texte):
        if any(g_debut <= i < g_fin for g_debut, g_fin in spans_guillemets):
            i += 1
            continue
        if texte[i] == "#" and (i == 0 or texte[i - 1] in _CARACTERES_PRECEDENT_COMMENTAIRE):
            fin_ligne = texte.find("\n", i)
            fin_ligne = len(texte) if fin_ligne == -1 else fin_ligne
            spans.append((i, fin_ligne))
            i = fin_ligne
            continue
        i += 1
    return spans


def _spans_exclus_recherche_cle(texte: str) -> list[tuple[int, int]]:
    """Calcule les spans à exclure d'une recherche textuelle de clé dans `texte` : chaînes
    guillemetées (doubles/simples) ET commentaires — round 33 (RC1-015). Un mapping YAML flow
    peut légitimement s'étendre sur plusieurs lignes physiques et contenir des commentaires sur
    ses lignes internes (vérifié empiriquement contre PyYAML :
    `{  # ignored_paths: [fake]\n  ignored_paths: [reel]\n}` résout bien `ignored_paths` à la
    vraie clé, le commentaire étant entièrement ignoré par tout parseur YAML conforme).

    Bug réel trouvé par revue scellée GPT-5.6-Terra-Pro : `_CLE_IGNORED_PATHS_DANS_FLOW.search()`
    sur l'intégralité du contenu d'un mapping flow pouvait matcher un texte `ignored_paths:`
    apparaissant dans la valeur guillemetée d'une AUTRE clé (`note: "ignored_paths: [safe]"`)
    AVANT la vraie clé, retournant alors la valeur de cette fausse occurrence — la vraie clé,
    plus loin dans le mapping, n'était jamais examinée. Trouvé proactivement en vérifiant ce
    correctif : la même confusion existe pour un `#` non guillemeté (commentaire), la clé
    factice à l'intérieur restant du texte brut pour une recherche non consciente des
    commentaires.

    Retourne le merge SIMPLE des deux catégories (guillemets + commentaires) — utilisé tel quel
    par `_profondeurs_flow` (pour laquelle la distinction guillemet/commentaire n'a pas
    d'importance : aucune des deux ne doit compter pour l'imbrication de collections flow).
    `_resoudre_ignored_paths_dans_mapping_flow` (round 37) calcule les deux catégories
    SÉPARÉMENT via `_spans_guillemets`/`_spans_commentaires` pour appliquer une règle de bord
    différente à chacune lors du filtrage des candidats de clé.
    """
    spans_guillemets = _spans_guillemets(texte)
    return spans_guillemets + _spans_commentaires(texte, spans_guillemets)


def _profondeurs_flow(texte: str, spans_exclus: list[tuple[int, int]]) -> list[int]:
    """Calcule, pour chaque position de `texte`, la profondeur d'imbrication de collections
    flow (compte net des `{`/`[` non guillemetés/commentés ouverts avant cette position,
    d'après `spans_exclus`) — round 35 (RC1-015). `profondeurs[i]` est la profondeur AVANT le
    caractère `i` (donc la profondeur à laquelle démarre un candidat de recherche en position
    `i`). Clampée à 0 (jamais négative) : un fermant surnuméraire est hors périmètre (YAML
    malformé), la docstring de `_trouver_fermeture_flow` documente déjà cette limite.
    """
    profondeurs = [0] * (len(texte) + 1)
    profondeur = 0
    for i, c in enumerate(texte):
        profondeurs[i] = profondeur
        if any(g_debut <= i < g_fin for g_debut, g_fin in spans_exclus):
            continue
        if c in "{[":
            profondeur += 1
        elif c in "}]":
            profondeur = max(0, profondeur - 1)
    profondeurs[len(texte)] = profondeur
    return profondeurs


def _resoudre_ignored_paths_dans_mapping_flow(
    texte: str, debut: int, fin: int, ancres: dict[str, str | list[str]]
) -> list[str] | None:
    """Cherche la clé `ignored_paths` au sein d'un mapping YAML FLOW (`{...}`, `debut`/`fin`
    positions absolues dans `texte`, bornant le contenu entre les accolades) et résout sa
    valeur — round 32 (RC1-015). Retourne `None` si `ignored_paths` n'apparaît pas dans cette
    portion.

    Bug réel trouvé par revue scellée GPT-5.6-Terra-Pro : le mapping `secret` exprimé en
    syntaxe flow, avec `ignored_paths` en son sein comme alias non guillemeté (YAML valide),
    n'était reconnu par aucune des recherches existantes — toutes
    exigent une ligne commençant par `ignored_paths` en syntaxe bloc. Gère les mêmes formes de
    valeur que le reste de l'analyseur : liste flow imbriquée (`[...]`), alias direct (`*nom`),
    chaîne guillemetée, ou scalaire nu jusqu'à la virgule/accolade fermante suivante.

    Round 33 : la clé n'est plus recherchée par un simple `.search()` sur l'intégralité du
    contenu — chaque candidat est vérifié contre `_spans_exclus_recherche_cle` (guillemets +
    commentaires) et le premier candidat HORS de ces spans est retenu (`finditer` avec
    filtrage), même motif que `_construire_table_ancres` (rounds 23/24) pour les ancres.

    Round 35 : le filtrage par spans (guillemets/commentaires) ne suffisait pas — un candidat
    `ignored_paths` réel (ni guillemeté ni commenté) mais situé DANS une collection flow
    IMBRIQUÉE (`other: {ignored_paths: [safe]}`, placée avant la vraie clé de premier niveau)
    était pris à tort pour la vraie clé. Vérifié empiriquement contre PyYAML : la valeur
    effective de la clé de PREMIER NIVEAU est bien celle attendue, la clé homonyme imbriquée
    dans `other` n'a aucun rapport sémantique. Chaque candidat est désormais aussi vérifié
    contre `_profondeurs_flow` : seul un candidat à profondeur 0 (aucune collection imbriquée
    encore ouverte à ce point du contenu de `secret`) est retenu.

    Round 37 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `_CLE_IGNORED_PATHS_DANS_FLOW`
    reconnaît désormais aussi la forme guillemetée du nom de clé (round 36) — mais le filtrage
    par spans du round 33 excluait purement et simplement TOUT candidat commençant dans un span
    guillemeté, y compris une clé `"ignored_paths"` légitimement guillemetée dont le `"`
    d'ouverture EST le premier caractère consommé par le candidat lui-même. Un candidat guillemet
    légitime commence donc TOUJOURS exactement à la position de départ (`g_debut`) de son propre
    span guillemeté, jamais strictement à l'intérieur — seule cette dernière position (occurrence
    de texte fortuite à l'intérieur d'une chaîne SANS rapport, round 33) reste exclue. Les
    commentaires, eux, excluent toujours intégralement (aucune forme de clé ne commence par `#`).

    Round 41 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la limite assumée à la fin
    du round 40 (« la recherche de clé DANS un mapping flow garde l'ancienne forme littérale »)
    est comblée — `_CLE_IGNORED_PATHS_DANS_FLOW` capture désormais le nom de clé BRUT via
    `_NOM_CLE_QUELCONQUE` (générique, comme les regexes bloc du round 40), et chaque candidat
    accepté par le filtrage structurel (spans/profondeur, inchangé) est en outre décodé via
    `_decoder_nom_cle()` et comparé à `"ignored_paths"` — un candidat dont le nom décodé ne
    correspond pas (ex. `"other"`, ou une clé homonyme guillemetée décodant vers autre chose) est
    ignoré et la recherche continue au candidat suivant. Le décodage intervient APRÈS le
    filtrage guillemets/commentaires/profondeur, jamais avant : la boundary `position == g_debut`
    (round 37) reste correcte quelle que soit la forme du nom capturé.

    Round 67 (gap symétrique comblé proactivement en vérifiant le finding round 67 sur la forme
    bloc, GPT-5.6-Terra-Pro) : YAML (PyYAML en particulier, vérifié empiriquement) accepte
    silencieusement une clé DUPLIQUÉE dans un mapping — la DERNIÈRE occurrence l'emporte. Le
    premier candidat valide était retenu (`break`), pas le dernier — la clé racine réduite à un
    mapping flow avec `ignored_paths` répétée deux fois, dont la seconde valeur ancrée `md` en
    scalaire bloc non guillemeté, résolvait à tort en la PREMIÈRE valeur. Plus de `break` :
    chaque candidat valide écrase `m`, la boucle va jusqu'au bout, ne retient donc que le
    DERNIER candidat valide rencontré.

    Round 82 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la fonction
    REÇOIT `ancres` (déjà utilisé plus bas pour résoudre la VALEUR) mais ne le transmettait pas
    à `_decoder_nom_cle()` pour le NOM de clé — un alias utilisé comme nom de clé
    `ignored_paths` DANS un mapping flow (`{*k: [*md]}`, où `&k` ancre `"ignored_paths"`)
    n'était donc pas résolu, contrairement aux formes bloc/explicite (round 80). Reproduction
    du reviewer, vérifiée empiriquement contre PyYAML.
    """
    sous_texte = texte[debut:fin]
    spans_guillemets = _spans_guillemets(sous_texte)
    spans_commentaires = _spans_commentaires(sous_texte, spans_guillemets)
    profondeurs = _profondeurs_flow(sous_texte, spans_guillemets + spans_commentaires)
    m = None
    for candidat in _CLE_IGNORED_PATHS_DANS_FLOW.finditer(sous_texte):
        position = candidat.start()
        if any(g_debut <= position < g_fin for g_debut, g_fin in spans_commentaires):
            continue
        if any(g_debut < position < g_fin for g_debut, g_fin in spans_guillemets):
            continue
        if profondeurs[position] != 0:
            continue
        if _decoder_nom_cle(candidat, 1, ancres) != "ignored_paths":
            continue
        m = candidat
    if not m:
        return None
    position_valeur = debut + m.end()
    reste = texte[position_valeur:fin]
    reste_lstrip = reste.lstrip()
    position_valeur += len(reste) - len(reste_lstrip)
    if reste_lstrip.startswith("["):
        contenu = _trouver_fermeture_flow(texte, position_valeur + 1, "]")
        return [_resoudre_jeton_item(t, ancres) for t in _decouper_liste_flow(contenu)]
    m_alias = _REF_ALIAS_PARTIEL.match(reste_lstrip)
    if m_alias:
        valeur_ancree = ancres.get(m_alias.group(1), "*" + m_alias.group(1))
        return valeur_ancree if isinstance(valeur_ancree, list) else [valeur_ancree]
    m_double = _CHAINE_DOUBLE_GUILLEMETS.match(reste_lstrip)
    if m_double:
        return [_decoder_echappements_yaml(m_double.group(1))]
    m_simple = _CHAINE_SIMPLE_GUILLEMETS.match(reste_lstrip)
    if m_simple:
        return [m_simple.group(1)]
    fin_scalaire = re.search(r"[,}]", reste_lstrip)
    valeur_nue = (reste_lstrip[: fin_scalaire.start()] if fin_scalaire else reste_lstrip).strip()
    return [valeur_nue] if valeur_nue else None


def _noms_fusion_dans_mapping_flow(texte: str, debut: int, fin: int) -> list[str]:
    """Cherche une clé de FUSION (`<<`) au sein d'un mapping YAML FLOW (`{...}`, `debut`/`fin`
    positions absolues dans `texte`) et retourne les noms d'ancre référencés, DANS L'ORDRE de
    la liste de fusion (round 100 — voir plus bas) — round 59 (RC1-015, bug réel trouvé par
    revue scellée GPT-5.6-Terra-Pro).

    Miroir de `_resoudre_ignored_paths_dans_mapping_flow` (round 32), même logique de filtrage
    par spans/profondeur, mais cherchant `<<` au lieu de `ignored_paths` : `cfg: &cfg {<<: *md}`,
    référencée par un alias direct `*cfg` en valeur de la clé `secret` (round 30), hérite
    sémantiquement de tout ce que `md` porte —
    ni `_noms_ancres_fusionnees_dans_secret` (round 31/56, ne regarde que les fusions
    textuellement descendantes de `secret` en syntaxe BLOC) ni le pré-passage round 57 (ne
    cherche que la clé directe `ignored_paths` dans le mapping flow d'une ancre) ne couvrent une
    fusion À L'INTÉRIEUR d'un mapping flow. Gère les deux formes de valeur de fusion (round 31 :
    alias unique ; round 56 : liste flow) en réutilisant `_trouver_fermeture_flow`/
    `_decouper_liste_flow` pour la forme liste — JAMAIS un découpage par virgule appliqué au
    mapping FLOW entier (qui casserait sur la liste imbriquée d'une fusion round 56 : `_decouper_
    liste_flow` ne suit pas la profondeur des crochets, documenté comme limite volontaire).
    """
    # Round 100 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : retournait un
    # `set[str]` — l'ORDRE réel des alias dans une fusion-LISTE (`<<: [*a, *b]`) était donc
    # perdu, empêchant tout appelant de reproduire la préséance YAML merge-key (le PREMIER
    # élément de la liste gagne en cas de clé dupliquée, round 99 — déjà corrigé pour la forme
    # BLOC dans `_noms_ancres_fusionnees_dans_secret`, jamais pour CETTE fonction sœur qui gère
    # les fusions au sein d'un mapping FLOW). Retourne désormais un `list[str]` ORDONNÉ
    # (première occurrence de chaque nom conservée, dédupliquée) — chaque appelant peut alors
    # reproduire la préséance via `enumerate()` (voir les 3 sites d'appel).
    noms: list[str] = []
    sous_texte = texte[debut:fin]
    spans_guillemets = _spans_guillemets(sous_texte)
    spans_commentaires = _spans_commentaires(sous_texte, spans_guillemets)
    profondeurs = _profondeurs_flow(sous_texte, spans_guillemets + spans_commentaires)
    for candidat in _CLE_FUSION_DANS_FLOW.finditer(sous_texte):
        position = candidat.start()
        if any(g_debut <= position < g_fin for g_debut, g_fin in spans_commentaires):
            continue
        # Round 114 (RC1-015, investigation proactive suite à un finding réfuté — voir
        # `_resoudre_ignored_paths_dans_mapping_flow`, dont cette fonction est le « miroir »
        # déclaré, round 32/59) : borne STRICTE (`<`), pas `<=`, pour rester cohérente avec sa
        # sœur. Vérifié empiriquement que cette borne est INATTEIGNABLE ICI (contrairement à la
        # fonction sœur) : `_CLE_FUSION_DANS_FLOW = re.compile(r"<<\s*:\s*")` ne matche jamais un
        # candidat guillemeté (la clé de fusion `<<` n'a pas d'alternative guillemetée, contrairement
        # à `_NOM_CLE_QUELCONQUE_FLOW`) — `position` (premier caractère `<`) ne peut donc JAMAIS
        # coïncider avec `g_debut` (premier caractère `"`/`'` d'un span) : un même index de texte
        # ne peut porter qu'UN seul caractère. Appliquée quand même pour l'harmonie déclarée entre
        # les deux fonctions « miroir » — élimine toute confusion future sur cette asymétrie
        # (traité, pas ignoré), sans risque de régression (comportement inchangé, prouvé inerte).
        if any(g_debut < position < g_fin for g_debut, g_fin in spans_guillemets):
            continue
        if profondeurs[position] != 0:
            continue
        position_valeur = debut + candidat.end()
        reste = texte[position_valeur:fin]
        reste_lstrip = reste.lstrip()
        position_valeur += len(reste) - len(reste_lstrip)
        noms_ici: list[str] = []
        if reste_lstrip.startswith("["):
            contenu = _trouver_fermeture_flow(texte, position_valeur + 1, "]")
            for jeton in _decouper_liste_flow(contenu):
                m_alias = _REF_ALIAS.match(jeton)
                if m_alias and m_alias.group(1) not in noms_ici:
                    noms_ici.append(m_alias.group(1))
        else:
            m_alias = _REF_ALIAS_PARTIEL.match(reste_lstrip)
            if m_alias:
                noms_ici.append(m_alias.group(1))
        # Round 96 (RC1-015, bug réel trouvé par revue scellée DeepSeek-V4-Pro-0813) :
        # REMPLACE (jamais fusionne avec) l'accumulateur des occurrences précédentes — une
        # clé de fusion `<<` DUPLIQUÉE au sein du MÊME mapping flow suit la même sémantique
        # YAML « dernière occurrence gagne » que toute autre clé dupliquée (round 67, déjà
        # vérifiée pour `ignored_paths` elle-même). `break` inconditionnel après le premier
        # candidat, retiré : ne traitait jamais qu'UNE seule occurrence de `<<`, quel que soit
        # le nombre réel présent dans le mapping — un `<<:` PLUS TARD (donc gagnant selon la
        # sémantique YAML) pouvait rester totalement invisible. Vérifié empiriquement contre
        # PyYAML (`secret: {<<: *safe, <<: *md}` où `md` porte `ignored_paths: ["**/*.md"]`)  <!-- proof:allow : exemple prose -->
        # que la DERNIÈRE occurrence REMPLACE ENTIÈREMENT la précédente (pas de fusion des
        # deux valeurs) — `secret.ignored_paths` résout vers `**/*.md` SEUL, `safe` disparaît.
        noms = noms_ici
    return noms


def _noms_ancres_fusionnees_dans_ancres_flow(
    texte: str, lignes: list[str], lignes_exclues: set[int], position_alias_racine: dict[str, int | float | Fraction]
) -> dict[str, int | float | Fraction]:
    """Noms d'ancre fusionnés (`<<`) À L'INTÉRIEUR de la valeur mapping FLOW d'une ancre déjà
    dans `position_alias_racine` — round 59 (RC1-015, bug réel trouvé par revue scellée
    GPT-5.6-Terra-Pro).

    Pour chaque nom d'ancre dans `position_alias_racine`, réutilise `_trouver_definition_ancre_valide`
    (round 59, factorisée du pré-passage round 57) pour trouver sa définition ; si sa valeur
    ouvre un mapping flow (`_SUITE_ANCRE_FLOW_OUVERTE`, round 57), délègue à
    `_noms_fusion_dans_mapping_flow` (ci-dessus) pour en extraire les noms fusionnés. Le résultat
    est destiné à être unioné dans `noms_alias_racine` par l'appelant (`parser_ignored_paths`,
    boucle à point fixe) — un nom ainsi découvert peut lui-même porter une valeur mapping flow
    fusionnant une AUTRE ancre, d'où l'itération jusqu'à stabilisation plutôt qu'une seule passe.

    Round 71 (RC1-015, bug réel trouvé — vérifié empiriquement contre PyYAML AVANT même dispatch
    revue, en testant ce correctif) : retourne un dict `{nom_ancre: indice_ligne}` — mais la
    position propagée est celle HÉRITÉE de l'ancre DÉCOUVRANTE (`position_alias_racine[nom]`),
    PAS la ligne où sa propre définition `&nom {...}` se trouve dans le fichier. Une ancre
    peut être définie AVANT la ligne racine qui la rend pertinente (déclaration avancée, YAML
    valide) — utiliser sa ligne de définition sous-évaluerait alors sa position effective par
    rapport à une occurrence racine ULTÉRIEURE légitimement gagnante (cas reproduit : `cfg`
    fusionne `inner`, `inner` est défini avant la première occurrence de la clé racine, mais
    c'est un alias direct vers `cfg` bien plus tardif qui doit l'emporter).
    """
    noms: dict[str, int | float | Fraction] = {}
    if not position_alias_racine:
        return noms
    offset = 0
    for idx, ligne in enumerate(lignes):
        if idx not in lignes_exclues:
            for m_ancre in _trouver_definition_ancre_valide(ligne):
                if m_ancre.group(1) not in position_alias_racine:
                    continue
                match_suite = _SUITE_ANCRE_FLOW_OUVERTE.match(ligne[m_ancre.end():])
                if match_suite:
                    absolu = offset + m_ancre.end() + match_suite.end()
                    contenu_ancre_flow = _trouver_fermeture_flow(texte, absolu, "}")
                    fin_accolade = absolu + len(contenu_ancre_flow)
                    position_source = position_alias_racine[m_ancre.group(1)]
                    # Round 100/101 : `_position_fusion` reproduit la préséance « premier
                    # élément de la liste de fusion gagne » (round 99, même principe, cette fois
                    # pour une fusion À L'INTÉRIEUR d'un mapping flow ancré) via un décalage
                    # FRACTIONNAIRE (round 101, jamais de collision avec une position réelle).
                    for index_fusionne, nom_fusionne in enumerate(
                        _noms_fusion_dans_mapping_flow(texte, absolu, fin_accolade)
                    ):
                        position_fusionne = _position_fusion(position_source, index_fusionne)
                        if nom_fusionne not in noms or position_fusionne > noms[nom_fusionne]:
                            noms[nom_fusionne] = position_fusionne
        offset += len(ligne) + 1
    return noms


def _noms_fusion_dans_flow_racine_secret(
    texte: str,
    lignes: list[str],
    lignes_exclues: set[int],
    ancres: dict[str, str | list[str]] | None = None,
) -> dict[str, int | float | Fraction]:
    """Noms d'ancre fusionnés (`<<`) au sein du mapping FLOW de la clé racine `secret`
    ELLE-MÊME (valeur `{<<: *nom}` directement en clé racine, sans aucune indirection d'ancre)
    — round 60 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro).

    Round 32 couvrait la recherche de la clé DIRECTE `ignored_paths` dans le mapping flow de
    `secret` elle-même ; round 59 couvrait la fusion dans le mapping flow d'une ANCRE
    référencée PAR un alias `*cfg` en valeur de la clé racine (`cfg: &cfg {<<: *md}`). Ni l'un
    ni l'autre ne couvre une fusion directement dans le mapping flow de `secret` ELLE-MÊME, sans
    alias intermédiaire. Réutilise `_LIGNE_SECRET_FLOW_OUVERTE` (round 32) pour localiser le
    mapping flow racine, puis `_noms_fusion_dans_mapping_flow` (round 59) pour en extraire les
    noms fusionnés — destinés à être unionés dans `noms_alias_racine` par l'appelant, exactement
    comme `_noms_ancres_fusionnees_dans_secret` (round 31/56) le fait pour la forme bloc.

    Gap symétrique comblé PROACTIVEMENT en vérifiant ce correctif (bug réel trouvé) : la clé
    racine `secret` peut aussi être exprimée en syntaxe EXPLICITE (round 49) avec une valeur
    mapping flow inline (round 50, `? secret\\n: {<<: *md}`) — le pré-passage round 50 souffrait
    de la MÊME limite (recherche uniquement la clé directe). Couverte ici via
    `_LIGNE_CLE_EXPLICITE` + `_LIGNE_VALEUR_EXPLICITE_SECRET_FLOW_OUVERTE` (round 50), même
    tolérance ligne vide/commentaire entre clé et valeur que le pré-passage round 50 original.

    Round 71 (même famille que `_noms_ancres_fusionnees_dans_secret`) : retourne désormais un
    dict `{nom_ancre: indice_ligne}` — position de la ligne portant la clé racine elle-même
    (occurrence RACINE, donc position directement comparable à `meilleur_trouve_ligne` sans
    approximation, contrairement aux deux fonctions sœurs round 59/71 qui n'ont qu'une position
    d'indirection).

    Round 81 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `ancres`
    (optionnel) permet de résoudre un alias utilisé comme nom de la clé racine `secret`
    elle-même, même mécanisme qu'ailleurs (round 80/81).
    """
    noms: dict[str, int | float | Fraction] = {}
    offset = 0
    for idx, ligne in enumerate(lignes):
        if idx not in lignes_exclues:
            match_secret_flow = _LIGNE_SECRET_FLOW_OUVERTE.match(ligne)
            if match_secret_flow and _decoder_nom_cle(match_secret_flow, 1, ancres) == "secret":
                absolu = offset + match_secret_flow.end()
                contenu_secret_flow = _trouver_fermeture_flow(texte, absolu, "}")
                fin_accolade = absolu + len(contenu_secret_flow)
                # Round 100/101 : même correctif que ci-dessus (préséance « premier élément de
                # la liste de fusion gagne », round 99, décalage FRACTIONNAIRE round 101) —
                # cette fois pour une fusion directement dans le mapping flow de la clé racine
                # `secret` ELLE-MÊME (round 60).
                for index_fusionne, nom_fusionne in enumerate(
                    _noms_fusion_dans_mapping_flow(texte, absolu, fin_accolade)
                ):
                    noms[nom_fusionne] = _position_fusion(idx, index_fusionne)
        offset += len(ligne) + 1

    for idx, ligne in enumerate(lignes):
        if idx in lignes_exclues:
            continue
        match_cle_explicite_racine = _LIGNE_CLE_EXPLICITE.match(ligne)
        if not (
            match_cle_explicite_racine
            and len(match_cle_explicite_racine.group(1)) == 0
            and _decoder_nom_cle(match_cle_explicite_racine, 2, ancres) == "secret"
        ):
            continue
        j = idx + 1
        while j < len(lignes) and (not lignes[j].strip() or lignes[j].strip().startswith("#")):
            j += 1
        if j >= len(lignes):
            continue
        match_valeur_secret_flow = _LIGNE_VALEUR_EXPLICITE_SECRET_FLOW_OUVERTE.match(lignes[j])
        if not match_valeur_secret_flow or len(match_valeur_secret_flow.group(1)) != 0:
            continue
        absolu = _position_debut_ligne(lignes, j) + match_valeur_secret_flow.end()
        contenu_secret_flow = _trouver_fermeture_flow(texte, absolu, "}")
        fin_accolade = absolu + len(contenu_secret_flow)
        # Round 100/101 : même correctif, forme EXPLICITE de la clé racine (round 50).
        for index_fusionne, nom_fusionne in enumerate(
            _noms_fusion_dans_mapping_flow(texte, absolu, fin_accolade)
        ):
            position_fusionne = _position_fusion(idx, index_fusionne)
            if nom_fusionne not in noms or position_fusionne > noms[nom_fusionne]:
                noms[nom_fusionne] = position_fusionne
    return noms


def _noms_ancres_aliasees_secret(
    texte: str,
    lignes: list[str],
    lignes_exclues: set[int],
    ancres: dict[str, str | list[str]] | None = None,
) -> dict[str, int | float | Fraction]:
    """Noms d'ancre référencés par un alias DIRECT du mapping `secret` tout entier (la clé
    `secret` réduite à une simple référence `*nom` comme valeur) trouvé n'importe où dans le
    fichier — round 30 (RC1-015). Sert à
    `_est_descendante_de_secret` : si `secret` lui-même est un alias vers un mapping ancré
    AILLEURS (`defaults: &cfg\\n  ignored_paths: ...` puis un alias vers `cfg` en valeur de la
    clé `secret`), le mapping `defaults` doit être traité comme équivalent au mapping `secret`
    pour la question d'ascendance, même si aucune ligne ne porte littéralement ce nom de clé.

    Round 45 (bug réel trouvé PROACTIVEMENT en vérifiant le correctif de `_est_descendante_de_secret`
    pour la même famille de bug) : `_LIGNE_SECRET_ALIAS` exige par construction que `secret` soit
    à la RACINE (aucune tolérance d'indentation) — matcher contre la ligne dépouillée de son
    indentation (`ligne.strip()`) annulait cette distinction, une clé `secret` HOMONYME réduite
    à un alias, imbriquée sous un autre parent, étant alors traitée comme la vraie clé racine,
    enregistrant à tort le nom d'ancre référencé comme équivalent-racine. Désormais matché
    contre `ligne` brute (indentation préservée) — voir `_est_descendante_de_secret` pour la
    reproduction complète et la même correction.

    Round 55 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la clé racine réduite à un
    alias peut aussi être exprimée en syntaxe EXPLICITE (rounds 42-43/46/49-54 supportaient déjà
    cette syntaxe ailleurs mais jamais pour CETTE forme précise) — `_LIGNE_SECRET_ALIAS` ne
    reconnaît que la forme classique sur une seule ligne. Chaque ligne `: *nom` (round 46) est
    désormais aussi vérifiée via `_nom_ancre_secret_explicite_alias`.

    Round 70 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : retourne désormais un
    dict `{nom_ancre: indice_ligne}` (au lieu d'un simple `set[str]`) — le pré-passage round 57
    a besoin de la position de l'occurrence RACINE (l'alias direct lui-même, pas celle de la
    définition de l'ancre référencée, potentiellement ailleurs dans le fichier) pour comparer
    correctement contre `meilleur_trouve_ligne` en cas de clé racine DUPLIQUÉE (rounds 67-69 :
    dernière occurrence gagne). Si le même nom d'ancre est référencé par PLUSIEURS alias racine
    directs (cas rare), la DERNIÈRE l'emporte pour la position — cohérent avec le principe
    général.

    Round 81 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `ancres`
    (optionnel) permet de résoudre un alias utilisé comme nom de la clé racine `secret`
    elle-même (`*k: *cfg` où `&k` ancre `"secret"`) — même mécanisme que pour `ignored_paths`
    (round 80), étendu ici à la clé racine et transmis à `_nom_ancre_secret_explicite_alias`
    pour la forme explicite jumelle.
    """
    noms: dict[str, int | float | Fraction] = {}
    for idx, ligne in enumerate(lignes):
        if idx in lignes_exclues:
            continue
        m = _LIGNE_SECRET_ALIAS.match(ligne)
        if m and _decoder_nom_cle(m, 1, ancres) == "secret":
            noms[m.group(4)] = idx
        nom_explicite = _nom_ancre_secret_explicite_alias(texte, lignes, idx, ancres)
        if nom_explicite is not None:
            noms[nom_explicite] = idx
    return noms


def _nom_ancre_secret_explicite_alias(
    texte: str,
    lignes: list[str],
    indice_alias: int,
    ancres: dict[str, str | list[str]] | None = None,
) -> str | None:
    """Si `lignes[indice_alias]` (un alias direct `: *nom`, round 46) referme une clé `secret`
    EXPLICITE à la RACINE, retourne le nom de l'ancre référencée — round 55 (RC1-015), sinon
    `None`. Même logique de remontée que `_est_ligne_secret_explicite` (round 49), appliquée à
    la forme alias plutôt qu'à la forme bloc — `secret` doit être à l'indentation 0 (même
    invariant que `_LIGNE_CLE_SECRET`/`_LIGNE_SECRET_ALIAS`, round 45).

    Round 63 (bug réel trouvé PROACTIVEMENT en vérifiant le correctif jumeau
    `_est_ligne_secret_explicite`, même famille de bug) : le nom de la clé explicite peut lui-
    même être une chaîne double-guillemets MULTILIGNE (round 58/63,
    `_decoder_cle_explicite_multiligne`) — tentée dès que le nom décodé sur une seule ligne
    n'est pas déjà `secret`. La ligne trouvée en remontant peut être soit la ligne `?` de
    DÉPART elle-même (guillemet non refermé sur cette même ligne), soit la DERNIÈRE ligne
    (fermeture de guillemet) d'une clé commencée PLUS HAUT — plusieurs positions de départ
    candidates sont donc essayées jusqu'à trouver une clé multiligne se terminant EXACTEMENT
    à la ligne trouvée.

    Round 81 (RC1-015, même famille que le correctif jumeau `_est_descendante_de_secret`) :
    `ancres` (optionnel) permet de résoudre un alias utilisé comme nom de la clé EXPLICITE
    elle-même, cohérent avec les autres mécanismes de reconnaissance de `secret`.
    """
    match_alias = _LIGNE_VALEUR_EXPLICITE_ALIAS.match(lignes[indice_alias])
    if not match_alias:
        return None
    indentation_alias = len(match_alias.group(1))
    for k in range(indice_alias - 1, -1, -1):
        ligne_k = lignes[k]
        nue_k = ligne_k.strip()
        if not nue_k or nue_k.startswith("#"):
            continue
        match_cle = _LIGNE_CLE_EXPLICITE.match(ligne_k)
        nom_cle = None
        indentation_cle = None
        if match_cle:
            nom_cle = _decoder_nom_cle(match_cle, 2, ancres)
            indentation_cle = len(match_cle.group(1))
        if nom_cle != "secret":
            for k_debut in range(k, -1, -1):
                resultat_multiligne = _decoder_cle_explicite_multiligne(texte, lignes, k_debut)
                if resultat_multiligne and resultat_multiligne[1] == k:
                    nom_cle = resultat_multiligne[0]
                    indentation_cle = len(lignes[k_debut]) - len(lignes[k_debut].lstrip(" "))
                    break
        if (
            indentation_cle == indentation_alias
            and indentation_alias == 0
            and nom_cle == "secret"
        ):
            return match_alias.group(2)
        return None
    return None


def _est_ligne_secret_explicite(
    texte: str,
    lignes: list[str],
    indice_deux_points: int,
    ancres: dict[str, str | list[str]] | None = None,
) -> bool:
    """True si `lignes[indice_deux_points]` (un séparateur `:` seul, round 42) referme une clé
    `secret` EXPLICITE (`? secret`) à la RACINE — round 49 (RC1-015, bug réel trouvé par revue
    scellée GPT-5.6-Terra-Pro).

    La syntaxe de clé explicite (`? nom\\n:`) avait été supportée pour `ignored_paths`
    (round 42-43, 46) mais jamais pour la clé racine elle-même — `_LIGNE_CLE_SECRET` exige la
    forme bloc classique (round 45 : à la racine), et ne reconnaît donc pas `? secret` sur une
    ligne séparée. Vérifié empiriquement contre PyYAML : la forme explicite de la clé racine,
    combinée à `ignored_paths` elle-même explicite, résout normalement.

    Remonte depuis la ligne `:` jusqu'à la première ligne non vide/non commentée précédente ; si
    elle matche `_LIGNE_CLE_EXPLICITE` à la MÊME indentation que le `:`, décode en `secret`, ET
    est elle-même à la RACINE (indentation 0 — même invariant que `_LIGNE_CLE_SECRET`, round 45 :
    un `? secret` imbriqué sous un autre parent n'est PAS le vrai mapping racine), la ligne `:`
    est traitée comme équivalente à la forme bloc classique. Portée bornée à la forme couverte
    par `_LIGNE_VALEUR_EXPLICITE` (`:` seul, valeur sur les lignes suivantes) — mêmes limites
    assumées que le round 42 pour la clé `ignored_paths`.

    Round 63 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : le nom de la clé explicite
    peut lui-même être une chaîne double-guillemets MULTILIGNE via une continuation échappée
    (round 58, `_decoder_cle_explicite_multiligne`) — cette capacité avait été branchée dans
    `parser_ignored_paths` pour reconnaître `ignored_paths`, jamais ici pour reconnaître `secret`
    à la racine. La ligne trouvée en remontant depuis `:` peut être soit la ligne `?` de DÉPART
    elle-même (guillemet non refermé sur cette même ligne, round 58), soit la DERNIÈRE ligne
    (fermeture de guillemet) d'une clé commencée PLUS HAUT (round 63) — plusieurs positions de
    départ candidates sont essayées jusqu'à trouver une clé multiligne se terminant EXACTEMENT à
    la ligne trouvée.

    Round 81 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `ancres` (optionnel,
    transmis depuis `_est_descendante_de_secret`) permet de résoudre un alias utilisé comme nom
    de la clé racine EXPLICITE elle-même (`? *k\\n:`) — même mécanisme que round 80 pour
    `ignored_paths`, étendu ici à la forme explicite de `secret`.
    """
    match_valeur = _LIGNE_VALEUR_EXPLICITE.match(lignes[indice_deux_points])
    if not match_valeur:
        return False
    indentation_deux_points = len(match_valeur.group(1))
    for k in range(indice_deux_points - 1, -1, -1):
        ligne_k = lignes[k]
        nue_k = ligne_k.strip()
        if not nue_k or nue_k.startswith("#"):
            continue
        match_cle = _LIGNE_CLE_EXPLICITE.match(ligne_k)
        nom_cle = None
        indentation_cle = None
        if match_cle:
            nom_cle = _decoder_nom_cle(match_cle, 2, ancres)
            indentation_cle = len(match_cle.group(1))
        if nom_cle != "secret":
            for k_debut in range(k, -1, -1):
                resultat_multiligne = _decoder_cle_explicite_multiligne(texte, lignes, k_debut)
                if resultat_multiligne and resultat_multiligne[1] == k:
                    nom_cle = resultat_multiligne[0]
                    indentation_cle = len(lignes[k_debut]) - len(lignes[k_debut].lstrip(" "))
                    break
        if indentation_cle == indentation_deux_points and indentation_deux_points == 0:
            return nom_cle == "secret"
        return False
    return False


def _decoder_cle_explicite_multiligne(
    texte: str, lignes: list[str], indice: int
) -> tuple[str, int] | None:
    """Pour une ligne `? "..."` (indice `indice`) dont le nom de clé est une chaîne DOUBLE-
    GUILLEMETS qui ne se referme PAS sur la même ligne physique, résout le nom de clé complet en
    balayant `texte` (pas seulement `lignes[indice]`) — retourne `(nom_décodé,
    indice_dernière_ligne_de_la_clé)`, ou None si cette ligne ne correspond pas à ce cas.

    Round 58 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `_LIGNE_CLE_EXPLICITE`
    exige la clé entière (guillemet ouvrant ET fermant) sur une seule ligne physique — une chaîne
    double-guillemets YAML valide peut légitimement s'étendre sur PLUSIEURS lignes via une
    continuation de ligne échappée (`\\` immédiatement suivi d'un saut de ligne), exactement le
    même mécanisme déjà couvert pour les VALEURS depuis le round 11 (voir
    `_decoder_echappements_yaml`). Reproduction du reviewer, vérifiée empiriquement contre PyYAML :
    `? "ignored_\\n    paths"` <!-- proof:allow : exemple prose --> (continuation échappée) résout
    bien en `ignored_paths`. Réutilise `_CHAINE_DOUBLE_GUILLEMETS` (déjà compilée en mode DOTALL,
    round 10) appliquée à `texte` à partir de la position absolue du guillemet ouvrant — capable
    nativement de franchir des sauts de ligne, contrairement à une recherche ligne par ligne.
    """
    m_prefixe = re.match(r"^(\s*)\?\s*" + _PROPRIETES_NOEUD, lignes[indice])
    if not m_prefixe:
        return None
    reste = lignes[indice][m_prefixe.end():]
    if not reste.startswith('"'):
        return None
    absolu = _position_debut_ligne(lignes, indice) + m_prefixe.end()
    m_chaine = _CHAINE_DOUBLE_GUILLEMETS.match(texte, absolu)
    if not m_chaine:
        return None
    apres = texte[m_chaine.end():]
    fin_ligne = apres.find("\n")
    reste_meme_ligne = apres if fin_ligne == -1 else apres[:fin_ligne]
    if not re.match(r"^\s*(#.*)?$", reste_meme_ligne):
        return None
    indice_derniere_ligne = indice + texte.count("\n", absolu, m_chaine.end())
    return _decoder_echappements_yaml(m_chaine.group(1)), indice_derniere_ligne


def _est_descendante_de_secret(
    texte: str,
    lignes: list[str],
    indice: int,
    indentation_cle: int,
    position_alias_racine: dict[str, int | float | Fraction] | None = None,
    ancres: dict[str, str | list[str]] | None = None,
) -> int | float | Fraction | None:
    """Position EFFECTIVE à utiliser pour la comparaison « dernière occurrence gagne » si
    `lignes[indice]` (portant une clé `ignored_paths` à `indentation_cle`) est bien un
    DESCENDANT du mapping secret (clé de schéma YAML, pas un secret réel — voir
    `_LIGNE_CLE_SECRET`), pas une clé homonyme sous un autre parent ; `None` sinon.

    Round 72 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : retournait
    auparavant un simple `bool` — chaque appelant utilisait alors SA PROPRE position locale
    (`indice`, ou une variable équivalente) pour la comparaison à `meilleur_trouve_ligne`. Ceci
    est CORRECT quand l'ascendant est la clé racine `secret` LITTÉRALE (la ligne est
    textuellement à l'intérieur de l'occurrence racine physique qui la concerne — la position
    locale REFLÈTE alors la position racine à un décalage constant près, sans jamais inverser
    l'ordre relatif entre deux occurrences racine distinctes). Mais quand l'ascendant est un nom
    d'ancre ALIAS-ÉQUIVALENT (`position_alias_racine`, rounds 30/55/31/56/59/60/71), la ligne
    candidate peut être définie N'IMPORTE OÙ dans le fichier (déclaration avancée, YAML valide)
    — potentiellement bien AVANT l'occurrence racine tardive qui la rend effectivement
    pertinente pour la clé racine. Reproduction du reviewer (voir
    `test_parser_detecte_cle_racine_secret_dupliquee_alias_vers_ancre_bloc` pour le YAML exact) :
    une ancre bloc `cfg` porte sa propre `ignored_paths`, la clé racine porte d'abord
    `ignored_paths: [safe]`, puis une SECONDE occurrence de la clé racine est un alias direct
    vers `cfg` — résout en `['**/*.md']` (dernière occurrence gagnante), alors que l'ancien code
    retournait `['safe']` — la position locale de la clé `ignored_paths` sous l'ancre (ligne 1,
    tôt dans le fichier) perdait à tort face à celle sous l'occurrence bloc intermédiaire (ligne
    5), la seconde occurrence racine tardive (ligne 7, l'alias) n'étant elle-même examinée par
    AUCUN mécanisme. Retourne désormais `indice` inchangé pour l'ascendance
    littérale (comportement identique à avant), et `position_alias_racine[nom]` (POSITION
    HÉRITÉE de l'ancre) pour l'ascendance par alias — chaque appelant compare directement la
    valeur retournée à `meilleur_trouve_ligne`, sans plus jamais utiliser sa propre position
    locale pour ce cas.

    Bug réel trouvé par revue scellée GPT-5.6-Terra-Pro (RC1-015 round 19) : le cliquet
    analysait la PREMIÈRE clé `ignored_paths` rencontrée dans le fichier, sans vérifier son
    appartenance à ce mapping. Un YAML valide où une clé `ignored_paths` homonyme existe sous un
    AUTRE parent (ex. `autre:\\n  ignored_paths: [safe]`), placée AVANT la vraie liste dans le
    fichier, masquait donc la vraie liste.

    Remonte les lignes précédentes en ignorant celles de même indentation ou plus profondes
    (frères/descendants sans rapport avec la question de parenté) ; la PREMIÈRE ligne rencontrée
    avec une indentation STRICTEMENT inférieure à `indentation_cle` doit matcher
    `_LIGNE_CLE_SECRET` — toute autre clé à ce niveau signifie que `ignored_paths` appartient à
    un parent différent. Round 30 : accepte aussi une ligne portant une ancre (`&nom`) dont le
    nom figure dans `noms_alias_racine` (voir `_noms_ancres_aliasees_secret`) — le mapping
    entier `secret` peut être fourni par alias vers un mapping ancré ailleurs.

    Round 45 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `_LIGNE_CLE_SECRET` exige
    par construction que la clé `secret` soit à la RACINE (aucune tolérance d'indentation avant
    la clé, contrairement aux formes `ignored_paths`) — c'est précisément ce qui distingue le
    VRAI mapping racine d'un mapping HOMONYME imbriqué sous un autre parent (`autre` portant une
    clé `secret` en fils, elle-même porteuse d'`ignored_paths`). Matcher cette regex contre la
    ligne DÉPOUILLÉE de son indentation (`nue`, comme c'était le cas jusqu'ici) annule cette
    distinction — la clé homonyme imbriquée à N'IMPORTE QUELLE profondeur devenait indiscernable
    de la vraie clé racine une fois l'indentation retirée. Désormais matché contre la ligne
    BRUTE (`ligne`, indentation préservée) : `_LIGNE_CLE_SECRET` échoue alors naturellement dès
    que le premier caractère n'est pas la clé elle-même (position 0 non blanche).

    Round 49 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la clé racine elle-même
    peut être exprimée en syntaxe EXPLICITE (`? nom\\n:`, round 42-43/46 supportait déjà cette
    forme pour `ignored_paths` mais jamais pour la clé racine) — `_LIGNE_CLE_SECRET` ne reconnaît
    que la forme bloc classique sur une seule ligne. Accepte désormais aussi une ligne `:` seule
    (round 42) qui referme une clé racine explicite (voir `_est_ligne_secret_explicite`).

    Round 63 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `texte` est désormais un
    paramètre (au lieu de ne recevoir que `lignes`) pour pouvoir transmettre à
    `_est_ligne_secret_explicite` la capacité de résoudre une clé racine explicite dont le nom
    est une chaîne double-guillemets MULTILIGNE (round 58, `_decoder_cle_explicite_multiligne`)
    — cette capacité n'avait été branchée que dans la recherche de `ignored_paths` elle-même
    (`parser_ignored_paths`), jamais dans la remontée d'ascendance vers la clé racine.

    Round 80 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `_decoder_nom_cle`
    résout désormais un alias utilisé comme nom de clé (`*k` où `&k` ancre `"ignored_paths"`)
    pour la clé `ignored_paths` ELLE-MÊME — voir `parser_ignored_paths`, dont les 6 mécanismes
    de recherche passent tous `ancres` à `_decoder_nom_cle`. Portée alors délibérément bornée au
    nom de `ignored_paths` — le nom de la clé RACINE `secret` (comparaison ci-dessous) n'était
    PAS résolu de la même façon.

    Round 81 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro — EXACTEMENT la
    limite documentée au round 80) : `ancres` est désormais aussi transmis ICI (paramètre
    ajouté) et à `_est_ligne_secret_explicite` — un alias utilisé comme nom de la clé RACINE
    elle-même (`*k:` où `&k` ancre `"secret"`, forme bloc OU explicite) est donc désormais
    résolu au même titre que `ignored_paths` (round 80). Reproduction du reviewer, vérifiée
    empiriquement contre PyYAML.

    Round 83 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la branche
    `position_alias_racine` ci-dessous scannait `ligne` via `_DEF_ANCRE.finditer()` BRUT, sans
    filtrer les spans guillemetés/commentaires ni vérifier `_PREFIXE_AVANT_ANCRE` — contrairement
    à TOUTE autre reconnaissance d'ancre dans ce fichier (`_construire_table_ancres`,
    `_trouver_definition_ancre_valide`). Un marqueur `&nom` apparaissant à l'intérieur d'une
    chaîne guillemetée SANS RAPPORT (`"&cfg"`, texte littéral, pas une vraie définition d'ancre
    — même famille que les rounds 23/24 pour `_construire_table_ancres`) pouvait donc être
    confondu avec une VRAIE définition d'ancre équivalente à `secret`. Reproduction construite
    et vérifiée empiriquement contre PyYAML (le YAML exact suggéré par le reviewer était
    lui-même invalide — corrigé en une forme équivalente valide avant tout ajout de test).
    Corrigé en réutilisant `_trouver_definition_ancre_valide(ligne)` (déjà filtrée) au lieu du
    `_DEF_ANCRE.finditer()` brut — même remède que round 59 avait déjà appliqué au pré-passage
    round 57, jamais rétro-appliqué ici.
    """
    for j in range(indice - 1, -1, -1):
        ligne = lignes[j]
        nue = ligne.strip()
        if not nue or nue.startswith("#"):
            continue
        indentation_j = len(ligne) - len(ligne.lstrip(" "))
        if indentation_j >= indentation_cle:
            continue
        m_cle_racine = _LIGNE_CLE_SECRET.match(ligne)
        if m_cle_racine and _decoder_nom_cle(m_cle_racine, 1, ancres) == "secret":
            return indice
        if _est_ligne_secret_explicite(texte, lignes, j, ancres):
            return indice
        if position_alias_racine:
            for candidat in _trouver_definition_ancre_valide(ligne):
                if candidat.group(1) in position_alias_racine:
                    return position_alias_racine[candidat.group(1)]
        return None
    return None


def _noms_ancres_fusionnees_dans_secret(
    texte: str,
    lignes: list[str],
    lignes_exclues: set[int],
    position_alias_racine: dict[str, int | float | Fraction],
    ancres: dict[str, str | list[str]] | None = None,
) -> dict[str, int | float | Fraction]:
    """Noms d'ancre fusionnés dans le mapping `secret` via une clé de FUSION YAML
    (`<<: *nom`) qui est elle-même descendante de `secret` — round 31 (RC1-015).

    Bug réel trouvé par revue scellée GPT-5.6-Terra-Pro : une clé de fusion `<<: *cfg` au sein
    du mapping `secret` (YAML valide, extension `tag:yaml.org,2002:merge` largement supportée
    dont PyYAML) fusionne les
    paires clé-valeur du mapping ancré `cfg` DANS `secret` — si `cfg` porte lui-même une clé
    `ignored_paths`, celle-ci devient effectivement `secret.ignored_paths` pour tout
    consommateur qui résout les fusions, sans qu'aucune ligne `ignored_paths` ne soit
    textuellement descendante de `secret`. Réutilise `_est_descendante_de_secret` (déjà
    générique — ne dépend pas du fait que la ligne contrôlée soit `ignored_paths`) pour établir
    qu'une ligne `<<: *nom` donnée est bien à l'intérieur du mapping `secret` avant de retenir
    son nom d'ancre. Portée volontairement bornée à un seul niveau d'indirection.

    Round 56 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la limite documentée à
    l'origine (« une SEULE ancre par fusion, `<<: *nom`, pas `<<: [*a, *b]` ») est comblée — la
    forme LISTE flow (`<<: [*a, *b]`) est une extension merge-key valide, vérifiée empiriquement
    contre PyYAML. `_LIGNE_FUSION_FLOW_OUVERTE` la reconnaît ; réutilise
    `_trouver_fermeture_flow`/`_decouper_liste_flow` (déjà en place pour les listes flow
    ailleurs, rounds 12/17) pour extraire CHAQUE alias référencé, pas seulement le premier.
    Gap symétrique comblé proactivement dans la foulée : la même « séquence de nœuds mapping »
    peut aussi s'écrire en style BLOC (`<<:\n  - *a\n  - *b`), vérifié empiriquement équivalent
    contre PyYAML — `_LIGNE_FUSION_VALEUR_VIDE` + items `- *nom` (réutilise `_LIGNE_ITEM_ALIAS`).

    Round 71 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : retournait un dict
    `{nom_ancre: indice_ligne}` (au lieu d'un simple `set[str]`) en utilisant systématiquement
    la position de la ligne `<<:` ELLE-MÊME.

    Round 72 (bug latent comblé PROACTIVEMENT dans la même famille que le correctif round 72 de
    `_est_descendante_de_secret`, vérifié empiriquement contre PyYAML avant tout dispatch de
    revue) : cette approximation n'est CORRECTE que lorsque l'ascendant de la ligne `<<:` est la
    clé racine `secret` LITTÉRALE — pas quand c'est un nom d'ancre ALIAS-ÉQUIVALENT (la ligne
    `<<:` peut alors être définie n'importe où dans le fichier, potentiellement bien avant
    l'occurrence racine tardive qui la rend pertinente). Utilise désormais directement la
    position EFFECTIVE retournée par `_est_descendante_de_secret` (au lieu de `idx`) — voir sa
    docstring. Si le même nom est fusionné par PLUSIEURS lignes `<<:` (cas rare), la position la
    PLUS TARDIVE l'emporte.

    Round 81 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `ancres`
    (optionnel) est transmis à `_est_descendante_de_secret` pour résoudre un alias utilisé
    comme nom de la clé racine `secret` elle-même (round 80/81, voir `_decoder_nom_cle`).

    Round 99 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : pour une fusion
    LISTE (`<<: [*a, *b, …]`, formes flow ET bloc), toutes les ancres recevaient la position
    IDENTIQUE de la ligne `<<:` elle-même — le résultat final dépendait alors de l'ordre de
    balayage TEXTUEL du document (quel `ignored_paths` est physiquement rencontré en premier),
    jamais de l'ordre RÉEL dans la liste de fusion. Or la sémantique YAML merge-key fait gagner
    le PREMIER élément de la liste sur les suivants en cas de clé dupliquée (vérifié
    empiriquement contre PyYAML) — l'INVERSE de la convention « dernière occurrence gagne » qui
    régit par ailleurs ce cliquet. Chaque jeton de la liste reçoit désormais `position -
    index_jeton` (le premier élément conserve la position pleine, chaque suivant une position
    strictement inférieure) — reproduit fidèlement l'ordre de préséance réel (vérifié dans les
    deux sens : `[*danger, *safe]` fait gagner `danger`, `[*safe, *danger]` fait gagner `safe`,
    à l'identique de PyYAML dans les deux cas), sans jamais changer l'ordonnancement relatif à
    une occurrence provenant d'une AUTRE ligne `<<:` distincte.
    """
    noms: dict[str, int | float | Fraction] = {}
    for idx, ligne in enumerate(lignes):
        if idx in lignes_exclues:
            continue
        m = _LIGNE_FUSION.match(ligne)
        if m:
            position = _est_descendante_de_secret(
                texte, lignes, idx, len(m.group(1)), position_alias_racine, ancres
            )
            if position is not None and (m.group(2) not in noms or position > noms[m.group(2)]):
                noms[m.group(2)] = position
        m_flow = _LIGNE_FUSION_FLOW_OUVERTE.match(ligne)
        if m_flow:
            position = _est_descendante_de_secret(
                texte, lignes, idx, len(m_flow.group(1)), position_alias_racine, ancres
            )
            if position is not None:
                absolu = _position_debut_ligne(lignes, idx) + m_flow.end()
                contenu = _trouver_fermeture_flow(texte, absolu, "]")
                # Round 99 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) :
                # toutes les ancres d'une même fusion-LISTE recevaient la position IDENTIQUE de
                # la ligne `<<:` elle-même — `<<: [*danger, *safe]` enregistrait `danger` et
                # `safe` à égalité, laissant le résultat final dépendre de l'ordre de balayage
                # TEXTUEL du DOCUMENT (quel `ignored_paths` est physiquement rencontré en
                # premier), jamais de l'ordre DANS LA LISTE de fusion. Or la sémantique YAML
                # merge-key fait gagner le PREMIER élément de la liste sur les suivants en cas
                # de clé dupliquée (vérifié empiriquement contre PyYAML) — l'INVERSE de l'ordre
                # « dernière occurrence gagne » qui régit le reste de ce cliquet. Décale
                # désormais la position de CHAQUE jeton par son index dans la liste via
                # `_position_fusion` : le premier élément conserve la position pleine de la
                # ligne `<<:`, chaque élément suivant reçoit une position strictement
                # inférieure — le premier gagne donc systématiquement la comparaison
                # `position > noms[...]` face aux suivants de LA MÊME liste. Round 101 (bug réel
                # trouvé par revue scellée GPT-5.6-Terra-Pro) : un décalage ENTIER (`position -
                # index_jeton`, comportement initial de ce round 99) pouvait entrer en
                # COLLISION avec la position RÉELLE d'un contenu totalement indépendant ailleurs
                # dans le document — `_position_fusion` utilise désormais un décalage
                # FRACTIONNAIRE, qui ne peut jamais atteindre ni dépasser un entier distinct
                # (voir sa docstring).
                for index_jeton, jeton in enumerate(_decouper_liste_flow(contenu)):
                    match_alias = _REF_ALIAS.match(jeton)
                    if match_alias:
                        position_jeton = _position_fusion(position, index_jeton)
                        if (
                            match_alias.group(1) not in noms
                            or position_jeton > noms[match_alias.group(1)]
                        ):
                            noms[match_alias.group(1)] = position_jeton
        m_vide = _LIGNE_FUSION_VALEUR_VIDE.match(ligne)
        if m_vide:
            position = _est_descendante_de_secret(
                texte, lignes, idx, len(m_vide.group(1)), position_alias_racine, ancres
            )
            if position is not None:
                indentation_fusion = len(m_vide.group(1))
                j = idx + 1
                index_item = 0
                while j < len(lignes):
                    nue_j = lignes[j].strip()
                    if not nue_j or nue_j.startswith("#"):
                        j += 1
                        continue
                    match_item_alias = _LIGNE_ITEM_ALIAS.match(lignes[j])
                    if match_item_alias and len(match_item_alias.group(1)) > indentation_fusion:
                        # Round 99/101 : même correctif que la forme flow ci-dessus, pour la
                        # forme BLOC de la séquence de fusion (`<<:\n  - *a\n  - *b`, round 56).
                        nom_item = match_item_alias.group(2)
                        position_item = _position_fusion(position, index_item)
                        if nom_item not in noms or position_item > noms[nom_item]:
                            noms[nom_item] = position_item
                        index_item += 1
                        j += 1
                        continue
                    break
    return noms


def parser_ignored_paths(fichier: Path) -> list[str]:
    """Extrait la liste `secret.ignored_paths` d'un `.gitguardian.yaml`.

    Analyseur minimal ligne par ligne (pas de dépendance YAML) : repère la ligne `ignored_paths:`,
    puis collecte les items plus indentés qui suivent — `- "..."` / `- '...'` / `- ...` sur une
    ligne, OU un scalaire bloc `- >`/`- |` (+ variantes de chomping `-`/`+`/indicateur de
    profondeur) dont le contenu réel vit sur les lignes suivantes, plus indentées — jusqu'à la
    première ligne moins indentée ou non-item (fin de liste). Une ligne VIDE ou un COMMENTAIRE
    SEUL entre deux items est du YAML valide au sein d'une séquence — ni l'un ni l'autre ne
    termine la liste (bug réel corrigé, trouvé par revue scellée GPT-5.6-Terra-Pro, RC1-015
    round 6 : sans cette tolérance, un item après une ligne vide/commentaire — dont une
    réintroduction de `**/*.md` — n'était jamais analysé). Le scalaire bloc (round 8) est le
    même bug de fond sous une autre forme : `- >-` capté comme valeur littérale `'>-'` par
    l'analyseur d'item plein-de-ligne laissait le VRAI contenu (la ligne suivante, plus indentée)
    jamais examiné.

    Round 12 : gère aussi la syntaxe "flow" `ignored_paths: [item1, "item2", *alias]`, et les
    items de bloc exprimés comme alias (`- *alias`) — les deux résolus via une table d'ancres
    construite sur l'INTÉGRALITÉ du fichier (voir `_construire_table_ancres`). Round 17 : la
    syntaxe flow est détectée sur plusieurs lignes physiques (`ignored_paths: [\n  *alias\n]`),
    hors de portée d'une regex ancrée à une seule ligne. Round 18 : la recherche de la clé flow
    ignore désormais les lignes qui sont le CONTENU d'un AUTRE scalaire bloc ailleurs dans le
    fichier (`_lignes_contenu_bloc`) — sans cette exclusion, du texte non structurel à
    l'intérieur d'un scalaire bloc sans rapport (ex. `note: |-\n  ignored_paths: [safe]`)
    pouvait être pris pour la vraie clé et empêcher l'analyse de la vraie liste. Round 19 :
    chaque candidat `ignored_paths:` (flow ou bloc) est vérifié comme DESCENDANT du mapping
    secret (`_est_descendante_de_secret`) — une clé homonyme sous un autre parent, placée
    avant la vraie dans le fichier, ne doit plus la masquer ; le premier candidat sans parent
    valide est ignoré et la recherche continue.
    """
    # SonarCloud pythonsecurity:S8707 (round 117, #445) : validé explicitement AVANT tout accès
    # disque, plutôt que de se reposer uniquement sur `main()` (appelant distant, non visible
    # par l'analyse de flux locale de Sonar) — même idiome que scripts/gate_docs.py et
    # scripts/state_current.py pour cette même règle (#385/#449).
    if not fichier.is_file():
        raise ValueError(f"fichier introuvable ou n'est pas un fichier régulier : {str(fichier)!r}")
    texte = fichier.read_text(encoding="utf-8")
    lignes = texte.splitlines()
    lignes_exclues = _lignes_contenu_bloc(lignes)
    ancres = _construire_table_ancres(texte, lignes, lignes_exclues)
    # Round 59 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `noms_alias_racine`
    # peut croître PAR PALIERS — un nom découvert par fusion (round 31/56) ou par fusion DANS un
    # mapping flow ancré (round 59, `_noms_ancres_fusionnees_dans_ancres_flow`) peut lui-même
    # porter une valeur qui, à son tour, fusionne une AUTRE ancre. Boucle à point fixe (jusqu'à
    # stabilisation) plutôt qu'une seule passe, pour ne pas rouvrir cette même limite à une
    # profondeur d'indirection supplémentaire à chaque futur round. Round 60 : la source initiale
    # inclut aussi `_noms_fusion_dans_flow_racine_secret` (fusion DIRECTEMENT dans le mapping flow
    # de la clé racine elle-même, valeur `{<<: *md}`, sans indirection d'ancre — ne dépend pas
    # d'un `noms_alias_racine` préexistant, comme `_noms_ancres_aliasees_secret`).
    # Round 70 : `position_alias_racine` (nom d'ancre -> indice de ligne de l'occurrence racine
    # qui l'a découvert) est conservé séparément de `noms_alias_racine` (qui reste un frozenset
    # de simples noms, inchangé pour tous ses usages existants) — le pré-passage round 57 en a
    # besoin pour comparer sa propre position à `meilleur_trouve_ligne` en cas de clé racine
    # DUPLIQUÉE dont une occurrence est un alias (rounds 67-69/70).
    # Round 71 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : `position_alias_racine`
    # se limitait à la source alias-direct (round 30/55) — un nom découvert UNIQUEMENT via une
    # FUSION (round 31/56/59/60) n'y avait aucune entrée, rouvrant le "dernière occurrence gagne"
    # (rounds 67-70) pour ce sous-cas précis. Toutes les sources dict[str,int] (alias direct,
    # fusion racine bloc round 31/56, fusion racine flow round 60, fusion dans ancre-flow
    # round 59) sont désormais fusionnées dans le MÊME dict `position_alias_racine`, en
    # conservant la position la PLUS TARDIVE en cas de nom découvert par plusieurs sources.
    position_alias_racine: dict[str, int | float | Fraction] = dict(
        _noms_ancres_aliasees_secret(texte, lignes, lignes_exclues, ancres)
    )
    for nom, pos in _noms_fusion_dans_flow_racine_secret(
        texte, lignes, lignes_exclues, ancres
    ).items():
        if nom not in position_alias_racine or pos > position_alias_racine[nom]:
            position_alias_racine[nom] = pos
    # Round 76 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la condition
    # d'arrêt `nouveau == noms_alias_racine` (comparaison d'ENSEMBLE DE NOMS) `break`ait AVANT
    # la mise à jour de `position_alias_racine` — un nom déjà connu (ensemble inchangé)
    # redécouvert à une position PLUS TARDIVE par une itération ultérieure (ex. une fusion
    # plus tardive qu'un alias racine direct qui l'avait initialement enregistré) ne voyait
    # donc JAMAIS sa position mise à jour, faisant perdre à tort face à une occurrence
    # intermédiaire de la clé racine. Vérifié empiriquement contre PyYAML. Corrigé en
    # inversant l'ordre : la mise à jour de position a lieu D'ABORD, pour TOUS les candidats
    # (nouveaux ou déjà connus), et la condition d'arrêt devient « aucune position n'a changé
    # cette itération » — terminaison garantie : chaque position ne peut que CROÎTRE, bornée
    # par `len(lignes)`, espace de noms fini.
    noms_alias_racine = frozenset(position_alias_racine)
    while True:
        candidats: dict[str, int | float | Fraction] = {}
        for source in (
            _noms_ancres_fusionnees_dans_secret(
                texte, lignes, lignes_exclues, position_alias_racine, ancres
            ),
            _noms_ancres_fusionnees_dans_ancres_flow(texte, lignes, lignes_exclues, position_alias_racine),
        ):
            for nom, pos in source.items():
                if nom not in candidats or pos > candidats[nom]:
                    candidats[nom] = pos
        change = False
        for nom, pos in candidats.items():
            if nom not in position_alias_racine or pos > position_alias_racine[nom]:
                position_alias_racine[nom] = pos
                change = True
        if not change:
            break
        noms_alias_racine = frozenset(position_alias_racine)
    chemins: list[str] = []

    # Round 69 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : PyYAML accepte
    # silencieusement une clé RACINE `secret` DUPLIQUÉE (pas seulement `ignored_paths` DANS
    # `secret`, déjà couvert rounds 67/68) — la DERNIÈRE occurrence l'emporte. Les pré-passages
    # ci-dessous (round 32, round 50) `return`aient immédiatement sur leur premier `secret`
    # trouvé, avant que le pré-passage round 68 ou la boucle principale n'aient la moindre
    # chance d'examiner une occurrence ULTÉRIEURE. `meilleur_trouve`/`meilleur_trouve_ligne`
    # sont donc déclarés ICI (avant TOUT pré-passage, pas seulement avant celui round 68) et
    # partagés par l'ENSEMBLE des mécanismes de recherche — chaque candidat valide, où qu'il
    # soit trouvé, n'écrase le résultat mémorisé QUE s'il est textuellement PLUS TARDIF.
    # Portée : couvre les pré-passages round 32 (clé racine réduite à un mapping flow entier)
    # et round 50 (même forme, syntaxe explicite `? nom\n: {...}`) — le pré-passage round 57
    # (clé racine réduite à un alias vers une ancre-mapping-flow, indirection potentiellement
    # définie n'importe où dans le fichier) reste hors périmètre de CE round, limite assumée et
    # documentée : la position pertinente pour la comparaison y serait celle de la ligne
    # d'alias racine elle-même, pas celle de la définition de l'ancre référencée — une
    # combinaison non encore rencontrée empiriquement.
    meilleur_trouve: list[str] | None = None
    meilleur_trouve_ligne: int | float | Fraction | None = None

    # Round 32 : `secret` peut être un mapping YAML FLOW entier (accolades) contenant
    # `ignored_paths` en son sein — vérifié AVANT la recherche bloc/flow de `ignored_paths`
    # elle-même, puisque cette forme
    # n'a pas de ligne `ignored_paths:` en tête de ligne du tout.
    offset = 0
    for idx, ligne in enumerate(lignes):
        if idx not in lignes_exclues:
            match_secret_flow = _LIGNE_SECRET_FLOW_OUVERTE.match(ligne)
            if match_secret_flow and _decoder_nom_cle(match_secret_flow, 1, ancres) == "secret":
                absolu = offset + match_secret_flow.end()
                contenu_secret_flow = _trouver_fermeture_flow(texte, absolu, "}")
                fin_accolade = absolu + len(contenu_secret_flow)
                resultat = _resoudre_ignored_paths_dans_mapping_flow(
                    texte, absolu, fin_accolade, ancres
                )
                if resultat is not None and (
                    meilleur_trouve_ligne is None or idx > meilleur_trouve_ligne
                ):
                    meilleur_trouve = resultat
                    meilleur_trouve_ligne = idx
        offset += len(ligne) + 1

    # Round 57 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : la clé `secret` réduite à
    # un alias direct `*cfg` (round 30) ou fusionnée via `<<: *cfg` (round 31/56) peuvent
    # référencer une ancre dont la valeur est un mapping FLOW (round 32) — non couvert par le
    # pré-passage ci-dessus (qui ne cherche `{` qu'après la clé littérale `secret`) ni par
    # `_construire_table_ancres` (qui exclut les ancres-mapping de son périmètre). Réutilise
    # `_trouver_definition_ancre_valide` (round 59 : factorisée de cette même logique, voir sa
    # docstring) pour trouver, pour chaque nom d'ancre dans `noms_alias_racine`, une définition
    # dont la valeur ouvre un mapping flow.
    #
    # Round 70 (bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : quand le nom d'ancre a
    # été découvert via un alias RACINE direct (round 30/55 —
    # `position_alias_racine` connaît alors sa position), le résultat est comparé à
    # `meilleur_trouve_ligne` comme les autres pré-passages (rounds 32/50/67-69), au lieu de
    # `return`er immédiatement — une clé racine DUPLIQUÉE dont la PREMIÈRE occurrence
    # est un tel alias ne doit plus masquer une occurrence ULTÉRIEURE. Round 71 (bug réel trouvé
    # par revue scellée GPT-5.6-Terra-Pro) : `position_alias_racine` couvre désormais AUSSI les
    # noms découverts UNIQUEMENT via une fusion (round 31/56/59/60) — le `return` immédiat
    # ci-dessous ne reste qu'un filet défensif pour une source future qui omettrait encore
    # d'alimenter `position_alias_racine`, plus un cas normalement atteignable avec les sources
    # actuelles.
    if noms_alias_racine:
        offset = 0
        for idx, ligne in enumerate(lignes):
            if idx not in lignes_exclues:
                for m_ancre in _trouver_definition_ancre_valide(ligne):
                    if m_ancre.group(1) not in noms_alias_racine:
                        continue
                    match_suite = _SUITE_ANCRE_FLOW_OUVERTE.match(ligne[m_ancre.end():])
                    if match_suite:
                        absolu = offset + m_ancre.end() + match_suite.end()
                        contenu_ancre_flow = _trouver_fermeture_flow(texte, absolu, "}")
                        fin_accolade = absolu + len(contenu_ancre_flow)
                        resultat = _resoudre_ignored_paths_dans_mapping_flow(
                            texte, absolu, fin_accolade, ancres
                        )
                        if resultat is not None:
                            indice_position = position_alias_racine.get(m_ancre.group(1))
                            if indice_position is None:
                                return resultat
                            if (
                                meilleur_trouve_ligne is None
                                or indice_position > meilleur_trouve_ligne
                            ):
                                meilleur_trouve = resultat
                                meilleur_trouve_ligne = indice_position
            offset += len(ligne) + 1

    # Round 50 : la clé racine explicite (round 49) peut porter une valeur MAPPING FLOW inline
    # après son séparateur `:` — symétrique au pré-passage ci-dessus pour la forme bloc classique.
    for idx, ligne in enumerate(lignes):
        if idx in lignes_exclues:
            continue
        match_cle_explicite_racine = _LIGNE_CLE_EXPLICITE.match(ligne)
        if not (
            match_cle_explicite_racine
            and len(match_cle_explicite_racine.group(1)) == 0
            and _decoder_nom_cle(match_cle_explicite_racine, 2, ancres) == "secret"
        ):
            continue
        j = idx + 1
        while j < len(lignes) and (not lignes[j].strip() or lignes[j].strip().startswith("#")):
            j += 1
        if j >= len(lignes):
            continue
        match_valeur_secret_flow = _LIGNE_VALEUR_EXPLICITE_SECRET_FLOW_OUVERTE.match(lignes[j])
        if not match_valeur_secret_flow or len(match_valeur_secret_flow.group(1)) != 0:
            continue
        absolu = _position_debut_ligne(lignes, j) + match_valeur_secret_flow.end()
        contenu_secret_flow = _trouver_fermeture_flow(texte, absolu, "}")
        fin_accolade = absolu + len(contenu_secret_flow)
        resultat = _resoudre_ignored_paths_dans_mapping_flow(texte, absolu, fin_accolade, ancres)
        if resultat is not None and (meilleur_trouve_ligne is None or idx > meilleur_trouve_ligne):
            meilleur_trouve = resultat
            meilleur_trouve_ligne = idx

    # Round 68 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : le correctif
    # round 67 (« dernière occurrence gagne ») ne couvrait que les formes traitées PAR la
    # boucle principale (alias, explicite, bloc) — ce pré-passage, dédié à la forme `ignored_paths:
    # [...]` (valeur FLOW inline pour une clé autrement en syntaxe bloc, rounds 12/17),
    # `return`ait toujours immédiatement sur son premier candidat, AVANT même que la boucle
    # principale n'ait la moindre chance d'examiner une occurrence ULTÉRIEURE en forme bloc.
    # `meilleur_trouve`/`meilleur_trouve_ligne` (déclarés plus haut depuis le round 69, avant
    # TOUS les pré-passages) sont partagés par l'ensemble des mécanismes — chaque candidat
    # valide, où qu'il soit trouvé, n'écrase le résultat mémorisé QUE s'il est textuellement
    # PLUS TARDIF (comparaison explicite de numéro de ligne), jamais par simple ordre
    # d'exécution du code.
    offset = 0
    for idx, ligne in enumerate(lignes):
        if idx not in lignes_exclues:
            match_flow_ouverte = _LIGNE_CLE_FLOW_OUVERTE.match(ligne)
            if match_flow_ouverte and _decoder_nom_cle(match_flow_ouverte, 2, ancres) == "ignored_paths":
                position = _est_descendante_de_secret(
                    texte, lignes, idx, len(match_flow_ouverte.group(1)), position_alias_racine, ancres
                )
                if position is not None:
                    absolu = offset + match_flow_ouverte.end()
                    contenu_flow = _trouver_fermeture_flow(texte, absolu)
                    candidat = [
                        _resoudre_jeton_item(jeton, ancres)
                        for jeton in _decouper_liste_flow(contenu_flow)
                    ]
                    if meilleur_trouve_ligne is None or position > meilleur_trouve_ligne:
                        meilleur_trouve = candidat
                        meilleur_trouve_ligne = position
        offset += len(ligne) + 1

    indentation_cle: int | None = None
    dans_la_liste = False
    indice_cle_courante: int | float | Fraction | None = None
    # Round 67 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : YAML (PyYAML,
    # vérifié empiriquement) accepte silencieusement une clé `ignored_paths` DUPLIQUÉE au sein
    # du même mapping `secret` — la DERNIÈRE occurrence l'emporte, jamais une erreur. La boucle
    # ci-dessous retournait immédiatement sur la PREMIÈRE occurrence trouvée (toutes formes :
    # alias, explicite, bloc), laissant une seconde occurrence — pourtant sémantiquement
    # gagnante — jamais examinée. `meilleur_trouve`/`meilleur_trouve_ligne` (déclarés plus haut,
    # round 68 : partagés avec le pré-passage flow ci-dessus) mémorisent le résultat de la
    # DERNIÈRE occurrence valide rencontrée, comparée par POSITION DE LIGNE, pas par ordre
    # d'exécution ; plus aucune branche ne `return` directement, chacune avance `i` et
    # `continue` pour laisser la recherche se poursuivre jusqu'à la fin du document.
    i = 0

    while i < len(lignes):
        ligne = lignes[i]
        if not dans_la_liste:
            match_cle_alias = _LIGNE_CLE_ALIAS.match(ligne)
            position_alias = None
            if (
                match_cle_alias
                and _decoder_nom_cle(match_cle_alias, 2, ancres) == "ignored_paths"
                and i not in lignes_exclues
            ):
                position_alias = _est_descendante_de_secret(
                    texte, lignes, i, len(match_cle_alias.group(1)), position_alias_racine, ancres
                )
            if position_alias is not None:
                valeur_ancree = ancres.get(match_cle_alias.group(5), "*" + match_cle_alias.group(5))
                if meilleur_trouve_ligne is None or position_alias > meilleur_trouve_ligne:
                    meilleur_trouve = (
                        valeur_ancree if isinstance(valeur_ancree, list) else [valeur_ancree]
                    )
                    meilleur_trouve_ligne = position_alias
                i += 1
                continue
            match_cle_explicite = _LIGNE_CLE_EXPLICITE.match(ligne)
            indentation_explicite = None
            nom_cle_explicite = None
            j_apres_cle = None
            if match_cle_explicite:
                indentation_explicite = len(match_cle_explicite.group(1))
                nom_cle_explicite = _decoder_nom_cle(match_cle_explicite, 2, ancres)
                j_apres_cle = i + 1
            if nom_cle_explicite != "ignored_paths" and i not in lignes_exclues:
                # Round 58 : essaie la résolution multiligne dès que le match sur une seule
                # ligne n'a PAS déjà résolu en `ignored_paths` — couvre à la fois l'absence de
                # match ET un match de REPLI erroné (round 58, bug trouvé PROACTIVEMENT en
                # vérifiant ce correctif : un guillemet non refermé, faute d'alternative
                # guillemetée valide sur la même ligne, est engouffré par l'alternative NUE de
                # `_NOM_CLE_QUELCONQUE` — `[^\s:#][^:#]*?` n'exclut pas `"` en tête, contrairement
                # à `ns-plain-first` du spec YAML — produisant un `match_cle_explicite` VÉRITÉ
                # mais dont le nom décodé est le texte brut tronqué, jamais `ignored_paths`).
                # `_decoder_cle_explicite_multiligne` est sans effet de bord si la ligne ne
                # correspond pas à son cas précis (retourne None).
                resultat_multiligne = _decoder_cle_explicite_multiligne(texte, lignes, i)
                if resultat_multiligne:
                    nom_cle_explicite, indice_derniere_ligne_cle = resultat_multiligne
                    indentation_explicite = len(ligne) - len(ligne.lstrip(" "))
                    j_apres_cle = indice_derniere_ligne_cle + 1
            position_explicite = None
            if nom_cle_explicite == "ignored_paths" and i not in lignes_exclues:
                position_explicite = _est_descendante_de_secret(
                    texte, lignes, i, indentation_explicite, position_alias_racine, ancres
                )
            if position_explicite is not None:
                j = j_apres_cle
                while j < len(lignes) and (
                    not lignes[j].strip() or lignes[j].strip().startswith("#")
                ):
                    j += 1
                if j < len(lignes):
                    ligne_valeur = lignes[j]
                    match_valeur_alias = _LIGNE_VALEUR_EXPLICITE_ALIAS.match(ligne_valeur)
                    if match_valeur_alias and len(match_valeur_alias.group(1)) == indentation_explicite:
                        valeur_ancree = ancres.get(
                            match_valeur_alias.group(2), "*" + match_valeur_alias.group(2)
                        )
                        if meilleur_trouve_ligne is None or position_explicite > meilleur_trouve_ligne:
                            meilleur_trouve = (
                                valeur_ancree if isinstance(valeur_ancree, list) else [valeur_ancree]
                            )
                            meilleur_trouve_ligne = position_explicite
                        i = j + 1
                        continue
                    match_valeur_flow = _LIGNE_VALEUR_EXPLICITE_FLOW_OUVERTE.match(ligne_valeur)
                    if match_valeur_flow and len(match_valeur_flow.group(1)) == indentation_explicite:
                        absolu = _position_debut_ligne(lignes, j) + match_valeur_flow.end()
                        contenu = _trouver_fermeture_flow(texte, absolu, "]")
                        if meilleur_trouve_ligne is None or position_explicite > meilleur_trouve_ligne:
                            meilleur_trouve = [
                                _resoudre_jeton_item(t, ancres) for t in _decouper_liste_flow(contenu)
                            ]
                            meilleur_trouve_ligne = position_explicite
                        sauts_ligne = texte.count("\n", absolu, absolu + len(contenu) + 1)
                        i = j + sauts_ligne + 1
                        continue
                    match_valeur_explicite = _LIGNE_VALEUR_EXPLICITE.match(ligne_valeur)
                    if match_valeur_explicite and len(match_valeur_explicite.group(1)) == indentation_explicite:
                        indentation_cle = indentation_explicite
                        indice_cle_courante = position_explicite
                        dans_la_liste = True
                        i = j + 1
                        continue
                i += 1
                continue
            match_cle = _LIGNE_CLE.match(ligne)
            position_bloc = None
            if (
                match_cle
                and _decoder_nom_cle(match_cle, 2, ancres) == "ignored_paths"
                and i not in lignes_exclues
            ):
                position_bloc = _est_descendante_de_secret(
                    texte, lignes, i, len(match_cle.group(1)), position_alias_racine, ancres
                )
            if position_bloc is not None:
                indentation_cle = len(match_cle.group(1))
                indice_cle_courante = position_bloc
                dans_la_liste = True
            i += 1
            continue

        ligne_nue = ligne.strip()
        if not ligne_nue or ligne_nue.startswith("#"):
            i += 1
            continue

        match_bloc = _LIGNE_ITEM_BLOC.match(ligne)
        if match_bloc and len(match_bloc.group(1)) > (indentation_cle or 0):
            valeur, i = _consommer_scalaire_bloc(lignes, i + 1, len(match_bloc.group(1)))
            chemins.append(valeur)
            continue

        match_alias = _LIGNE_ITEM_ALIAS.match(ligne)
        if match_alias and len(match_alias.group(1)) > (indentation_cle or 0):
            valeur_ancree = ancres.get(match_alias.group(2), "*" + match_alias.group(2))
            if isinstance(valeur_ancree, list):
                chemins.extend(valeur_ancree)
            else:
                chemins.append(valeur_ancree)
            i += 1
            continue

        match_item = _LIGNE_ITEM.match(ligne)
        if match_item and len(match_item.group(1)) > (indentation_cle or 0):
            valeur_double = match_item.group(2)
            if valeur_double is not None:
                valeur = _decoder_echappements_yaml(valeur_double)
            else:
                valeur = match_item.group(3)
                if valeur is None:
                    valeur = match_item.group(4)
            chemins.append(valeur)
            i += 1
            continue

        # Ligne non-item (ou moins indentée) : fin de la liste ignored_paths COURANTE — round 67 :
        # ne PAS retourner immédiatement, une clé `ignored_paths` DUPLIQUÉE plus loin doit
        # l'emporter (dernière clé gagne, vérifié empiriquement contre PyYAML). Mémorise cette
        # liste comme meilleur résultat connu (round 68 : comparée par position de ligne de sa
        # CLÉ — `indice_cle_courante` — au pré-passage flow, pas par simple ordre d'exécution),
        # réinitialise l'état d'accumulation, et laisse la boucle RE-EXAMINER la ligne courante
        # (`i` inchangé) au cas où elle serait elle-même une NOUVELLE clé `ignored_paths` —
        # `dans_la_liste` redevient False, donc la prochaine itération retombe naturellement
        # dans la branche de détection de clé ci-dessus.
        if meilleur_trouve_ligne is None or indice_cle_courante > meilleur_trouve_ligne:
            meilleur_trouve = chemins
            meilleur_trouve_ligne = indice_cle_courante
        chemins = []
        dans_la_liste = False
        indentation_cle = None
        indice_cle_courante = None

    if dans_la_liste:
        # La dernière liste rencontrée n'a jamais été refermée par une ligne non-item — le
        # document s'est terminé en plein milieu de son accumulation. Ses items sont le
        # résultat le plus RÉCENT trouvé (textuellement après tout `meilleur_trouve`
        # antérieur), donc gagnant.
        return chemins
    return meilleur_trouve if meilleur_trouve is not None else []


# Round 78 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : rounds 73/77
# avaient tous deux tenté de couvrir « toute syntaxe de glob qui exclut tout le Markdown » par
# une liste FINIE de chaînes littérales reconnues — round 73 a réfuté une classe de motifs
# (classes de caractères, non supportées par GitGuardian), round 77 en a ajouté 4 de plus
# (formes « exclure tout le dépôt »), et CE round en trouve encore un AUTRE, `**/*.m*`, qui
# utilise UNIQUEMENT les deux vrais méta-caractères de GitGuardian (`*`/`**/`, contrairement à
# round 73) et matche pourtant bien tout fichier `.md` réel (vérifié contre le moteur
# `ggshield.core.filter`, venv scratch). Le nombre de motifs `*`/`**/`-uniquement qui matchent
# TOUT `.md` du dépôt est en pratique NON BORNÉ (`**/*.m*`, `**/*.*d`, `**/*.*`, `**/*md*`, …) —
# continuer à en ajouter un par un à une liste littérale rejouerait indéfiniment ce même
# scénario à chaque round. Remplacé par une approche COMPUTATIONNELLE : plutôt que de
# reconnaître des CHAÎNES précises, `_traduire_pattern_glob_ggshield()` VENDORISE fidèlement
# l'algorithme RÉEL de traduction glob→regex de `ggshield.core.filter.translate_user_pattern()`
# (lu et vérifié ligne à ligne dans le venv scratch — reproduction, PAS une dépendance
# `ggshield` au runtime, ce outil restant absent de `dependencies=[]` du produit) ;
# `est_exclusion_markdown_globale()` compile ce regex et teste s'il matche la TOTALITÉ d'un
# échantillon représentatif de chemins Markdown plausibles (racine, sous-dossiers, noms variés)
# — un motif qui matche l'échantillon ENTIER est traité comme excluant tout le Markdown, qu'il
# s'agisse d'une chaîne déjà connue ou d'une construction glob inédite. Vérifié que cette
# approche retrouve EXACTEMENT les mêmes verdicts que les rounds 73/77 sur leurs cas déjà
# testés (voir `test_gitguardian_yaml_reel_du_depot_toujours_conforme_apres_round78` et les
# tests dédiés), sans lister explicitement `**/*.md`/`*.md`/`*`/`**`/`**/*`/`**/**` : ces six
# formes ressortent naturellement de l'algorithme général, comme toute construction future
# utilisant les deux mêmes méta-caractères et couvrant le même échantillon.
_CARACTERES_SPECIAUX_GLOB_GGSHIELD = frozenset(".^$+*?{}()[]\\|")
_MOTIF_GLOB_INVALIDE_GGSHIELD = re.compile(
    r"(\*\*\*)"  # la séquence "***" n'est jamais valide
    r"|(\*\*[^/])"  # une séquence "**" doit être immédiatement suivie de "/"
    r"|([^/]\*\*)"  # une séquence "**" doit être en tête ou immédiatement précédée de "/"
)
_ECHANTILLON_CHEMINS_MARKDOWN = (
    "a.md",
    "foo.md",
    "stories/bar.md",
    "evidence/reviews/x.md",
    "a/b/c/d.md",
    "quelque-chose_de.long.md",
)


def _pattern_glob_ggshield_valide(pattern: str) -> bool:
    """Vendorisation fidèle de `ggshield.core.filter.is_pattern_valid()` — round 78."""
    return bool(pattern) and not _MOTIF_GLOB_INVALIDE_GGSHIELD.search(pattern)


def _traduire_pattern_glob_ggshield(pattern: str) -> str:
    """Vendorisation fidèle de `ggshield.core.filter.translate_user_pattern()` — round 78. Ne
    modifie AUCUNE des règles observées dans le code source réel (venv scratch) : échappe tout
    méta-caractère regex, puis substitue spécifiquement `**/` et `*` en motifs de dossiers/nom
    de fichier, avec les mêmes ancrages `(^|/)`/`$`/`^`."""
    traduit = "".join(
        f"\\{c}" if c in _CARACTERES_SPECIAUX_GLOB_GGSHIELD else c for c in pattern
    )
    if traduit[-1] != "/":
        traduit += "$"
    if traduit[0] == "/":
        traduit = "^" + traduit[1:]
    else:
        traduit = "(^|/)" + traduit
    traduit = re.sub(r"\\\*\\\*/", "([^/]+/)*", traduit)
    traduit = re.sub(r"\\\*", "([^/]+)", traduit)
    return traduit


def est_exclusion_markdown_globale(chemin: str) -> bool:
    """True si `chemin` exclut TOUS les fichiers Markdown du dépôt (motif interdit).

    Round 78 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : rounds 1-77
    reconnaissaient une liste FINIE de chaînes littérales (`**/*.md`, `*.md`, puis `*`, `**`,
    `**/*`, `**/**` au round 77) — approche condamnée à rater toute NOUVELLE construction glob
    valide (`**/*.m*`, exemple réel du reviewer). Traduit désormais `chemin` en regex via
    `_traduire_pattern_glob_ggshield()` (vendorisation fidèle du moteur RÉEL de GitGuardian) et
    teste s'il matche la TOTALITÉ de `_ECHANTILLON_CHEMINS_MARKDOWN` (racine, sous-dossiers
    variés) — un glob borné à un sous-arbre précis (`evidence/reviews/**/*.md`) ou un chemin de
    fixture individuel (`tests/fixtures/exemple.md`) ne matche jamais TOUT l'échantillon (au
    moins un chemin hors de son sous-arbre lui échappe), donc reste correctement `False`.
    """
    if not chemin or not _pattern_glob_ggshield_valide(chemin):
        return False
    try:
        regex = re.compile(_traduire_pattern_glob_ggshield(chemin))
    except re.error:
        return False
    return all(regex.search(c) for c in _ECHANTILLON_CHEMINS_MARKDOWN)


def _lignes_dans_bloc_secret_racine(
    texte: str, ancres: dict[str, str | list[str]]
) -> list[bool] | None:
    """Pour chaque ligne physique de `texte`, indique si elle appartient à la session du
    mapping racine `secret` — round 89 (RC1-015, correctif réel du finding round 87/89, revue
    scellée GPT-5.6-Terra-Pro). Retourne `None` si cette session ne peut PAS être délimitée de
    façon fiable par les 2 formes SIMPLES (bloc littéral, flow-ouvert) : racine `secret` fournie
    par ALIAS (`secret: *cfg`  <!-- proof:allow : exemple prose --> — le contenu réel vit ailleurs, potentiellement AVANT cette ligne,
    hors de portée d'un balayage à sens unique) ou toute clé racine en forme EXPLICITE
    (`? nom\\n:` — nom potentiellement `secret`, résolution non dupliquée ici). Dans ces deux cas
    l'appelant DOIT se rabattre sur le balayage INTÉGRAL (comportement d'avant round 89, jamais
    moins couvrant que lui).

    Une nouvelle SESSION de clé racine démarre à une ligne dont la profondeur flow
    (`_profondeurs_flow`) est 0 EN DÉBUT DE LIGNE ET dont l'indentation est 0 — une ligne de
    CONTINUATION flow non indentée (round 87, YAML valide :
    `secret: {\\nignored_paths: [...]\\n}`)  <!-- proof:allow : exemple prose --> a une profondeur > 0 à son début et n'est donc
    jamais confondue avec une nouvelle clé racine (le contre-exemple du round 87 reste
    correctement couvert : sa ligne de continuation hérite de la session `secret` en cours).
    """
    lignes = texte.splitlines(keepends=False)
    spans_exclus = _spans_exclus_recherche_cle(texte)
    profondeurs = _profondeurs_flow(texte, spans_exclus)

    resultat = [False] * len(lignes)
    dans_secret = False  # proof:allow — identifiant de variable, pas un secret réel
    offset = 0
    for i, ligne in enumerate(lignes):
        profondeur_ici = profondeurs[offset]
        nue = ligne.strip()
        est_ligne_racine_candidate = profondeur_ici == 0 and ligne[:1] not in ("", " ", "\t")
        if est_ligne_racine_candidate and nue and not nue.startswith("#"):
            if _LIGNE_CLE_EXPLICITE.match(ligne):
                return None
            m = _LIGNE_SECRET_ALIAS.match(ligne)
            if m and _decoder_nom_cle(m, 1, ancres) == "secret":
                return None
            m = _LIGNE_CLE_SECRET.match(ligne)
            if m and _decoder_nom_cle(m, 1, ancres) == "secret":
                dans_secret = True  # proof:allow — identifiant de variable, pas un secret réel
            else:
                m = _LIGNE_SECRET_FLOW_OUVERTE.match(ligne)
                dans_secret = bool(m and _decoder_nom_cle(m, 1, ancres) == "secret")  # proof:allow — identifiant de variable
        resultat[i] = dans_secret
        offset += len(ligne) + 1
    return resultat


def _chaines_guillemetees_decodees(
    texte: str, ancres: dict[str, str | list[str]] | None = None
) -> list[str]:
    """Toutes les chaînes guillemetées (simples ou doubles) du texte brut, valeurs décodées.

    Sert de filet pour toute forme non couverte par l'analyseur structurel (ex. syntaxe YAML
    "flow" `ignored_paths: ["**/*.md"]`). Guillemets doubles : échappements décodés (voir
    `_decoder_echappements_yaml`). Guillemets simples : YAML n'y support aucun échappement,
    valeur retournée telle quelle.

    Round 84 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro) : exclut désormais
    les chaînes guillemetées situées À L'INTÉRIEUR d'un COMMENTAIRE (`_spans_commentaires`,
    round 38). Un commentaire documentaire (`# exemple "**/*.md"`) n'est JAMAIS une donnée YAML
    active pour AUCUN parseur conforme — l'exclure ne réduit donc PAS la couverture réelle du
    filet (aucune exclusion active ne peut être « cachée » dans un commentaire, par définition
    de la syntaxe YAML), mais évite un FAUX POSITIF qui bloquerait à tort un
    `.gitguardian.yaml` par ailleurs parfaitement conforme (`secret.ignored_paths` sans aucune
    exclusion globale) simplement parce qu'un commentaire cite le motif interdit à titre
    d'exemple. Vérifié empiriquement.

    Round 87 (RC1-015, revue scellée GPT-5.6-Terra-Pro, MINEURE, non bloquante) : finding
    correctement reproduit — ce filet balaie TOUT le texte, y compris des clés racine sans
    aucun rapport avec `secret.ignored_paths` (ex. `note: "**/*.md"`). Une piste de correctif
    naïve (exclure toute ligne à indentation ZÉRO qui n'est pas la clé racine `secret`) a été
    ÉVALUÉE puis ÉCARTÉE avec preuve empirique : une forme YAML flow valide place une ligne de
    CONTINUATION à indentation ZÉRO tout en restant un vrai descendant de la clé racine
    (`yaml.safe_load` confirmé) — cette piste aurait donc créé un FAUX NÉGATIF.

    Round 89 (RC1-015, MÊME finding reproduit une 2e fois sans preuve nouvelle, revue scellée
    GPT-5.6-Terra-Pro) : correctif RÉEL apporté via `_lignes_dans_bloc_secret_racine` (round 89)
    — qui suit la profondeur flow (`_profondeurs_flow`, déjà robuste depuis le round 35) plutôt
    que la seule indentation, donc N'EST PAS exposé au contre-exemple du round 87 (la ligne de
    continuation `ignored_paths: [...]` a une profondeur flow > 0 à son début, jamais confondue
    avec une nouvelle clé racine). Quand `ancres` est fourni ET que la session du mapping racine
    `secret` est délimitable SANS AMBIGUÏTÉ (formes bloc/flow-ouvert simples), le filet ne
    considère plus que les chaînes de CETTE session — sinon (racine par alias, forme explicite,
    ou `ancres` non fourni), repli INCHANGÉ sur le balayage intégral (couverture jamais réduite
    dans les cas ambigus).

    Round 115 (RC1-015, bug réel trouvé par revue scellée GPT-5.6-Terra-Pro, MINEURE, non
    bloquante — même famille que round 87/89, nouveau symptôme) : même en restreignant à la
    session `secret`, ce filet ne filtrait pas le CONTENU d'un scalaire bloc SANS RAPPORT avec
    `ignored_paths` mais SITUÉ SOUS `secret` (ex. `secret.note: |\n  "**/*.md"` — texte littéral
    documentaire, pas une chaîne YAML active). Repro confirmée AVANT correctif : `verifier()`
    retournait à tort `(False, ['**/*.md'])` pour un fichier dont `secret.ignored_paths` ne
    contient AUCUNE exclusion Markdown. Un scalaire bloc n'est JAMAIS re-parsé par YAML (son
    contenu est un texte littéral opaque, y compris tout caractère `"`/`'` qu'il porte) — exclure
    ces lignes du filet ne peut donc jamais masquer une exclusion RÉELLE (le round 108 a déjà
    établi qu'un scalaire bloc porté DIRECTEMENT par `ignored_paths` n'est de toute façon jamais
    une liste fonctionnelle ; un scalaire bloc porté par un AUTRE item de liste PASSE par
    l'analyseur structurel dédié, pas par ce filet textuel). Réutilise `_lignes_contenu_bloc`
    (déjà utilisée ailleurs, round 44+, pour exactement cette classification) — appliquée
    INCONDITIONNELLEMENT (indépendamment de `ancres`), la propriété « un scalaire bloc n'est
    jamais re-parsé » étant vraie quelle que soit la délimitation de la session `secret`.
    """
    spans_guillemets = _spans_guillemets(texte)
    spans_commentaires = _spans_commentaires(texte, spans_guillemets)
    lignes_dans_secret = (  # proof:allow — identifiant de variable, pas un secret réel
        _lignes_dans_bloc_secret_racine(texte, ancres) if ancres is not None else None
    )
    lignes_contenu_bloc = _lignes_contenu_bloc(texte.splitlines())

    def _garder(m: re.Match) -> bool:
        if any(g_debut <= m.start() < g_fin for g_debut, g_fin in spans_commentaires):
            return False
        indice_ligne = texte.count("\n", 0, m.start())
        if indice_ligne in lignes_contenu_bloc:
            return False
        if lignes_dans_secret is None:
            return True
        return lignes_dans_secret[indice_ligne]

    resultats = [
        _decoder_echappements_yaml(m.group(1))
        for m in _CHAINE_DOUBLE_GUILLEMETS.finditer(texte)
        if _garder(m)
    ]
    resultats += [m.group(1) for m in _CHAINE_SIMPLE_GUILLEMETS.finditer(texte) if _garder(m)]
    return resultats


def verifier(fichier: Path) -> tuple[bool, list[str]]:
    """Vérifie `fichier` : retourne (conforme, [motifs interdits trouvés]).

    Deux couches indépendantes, la seconde en filet de sécurité de la première : après plusieurs
    lacunes réelles de l'analyseur structurel trouvées par revue scellée (RC1-015 rounds 1/5/6 —
    commentaire sur la ligne clé, commentaire sur un item, ligne vide/commentaire seul entre
    items ; round 7 — échappement YAML `\\uNNNN` d'un `.` non décodé ; round 8 — scalaire bloc
    `- >-`/`- |` dont le contenu vit sur la ligne suivante, désormais consommé par
    `parser_ignored_paths` ; round 12 — syntaxe flow `[...]` et alias `*nom` résolus via une
    table d'ancres construite sur l'intégralité du fichier, désormais couverts par
    `parser_ignored_paths` elle-même), la conformité ne doit JAMAIS reposer uniquement sur le
    succès du parsing structurel. Un balayage de TOUTES les chaînes guillemetées du texte brut
    (décodées pour les échappements `\\uNNNN`/`\\xNN` des guillemets doubles), comparées à
    `est_exclusion_markdown_globale()`, détecte en plus toute forme non couverte par l'analyseur
    structurel (échappement Unicode/hex du séparateur `.`, continuation de ligne échappée) — les
    scalaires bloc et les alias, intrinsèquement non guillemetés, ne peuvent PAS être couverts
    par ce filet textuel et exigent donc un traitement structurel correct en amont (voir
    `_consommer_scalaire_bloc`, `_construire_table_ancres`).

    Round 89 (RC1-015) : construit désormais sa propre table d'ancres (identique à celle de
    `parser_ignored_paths`) et la transmet à `_chaines_guillemetees_decodees` — quand la session
    du mapping racine `secret` est délimitable sans ambiguïté, le filet se restreint à cette
    session (précision accrue) ; sinon, repli automatique et INCHANGÉ sur le balayage intégral
    (couverture jamais réduite). Voir `_lignes_dans_bloc_secret_racine`.
    """
    chemins = parser_ignored_paths(fichier)
    motifs_interdits = [c for c in chemins if est_exclusion_markdown_globale(c)]
    if motifs_interdits:
        return (False, motifs_interdits)

    # SonarCloud pythonsecurity:S8707 (round 117, #445) : même idiome que
    # `parser_ignored_paths` ci-dessus — validé explicitement à CE site d'appel, l'analyse de
    # flux de Sonar ne créditant pas la validation déjà effectuée par l'appel précédent.
    if not fichier.is_file():
        raise ValueError(f"fichier introuvable ou n'est pas un fichier régulier : {str(fichier)!r}")
    texte = fichier.read_text(encoding="utf-8")
    lignes = texte.splitlines()
    ancres = _construire_table_ancres(texte, lignes, _lignes_contenu_bloc(lignes))
    trouvailles_brutes = sorted({
        c
        for c in _chaines_guillemetees_decodees(texte, ancres)
        if est_exclusion_markdown_globale(c)
    })
    if trouvailles_brutes:
        return (False, trouvailles_brutes)

    return (True, [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--fichier",
        default=str(Path(__file__).resolve().parent.parent.parent / ".gitguardian.yaml"),
        help="chemin du fichier .gitguardian.yaml à vérifier",
    )
    args = ap.parse_args(argv)

    fichier = Path(args.fichier)
    if not fichier.is_file():
        print(f"check_gitguardian_scope : fichier introuvable : {fichier}", file=sys.stderr)
        return 2

    ok, motifs = verifier(fichier)
    if ok:
        print(f"check_gitguardian_scope : OK ({fichier}, aucune exclusion Markdown globale)")
        return 0

    print(f"check_gitguardian_scope : exclusion(s) Markdown globale(s) interdite(s) dans {fichier}")
    for motif in motifs:
        print(f"  - {motif!r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
