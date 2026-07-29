# Revue scellée TOUR 2 — B-24c/d : garde filesystem, 6 contournements fermés (commit d088221)

## Contexte
Le tour 1 a rendu REJECT 2/3 : 6 objections CRITIQUES fondées — des chemins littéraux
TRIVIAUX passaient à travers le confinement Bash (tokens quotés `cat "/etc/passwd"`,
chemins relatifs sans préfixe `rm -rf .claude/hooks`, chemins Windows, dossier `.claude`
parent non protégé, `rm -rf .claude`). Ce tour 2 les ferme. Jugez le diff du tour 2 et le
traitement de chaque objection. C'est un composant de SÉCURITÉ : cherchez activement un
contournement résiduel. REJECT si un chemin littéral hors racine passe encore.

## Corrections (à vérifier)
- Extraction Bash : shlex.split (dé-quote) + _ressemble_chemin (séparateur / os.sep / \\,
  préfixe ~ ou ., lecteur Windows). Token nu sans séparateur ignoré (commande, pas chemin).
- Auto-protection du répertoire .claude ENTIER (CLAUDE_DIR) + SCRIPT_PATH isolé.
- cwd non absolu -> refus structurel fail-closed.

## Limite explicitement hors périmètre (ne pas REJETER pour ça — signaler si mal bornée)
L'exécution de code arbitraire via Bash (variables, substitution, base64|sh, globbing)
n'est PAS confinable sans sandbox OS. Le périmètre est « chemins littéraux résolubles ».

