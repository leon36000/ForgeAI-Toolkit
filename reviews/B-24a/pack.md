# Revue scellée — B-24a : validateur de chemin partagé (commit e33758e)

## Story et contexte
Première des quatre stories du confinement filesystem (B-24, décision d'architecte
jointe en annexe). Périmètre : UNIQUEMENT la décision n°4 de l'ADR — extraire un
validateur de chemin réutilisable et refactorer le seul duplicat existant. Les
stories HookSpec / génération de la garde / comportement runtime suivront ;
ne jugez PAS leur absence ici.

## Critères d'acceptation de CETTE story (tous doivent être tenus)
CA-1 : resolve_within rejette `..` sortant, symlink sortant, chemin hors racine,
       répertoire frère à préfixe commun (/repo vs /repo-evil) ; accepte symlink
       entrant (racine symlinkée, cas macOS), `..` interne restant dedans, la
       racine elle-même, et une cible inexistante (écriture future).
CA-2 : realpath des DEUX côtés ; comparaison commonpath après normcase ;
       ValueError de commonpath convertie en ValidationError.
CA-3 : models/local.py refactoré vers le validateur ; message d'erreur STRICTEMENT
       identique ; ses 15 tests existants verts sans modification.
CA-4 : aucune dépendance externe (le produit a dependencies=[]).

## Ce qu'il faut chercher (adversarial)
- un chemin qui contourne le confinement malgré resolve_within (encodages, chemins
  UNC Windows, casse, `base` relatif, root lui-même relatif…) ;
- une régression de comportement de download_verified (le chemin retourné est
  désormais RÉSOLU — durcissement assumé : dites si cela peut casser un appelant) ;
- un test qui semble couvrir mais ne détecte pas.

