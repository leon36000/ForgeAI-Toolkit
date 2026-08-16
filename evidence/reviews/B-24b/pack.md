# Revue scellée — B-24b : HookSpec (commit f744dfb)

## Story et contexte
Deuxième des quatre stories du confinement filesystem (ADR en annexe, décision n°1).
Périmètre : UNIQUEMENT le découplage événement/commande/matcher dans
generate_governance_config. La génération du script de garde (B-24c) et le
comportement runtime (B-24d) suivent — ne jugez pas leur absence.

## Critères d'acceptation
CA-1 : les tests existants passent SANS modification (une str produit exactement
       la forme historique : event==command, matcher "*").
CA-2 : HookSpec(event, command, matcher) produit la structure
       {event: [{matcher, hooks: [{type: "command", command}]}]} ; deux HookSpec
       même event s'agrègent, ordre préservé.
CA-3 : validation au __post_init__ : event/command/matcher vides -> IDEError ;
       dataclass gelée ; type inattendu dans la liste -> IDEError.
CA-4 : stdlib uniquement ; verify_bootstrap inchangé.

## Ce qu'il faut chercher (adversarial)
- une entrée qui produit un settings.json invalide pour l'IDE cible (structure
  hooks de Claude Code) ;
- un cas où la normalisation str diverge du comportement historique ;
- une validation contournable (HookSpec construit puis muté ? object.__setattr__ ?
  dites si c'est un risque réel ou théorique) ;
- un test qui semble couvrir mais ne détecte pas.

## Diff INTÉGRAL vs origin/main
```diff
diff --git a/src/forgeai/ide/bootstrap.py b/src/forgeai/ide/bootstrap.py
index 071bab3..4f49da2 100644
--- a/src/forgeai/ide/bootstrap.py
+++ b/src/forgeai/ide/bootstrap.py
@@ -14,6 +14,29 @@ class McpServer:
         if self.transport not in ("http", "sse"):
             raise IDEError(f"transport MCP invalide: {self.transport} (attendu http ou sse)")
 
+@dataclass(frozen=True)
+class HookSpec:
+    event: str
+    command: str
+    matcher: str = "*"
+
+    def __post_init__(self):
+        if not self.event:
+            raise IDEError("HookSpec: 'event' vide")
+        if not self.command:
+            raise IDEError("HookSpec: 'command' vide")
+        if not self.matcher:
+            raise IDEError("HookSpec: 'matcher' vide")
+
+def _normalize_hook(item):
+    if isinstance(item, HookSpec):
+        return item
+    if isinstance(item, str):
+        if not item:
+            raise IDEError("hook str vide")
+        return HookSpec(event=item, command=item, matcher="*")
+    raise IDEError(f"type de hook invalide: {type(item).__name__}")
+
 def generate_mcp_config(ide: str, servers: list[McpServer]) -> IdeConfig:
     if ide not in MCP_CAPABLE:
         raise IDEError(f"IDE '{ide}' ne supporte pas la configuration MCP")
@@ -45,16 +68,20 @@ def generate_mcp_config(ide: str, servers: list[McpServer]) -> IdeConfig:
     content_str = json.dumps(content, ensure_ascii=False, indent=1)
     return IdeConfig(ide=ide, path=path, content=content_str, fmt="json")
 
-def generate_governance_config(skills: list[str], hooks: list[str], *, ide: str = "claude-code") -> IdeConfig:
+def generate_governance_config(skills: list[str], hooks: list[str | HookSpec], *, ide: str = "claude-code") -> IdeConfig:
     if ide != "claude-code":
         raise IDEError("governance skills+hooks n'est supportée que pour claude-code")
     # Build permissions.allow from skills
     permissions = {"allow": skills}
     # Build hooks: each hook becomes a key with a list of one matcher rule
-    hooks_dict = {
-        hook: [{"matcher": "*", "hooks": [{"type": "command", "command": hook}]}]
-        for hook in hooks
-    }
+    hooks_dict: dict[str, list[dict]] = {}
+    for item in hooks:
+        spec = _normalize_hook(item)
+        rule = {
+            "matcher": spec.matcher,
+            "hooks": [{"type": "command", "command": spec.command}],
+        }
+        hooks_dict.setdefault(spec.event, []).append(rule)
     content = {"permissions": permissions, "hooks": hooks_dict}
     content_str = json.dumps(content, ensure_ascii=False, indent=1)
     return IdeConfig(ide="claude-code", path=".claude/settings.json", content=content_str, fmt="json")
diff --git a/tests/test_ide_bootstrap.py b/tests/test_ide_bootstrap.py
index 2ca1d0a..522b60b 100644
--- a/tests/test_ide_bootstrap.py
+++ b/tests/test_ide_bootstrap.py
@@ -133,3 +133,83 @@ def test_cli_ide_mcp_et_governance(tmp_path):
     gov = json.loads(gov_file.read_text(encoding="utf-8"))
     assert "Skill(read)" in gov["permissions"]["allow"]
     assert "pre-commit-guard" in gov["hooks"]
+
+
+import dataclasses
+from forgeai.ide.bootstrap import HookSpec
+
+
+class TestHookSpecNormalisation:
+
+    def test_hookspec_seul_genere_un_dict_avec_matcher_explicite(self):
+        """HookSpec seul -> clé unique, matcher explicite, structure complète."""
+        spec = HookSpec(event="PreToolUse", command="python3 /x/garde.py", matcher="Write|Edit")
+        cfg = generate_governance_config(skills=[], hooks=[spec])
+        hooks = json.loads(cfg.content)["hooks"]
+        assert hooks == {
+            "PreToolUse": [
+                {
+                    "matcher": "Write|Edit",
+                    "hooks": [{"type": "command", "command": "python3 /x/garde.py"}],
+                }
+            ]
+        }
+
+    def test_melange_str_et_hookspec_coexistent_avec_forme_historique_pour_str(self):
+        """Mélange str + HookSpec -> deux clés ; la str garde event==command et matcher '*'."""
+        spec = HookSpec(event="PreToolUse", command="cmd")
+        cfg = generate_governance_config(
+            skills=[],
+            hooks=["SessionStart", spec],
+        )
+        hooks = json.loads(cfg.content)["hooks"]
+        assert set(hooks.keys()) == {"SessionStart", "PreToolUse"}
+        assert hooks["SessionStart"] == [
+            {
+                "matcher": "*",
+                "hooks": [{"type": "command", "command": "SessionStart"}],
+            }
+        ]
+        assert hooks["PreToolUse"] == [
+            {
+                "matcher": "*",
+                "hooks": [{"type": "command", "command": "cmd"}],
+            }
+        ]
+
+    def test_deux_hookspec_meme_event_une_seule_cle_ordre_preservé(self):
+        """Deux HookSpec sur le même event -> une seule clé, deux règles, ordre d'origine conservé."""
+        spec1 = HookSpec(event="PreToolUse", command="a", matcher="Write")
+        spec2 = HookSpec(event="PreToolUse", command="b", matcher="Edit")
+        cfg = generate_governance_config(skills=[], hooks=[spec1, spec2])
+        hooks = json.loads(cfg.content)["hooks"]
+        assert list(hooks.keys()) == ["PreToolUse"]
+        assert hooks["PreToolUse"] == [
+            {
+                "matcher": "Write",
+                "hooks": [{"type": "command", "command": "a"}],
+            },
+            {
+                "matcher": "Edit",
+                "hooks": [{"type": "command", "command": "b"}],
+            },
+        ]
+
+    def test_champs_vides_levent_ideerror(self):
+        """event / command / matcher vides -> IDEError (vérif via __post_init__)."""
+        with pytest.raises(IDEError):
+            HookSpec(event="", command="cmd")
+        with pytest.raises(IDEError):
+            HookSpec(event="PreToolUse", command="")
+        with pytest.raises(IDEError):
+            HookSpec(event="PreToolUse", command="cmd", matcher="")
+
+    def test_hookspec_est_gelee(self):
+        """HookSpec est frozen -> toute affectation d'attribut lève FrozenInstanceError."""
+        spec = HookSpec(event="PreToolUse", command="cmd")
+        with pytest.raises(dataclasses.FrozenInstanceError):
+            spec.event = "PostToolUse"
+        with pytest.raises(dataclasses.FrozenInstanceError):
+            spec.command = "autre"
+        with pytest.raises(dataclasses.FrozenInstanceError):
+            spec.matcher = "Edit"
```

## Preuve d'exécution CAPTURÉE (rejouée après commit)
```
$ python3 -m pytest tests/test_ide_bootstrap.py tests/test_ide.py -q
........................                                                 [100%]
exit=0

# mutations (substitution vérifiée avant interprétation)
  matcher du HookSpec ignoré (force '*')     : ROUGE (exit 1)
  agrégation écrasée (une règle par event)   : ROUGE (exit 1)
  normalisation str perd la commande         : ROUGE (exit 1)
  restauration                               : VERT  (exit 0)
$ no_stub_scan (2 fichiers) : OK ; suite complète : exit=0
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
