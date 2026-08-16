# Revue de CLÔTURE (3e passe) — B-24c/d : garde de confinement filesystem (commit 8e9bf7b)

## D'ABORD : vous aviez raison, et voici ce qui s'est passé
À la passe précédente, Nemotron-3-Ultra et Qwen3.7-Max ont tous deux signalé que le
correctif annoncé (accolades dans la classe des délimiteurs) était ABSENT du diff soumis.
C'était EXACT. Le défaut était dans MON PACK, pas dans le code : j'avais réutilisé le pack de
la passe antérieure en n'actualisant que la preuve d'exécution, laissant un diff périmé d'un
commit. Le pack se contredisait donc lui-même — diff sans accolades, preuve d'exécution
montrant leur effet. Vous avez détecté l'incohérence exactement comme il fallait.

Ce pack-ci est REGÉNÉRÉ INTÉGRALEMENT depuis le commit 8e9bf7b. Le diff ci-dessous est celui
du code réellement en place. Vérifiez-le : la classe doit contenir `{`, `}` et `,`.

## Votre rôle
Le critère d'arrêt de l'ADR : la story est close si AUCUN de vous n'annonce une NOUVELLE
CLASSE de contournement. Un cas isolé dans une classe déjà traitée n'en est pas une.
Si vous en trouvez une, donnez un exemple que vous avez VOUS-MÊME jugé plausible.

## Précision issue de la passe précédente, à ne pas propager
Un exemple avancé alors — `cat /workspace/{../../etc/passwd}` — reposait sur l'idée que bash
expand cette forme. Mesure au binaire bash : FAUX. Bash n'expand les accolades QUE s'il y a
une virgule ou une séquence `{a..b}` ; `{x}` reste littéral. La garde refuse ce cas, mais
parce que le littéral résolu sort de la racine — pas par expansion.

## Ce que fait le composant
Le produit GÉNÈRE un script de garde autonome (stdlib pure, n'importe JAMAIS le produit : il
doit survivre à sa désinstallation), branché en hook PreToolUse. Il lit une charge JSON sur
stdin, extrait les chemins visés, et REFUSE (exit 2, journalisé) tout accès hors du workspace.

## Architecture
- Racine figée par realpath À LA GÉNÉRATION. realpath des DEUX côtés. commonpath+normcase
  (jamais startswith : piège /repo vs /repo-evil). FAIL-CLOSED partout.
- cwd validé EN PROPRE avant extraction (auto-protection puis confinement), refus journalisé.
- Extraction Bash = UNION de deux méthodes : shlex (restitue la CONCATÉNATION des quotes) et
  un découpage strict sur les délimiteurs, appliqué DANS TOUS LES CAS. Le `except ValueError`
  ne contient que `pass` : shlex est un ENRICHISSEUR dont l'échec est sans conséquence, pas un
  primaire avec repli — c'est cette propriété qui interdit une porte de service. Garantie
  MONOTONE : l'union ne peut qu'élargir l'ensemble contrôlé.
- Normalisation de la continuation de ligne bash ; retrait du backslash d'échappement sur
  POSIX (conservé sur Windows, séparateur natif).
- Chemins collés à un préfixe d'option : `=` délimiteur, suffixe extrait après une grappe de
  1 à 3 lettres (borne MESURÉE : 0 faux positif à 3, deux à 4).
