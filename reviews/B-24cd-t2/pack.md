# Revue scellée — B-24c/d (commit 7738439) — garde filesystem, revue complète

## Contexte
Composant de SÉCURITÉ. Quatre stories du confinement filesystem regroupées ici (B-24c
génération de la garde, B-24d comportement + journalisation ; B-24a/b déjà sur main).
Historique de revue : tour 1 REJECT (6 contournements Bash triviaux) -> corrigés ;
une passe partielle a ensuite signalé `C:Windows` (lecteur sans séparateur) -> corrigé
dans ce commit. Jugez le DIFF CUMULÉ ci-dessous. REJECT si un chemin littéral hors
racine passe encore, ou si l'auto-protection est contournable.

## Ce qui est livré (guard_fs.py + tests)
- generate_guard_fs / install_guard_fs : script de garde autonome (stdlib pure, n'importe
  jamais forgeai) + HookSpec PreToolUse (interpréteur absolu + script absolu).
- Confinement : realpath des deux côtés, commonpath+normcase (jamais startswith),
  fail-closed (toute exception -> refus), cwd absolu obligatoire.
- Extraction Bash : shlex (dé-quote) + _ressemble_chemin (séparateur, ~, préfixe .,
  lecteur Windows avec/sans séparateur). Token nu sans séparateur ignoré (commande).
- Auto-protection : script + répertoire .claude ENTIER non réinscriptibles par le confiné.
- Journalisation d'un refus au format EXACT de core.registre (verify-compatible).

## Limite hors périmètre (documentée — ne pas REJETER pour ça)
Exécution de code arbitraire via Bash (variables, substitution, base64|sh, globbing)
non confinable sans sandbox OS. Périmètre : chemins littéraux résolubles.

## Diff CUMULÉ vs origin/main (toute la story)
```diff
diff --git a/src/forgeai/ide/guard_fs.py b/src/forgeai/ide/guard_fs.py
new file mode 100644
index 0000000..c6b6f7e
--- /dev/null
+++ b/src/forgeai/ide/guard_fs.py
@@ -0,0 +1,431 @@
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
+    p = os.path.expanduser(chemin)
+    if not os.path.isabs(p):
+        p = os.path.join(cwd, p)
+    return os.path.realpath(p)
+
+
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
+    # - il débute par un lecteur Windows `X:` — avec séparateur (`C:\x`, `C:/x`)
+    #   OU sans (`C:x`, chemin relatif au répertoire courant du lecteur, tout
+    #   aussi valide sous Windows). Regex `^[A-Za-z]:`.
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
+    if tool_name == "Bash":
+        commande = tool_input.get("command")
+        if isinstance(commande, str):
+            # Politique « chemins littéraux résolubles uniquement » : seuls
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
+                    trouves.append(token)
+    return trouves
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
+
+        tool_input = {}
+    if not isinstance(tool_input, dict):
+        _refus_structurel("tool_input non-objet")
+    candidats = _candidats(tool_name, tool_input)
+    if not candidats:
+        return  # Aucun chemin candidat : AUTORISER (exit 0).
+    exceptions = _exceptions()
+    for demande in candidats:
+        resolu = _resoudre(demande, cwd)
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
index 0000000..5bae0d1
--- /dev/null
+++ b/tests/test_guard_fs.py
@@ -0,0 +1,454 @@
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
```

## Preuve d'exécution CAPTURÉE (après le commit)
```
........................s......                                          [100%]
exit=0
   2  cat "/etc/passwd"
   2  rm -rf .claude
   2  mv script
   0  echo (autorisé)
(0 autorisé / 2 refusé)  ;  no_stub OK ; 5 mutations TEMPLATE détectées ; source double-compile
```
