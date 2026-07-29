# Revue scellée TOUR 2 — B-24b : HookSpec, objections corrigées (commit d26de53)

## Contexte
Le tour 1 a rendu APPROVE 2/3 : REJECT de Gemini avec 5 objections (1 majeure).
Ce tour 2 les corrige TOUTES. Jugez le diff du tour 2 ET le traitement de chaque
objection — REJECT si une objection est mal traitée ou si le correctif introduit
un nouveau défaut.

## Traitement des objections (à vérifier une à une)
O1 (majeure, doublons str) : règles strictement identiques dédupliquées par égalité
    structurelle ; hooks=["A","A"] -> 1 règle (comportement historique restauré) ;
    deux HookSpec distincts même event -> agrégés.
O2 (str vides historiques) : durcissement assumé, documenté dans la docstring.
O3 (object.__setattr__) : re-validation À L'USAGE dans _normalize_hook, avec le
    pourquoi en docstring (la re-validation avait été retirée comme code mort au
    tour 1 — la revue a démontré qu'elle ne l'était pas).
O4 (whitespace-only) : validation par strip() sur les trois champs.
O5 (matcher non-str truthy) : isinstance(champ, str) exigé, message avec le type.

## Diff INTÉGRAL du tour 2 (commit précédent -> d26de53)
```diff
diff --git a/src/forgeai/ide/bootstrap.py b/src/forgeai/ide/bootstrap.py
index 4f49da2..aaedf17 100644
--- a/src/forgeai/ide/bootstrap.py
+++ b/src/forgeai/ide/bootstrap.py
@@ -16,25 +16,79 @@ class McpServer:
 
 @dataclass(frozen=True)
 class HookSpec:
+    """Spécification d'un hook claude-code (event + commande + matcher optionnel).
+
+    Invariants durcis (gelés par ``__post_init__`` ET revérifiés à l'usage dans
+    ``_normalize_hook`` — un appelant peut muter une instance frozen via
+    ``object.__setattr__``, ce qui contourne ``__post_init__`` ; c'est pourquoi
+    la validation est *aussi* re-effectuée à chaque consommation) :
+
+    - les trois champs doivent être des ``str`` (ni ``int``, ni ``list``, etc.) ;
+    - aucun champ ne doit être vide ni whitespace-only (un event/command/matcher
+      « mort » ne doit jamais atteindre le JSON).
+    """
+
     event: str
     command: str
     matcher: str = "*"
 
     def __post_init__(self):
-        if not self.event:
-            raise IDEError("HookSpec: 'event' vide")
-        if not self.command:
-            raise IDEError("HookSpec: 'command' vide")
-        if not self.matcher:
-            raise IDEError("HookSpec: 'matcher' vide")
+        # O2 : validation à la construction — type strict + non-vide après strip.
+        # O3 : le message d'erreur inclut le type reçu pour faciliter le diagnostic.
+        if not isinstance(self.event, str):
+            raise IDEError(
+                f"HookSpec: 'event' doit être str, reçu {type(self.event).__name__}"
+            )
+        if not isinstance(self.command, str):
+            raise IDEError(
+                f"HookSpec: 'command' doit être str, reçu {type(self.command).__name__}"
+            )
+        if not isinstance(self.matcher, str):
+            raise IDEError(
+                f"HookSpec: 'matcher' doit être str, reçu {type(self.matcher).__name__}"
+            )
+        if not self.event.strip():
+            raise IDEError("HookSpec: 'event' vide ou whitespace-only")
+        if not self.command.strip():
+            raise IDEError("HookSpec: 'command' vide ou whitespace-only")
+        if not self.matcher.strip():
+            raise IDEError("HookSpec: 'matcher' vide ou whitespace-only")
+
 
 def _normalize_hook(item):
-    if isinstance(item, HookSpec):
-        return item
+    """Normalise un élément de ``hooks`` en ``HookSpec``, avec re-validation défensive.
+
+    Pourquoi re-valider ici alors que ``HookSpec.__post_init__`` valide déjà ?
+    Parce qu'une dataclass ``frozen`` n'est gelée que par son ``__setattr__``
+    généré ; ``object.__setattr__(instance, ...)`` contourne cette protection.
+    Un appelant peut donc muter un ``HookSpec`` après construction ; la
+    validation de construction seule ne couvre pas ce chemin. On revérifie donc
+    les trois invariants (type str + strip non vide) à chaque consommation.
+    """
+    # Cas str : on construit un HookSpec canonique (event == command, matcher "*").
     if isinstance(item, str):
-        if not item:
-            raise IDEError("hook str vide")
+        if not item or not item.strip():
+            # O4 : durcissement VOLONTAIRE — chaîne vide / whitespace-only rejetée.
+            raise IDEError("hook str vide ou whitespace-only")
         return HookSpec(event=item, command=item, matcher="*")
+
+    # Cas HookSpec : on revérifie les trois champs (le contournement
+    # object.__setattr__ rend __post_init__ insuffisant).
+    if isinstance(item, HookSpec):
+        if not isinstance(item.event, str) or not item.event.strip():
+            raise IDEError(
+                f"HookSpec: 'event' invalide à l'usage (type={type(item.event).__name__})"
+            )
+        if not isinstance(item.command, str) or not item.command.strip():
+            raise IDEError(
+                f"HookSpec: 'command' invalide à l'usage (type={type(item.command).__name__})"
+            )
+        if not isinstance(item.matcher, str) or not item.matcher.strip():
+            raise IDEError(
+                f"HookSpec: 'matcher' invalide à l'usage (type={type(item.matcher).__name__})"
+            )
+        return item
+
     raise IDEError(f"type de hook invalide: {type(item).__name__}")
 
 def generate_mcp_config(ide: str, servers: list[McpServer]) -> IdeConfig:
@@ -69,6 +123,27 @@ def generate_mcp_config(ide: str, servers: list[McpServer]) -> IdeConfig:
     return IdeConfig(ide=ide, path=path, content=content_str, fmt="json")
 
 def generate_governance_config(skills: list[str], hooks: list[str | HookSpec], *, ide: str = "claude-code") -> IdeConfig:
+    """Construit ``.claude/settings.json`` (claude-code uniquement).
+
+    Chaque entrée de ``skills`` devient un élément de ``permissions.allow``.
+    Chaque entrée de ``hooks`` (str ou ``HookSpec``) devient une règle
+    ``{matcher, hooks:[{type: command, command}]}`` groupée par ``event``.
+
+    **Divergences assumées par rapport à l'historique (durcissement volontaire,
+    pas un bug)** :
+
+    - Une chaîne vide ou whitespace-only dans ``hooks`` (``[""]``, ``[" "]``)
+      lève ``IDEError`` au lieu d'être sérialisée comme une clé/event mort
+      dans le JSON (O4).
+    - Un ``HookSpec`` dont un champ n'est pas ``str`` ou est vide/whitespace
+      est rejeté — à la construction (``__post_init__``) ET à l'usage dans
+      ``_normalize_hook`` (un HookSpec peut être muté via
+      ``object.__setattr__`` après construction, ce qui contourne le
+      ``__post_init__`` d'une dataclass frozen).
+    - Les règles strictement identiques (même ``matcher`` ET même liste de
+      commandes) pour un même ``event`` sont dédupliquées ; deux ``HookSpec``
+      distincts sur le même event restent agrégés.
+    """
     if ide != "claude-code":
         raise IDEError("governance skills+hooks n'est supportée que pour claude-code")
     # Build permissions.allow from skills
@@ -81,7 +156,11 @@ def generate_governance_config(skills: list[str], hooks: list[str | HookSpec], *
             "matcher": spec.matcher,
             "hooks": [{"type": "command", "command": spec.command}],
         }
-        hooks_dict.setdefault(spec.event, []).append(rule)
+        bucket = hooks_dict.setdefault(spec.event, [])
+        # Égalité structurelle des dicts : même matcher + même contenu == même règle.
+        # Préserve l'historique (["A","A"] -> 1 règle) tout en agrégeant les DISTINCTES.
+        if rule not in bucket:
+            bucket.append(rule)
     content = {"permissions": permissions, "hooks": hooks_dict}
     content_str = json.dumps(content, ensure_ascii=False, indent=1)
     return IdeConfig(ide="claude-code", path=".claude/settings.json", content=content_str, fmt="json")
diff --git a/tests/test_ide_bootstrap.py b/tests/test_ide_bootstrap.py
index 522b60b..9aa3c87 100644
--- a/tests/test_ide_bootstrap.py
+++ b/tests/test_ide_bootstrap.py
@@ -213,3 +213,168 @@ class TestHookSpecNormalisation:
             spec.command = "autre"
         with pytest.raises(dataclasses.FrozenInstanceError):
             spec.matcher = "Edit"
+
+
+# O1 — déduplication stricte des règles identiques
+def test_hooks_str_doublon_produit_une_seule_regle():
+    """["A", "A"] : une seule règle, pas deux exécutions de la même commande."""
+    cfg = generate_governance_config(skills=["s"], hooks=["A", "A"])
+    data = json.loads(cfg.content)
+    assert data["hooks"]["A"] == [
+        {"matcher": "*", "hooks": [{"type": "command", "command": "A"}]}
+    ]
+    assert len(data["hooks"]["A"]) == 1
+
+
+def test_hooks_hookspec_doublon_strict_produit_une_seule_regle():
+    """[HookSpec(e, c1), HookSpec(e, c1)] : une seule règle (dedup strict)."""
+    cfg = generate_governance_config(
+        skills=["s"], hooks=[HookSpec("e", "c1"), HookSpec("e", "c1")]
+    )
+    data = json.loads(cfg.content)
+    assert len(data["hooks"]["e"]) == 1
+    assert data["hooks"]["e"][0]["matcher"] == "*"
+    assert data["hooks"]["e"][0]["hooks"][0]["command"] == "c1"
+
+
+def test_hooks_hookspec_distincts_sont_agreges():
+    """[HookSpec(e, c1, m1), HookSpec(e, c2, m2)] : DEUX règles (distinctes)."""
+    cfg = generate_governance_config(
+        skills=["s"],
+        hooks=[
+            HookSpec("e", "c1", "m1"),
+            HookSpec("e", "c2", "m2"),
+        ],
+    )
+    data = json.loads(cfg.content)
+    assert len(data["hooks"]["e"]) == 2
+    matchers = {r["matcher"] for r in data["hooks"]["e"]}
+    assert matchers == {"m1", "m2"}
+
+
+def test_hooks_str_et_hookpec_meme_event_et_meme_commande_dedupliques():
+    """["A", HookSpec("A","A")] : une seule règle (équivalence stricte)."""
+    cfg = generate_governance_config(
+        skills=["s"],
+        hooks=["A", HookSpec("A", "A")],
+    )
+    data = json.loads(cfg.content)
+    assert len(data["hooks"]["A"]) == 1
+
+
+def test_hooks_meme_event_mais_commandes_differentes_pas_dedupliques():
+    """["A", HookSpec("A", "B")] : deux règles (commandes différentes)."""
+    cfg = generate_governance_config(
+        skills=["s"],
+        hooks=["A", HookSpec("A", "B")],
+    )
+    data = json.loads(cfg.content)
+    assert len(data["hooks"]["A"]) == 2
+
+
+# O2+O3 — validation : type strict + whitespace + contournement object.__setattr__
+def test_hookspec_event_whitespace_leve_ideerror():
+    with pytest.raises(IDEError) as exc:
+        HookSpec(event=" ", command="c", matcher="*")
+    assert "event" in str(exc.value)
+
+
+def test_hookspec_command_whitespace_leve_ideerror():
+    with pytest.raises(IDEError) as exc:
+        HookSpec(event="e", command="   ", matcher="*")
+    assert "command" in str(exc.value)
+
+
+def test_hookspec_matcher_whitespace_leve_ideerror():
+    with pytest.raises(IDEError) as exc:
+        HookSpec(event="e", command="c", matcher="\t\n")
+    assert "matcher" in str(exc.value)
+
+
+def test_hookspec_matcher_liste_leve_ideerror_avec_type_dans_message():
+    with pytest.raises(IDEError) as exc:
+        HookSpec(event="e", command="c", matcher=["*"])
+    msg = str(exc.value)
+    assert "matcher" in msg
+    # O3 : le type reçu doit figurer dans le message pour faciliter le diagnostic.
+    assert "list" in msg
+
+
+def test_hookspec_event_int_leve_ideerror_avec_type_dans_message():
+    with pytest.raises(IDEError) as exc:
+        HookSpec(event=42, command="c", matcher="*")
+    msg = str(exc.value)
+    assert "event" in msg
+    assert "int" in msg
+
+
+def test_hookspec_command_int_leve_ideerror_avec_type_dans_message():
+    with pytest.raises(IDEError) as exc:
+        HookSpec(event="e", command=42, matcher="*")
+    msg = str(exc.value)
+    assert "command" in msg
+    assert "int" in msg
+
+
+def test_generate_governance_rejette_hookspec_mute_via_object_setattr():
+    """Le contournement object.__setattr__(frozen_hookspec, ...) doit être rattrapé
+    à l'usage (la validation de construction seule ne suffit pas)."""
+    spec = HookSpec(event="e", command="c", matcher="*")
+    # Bypass du gel : object.__setattr__ saute le __setattr__ généré par le
+    # décorateur @dataclass(frozen=True).
+    object.__setattr__(spec, "event", "")
+    with pytest.raises(IDEError) as exc:
+        generate_governance_config(skills=["s"], hooks=[spec])
+    assert "event" in str(exc.value)
+
+
+def test_generate_governance_rejette_hookspec_mute_command_whitespace():
+    spec = HookSpec(event="e", command="c", matcher="*")
+    object.__setattr__(spec, "command", "   ")
+    with pytest.raises(IDEError) as exc:
+        generate_governance_config(skills=["s"], hooks=[spec])
+    assert "command" in str(exc.value)
+
+
+def test_generate_governance_rejette_hookspec_mute_matcher_liste():
+    spec = HookSpec(event="e", command="c", matcher="*")
+    object.__setattr__(spec, "matcher", ["*"])
+    with pytest.raises(IDEError) as exc:
+        generate_governance_config(skills=["s"], hooks=[spec])
+    assert "matcher" in str(exc.value)
+    assert "list" in str(exc.value)
+
+
+def test_hookspec_vide_a_la_construction_leve_ideerror():
+    with pytest.raises(IDEError):
+        HookSpec(event="", command="c", matcher="*")
+
+
+# O4 — chaîne vide str : durcissement documenté
+def test_hook_str_vide_leve_ideerror():
+    with pytest.raises(IDEError):
+        generate_governance_config(skills=["s"], hooks=[""])
+
+
+def test_hook_str_whitespace_leve_ideerror():
+    with pytest.raises(IDEError):
+        generate_governance_config(skills=["s"], hooks=["   "])
+
+
+def test_docstring_generate_governance_documente_durcissement_chaine_vide():
+    """O4 : la docstring doit explicitement mentionner que la chaîne vide est
+    rejetée (durcissement volontaire, pas un bug)."""
+    doc = generate_governance_config.__doc__ or ""
+    # Présence d'au moins un mot-clé indiquant que la chaîne vide est rejetée.
+    lowered = doc.lower()
+    assert (
+        "chaîne vide" in lowered
+        or "chaine vide" in lowered
+        or ("vide" in lowered and "durcissement" in lowered)
+    )
+
+
+def test_docstring_generate_governance_documente_dedup_strict():
+    """O1 : la docstring doit mentionner la déduplication stricte des règles."""
+    doc = generate_governance_config.__doc__ or ""
+    assert "édupliqu" in doc.lower() or "dedupliqu" in doc.lower()
```

