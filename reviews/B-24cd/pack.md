# Revue scellée — B-24c/d : garde filesystem + confinement prouvé (commit 61ff664)

## Story et contexte
Troisième et quatrième stories du confinement filesystem (ADR en annexe). C'est ici que
le CRITÈRE FIGÉ de B-24 est atteint : « tout accès fichier hors workspace via les outils
structurés, et tout chemin littéral hors workspace dans une commande Bash, est refusé ET
journalisé ». Ce diff EMPILE sur B-24b (HookSpec) — jugez UNIQUEMENT le nouveau module
guard_fs.py et ses tests ; HookSpec est déjà scellé.

## Ce qui est livré
- generate_guard_fs(root) rend le SOURCE d'un script de garde autonome (stdlib pure,
  n'importe jamais forgeai) ; install_guard_fs l'écrit + rend un HookSpec PreToolUse.
- Le script : fail-closed (toute exception -> refus), racine figée par realpath à la
  génération, containment par commonpath+normcase (jamais startswith), realpath des deux
  côtés (symlink sortant refusé), politique Bash « chemins littéraux résolubles »,
  auto-protection (script + .claude/hooks/ + settings.json non réinscriptibles),
  journalisation d'un refus au format EXACT de core.registre.

## Critères d'acceptation (tous tenus, prouvés par exécution réelle)
CA-1 : lecture/écriture hors racine -> refus (exit 2) ; dans racine -> autorisé.
CA-2 : symlink sortant, répertoire frère à préfixe commun, `..` sortant -> refus.
CA-3 : Bash avec chemin littéral hors racine -> refus ; sans chemin -> autorisé.
CA-4 : auto-protection : le confiné ne peut réécrire ni le script, ni le hook, ni settings.
CA-5 (CRITÈRE FIGÉ) : un refus écrit une entrée guard_fs_denied LUE ET VALIDÉE par le
       `verify` officiel du produit (chaîne intègre) ; deux refus -> chaîne de 2 intègre.
CA-6 : journalisation impossible n'annule JAMAIS le refus (fail-closed sur le log aussi).
CA-7 : stdlib uniquement ; le SOURCE généré double-compile.

## Ce qu'il faut chercher (adversarial — c'est un composant de SÉCURITÉ)
- un chemin qui CONTOURNE le confinement (encodage, UNC Windows, TOCTOU symlink,
  `~` mal étendu, token Bash exotique, casse) ;
- une auto-protection contournable (renommer, chemin relatif vers le script) ;
- un cas où la journalisation casse la chaîne du registre (format divergent) ;
- un test qui LANCE le script mais n'observe pas le bon effet.
Rappel documenté et ASSUMÉ : l'exécution de code arbitraire via Bash (base64|sh, etc.)
n'est PAS confinable sans sandbox OS — le périmètre est « chemins littéraux ». Ne
REJETEZ pas pour cette limite explicitement hors périmètre ; signalez si elle est mal bornée.

## Diff INTÉGRAL du module + tests (vs le commit B-24b parent)
```diff
diff --git a/src/forgeai/ide/guard_fs.py b/src/forgeai/ide/guard_fs.py
new file mode 100644
index 0000000..5922d92
--- /dev/null
+++ b/src/forgeai/ide/guard_fs.py
@@ -0,0 +1,373 @@
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
+            # les tokens qui ressemblent à un chemin littéral sont contrôlés.
+            # L'exécution de code arbitraire (variables, substitutions,
+            # globbing) n'est PAS confinable sans sandbox OS — limitation
+            # documentée et assumée.
+            for token in commande.split():
+                if token.startswith(("/", "./", "../", "~")):
+                    trouves.append(token)
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
+    # Même DANS la racine, un outil d'écriture ne peut toucher ni ce script,
+    # ni le répertoire des hooks, ni settings.json : la garde qui se laisse
+    # réécrire par le confiné est du théâtre. Ce contrôle précède les
+    # exceptions pour n'être jamais contourné par le fichier d'exceptions.
+    if tool_name not in WRITE_TOOLS:
+        return False
+    cible = os.path.normcase(resolu)
+    if cible == os.path.normcase(SCRIPT_PATH):
+        return True
+    if _sous(resolu, HOOKS_DIR):
+        return True
+    if cible == os.path.normcase(SETTINGS_JSON):
+        return True
+    return False
+
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
+    tool_input = payload.get("tool_input")
+    if tool_input is None:
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
index 0000000..879a948
--- /dev/null
+++ b/tests/test_guard_fs.py
@@ -0,0 +1,342 @@
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
```