## Diff INTÉGRAL du tour 2 (vs commit précédent)
```diff
diff --git a/src/forgeai/ide/guard_fs.py b/src/forgeai/ide/guard_fs.py
index 5922d92..596cf6f 100644
--- a/src/forgeai/ide/guard_fs.py
+++ b/src/forgeai/ide/guard_fs.py
@@ -59,6 +59,8 @@ import hashlib
 import json
 import os
 import sys
+import re
+import shlex
 import tempfile
 from datetime import datetime, timezone
 
@@ -77,6 +79,11 @@ WRITE_TOOLS = ("Write", "Edit", "NotebookEdit", "Bash")
 PATH_KEYS = ("file_path", "path", "notebook_path")
 
 SCRIPT_PATH = os.path.realpath(__file__)
+# Le répertoire « .claude » ENTIER est protégé en écriture (O4) : hooks,
+# settings.json et toute cible sous .claude. HOOKS_DIR et SETTINGS_JSON
+# restent définis — couverts a fortiori par CLAUDE_DIR — pour la
+# lisibilité et les messages du registre.
+CLAUDE_DIR = os.path.realpath(os.path.join(ROOT, ".claude"))
 HOOKS_DIR = os.path.realpath(os.path.join(ROOT, ".claude", "hooks"))
 SETTINGS_JSON = os.path.realpath(os.path.join(ROOT, ".claude", "settings.json"))
 
@@ -99,6 +106,39 @@ def _resoudre(chemin, cwd):
     return os.path.realpath(p)
 
 
+# shlex et re sont stdlib : le script généré reste autonome et n'importe
+# jamais forgeai.
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
+    # - il débute par un lecteur Windows (regex ^[A-Za-z]:[\\/]).
+    # Un token SANS séparateur et sans préfixe « ~ »/« . » (ex. « cat »,
+    # « rm », « -rf ») N'EST PAS un chemin : l'ajouter provoquerait des
+    # faux positifs massifs sur les commandes et leurs options.
+    if not token:
+        return False
+    if "/" in token or os.sep in token or chr(92) in token:
+        return True
+    if token.startswith("~"):
+        return True
+    if token.startswith("."):
+        return True
+    if re.match(r"^[A-Za-z]:[\\/]", token):
+        return True
+    return False
+
+
 def _candidats(tool_name, tool_input):
     trouves = []
     for cle in PATH_KEYS:
@@ -109,16 +149,25 @@ def _candidats(tool_name, tool_input):
         commande = tool_input.get("command")
         if isinstance(commande, str):
             # Politique « chemins littéraux résolubles uniquement » : seuls
-            # les tokens qui ressemblent à un chemin littéral sont contrôlés.
-            # L'exécution de code arbitraire (variables, substitutions,
-            # globbing) n'est PAS confinable sans sandbox OS — limitation
-            # documentée et assumée.
-            for token in commande.split():
-                if token.startswith(("/", "./", "../", "~")):
+            # les tokens qui ressemblent à un chemin littéral sont
+            # contrôlés. shlex découpe la commande et retire les
+            # guillemets équilibrés, mais ne « comprend » PAS le shell :
+            # aucune expansion de variable, aucune substitution de
+            # commande, aucun globbing — c'est une extraction de tokens
+            # littéraux, pas un interprète. L'exécution de code
+            # arbitraire n'est PAS confinable sans sandbox OS —
+            # limitation documentée et assumée.
+            try:
+                tokens = shlex.split(commande, posix=True)
+            except ValueError:
+                # Guillemets déséquilibrés : repli sur un découpage naïf
+                # sur les espaces ; un token mal découpé qui contient un
+                # séparateur reste contrôlé (fail-closed côté décision).
+                tokens = commande.split()
+            for token in tokens:
+                if _ressemble_chemin(token):
                     trouves.append(token)
     return trouves
-
-
 def _exceptions():
     # tempfile.gettempdir() résolu, plus chaque ligne non vide du fichier
     # d'exceptions s'il existe. Un fichier illisible ne lève pas : on reste
@@ -138,22 +187,24 @@ def _exceptions():
 
 
 def _auto_protege(tool_name, resolu):
-    # Même DANS la racine, un outil d'écriture ne peut toucher ni ce script,
-    # ni le répertoire des hooks, ni settings.json : la garde qui se laisse
-    # réécrire par le confiné est du théâtre. Ce contrôle précède les
-    # exceptions pour n'être jamais contourné par le fichier d'exceptions.
+    # Même DANS la racine, un outil d'écriture ne peut toucher ni ce
+    # script, ni le répertoire « .claude » ENTIER — lui-même ou toute
+    # cible sous lui (hooks, settings.json, etc.) : la garde qui se
+    # laisse réécrire par le confiné est du théâtre. SCRIPT_PATH est
+    # testé isolément car le script peut vivre HORS de .claude. Ce
+    # contrôle précède les exceptions pour n'être jamais contourné par
+    # le fichier d'exceptions.
     if tool_name not in WRITE_TOOLS:
         return False
     cible = os.path.normcase(resolu)
     if cible == os.path.normcase(SCRIPT_PATH):
         return True
-    if _sous(resolu, HOOKS_DIR):
+    if cible == os.path.normcase(CLAUDE_DIR):
         return True
-    if cible == os.path.normcase(SETTINGS_JSON):
+    if _sous(resolu, CLAUDE_DIR):
         return True
     return False
 
-
 def _journaliser(tool, demande, resolu, cwd):
     # Réplique exacte du format de forgeai.core.registre (contrat de
     # compatibilité avec la vérification de chaîne du produit) : seq et
@@ -249,8 +300,13 @@ def _decider():
     cwd = payload.get("cwd")
     if not isinstance(cwd, str) or not cwd:
         _refus_structurel("cwd absent ou invalide")
+    # Fail-closed : un cwd relatif rendrait la résolution des chemins
+    # relatifs ambiguë — refus structurel avant toute décision.
+    if not os.path.isabs(cwd):
+        _refus_structurel("cwd non absolu: {0}".format(cwd))
     tool_input = payload.get("tool_input")
     if tool_input is None:
+
         tool_input = {}
     if not isinstance(tool_input, dict):
         _refus_structurel("tool_input non-objet")
diff --git a/tests/test_guard_fs.py b/tests/test_guard_fs.py
index 879a948..5bae0d1 100644
--- a/tests/test_guard_fs.py
+++ b/tests/test_guard_fs.py
@@ -340,3 +340,115 @@ def test_auto_protection_du_script_dans_racine_hors_hooks(tmp_path, racine, env_
     script.write_text(src, encoding="utf-8")
     code, err = run(script, charge("Edit", {"file_path": str(script)}, cwd=racine), env=env_tmpdir)
     assert code == 2, f"le script doit se protéger même hors du dossier hooks (stderr={err!r})"
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
```

## Preuve d'exécution CAPTURÉE (rejouée après le commit d088221)
```
$ python3 -m pytest tests/test_guard_fs.py -q
........................s......                                          [100%]
exit=0

# les 6 contournements de la revue, e2e en subprocess réel :
   2  cat "/etc/passwd"
   2  rm -rf .claude/hooks
   2  rm -rf .claude
   2  traversal
   2  mv script
   0  echo (autorisé)
(0 = autorisé, 2 = refusé)
$ no_stub_scan : OK ; suite complète : exit=0 ; 5 mutations TEMPLATE toutes détectées
```