## Diff CUMULÉ vs origin/main (état final de la story)
```diff
diff --git a/src/forgeai/ide/bootstrap.py b/src/forgeai/ide/bootstrap.py
index 071bab3..aaedf17 100644
--- a/src/forgeai/ide/bootstrap.py
+++ b/src/forgeai/ide/bootstrap.py
@@ -14,6 +14,83 @@ class McpServer:
         if self.transport not in ("http", "sse"):
             raise IDEError(f"transport MCP invalide: {self.transport} (attendu http ou sse)")
 
+@dataclass(frozen=True)
+class HookSpec:
+    """Spécification d'un hook claude-code (event + commande + matcher optionnel).
+
+    Invariants durcis (gelés par ``__post_init__`` ET revérifiés à l'usage dans
+    ``_normalize_hook`` — un appelant peut muter une instance frozen via
+    ``object.__setattr__``, ce qui contourne ``__post_init__`` ; c'est pourquoi
+    la validation est *aussi* re-effectuée à chaque consommation) :
+
+    - les trois champs doivent être des ``str`` (ni ``int``, ni ``list``, etc.) ;
+    - aucun champ ne doit être vide ni whitespace-only (un event/command/matcher
+      « mort » ne doit jamais atteindre le JSON).
+    """
+
+    event: str
+    command: str
+    matcher: str = "*"
+
+    def __post_init__(self):
+        # O2 : validation à la construction — type strict + non-vide après strip.
+        # O3 : le message d'erreur inclut le type reçu pour faciliter le diagnostic.
+        if not isinstance(self.event, str):
+            raise IDEError(
+                f"HookSpec: 'event' doit être str, reçu {type(self.event).__name__}"
+            )
+        if not isinstance(self.command, str):
+            raise IDEError(
+                f"HookSpec: 'command' doit être str, reçu {type(self.command).__name__}"
+            )
+        if not isinstance(self.matcher, str):
+            raise IDEError(
+                f"HookSpec: 'matcher' doit être str, reçu {type(self.matcher).__name__}"
+            )
+        if not self.event.strip():
+            raise IDEError("HookSpec: 'event' vide ou whitespace-only")
+        if not self.command.strip():
+            raise IDEError("HookSpec: 'command' vide ou whitespace-only")
+        if not self.matcher.strip():
+            raise IDEError("HookSpec: 'matcher' vide ou whitespace-only")
+
+
+def _normalize_hook(item):
+    """Normalise un élément de ``hooks`` en ``HookSpec``, avec re-validation défensive.
+
+    Pourquoi re-valider ici alors que ``HookSpec.__post_init__`` valide déjà ?
+    Parce qu'une dataclass ``frozen`` n'est gelée que par son ``__setattr__``
+    généré ; ``object.__setattr__(instance, ...)`` contourne cette protection.
+    Un appelant peut donc muter un ``HookSpec`` après construction ; la
+    validation de construction seule ne couvre pas ce chemin. On revérifie donc
+    les trois invariants (type str + strip non vide) à chaque consommation.
+    """
+    # Cas str : on construit un HookSpec canonique (event == command, matcher "*").
+    if isinstance(item, str):
+        if not item or not item.strip():
+            # O4 : durcissement VOLONTAIRE — chaîne vide / whitespace-only rejetée.
+            raise IDEError("hook str vide ou whitespace-only")
+        return HookSpec(event=item, command=item, matcher="*")
+
+    # Cas HookSpec : on revérifie les trois champs (le contournement
+    # object.__setattr__ rend __post_init__ insuffisant).
+    if isinstance(item, HookSpec):
+        if not isinstance(item.event, str) or not item.event.strip():
+            raise IDEError(
+                f"HookSpec: 'event' invalide à l'usage (type={type(item.event).__name__})"
+            )
+        if not isinstance(item.command, str) or not item.command.strip():
+            raise IDEError(
+                f"HookSpec: 'command' invalide à l'usage (type={type(item.command).__name__})"
+            )
+        if not isinstance(item.matcher, str) or not item.matcher.strip():
+            raise IDEError(
+                f"HookSpec: 'matcher' invalide à l'usage (type={type(item.matcher).__name__})"
+            )
+        return item
+
+    raise IDEError(f"type de hook invalide: {type(item).__name__}")
+
 def generate_mcp_config(ide: str, servers: list[McpServer]) -> IdeConfig:
     if ide not in MCP_CAPABLE:
         raise IDEError(f"IDE '{ide}' ne supporte pas la configuration MCP")
@@ -45,16 +122,45 @@ def generate_mcp_config(ide: str, servers: list[McpServer]) -> IdeConfig:
     content_str = json.dumps(content, ensure_ascii=False, indent=1)
     return IdeConfig(ide=ide, path=path, content=content_str, fmt="json")
 
-def generate_governance_config(skills: list[str], hooks: list[str], *, ide: str = "claude-code") -> IdeConfig:
+def generate_governance_config(skills: list[str], hooks: list[str | HookSpec], *, ide: str = "claude-code") -> IdeConfig:
+    """Construit ``.claude/settings.json`` (claude-code uniquement).
+
+    Chaque entrée de ``skills`` devient un élément de ``permissions.allow``.
+    Chaque entrée de ``hooks`` (str ou ``HookSpec``) devient une règle
+    ``{matcher, hooks:[{type: command, command}]}`` groupée par ``event``.
+
+    **Divergences assumées par rapport à l'historique (durcissement volontaire,
+    pas un bug)** :
+
+    - Une chaîne vide ou whitespace-only dans ``hooks`` (``[""]``, ``[" "]``)
+      lève ``IDEError`` au lieu d'être sérialisée comme une clé/event mort
+      dans le JSON (O4).
+    - Un ``HookSpec`` dont un champ n'est pas ``str`` ou est vide/whitespace
+      est rejeté — à la construction (``__post_init__``) ET à l'usage dans
+      ``_normalize_hook`` (un HookSpec peut être muté via
+      ``object.__setattr__`` après construction, ce qui contourne le
+      ``__post_init__`` d'une dataclass frozen).
+    - Les règles strictement identiques (même ``matcher`` ET même liste de
+      commandes) pour un même ``event`` sont dédupliquées ; deux ``HookSpec``
+      distincts sur le même event restent agrégés.
+    """
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
+        bucket = hooks_dict.setdefault(spec.event, [])
+        # Égalité structurelle des dicts : même matcher + même contenu == même règle.
+        # Préserve l'historique (["A","A"] -> 1 règle) tout en agrégeant les DISTINCTES.
+        if rule not in bucket:
+            bucket.append(rule)
     content = {"permissions": permissions, "hooks": hooks_dict}
     content_str = json.dumps(content, ensure_ascii=False, indent=1)
     return IdeConfig(ide="claude-code", path=".claude/settings.json", content=content_str, fmt="json")
```

## Preuve d'exécution CAPTURÉE (rejouée après le commit d26de53)
```
$ python3 -m pytest tests/test_ide_bootstrap.py tests/test_ide.py -q
...........................................                              [100%]
exit=0

# mutations tour 2 (substitution vérifiée avant interprétation)
  dédup retirée              : ROUGE (exit 1)
  strip() affaibli           : ROUGE (exit 1)
  isinstance retiré          : ROUGE (exit 1)
  re-validation neutralisée  : ROUGE (exit 1)
  restauration               : VERT  (exit 0)
$ no_stub_scan : OK ; suite complète : exit=0
```