## Preuve d'exécution CAPTURÉE (rejouée après le commit 61ff664)
```
$ python3 -m pytest tests/test_guard_fs.py -q
..................                                                       [100%]
exit=0

# le SCRIPT GÉNÉRÉ confine-t-il vraiment ? (test e2e hors pytest, subprocess réel)
  Read dans racine   -> 0 (0)
  Read /etc/passwd   -> 2 (2)
  Bash cat /etc/shadow -> 2 (2)
  registre: 2 entrees guard_fs_denied ; verify -> OK /tmp/tmp249x23g0/reg.jsonl: 2 entrées, chaîne intègre exit 0

# mutations sur le TEMPLATE du script (substitution vérifiée avant interprétation)
  containment par startswith             : ROUGE ; abspath au lieu de realpath : ROUGE
  auto-protection SCRIPT_PATH désactivée : ROUGE (après ajout du test isolant) ; tokens Bash non résolus : ROUGE
$ no_stub_scan : OK ; suite complète : exit=0
```

## Annexe — ADR B-24 (déjà tranché, ne pas re-juger)
# B-24 — Confinement filesystem au workspace : décision d'architecture

Décision rendue par l'architecte (Kimi-K3) le 2026-07-29, appliquée telle quelle.
Périmètre de CETTE story (B-24a) : décisions 4 uniquement (validateur partagé).
B-24b (HookSpec), B-24c (génération de la garde), B-24d (comportement + journal)
suivent dans cet ordre. Le critère figé « refusée ET journalisée » est porté par
B-24d seule — aucune story intermédiaire ne le promet.

Adaptation de type journalisée (orchestrateur) : resolve_within accepte
str | os.PathLike et retourne Path — la sémantique de l'architecte (realpath des
deux côtés, commonpath après normcase, exceptions typées) est inchangée ; seuls
les types s'alignent sur le reste du code. Les relecteurs scellés jugent ce choix.

# Décision d'architecture — B-24 : confinement filesystem au workspace

## 1. Signature — type dédié `HookSpec`, union additive

**Décision : introduire une dataclass gelée `HookSpec(event: str, command: str, matcher: str = "*")` et étendre le paramètre en `hooks: list[str | HookSpec]`. Les `str` sont normalisés en interne vers `HookSpec(event=s, command=s, matcher="*")` — exactement le comportement actuel.**

Justification : signature additive à comportement inchangé pour le cas `str`, donc `tests/test_ide_bootstrap.py:68-73` passe sans modification et les appelants existants sont préservés — c'est le même principe que la décision FAI-0006 (paramètre optionnel, défaut qui reproduit l'ancien comportement). Un paramètre séparé `hook_specs: list[HookSpec] | None = None` est rejeté : deux listes parallèles exprimant la même notion est une source permanente de confusion (« lequel gagne ? »). La sérialisation vers le dict JSON reste interne à `generate_governance_config` ; `IdeConfig` ne change pas de forme.

Signature retenue :
`generate_governance_config(skills: list[str], hooks: list[str | HookSpec], *, ide: str = "claude-code") -> IdeConfig`

## 2. Où vit la garde — script autonome généré, interpréteur absolu

**Décision : un script Python stdlib autonome, généré (pas copié depuis un template fichier : une constante chaîne dans le produit) à `<dest>/.claude/hooks/forgeai_guard_fs.py`. La commande écrite dans settings.json est `"<sys.executable_capturé_au_bootstrap>" "<chemin_absolu_du_script>"`.**

Justification triple. (a) *PATH* : la commande ne dépend ni de `forgeai` dans le PATH ni même de `python` dans le PATH — `sys.executable` au moment du bootstrap est un chemin valide sur la machine de l'utilisateur par construction. (b) *Survie* : la garde est une protection ; elle ne doit pas mourir avec la désinstallation ou le changement de venv de l'outil qui l'a posée — un `forgeai guard-fs` (module du produit) transformerait une mise à jour de forgeai en fenêtre de trou ou en panne, au gré du fail-open/fail-closed de l'IDE. (c) *Zéro dépendance préservée* : le script n'importe que stdlib et n'importe pas forgeai, donc aucune couplage de version. Coût assumé : ~30 lignes d'append JSONL dupliquées dans le template (voir §5), duplicat documenté comme contrat de format, pas comme logique partagée. Le script lit la charge JSON du hook sur stdin, répond selon le contrat de sortie de l'IDE cible (code de sortie de refus + message sur stderr), et **toute exception interne du script produit un refus** (fail-closed) : une garde de sécurité qui crash en autorisant est un trou, pas une garde.