## Diff INTÉGRAL vs origin/main
```diff
diff --git a/src/forgeai/core/validation.py b/src/forgeai/core/validation.py
index 1a70af8..c02d0e5 100644
--- a/src/forgeai/core/validation.py
+++ b/src/forgeai/core/validation.py
@@ -1,6 +1,64 @@
 """Validateurs partagés (source unique — évite la duplication CLI ↔ web ↔ …)."""
+import os
 import re
+from pathlib import Path
 
 # Nom de nœud / hôte : label RFC1123 en minuscules (a-z0-9, tirets/points internes, 1-63 car.).
 # Source UNIQUE réutilisée par cli.py et web/server.py (FAI-0016 : dé-duplication).
 NODE_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,62})$", re.ASCII)
+
+
+class ValidationError(ValueError):
+    """Erreur de validation d'un chemin ou d'un nom."""
+
+
+def valider_nom_simple(name: str) -> None:
+    """Lève ValidationError si le nom est vide, vaut '.', contient '/', os.sep ou '..'."""
+    if (
+        not name
+        or name == "."
+        or "/" in name
+        or os.sep in name
+        or ".." in name
+    ):
+        raise ValidationError(f"nom invalide : {name!r}")
+
+
+def resolve_within(
+    path: str | os.PathLike[str],
+    root: str | os.PathLike[str],
+    *,
+    base: str | os.PathLike[str] | None = None,
+) -> Path:
+    """Résout `path` et vérifie qu'il est contenu dans `root` (realpath des deux côtés)."""
+    path_str = os.fspath(path)
+    root_str = os.fspath(root)
+
+    if not os.path.isabs(path_str):
+        if base is not None:
+            base_str = os.fspath(base)
+            resolved = os.path.join(base_str, path_str)
+        else:
+            resolved = path_str
+    else:
+        resolved = path_str
+
+    cible_reelle = os.path.realpath(resolved)
+    racine_reelle = os.path.realpath(root_str)
+
+    cible_norm = os.path.normcase(cible_reelle)
+    racine_norm = os.path.normcase(racine_reelle)
+
+    try:
+        common = os.path.commonpath([racine_norm, cible_norm])
+    except ValueError as exc:
+        raise ValidationError(
+            f"chemin hors racine : {cible_reelle!r} n'est pas dans {racine_reelle!r}"
+        ) from exc
+
+    if common != racine_norm:
+        raise ValidationError(
+            f"chemin hors racine : {cible_reelle!r} n'est pas dans {racine_reelle!r}"
+        )
+
+    return Path(cible_reelle)
diff --git a/src/forgeai/models/local.py b/src/forgeai/models/local.py
index c901dcc..211a5eb 100644
--- a/src/forgeai/models/local.py
+++ b/src/forgeai/models/local.py
@@ -18,6 +18,7 @@ from pathlib import Path
 from typing import Callable, Protocol
 
 from ..core.runner import CommandRunner
+from ..core.validation import ValidationError, resolve_within, valider_nom_simple
 from .probe import ProbeResult, Transport, probe_route
 
 
@@ -82,13 +83,11 @@ def download_verified(model: LocalModel, dest_dir: Path, fetcher: Fetcher) -> Pa
     on vérifie, PUIS on renomme atomiquement vers la destination finale. Ainsi le fichier
     présent à `dest` est toujours exactement l'artefact vérifié (pas de fenêtre de
     substitution entre vérification et usage)."""
-    if "/" in model.name or os.sep in model.name or ".." in model.name:
-        raise LocalModelError(f"nom de modèle invalide : {model.name}")
-    dest = Path(dest_dir) / f"{model.name}.bin"
-    dest_resolved = dest.resolve()
-    dest_dir_resolved = Path(dest_dir).resolve()
-    if not dest_resolved.is_relative_to(dest_dir_resolved):
-        raise LocalModelError(f"nom de modèle invalide : {model.name}")
+    try:
+        valider_nom_simple(model.name)
+        dest = resolve_within(Path(dest_dir) / f"{model.name}.bin", dest_dir)
+    except ValidationError:
+        raise LocalModelError(f"nom de modèle invalide : {model.name}") from None
     tmp = dest.with_suffix(".part")
     fetcher.fetch(model.download_url, tmp)
     actual = _sha256_file(tmp)
diff --git a/tests/test_core_validation.py b/tests/test_core_validation.py
new file mode 100644
index 0000000..c4a6db3
--- /dev/null
+++ b/tests/test_core_validation.py
@@ -0,0 +1,156 @@
+"""Tests pour src/forgeai/core/validation.py."""
+import os
+from pathlib import Path
+
+import pytest
+
+from forgeai.core.validation import (
+    NODE_NAME_RE,
+    ValidationError,
+    resolve_within,
+    valider_nom_simple,
+)
+
+
+# --- valider_nom_simple ---
+
+
+def test_valider_nom_simple_valide():
+    assert valider_nom_simple("abc") is None
+    assert valider_nom_simple("a-b") is None
+    assert valider_nom_simple("a.b") is None
+    assert valider_nom_simple("x") is None
+
+
+def test_valider_nom_simple_slash():
+    with pytest.raises(ValidationError):
+        valider_nom_simple("a/b")
+
+
+def test_valider_nom_simple_double_point():
+    with pytest.raises(ValidationError):
+        valider_nom_simple("..")
+
+
+def test_valider_nom_simple_double_point_inclus():
+    # "a..b" contient ".." donc rejeté par le prédicat `".." in name`.
+    with pytest.raises(ValidationError):
+        valider_nom_simple("a..b")
+
+
+def test_valider_nom_simple_vide():
+    with pytest.raises(ValidationError):
+        valider_nom_simple("")
+
+
+def test_valider_nom_simple_point():
+    with pytest.raises(ValidationError):
+        valider_nom_simple(".")
+
+
+# --- resolve_within ---
+
+
+def test_resolve_within_absolu_dans_racine(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    cible = root / "file"
+    cible.write_text("x")
+    result = resolve_within(cible, root)
+    assert result == Path(os.path.realpath(cible))
+
+
+def test_resolve_within_racine_ellememe(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    result = resolve_within(root, root)
+    assert result == Path(os.path.realpath(root))
+
+
+def test_resolve_within_relatif_avec_base(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    cible = root / "file"
+    cible.write_text("x")
+    result = resolve_within("file", root, base=root)
+    assert result == Path(os.path.realpath(cible))
+
+
+def test_resolve_within_double_point_sortant(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    cible = root / ".." / "other"
+    with pytest.raises(ValidationError):
+        resolve_within(cible, root)
+
+
+def test_resolve_within_double_point_interne(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    cible = root / "a" / ".." / "b"
+    result = resolve_within(cible, root)
+    assert result == Path(os.path.realpath(root / "b"))
+
+
+def test_resolve_within_symlink_sortant(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    dehors = tmp_path / "dehors"
+    dehors.mkdir()
+    lien = root / "lien"
+    os.symlink(dehors, lien)
+    with pytest.raises(ValidationError):
+        resolve_within(lien, root)
+
+
+def test_resolve_within_symlink_entrant(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    cible = root / "file"
+    cible.write_text("x")
+    lien_racine = tmp_path / "lien_racine"
+    os.symlink(root, lien_racine)
+    result = resolve_within(lien_racine / "file", lien_racine)
+    assert result == Path(os.path.realpath(cible))
+
+
+def test_resolve_within_cible_inexistante_dans_racine(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    cible = root / "future"
+    result = resolve_within(cible, root)
+    assert result == Path(os.path.realpath(cible))
+
+
+def test_resolve_within_cible_inexistante_hors_racine(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    cible = tmp_path / "future"
+    with pytest.raises(ValidationError):
+        resolve_within(cible, root)
+
+
+def test_resolve_within_message_erreur(tmp_path):
+    root = tmp_path / "root"
+    root.mkdir()
+    cible = tmp_path / "dehors"
+    with pytest.raises(ValidationError) as exc_info:
+        resolve_within(cible, root)
+    msg = str(exc_info.value)
+    assert os.path.realpath(str(cible)) in msg
+    assert os.path.realpath(str(root)) in msg
+
+
+def test_resolve_within_rejette_repertoire_frere_prefixe_commun(tmp_path):
+    repo = tmp_path / "repo"
+    repo.mkdir()
+    repo_evil = tmp_path / "repo-evil"
+    repo_evil.mkdir()
+    cible_evil = repo_evil / "x.txt"
+    cible_evil.write_text("x")
+    with pytest.raises(ValidationError):
+        resolve_within(cible_evil, repo)
+    cible_ok = repo / "x.txt"
+    cible_ok.write_text("x")
+    result = resolve_within(cible_ok, repo)
+    assert result == Path(os.path.realpath(cible_ok))
```

## Preuve d'exécution CAPTURÉE (rejouée après le commit e33758e)
```
$ python3 -m pytest tests/test_core_validation.py tests/test_models_local.py -q
................................                                         [100%]
exit=0

# campagne de mutations (substitution vérifiée avant interprétation)
  realpath(cible)->abspath        : suite ROUGE (exit 1)
  realpath(racine)->abspath       : suite ROUGE (exit 1)
  comparaison neutralisée (False) : suite ROUGE (exit 1)
  retrait du filtre '..'          : suite ROUGE (exit 1)
  commonpath->startswith          : suite ROUGE (exit 1) — après ajout du test frère-préfixe
  restauration                    : suite VERTE (exit 0)

$ python3 scripts/no_stub_scan.py <3 fichiers> : OK, zéro violation
$ suite complète : exit=0
```

## Annexe — ADR B-24 (contexte, déjà tranché, ne pas re-juger)
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