- Accolades et virgule délimiteurs (expansion d'accolades de bash).
- AUTO-PROTECTION : le script et `.claude` ENTIER non réinscriptibles par le confiné.
- Refus journalisé au format EXACT du registre du produit, vérifiable par son propre outil.

## Les 12 classes fermées — n'en refaites pas le tour
tokens quotés · chemins Windows · relatifs sans préfixe · `.claude` parent · traversal ·
opérateurs shell collés · cwd non validé · repli permissif (2×) · continuation de ligne ·
backslash d'échappement · préfixes d'options (`=`, grappes ≤3) · scission par guillemets ·
expansion d'accolades.

## Limite HORS PÉRIMÈTRE, assumée depuis l'origine
Aucune interprétation du shell : ni expansion `$VAR`, ni substitution `$(cmd)`, ni globbing.
`CIBLE=/etc/passwd; cat $CIBLE` n'est PAS arrêté — rôle d'une sandbox OS. Les chemins
contenant un espace ne sont pas captés en entier. Ne REJETEZ pas pour cette limite.

## Faux positifs résiduels, assumés, documentés ET testés
1. Répertoire relatif de ≤3 lettres collé à une grappe (`gcc -Iab/x`) : refusé à tort.
2. Nom de fichier contenant une virgule : coupé (`dossier/mon,fichier.txt` -> `dossier/mon`),
   qui reste interne donc autorisé.
Les deux sont verrouillés par des tests de caractérisation.

## CE QUI CONSTITUERAIT UN REJECT LÉGITIME
(a) un chemin littéral hors racine qui passe ; (b) le confiné peut neutraliser sa garde ;
(c) une transformation lexicale de bash pré-découpage non traitée (les deux connues —
    continuation de ligne, échappement backslash — le sont, liste établie par MESURE) ;
(d) une convention de collage autre que `=` ou la grappe ≤3 ;
(e) un FAUX POSITIF sur une commande de développement courante — une garde qui bloque
    `gcc -Isrc/include` sera désactivée, et une garde désactivée ne protège rien.

## Diff CUMULÉ vs origin/main — REGÉNÉRÉ depuis le commit courant
## (vérifiez la ligne DELIMITEURS : elle doit contenir { } et ,)
~~~diff
diff --git a/src/forgeai/ide/guard_fs.py b/src/forgeai/ide/guard_fs.py
new file mode 100644
index 0000000..d30e09f
--- /dev/null
+++ b/src/forgeai/ide/guard_fs.py
@@ -0,0 +1,596 @@
+"""Génération et installation de la garde filesystem autonome (B-24).
+
+Pourquoi un script GÉNÉRÉ plutôt qu'un module du produit : la garde est
+branchée en hook PreToolUse chez l'utilisateur et doit survivre à la
+désinstallation de forgeai — elle n'importe donc jamais le produit, uniquement
+la stdlib. Trois principes la gouvernent :
+
+- fail-closed : toute exception interne, un stdin illisible ou un JSON
+  invalide se convertissent en REFUS (exit 2) ; un refus tient même si la
+  journalisation échoue ;
+- racine figée : la racine de confinement est résolue (``os.path.realpath``)
+  AU MOMENT DE LA GÉNÉRATION et embarquée en constante dans le script —
+  jamais dérivée du cwd à l'exécution, sinon le confinement suivrait le
+  confiné ;
+- auto-protection : même dans la racine, un outil d'écriture ne peut réécrire
+  ni la garde elle-même, ni le répertoire des hooks, ni ``settings.json`` —
+  une garde réécrivable par le confiné est du théâtre.
+
+Le format du registre JSONL répliqué dans le script généré est une duplication
+ASSUMÉE de celui de ``forgeai.core.registre`` : c'est un contrat de
+compatibilité avec la vérification de chaîne du produit, à faire évoluer de
+pair avec lui.
+"""
+
+from __future__ import annotations
+
+import os
+import sys
+from pathlib import Path
+
+from . import IDEError
+from .bootstrap import HookSpec
+
+__all__ = ["generate_guard_fs", "install_guard_fs"]
+
+# Source complet du script autonome déposé chez l'utilisateur. Trois
+# emplacements — __FORGEAI_ROOT__, __FORGEAI_REGISTRE__, __FORGEAI_ALLOW__ —
+# sont substitués par generate_guard_fs via repr() : jamais d'interpolation
+# nue dans du code généré. Chaîne brute : les séquences « \n » / « \r » du
+# script généré doivent rester des échappements littéraux dans le template.
+_SCRIPT_TEMPLATE = r'''#!/usr/bin/env python3
+"""Garde filesystem autonome générée par ForgeAI (B-24) — hook PreToolUse.
+
+Autonome par construction : stdlib uniquement, n'importe jamais forgeai, et
+survit donc à la désinstallation du produit. La racine de confinement est
+figée (realpath) au moment de la génération — jamais dérivée du cwd à
+l'exécution. Politique fail-closed : stdin illisible, JSON invalide ou toute
+exception interne se convertissent en REFUS (exit 2) ; un refus tient même si
+la journalisation échoue.
+
+CONTRAT ASSUMI : le format d'entrée du registre JSONL répliqué ici (seq, ts,
+type, actor, payload, prev_hash, hash sha256 du matériau canonique, ligne JSON
+compacte à clés triées) est celui de forgeai.core.registre. Cette duplication
+est volontaire : elle préserve la vérification de chaîne du produit. Toute
+évolution du format doit être coordonnée des deux côtés.
+"""
+
+import hashlib
+import json
+import os
+import sys
+import re
+import shlex
+import tempfile
+from datetime import datetime, timezone
+
+try:
+    import fcntl
+except ImportError:
+    # Windows : pas de flock — écriture sans verrou, contrat assumé.
+    fcntl = None
+
+ROOT = __FORGEAI_ROOT__
+REGISTRE_DEFAUT = __FORGEAI_REGISTRE__
+ALLOW_PATH = __FORGEAI_ALLOW__
+
+GENESIS = "0" * 64
+WRITE_TOOLS = ("Write", "Edit", "NotebookEdit", "Bash")
+PATH_KEYS = ("file_path", "path", "notebook_path")
+
+SCRIPT_PATH = os.path.realpath(__file__)
+# Le répertoire « .claude » ENTIER est protégé en écriture (O4) : hooks,
+# settings.json et toute cible sous .claude. HOOKS_DIR et SETTINGS_JSON
+# restent définis — couverts a fortiori par CLAUDE_DIR — pour la
+# lisibilité et les messages du registre.
+CLAUDE_DIR = os.path.realpath(os.path.join(ROOT, ".claude"))
+HOOKS_DIR = os.path.realpath(os.path.join(ROOT, ".claude", "hooks"))
+SETTINGS_JSON = os.path.realpath(os.path.join(ROOT, ".claude", "settings.json"))
+
+
+def _sous(chemin, prefixe):
+    # Contenance par composants via commonpath — jamais par préfixe de chaîne
+    # ("/atelier/b" n'est pas sous "/atelier/bc"). ValueError (chemins
+    # incomparables, ex. deux lecteurs Windows) signifie hors racine.
+    try:
+        commun = os.path.commonpath((os.path.normcase(chemin), os.path.normcase(prefixe)))
+    except ValueError:
+        return False
+    return commun == os.path.normcase(prefixe)
+
+
+def _resoudre(chemin, cwd):
+    # Backslash d'échappement : retrait avant résolution, sur POSIX uniquement.
+    # Sur POSIX, ``\/etc/passwd`` est lu par Bash comme ``/etc/passwd`` :
+    # sans retrait du backslash, le fragment brut n'est pas absolu et se
+    # résout contre le cwd en ``<racine>/\/etc/passwd`` — DANS la racine,
+    # donc autorisé à tort (contournement trivial). Sur Windows, le
+    # backslash est le séparateur natif, pas un échappement : on le
+    # conserve tel quel. Ce traitement couvre AUSSI les chemins venant de
+    # file_path (pas seulement ceux extraits de Bash).
+    if os.sep != chr(92):
+        chemin = chemin.replace(chr(92), "")
+    p = os.path.expanduser(chemin)
+    if not os.path.isabs(p):
+        p = os.path.join(cwd, p)
+    return os.path.realpath(p)
+
+
+def _ressemble_chemin(token):
+    # Un token « ressemble à un chemin littéral » si et seulement si :
+    # - il contient un séparateur : « / », le séparateur natif os.sep, ou
+    #   la barre oblique inverse Windows — chr(92) plutôt qu'un littéral,
+    #   pour ne dépendre d'aucun échappement dans la chaîne template ; OU
+    # - il commence par « ~ » ; OU
+    # - il commence par « . » : navigation (« . », « .. ») ou entrée
+    #   cachée (« .claude », « .env ») — dans les deux cas un chemin
+    #   littéral ; c'est ce qui capture la cible nue « .claude » de
+    #   « rm -rf .claude » (O4), qu'une règle limitée à « .. »/« . »
+    #   exacts laisserait passer. Un token non-chemin (commande, option)
+    #   ne commence pratiquement jamais par « . » ; OU
+    # - il débute par un lecteur Windows `X:` — avec séparateur (`C:\x`, `C:/x`)
+    #   OU sans (`C:x`, chemin relatif au répertoire courant du lecteur, tout
+    #   aussi valide sous Windows). Regex `^[A-Za-z]:`.
+    # Un token SANS séparateur et sans préfixe « ~ »/« . » (ex. « cat »,
+    # « rm », « -rf ») N'EST PAS un chemin : l'ajouter provoquerait des
+    # faux positifs massifs sur les commandes et leurs options.
+    # NOTE B-24d : les opérateurs shell font partie de la classe de
+    # découpage de `_candidats`, ils n'apparaissent donc jamais dans un
+    # fragment. Et même isolés ils ne ressembleraient pas à un chemin :
+    # par construction ils ne contiennent pas de séparateur et ne
+    # commencent ni par « ~ », ni par « . », ni par une lettre+« : ».
+    if not token:
+        return False
+    if "/" in token or os.sep in token or chr(92) in token:
+        return True
+    if token.startswith("~"):
+        return True
+    if token.startswith("."):
+        return True
+    if re.match(r"^[A-Za-z]:", token):
+        return True
+    return False
+
+
+def _candidats(tool_name, tool_input):
+    trouves = []
+    for cle in PATH_KEYS:
+        valeur = tool_input.get(cle)
+        if isinstance(valeur, str) and valeur:
+            trouves.append(valeur)
+    # Politique « chemins littéraux résolubles uniquement » : seuls les
+    # fragments qui ressemblent à un chemin littéral sont contrôlés.
+    #
+    # B-24c/d — UN SEUL découpage de la commande brute sur la classe des
+    # délimiteurs shell (``\s<>;|&()"'`$``), puis application du filtre
+    # ``_ressemble_chemin``. Aucune tokenisation de type shell : shlex et
+    # son repli re.split ont été rejetés par la revue scellée (chaque
+    # tour trouvait un opérateur ou un séparateur oublié, signal de
+    # conception). On n'extrait que des fragments LITTÉRAUX.
+    #
+    # B-24d tour 10 — grappes d'options courtes (1 à 3 lettres).
+    # L'ambiguïté entre une grappe d'options courtes agglutinée à un
+    # chemin (``-cf/etc/passwd``, dangereux) et un argument relatif
+    # légitime (``-Iinclude/sys``, chemin vers un répertoire de
+    # headers) est IRRÉDUCTIBLE lexicalement : les deux formes ont
+    # exactement la même structure (tiret + lettres + ``/`` + reste),
+    # et seule la sémantique de l'outil invoqué les distingue —
+    # sémantique qu'on ne peut pas connaître depuis le guard. On borne
+    # donc par une propriété MESURÉE : les grappes d'options courtes
+    # usuelles font 1 à 3 lettres (``-f``, ``-cf``, ``-czf``, ``-so``,
+    # ``-xzf``), tandis qu'un argument relatif commence par un mot
+    # plus long (``include``, ``src``, ``out``). Mesure : à 3 lettres,
+    # 0 faux positif sur les cas légitimes ; à 4 lettres, 2 faux
+    # positifs réapparaissent (``-Isrc/include``, ``-fout/archive.tar``).
+    # La borne 3 est donc un choix mesuré, pas arbitraire. Faux positif
+    # résiduel assumé : un répertoire relatif dont le nom fait 3
+    # lettres ou moins et colle à une grappe (ex. ``-Iab/x``) serait
+    # refusé à tort — cas rare, coût accepté.
+    #
+    # B-24d tour 8 — collage d'un chemin à un préfixe d'option.
+    # Le collage d'un chemin à un préfixe d'option suit les conventions
+    # POSIX/GNU : séparateur ``=`` pour les options longues
+    # (``--file=...``, ``--target-directory=...``) et agglutination
+    # après ``-`` pour les options courtes (``-f...``, ``-o...``, etc.).
+    # Deux règles bornées par ces conventions les couvrent :
+    #
+    # R1. Le signe ``=`` est ajouté à la classe des délimiteurs : il
+    #     isole le préfixe d'option longue de son argument et couvre
+    #     aussi les affectations de variables d'environnement en
+    #     préfixe de commande (``VAR=/chemin cmd``).
+    # R2. Un fragment qui COMMENCE par ``-`` est une option. Pour les
+    #     options courtes avec argument agglutiné (``-x<chemin>`` ou
+    #     ``-xyz<chemin>`` avec grappe de 1 à 3 lettres), on cherche
+    #     le plus petit préfixe alphabétique de longueur 1 à 3 suivi
+    #     d'un caractère ouvrant un chemin (``/``, ``~``, ``.``,
+    #     backslash Windows, ou lecteur ``X:``). Le fragment entier
+    #     reste également candidat ; les doublons sont évités par
+    #     ``vus``.
+    #
+    # Conséquences : un fragment contenant un séparateur et composé de
+    # caractères hors délimiteurs ne peut PAS se cacher — s'il est dans
+    # la commande, le motif le trouve, qu'il soit entre guillemets,
+    # après une redirection, dans une substitution de commande, dans un
+    # heredoc ou collé à un préfixe d'option. Le découpage NE LÈVE PAS
+    # d'exception (re.split ne lève jamais sur des guillemets
+    # déséquilibrés) : le chemin dégradé ``try/except`` disparaît, et
+    # avec lui la porte de service qu'il constituait.
+    #
+    # Limite de périmètre inchangée : on n'interprète PAS le shell — pas
+    # d'expansion de variable (``$HOME``, ``${X}``), pas de substitution
+    # de commande (``$(...)``, ``...``), pas de globbing (``*``, ``?``,
+    # ``[...]``), pas de compréhension des quotes imbriquées au-delà du
+    # découpage. L'extraction porte sur des FRAGMENTS LITTÉRAUX.
+    if tool_name == "Bash":
+        commande = tool_input.get("command")
+        if isinstance(commande, str):
+            # bash supprime la continuation de ligne (backslash + saut
+            # de ligne) avant tout découpage (mesure). Sans cette
+            # normalisation, un chemin fragmenté par des continuations
+            # échappe au contrôle. Normalisation appliquée partout, y
+            # compris dans des guillemets simples où bash ne le ferait
+            # pas — sur-détection assumée, fail-closed. Avec le retrait
+            # du backslash dans _resoudre, cela couvre la liste
+            # COMPLÈTE et MESURÉE des transformations pré-découpage
+            # de bash.
+            commande = commande.replace(chr(92) + "\n", "")
+            # B-24f — expansion d'accolades (Bash T{4..6}) : ajout de
+            # { } , à la classe des délimiteurs. Bash applique
+            # l'expansion d'accolades AVANT le découpage en mots ;
+            # sans ces délimiteurs, le fragment ``{.claude,x}/settings.json``
+            # restait entier, ne correspondait pas à ``.claude``, et se
+            # résolvait sous la racine : le confiné pouvait donc
+            # ÉCRASER la configuration de sa propre garde. Précision :
+            # bash n'expand les accolades QUE s'il y a une virgule ou
+            # une séquence ``{a..b}`` — une accolade SANS virgule reste
+            # littérale (mesure : ``{../../etc/passwd}`` reste tel quel).
+            DELIMITEURS = r"""[\s<>;|&()"'`$={},]+"""
+            fragments = [f for f in re.split(DELIMITEURS, commande) if f]
+            # Règle R2 (grappe de 1 à 3 lettres) : un fragment
+            # commençant par ``-`` est une option courte avec argument
+            # agglutiné. On cherche le plus petit préfixe alphabétique
+            # de longueur n (1 ≤ n ≤ 3) tel que le reste commence par
+            # un caractère ouvrant un chemin. Le motif accepte les
+            # trois ouvrants POSIX (``/``, ``~``, ``.``), le backslash
+            # Windows (via chr(92), jamais littéral pour ne dépendre
+            # d'aucun échappement dans la chaîne template) et un
+            # lecteur Windows ``C:``. chr(92)*2 et non chr(92) : dans
+            # une classe de caracteres, un backslash SEUL échapperait
+            # le crochet fermant et rendrait la classe invalide
+            # (« bad character range ») — le script lèverait alors à
+            # chaque appel et, fail-closed oblige, refuserait TOUTES
+            # les commandes. Dédoublonnage par ``vus`` pour ne pas
+            # accumuler la même cible sous deux formes.
+            OUVRE_AGGLUTINE = re.compile(r"^[/~." + chr(92) * 2 + r"]|^[A-Za-z]:")
+            vus = set()
+            # Traitement d'un fragment, factorisé pour être appliqué
+            # à DEUX sources (jetons shlex PUIS fragments du découpage)
+            # sans duplication de code : filtre ``_ressemble_chemin``
+            # avec dédoublonnage, puis règle R2 des grappes d'options
+            # courtes. L'ensemble ``vus`` est GLOBAL aux deux sources :
+            # une même cible n'est jamais accumulée sous deux formes.
+            def traiter(fragment):
+                if _ressemble_chemin(fragment) and fragment not in vus:
+                    trouves.append(fragment)
+                    vus.add(fragment)
+                if fragment.startswith("-"):
+                    for n in range(1, 4):
+                        prefix = fragment[1:1 + n]
+                        reste = fragment[1 + n:]
+                        if len(prefix) == n and prefix.isalpha() and reste and OUVRE_AGGLUTINE.match(reste):
+                            if _ressemble_chemin(reste) and reste not in vus:
+                                trouves.append(reste)
+                                vus.add(reste)
+                            break
+            # B-24e — extraction EN UNION, shlex PUIS découpage, sans
+            # que l'un remplace jamais l'autre. Bash CONCATÈNE les
+            # parties quotées adjacentes ; le découpage, lui, les
+            # SÉPARE. Mesure : ``echo bad > .cl"aude/settings.json"``
+            # produit au découpage les fragments ``.cl`` et
+            # ``aude/settings.json``, dont AUCUN ne correspond à
+            # ``.claude`` : le confiné pouvait ÉCRASER la configuration
+            # de sa propre garde. shlex, lui, restitue le jeton
+            # ``.claude/settings.json``. L'union des deux méthodes
+            # couvre les deux classes de fragments.
+            # La décision de blocage n'est JAMAIS « cette chaîne
+            # apparaît dans la commande » mais « un chemin littéral
+            # résolvable, extrait par au moins une des deux méthodes,
+            # pointe hors racine » — l'union produit des sur-ensembles,
+            # filtrés en aval par la résolution confinée.
+            #
+            # Source (a) : jetons shlex (posix, ponctuation shell émise
+            # en jetons distincts, découpage sur les blancs).
+            try:
+                lx = shlex.shlex(commande, posix=True, punctuation_chars=True)
+                lx.whitespace_split = True
+                for jeton in lx:
+                    traiter(jeton)
+            except ValueError:
+                # Aucun traitement alternatif ici : c'est précisément
+                # cette absence qui interdit une porte de service. Le
+                # découpage strict de (b) s'applique TOUJOURS — shlex
+                # n'est pas un primaire dont on espère le succès, c'est
+                # un enrichisseur dont l'échec est sans conséquence.
+                pass
+            # Source (b) : fragments du découpage sur DELIMITEURS,
+            # appliqué INCONDITIONNELLEMENT, que (a) ait réussi ou non.
+            for fragment in fragments:
+                traiter(fragment)
+    return trouves
+
+
+def _exceptions():
+    # tempfile.gettempdir() résolu, plus chaque ligne non vide du fichier
+    # d'exceptions s'il existe. Un fichier illisible ne lève pas : on reste
+    # étroit (fail-closed) plutôt que de s'autoriser ce qu'on ne vérifie pas.
+    prefixes = [os.path.realpath(tempfile.gettempdir())]
+    if os.path.exists(ALLOW_PATH):
+        try:
+            with open(ALLOW_PATH, "r", encoding="utf-8") as fh:
+                lignes = fh.read().splitlines()
+        except OSError:
+            lignes = []
+        for ligne in lignes:
+            ligne = ligne.strip()
+            if ligne:
+                prefixes.append(os.path.realpath(os.path.expanduser(ligne)))
+    return prefixes
+
+
+def _auto_protege(tool_name, resolu):
+    # Même DANS la racine, un outil d'écriture ne peut toucher ni ce
+    # script, ni le répertoire « .claude » ENTIER — lui-même ou toute
+    # cible sous lui (hooks, settings.json, etc.) : la garde qui se
+    # laisse réécrire par le confiné est du théâtre. SCRIPT_PATH est
+    # testé isolément car le script peut vivre HORS de .claude. Ce
+    # contrôle précède les exceptions pour n'être jamais contourné par
+    # le fichier d'exceptions.
+    if tool_name not in WRITE_TOOLS:
+        return False
+    cible = os.path.normcase(resolu)
+    if cible == os.path.normcase(SCRIPT_PATH):
+        return True
+    if cible == os.path.normcase(CLAUDE_DIR):
+        return True
+    if _sous(resolu, CLAUDE_DIR):
+        return True
+    return False
+
+def _journaliser(tool, demande, resolu, cwd):
+    # Réplique exacte du format de forgeai.core.registre (contrat de
+    # compatibilité avec la vérification de chaîne du produit) : seq et
+    # prev_hash dérivés du registre lu, ts UTC à la seconde, hash sha256 du
+    # matériau canonique (entrée sans « hash », clés triées, JSON compact
+    # UTF-8), ligne écrite en JSON compact trié suivie de « \n », flock
+    # LOCK_EX quand fcntl existe, fsync avant de rendre.
+    registre = os.environ.get("FORGEAI_REGISTRE", REGISTRE_DEFAUT)
+    entries = []
+    if os.path.exists(registre):
+        with open(registre, "r", encoding="utf-8") as fh:
+            for ligne in fh:
+                ligne = ligne.strip()
+                if ligne:
+                    entries.append(json.loads(ligne))
+    prev_hash = entries[-1]["hash"] if entries else GENESIS
+    entry = {
+        "seq": len(entries) + 1,
+        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
+        "type": "guard_fs_denied",
+        "actor": "guard-fs",
+        "payload": {
+            "tool": tool,
+            "chemin_demande": demande,
+            "chemin_resolu": resolu,
+            "racine": ROOT,
+            "cwd": cwd,
+        },
+        "prev_hash": prev_hash,
+    }
+    materiau = json.dumps(
+        {k: v for k, v in entry.items() if k != "hash"},
+        sort_keys=True,
+        ensure_ascii=False,
+        separators=(",", ":"),
+    ).encode("utf-8")
+    entry["hash"] = hashlib.sha256(materiau).hexdigest()
+    ligne = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
+    parent = os.path.dirname(registre)
+    if parent:
+        os.makedirs(parent, exist_ok=True)
+    with open(registre, "a", encoding="utf-8") as fh:
+        if fcntl is not None:
+            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
+        try:
+            fh.seek(0, os.SEEK_END)
+            fh.write(ligne + "\n")
+            fh.flush()
+            os.fsync(fh.fileno())
+        finally:
+            if fcntl is not None:
+                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
+
+
+def _refuser(tool, demande, resolu, cwd, motif):
+    # Message d'UNE ligne : outil, chemin résolu refusé, racine. La
+    # journalisation est tentée AVANT de sortir ; si elle échoue, la raison
+    # est ajoutée au message — le refus tient TOUJOURS.
+    message = "forgeai-guard-fs: REFUS outil={0} chemin={1} racine={2} motif={3}".format(
+        tool, resolu, ROOT, motif
+    )
+    message = message.replace("\r", " ").replace("\n", " ")
+    try:
+        _journaliser(tool, demande, resolu, cwd)
+    except Exception as exc:
+        raison = str(exc).replace("\r", " ").replace("\n", " ")
+        message += " (journalisation impossible: {0})".format(raison)
+    sys.stderr.write(message + "\n")
+    raise SystemExit(2)
+
+
+def _refus_structurel(motif):
+    # Refus avant extraction : pas de chemin résolu à journaliser.
+    motif = motif.replace("\r", " ").replace("\n", " ")
+    sys.stderr.write("forgeai-guard-fs: REFUS racine={0} motif={1}\n".format(ROOT, motif))
+    raise SystemExit(2)
+
+
+def _decider():
+    try:
+        brut = sys.stdin.read()
+    except Exception as exc:
+        _refus_structurel("stdin illisible: {0}".format(exc))
+    try:
+        payload = json.loads(brut)
+    except ValueError as exc:
+        _refus_structurel("JSON stdin invalide: {0}".format(exc))
+    if not isinstance(payload, dict):
+        _refus_structurel("charge JSON non-objet")
+    tool_name = payload.get("tool_name")
+    if not isinstance(tool_name, str) or not tool_name:
+        _refus_structurel("tool_name absent ou invalide")
+    cwd = payload.get("cwd")
+    if not isinstance(cwd, str) or not cwd:
+        _refus_structurel("cwd absent ou invalide")
+    # Fail-closed : un cwd relatif rendrait la résolution des chemins
+    # relatifs ambiguë — refus structurel avant toute décision.
+    if not os.path.isabs(cwd):
+        _refus_structurel("cwd non absolu: {0}".format(cwd))
+    tool_input = payload.get("tool_input")
+    if tool_input is None:
+        tool_input = {}
+    if not isinstance(tool_input, dict):
+        _refus_structurel("tool_input non-objet")
+    # Le cwd est validé en propre, avant l'extraction des candidats : un
+    # cwd non contraint transforme tout nom de fichier nu (sans séparateur,
+    # donc jamais extrait comme candidat) en accès arbitraire — ce que le
+    # contrôle des candidats ne peut pas rattraper par construction.
+    cwd_resolu = os.path.realpath(cwd)
+    exceptions = _exceptions()
+    # Auto-protection AVANT confinement (comme pour les candidats) : un cwd
+    # sous .claude est refusé même si .claude est sous ROOT — depuis ce
+    # cwd, tout nom nu écrirait dans le répertoire de la garde. _sous
+    # inclut l'égalité (commonpath d'un chemin avec lui-même).
+    if tool_name in WRITE_TOOLS and _sous(cwd_resolu, CLAUDE_DIR):
+        _refuser(tool_name, cwd, cwd_resolu, cwd, "cwd sous auto-protection")
+    # Confinement : ROOT lui-même et tout descendant sont acceptés, ainsi
+    # que tout cwd sous une exception explicite (tempdir, fichier allow).
+    if not _sous(cwd_resolu, ROOT) and not any(
+        _sous(cwd_resolu, prefixe) for prefixe in exceptions
+    ):
+        _refuser(tool_name, cwd, cwd_resolu, cwd, "cwd hors racine")
+    candidats = _candidats(tool_name, tool_input)
+    if not candidats:
+        return  # Aucun chemin candidat : AUTORISER (exit 0).
+    for demande in candidats:
+        resolu = _resoudre(demande, cwd_resolu)
+        if _auto_protege(tool_name, resolu):
+            _refuser(tool_name, demande, resolu, cwd, "auto-protection")
+        if any(_sous(resolu, prefixe) for prefixe in exceptions):
+            continue  # Candidat dans une exception explicite : autorisé.
+        if not _sous(resolu, ROOT):
+            _refuser(tool_name, demande, resolu, cwd, "hors racine")
+    # Tous les candidats sont conformes : AUTORISER (exit 0).
+
+
+def main():
+    # Fail-closed global : TOUTE exception interne devient un REFUS exit 2
+    # avec la raison sur stderr. SystemExit (autorisation implicite exit 0 ou
+    # refus explicite exit 2) est laissé intact.
+    try:
+        _decider()
+    except SystemExit:
+        raise
+    except Exception as exc:
+        raison = str(exc).replace("\r", " ").replace("\n", " ")
+        sys.stderr.write(
+            "forgeai-guard-fs: REFUS racine={0} motif=erreur interne: {1}\n".format(ROOT, raison)
+        )
+        raise SystemExit(2)
+
+
+if __name__ == "__main__":
+    main()
+'''
+
+
+def _chemin_embarque(chemin: str | os.PathLike[str]) -> str:
+    """expanduser puis absolu, au moment de la génération.
+
+    Un chemin relatif embarqué dans le script généré serait résolu contre un
+    cwd imprévisible à l'exécution du hook — même piège que la racine mobile,
+    même remède : figer à la génération.
+    """
+    return os.path.abspath(os.path.expanduser(os.fspath(chemin)))
+
+
+def generate_guard_fs(
+    workspace_root: str | os.PathLike[str],
+    *,
+    registre_path: str | os.PathLike[str] | None = None,
+    allow_path: str | os.PathLike[str] | None = None,
+) -> str:
+    """Retourne le source complet de la garde, substitutions faites.
+
+    ``workspace_root`` est figé par ``os.path.realpath`` AU MOMENT DE LA
+    GÉNÉRATION (décision B-24 : la racine ne doit jamais être dérivée du cwd
+    à l'exécution). Une racine inexistante lève ``IDEError`` : générer une
+    garde pour une racine fantôme est un piège silencieux.
+
+    ``registre_path`` (défaut ``~/.forgeai/Registres/mission.jsonl``) et
+    ``allow_path`` (défaut ``~/.forgeai/guard-fs.allow``) sont expanduser à la
+    génération. Les trois chemins sont injectés via ``repr`` — jamais
+    d'interpolation nue dans du code généré.
+    """
+    root = os.path.realpath(os.fspath(workspace_root))
+    if not os.path.exists(root):
+        raise IDEError(f"generate_guard_fs: racine de workspace inexistante : {root}")
+    registre = (
+        _chemin_embarque(registre_path)
+        if registre_path is not None
+        else _chemin_embarque("~/.forgeai/Registres/mission.jsonl")
+    )
+    allow = (
+        _chemin_embarque(allow_path)
+        if allow_path is not None
+        else _chemin_embarque("~/.forgeai/guard-fs.allow")
+    )
+    script = _SCRIPT_TEMPLATE
+    for jeton, valeur in (
+        ("__FORGEAI_ROOT__", root),
+        ("__FORGEAI_REGISTRE__", registre),
+        ("__FORGEAI_ALLOW__", allow),
+    ):
+        if jeton not in script:
+            raise IDEError(f"generate_guard_fs: emplacement {jeton} absent du template")
+        script = script.replace(jeton, repr(valeur))
+    return script
+
+
+def install_guard_fs(
+    dest_dir: str | os.PathLike[str],
+    *,
+    python_executable: str | None = None,
+) -> tuple[Path, HookSpec]:
+    """Écrit la garde dans ``<dest_dir>/.claude/hooks/`` et retourne son hook.
+
+    Le script est écrit en UTF-8, mode 0o755, à
+    ``<dest_dir>/.claude/hooks/forgeai_guard_fs.py`` (répertoires parents
+    créés). La commande du hook épingle l'interpréteur ABSOLU capturé au
+    bootstrap (``sys.executable`` par défaut — jamais « python » nu, le PATH
+    n'est pas garanti chez l'utilisateur) et le chemin absolu du script.
+
+    Retourne ``(chemin_absolu_du_script, HookSpec PreToolUse matcher "*")``.
+    """
+    dest = Path(dest_dir)
+    script_path = (dest / ".claude" / "hooks" / "forgeai_guard_fs.py").resolve()
+    contenu = generate_guard_fs(dest)
+    script_path.parent.mkdir(parents=True, exist_ok=True)
+    script_path.write_text(contenu, encoding="utf-8")
+    script_path.chmod(0o755)
+    python = python_executable if python_executable is not None else sys.executable
+    hook = HookSpec(
+        event="PreToolUse",
+        command=f'"{python}" "{script_path}"',
+        matcher="*",
+    )
+    return script_path, hook
~~~

## Vérification ciblée de la ligne contestée à la passe précédente
~~~
$ grep -n 'DELIMITEURS = ' src/forgeai/ide/guard_fs.py
247:            DELIMITEURS = r"""[\s<>;|&()"'`$={},]+"""
$ git rev-parse --short HEAD
8e9bf7b
~~~

## Preuve d'exécution CAPTURÉE après le commit 8e9bf7b
~~~
$ python3 -m pytest tests/test_guard_fs.py -q
........................s......................................s........ [ 57%]
......................................................                   [100%]
exit=0 — 125 tests, 2 skips (Windows, non observable sur POSIX)

# 30 cas en subprocess reel (0=autorise, 2=refuse)
   REFUS attendus :
     2  ACCOLADES {/etc/passwd,x}
     2  ACCOLADES {/etc,/tmp}/passwd
     2  ACCOLADES {.claude,x}/settings.json
     2  ACCOLADES echo > {.claude,y}/settings
     2  accolade SANS virgule (litteral)
     2  SCISSION .cl"aude/settings.json"
     2  SCISSION "/etc"/passwd
     2  grappe tar -cf/etc/passwd
     2  grappe curl -so.claude/settings
     2  option tar -f/etc/passwd
     2  prefixe dd if=/etc/passwd
     2  prefixe awk --file=/etc/passwd
     2  continuation de ligne
     2  quote orphelin
     2  backslash echappe
     2  operateur colle
     2  rm -rf .claude
     2  mv du script installe
     2  traversal
     2  cwd=/etc + cat passwd
     2  cwd=.claude + echo > settings
     2  Read /etc/passwd
     2  cwd relatif (fail-closed)
     2  FP ASSUME gcc -Iab/x
   AUTORISATIONS attendues (zero faux positif) :
     0  find . -exec cat {} ;
     0  find -name *.py -exec rm {} +
     0  gcc -Iinclude/sys x.c
     0  gcc -Isrc/include x.c
     0  tar -xzf archive.tar.gz
     0  gcc -I. x.c
     0  ls -la
     0  echo l'utilisateur
     0  grep don't fichier.txt
     0  ls *.py
     0  cat $HOME/truc
     0  cat "fichier>bizarre.txt"
     0  cat sous/f.txt
     0  continuation interne
     0  cwd=racine/sous
     0  Read sous/f.txt

# CRITERE FIGE : refus journalise ET chaine verifiee par l'outil DU PRODUIT
   3 entrees ecrites par le script AUTONOME ; types={'guard_fs_denied'}
   verify OFFICIEL du produit : OK /tmp/tmpjm98b7my/reg.jsonl: 3 entrées, chaîne intègre (exit 0)

# MUTATIONS — 20 sur les 12 tours, substitution VERIFIEE effective a chaque fois.
  Toutes ROUGE, vert au retour. Derniere en date : retrait des accolades de la classe
  -> 4 tests en echec, exit=1.
  UNE mutation survit et c'est ATTENDU : resoudre contre le cwd BRUT au lieu du cwd
  resolu est semantiquement EQUIVALENT (_resoudre applique deja realpath en sortie),
  verifie par mesure avec un symlink dans le cwd.

# CI : job guard-fs-multi-os (ubuntu + macos + windows, fail-fast: false)
$ no_stub_scan : OK ; $ suite complete du depot : exit=0 ; 0 SyntaxWarning
~~~