## 3. « Hors workspace » — racine figée au bootstrap, realpath des deux côtés, exceptions hors de portée de l'agent

**Racine.** C'est `dest_dir` passé à `write_ide_config`, canonisé par `os.path.realpath` **au bootstrap** et embarqué en constante dans le script généré. Justification : figer la racine dans le script évite toute dérive par `cwd` à l'exécution ; `realpath` (pas `abspath`) au bootstrap car sur macOS `/tmp` → `/private/tmp` et un home symlinké produirait sinon des faux positifs de masse.

**Cible.** Chaque chemin extrait de la charge est résolu par `os.path.realpath` contre le `cwd` fourni par la charge ; `..` et les relatifs disparaissent dans la résolution réelle ; la comparaison utilise `os.path.commonpath` après `os.path.normcase` (Windows : `C:\Repo` vs `c:\repo` sinon = faux positif immédiat). Résoudre les symlinks **des deux côtés** est non négociable : ne résoudre que la cible laisse passer un symlink sortant (faux négatif) ; ne résoudre que la racine casse tout symlink entrant légitime (faux positif).

**Exceptions.** Oui, obligatoires — sinon `pip`, tout compilateur et tout outil écrivant dans le tempdir rendent le produit inutilisable, et un confinement contourné par l'utilisateur agacé est pire que pas de confinement. Décision : la liste vit dans `~/.forgeai/guard-fs.allow` (une ligne = un chemin réel préfixe), **jamais dans le workspace** — un fichier d'exceptions dans le workspace est modifiable par l'agent confiné, ce qui revient à laisser le prisonnier tenir la liste de ses permissions. Défaut livré : le tempdir système résolu (`tempfile.gettempdir()` passé par `realpath`), en lecture-écriture. Aucune autre exception implicite : tout le reste (cache pip, etc.) est un choix explicite de l'utilisateur, éclairé par le fait que chaque refus journalise le chemin exact refusé. Le script, processus non confiné de l'utilisateur, peut lire ce fichier ; l'agent ne peut pas l'écrire sans déclencher le refus qu'il cherche à lever.

## 4. Validateur partagé — extraction dans `core/validation.py`, refactor de `local.py` inclus

**Décision : extraire `resolve_within(path: str, root: str, *, base: str | None = None) -> str` (lève `ValidationError`) dans `core/validation.py`, et refactorer `models/local.py:85-91` pour l'utiliser dans la MÊME story.**

Justification : un validateur « partagé » livré avec un seul consommateur pendant que l'ancien duplicat survit à 20 lignes de là, c'est exactement la duplication que l'extraction prétendait éliminer — l'extraction sans refactor est une promesse non tenue déguisée. Le risque du refactor est borné par les tests existants de `local.py` ; le validateur doit exposer aussi la primitive « nom simple » (rejet de `/`, `os.sep`, `..`) car `local.py` valide un *nom de fichier* avant de valider un *chemin*, et confondre les deux ferait régresser son comportement. `core/validation.py` plutôt qu'un nouveau module : il existe, c'est son rôle déclaré, et un module par fonction est du sur-découpage.

## 5. Journalisation — registre hors workspace, refus inconditionnel

**Décision : chemin `~/.forgeai/Registres/mission.jsonl` (surchargeable via la variable d'environnement `FORGEAI_REGISTRE` lue par le script), `type_ = "guard_fs_denied"`, `actor = "guard-fs"`, payload : chemin demandé, chemin résolu, racine, outil, cwd, horodatage.**

Justification du chemin : le registre hors workspace est **hors de portée d'écriture de l'agent confiné** — il ne peut ni l'effacer ni le falsifier, ce qui est précisément la propriété qu'on exige d'un journal d'audit de sécurité. Le script, non confiné, peut y écrire. Le script n'important pas forgeai, il embarque un append JSONL minimal conforme au schéma de ligne de `core/registre.py` (verrouillage `fcntl` POSIX / `msvcrt` Windows, fsync) — duplication contrôlée d'un *format*, assumée et couverte par un test de compatibilité : une ligne écrite par le script doit être lisible par le lecteur officiel du registre.

**Si l'écriture échoue : le refus tient, toujours.** Justification : l'inverse (autoriser quand le log est KO) fait de la journalisation un kill-switch de la sécurité — il suffirait à l'agent de saturer le disque ou de rendre le registre inaccessible pour sortir librement. L'échec de log est rapporté dans le message de refus (stderr, visible par l'utilisateur) ; il n'y a pas de fallback d'écriture dans le workspace, qu'un agent confiné pourrait effacer.

## 6. Découpage — quatre stories, le critère figé porté par la dernière

Une seule story mélangerait refactor, modèle de données, génération et comportement runtime : improuvable proprement. Découpage ordonné :

1. **B-24a — Validateur partagé.** Critère : `resolve_within` rejette `..`, symlink sortant, chemin hors racine après `normcase` ; accepte symlink entrant et racine symlinkée (cas macOS `/tmp`) ; `models/local.py` refactoré, ses tests existants verts.
2. **B-24b — `HookSpec`.** Critère : `test_ide_bootstrap.py:68-73` vert sans modification ; nouveau test assertant la forme exacte `{event: [{matcher, hooks: [{type: "command", command}]}]}` avec événement ≠ commande et matcher ≠ `"*"`.
3. **B-24c — Génération de la garde.** Critère : le bootstrap écrit le script (existant, non vide) et le hook `PreToolUse` dont la commande est un interpréteur absolu + chemin absolu du script ; la racine canonique est embarquée dans le script.
4. **B-24d — Comportement + journal (critère figé B-24).** Critère : e2e, exécution du script généré — charge pointant hors racine (résolue) → refus **et** ligne `guard_fs_denied` lisible par le lecteur officiel du registre ; charge dans la racine → autorisation ; registre inaccessible → refus maintenu.

Le critère figé « refusée ET journalisée » est inséparable : il est donc le critère unique de B-24d, et aucune story intermédiaire ne le promet.

## 7. Le piège que tu n'as pas vu — deux, dont un qui menace le critère figé

**Piège majeur — le matcher `PreToolUse` ne voit pas Bash.** Le hook reçoit des charges structurées pour les outils fichier (`Read`, `Write`, `Edit` : `file_path` explicite), mais pour `Bash` il reçoit une *chaîne de commande*. Confiner `cat /etc/passwd`, `cd /etc && cat passwd`, `base64 -d <<< … | sh` ou `python -c "open('/etc/passwd')"` par analyse textuelle est indécidable : toute tokenisation `shlex` se fait déborder par les substitutions, l'expansion de variables et l'encodage. Un hook qui prétend tenir « **tout** accès en lecture/écriture » (critère figé) avec Bash dans le matcher vend une promesse algébriquement fausse. Décision : le matcher couvre les outils fichier + `Bash` avec une politique « chemins littéraux résolubles uniquement » — chaque token de forme chemin est vérifié via `resolve_within`, et la documentation produit écrit noir sur blanc que l'exécution de code arbitraire via Bash n'est pas confinable sans sandbox OS (hors périmètre zéro-dépendance). **Conséquence non négociable : le critère d'acceptation de B-24d est reformulé avant codage en « tout accès fichier hors workspace via les outils structurés, et tout chemin littéral hors workspace dans une commande Bash, est refusé et journalisé »** — sinon on livre un critère non tenu, ce qui est pire qu'un critère honnête et réduit.

**Piège second — la garde est auto-révocable par le confiné.** `.claude/settings.json` et le script de garde vivent *dans* le workspace : l'agent a le droit d'y écrire, donc peut retirer son propre hook ou réécrire la garde. Décision corrective intégrée à B-24d : la racine de confinement exclut **en écriture** `.claude/settings.json`, `.claude/hooks/` et le script lui-même — la garde se protège elle-même, sinon elle est du théâtre.

Et deux risques connus à documenter sans prétendre les résoudre : la course symlink TOCTOU entre validation et accès (irréductible au niveau hook, sandbox OS requise), et la divergence de verrouillage POSIX/Windows du registre, couverte par le test de compatibilité de format de B-24d.
