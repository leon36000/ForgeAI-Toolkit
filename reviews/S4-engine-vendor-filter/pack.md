# Story S4 — « au choix » FILTRÉ par vendor (rejet moteur↔vendor incompatible)

## Gap comblé (recon gap #1 inference)
La validation de sélection ne vérifiait que l'EXISTENCE du moteur, jamais sa compatibilité avec le
vendor GPU du nœud cible. moteurs-inference.json porte pourtant gpu_vendors[] par moteur, inexploité.
Conséquence : tensorrt-llm (nvidia-only) assignable à un nœud AMD sans erreur.

## Changements
- Nouveau module `forgeai/engines.py` (FONCTIONS PURES, source = moteurs-inference.json) :
  engine_vendors, engine_supports_vendor, compatible_engines (la liste de choix FILTRÉE pour l'UI),
  incompatible_selections([{engine, vendor?}]) -> ['engine@vendor', ...] (entrée sans vendor ignorée).
- `cli.py` : la validation de sélection rejette (ABORT [SEL], exit 8) tout couple moteur↔vendor
  incompatible. Le vendor est lu des entrées BRUTES (non persisté au manifeste => rétrocompat totale).

## Critères (testés)
1. engine_supports_vendor('tensorrt-llm','amd')=False, ('...','nvidia')=True ; llama-cpp multi-vendor.
2. compatible_engines('amd') exclut tensorrt-llm/lorax/lmdeploy ; inclut llama-cpp/vllm.
3. incompatible_selections : signale tensorrt-llm@amd, ignore une entrée sans vendor.
4. CLI e2e : sélection {tensorrt-llm, vendor:amd} -> exit 8 'incompatible avec le vendor'.
5. Non-régression : retrocompat v1 + e2e web deploy inchangés (manifeste identique).
## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/cli.py b/src/forgeai/cli.py
index ce4124c..dda5f48 100644
--- a/src/forgeai/cli.py
+++ b/src/forgeai/cli.py
@@ -217,6 +217,20 @@ def wizard_ci(args: argparse.Namespace) -> int:
             print(f"ABORT [SEL] moteurs inconnus au registre des moteurs : {mauvais_moteurs}",
                   file=sys.stderr)
             return 8
+        # S4 : « au choix » FILTRÉ — un moteur incompatible avec le vendor du nœud cible est refusé
+        # (ex. tensorrt-llm sur un nœud AMD). Le vendor est lu des entrées BRUTES (non persisté au
+        # manifeste) ; une entrée sans vendor connu est ignorée (pas de faux rejet).
+        def _paires_vendor(brut, engine_defaut):
+            return [{"engine": str(e.get("engine", engine_defaut)), "vendor": str(e["vendor"])}
+                    for e in (brut or []) if isinstance(e, dict) and e.get("vendor")]
+        from forgeai.engines import incompatible_selections
+        incompat = incompatible_selections(
+            _paires_vendor(sel.get("models"), "vllm")
+            + _paires_vendor(sel.get("embeddings"), "llama-cpp"))
+        if incompat:
+            print(f"ABORT [SEL] moteur incompatible avec le vendor du nœud : {incompat}",
+                  file=sys.stderr)
+            return 8
         mauvais_noeuds = sorted({e["node"] for e in toutes if e["node"] not in ("local", "auto")
                                  and not node_re.match(e["node"])})
         if mauvais_noeuds:
diff --git a/src/forgeai/engines.py b/src/forgeai/engines.py
new file mode 100644
index 0000000..b302d45
--- /dev/null
+++ b/src/forgeai/engines.py
@@ -0,0 +1,45 @@
+"""Story S4 — compatibilité moteur↔vendor : le « au choix » FILTRÉ par vendor.
+
+Source de vérité unique : `data/moteurs-inference.json` (champ `gpu_vendors` par moteur). Permet
+de proposer/valider uniquement les moteurs compatibles avec le vendor GPU du nœud cible (ex.
+tensorrt-llm est nvidia-only → jamais sur un nœud AMD). Fonctions pures, sans I/O réseau.
+"""
+from __future__ import annotations
+
+import json
+from importlib.resources import files
+
+
+def _moteurs() -> list[dict]:
+    raw = (files("forgeai.data") / "moteurs-inference.json").read_text(encoding="utf-8")
+    return json.loads(raw)["moteurs"]
+
+
+def engine_vendors(engine_id: str) -> tuple[str, ...]:
+    """Vendors GPU supportés par un moteur (tuple vide si moteur inconnu)."""
+    for m in _moteurs():
+        if m.get("id") == engine_id:
+            return tuple(m.get("gpu_vendors", ()))
+    return ()
+
+
+def engine_supports_vendor(engine_id: str, vendor: str) -> bool:
+    """Le moteur supporte-t-il ce vendor ? (False si moteur inconnu ou vendor absent)."""
+    return vendor in engine_vendors(engine_id)
+
+
+def compatible_engines(vendor: str) -> list[str]:
+    """Liste des moteurs compatibles avec un vendor (la liste de choix FILTRÉE de l'UI)."""
+    return [m["id"] for m in _moteurs() if vendor in m.get("gpu_vendors", ())]
+
+
+def incompatible_selections(selections: list[dict]) -> list[str]:
+    """Signale les couples moteur↔vendor incompatibles d'une sélection [{engine, vendor?}, ...].
+    Une entrée sans `vendor` (vendor du nœud inconnu) est IGNORÉE — on ne peut pas la valider,
+    donc pas de faux rejet. Retourne une liste triée de 'engine@vendor'."""
+    bad = []
+    for e in selections:
+        vendor = e.get("vendor")
+        if vendor and not engine_supports_vendor(e.get("engine", ""), vendor):
+            bad.append(f"{e.get('engine', '')}@{vendor}")
+    return sorted(bad)
diff --git a/tests/test_engine_vendor_filter.py b/tests/test_engine_vendor_filter.py
new file mode 100644
index 0000000..00b6422
--- /dev/null
+++ b/tests/test_engine_vendor_filter.py
@@ -0,0 +1,50 @@
+"""Story S4 — « au choix » FILTRÉ par vendor : un moteur incompatible avec le vendor du nœud
+cible est rejeté à la sélection. Source de vérité : moteurs-inference.json (gpu_vendors par moteur).
+Ex. tensorrt-llm (nvidia-only) sur un nœud AMD => refusé. Une entrée sans vendor connu = ignorée.
+"""
+import sys
+from pathlib import Path
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.engines import (
+    compatible_engines,
+    engine_supports_vendor,
+    engine_vendors,
+    incompatible_selections,
+)
+
+
+def test_tensorrt_llm_nvidia_pas_amd():
+    assert engine_supports_vendor("tensorrt-llm", "nvidia") is True
+    assert engine_supports_vendor("tensorrt-llm", "amd") is False
+
+
+def test_llama_cpp_multi_vendor():
+    for v in ("nvidia", "amd", "intel", "cpu"):
+        assert engine_supports_vendor("llama-cpp", v) is True
+
+
+def test_compatible_engines_amd_exclut_nvidia_only():
+    amd = compatible_engines("amd")
+    assert "llama-cpp" in amd and "vllm" in amd
+    assert "tensorrt-llm" not in amd and "lorax" not in amd and "lmdeploy" not in amd
+
+
+def test_compatible_engines_nvidia_inclut_tensorrt():
+    nv = compatible_engines("nvidia")
+    assert "tensorrt-llm" in nv and "vllm" in nv
+
+
+def test_engine_inconnu_aucun_vendor():
+    assert engine_vendors("inexistant") == ()
+    assert engine_supports_vendor("inexistant", "nvidia") is False
+
+
+def test_incompatible_selections():
+    sels = [
+        {"engine": "tensorrt-llm", "vendor": "amd"},  # incompatible -> signalé
+        {"engine": "llama-cpp", "vendor": "amd"},     # compatible
+        {"engine": "vllm", "vendor": ""},             # vendor inconnu -> ignoré (pas de faux rejet)
+    ]
+    assert incompatible_selections(sels) == ["tensorrt-llm@amd"]
diff --git a/tests/test_selection_v2.py b/tests/test_selection_v2.py
index d1b7a51..4c6120c 100644
--- a/tests/test_selection_v2.py
+++ b/tests/test_selection_v2.py
@@ -63,6 +63,15 @@ def test_v2_moteur_inconnu(tmp_path: Path) -> None:
     assert "moteur-fantome" in res.stderr
 
 
+def test_v2_moteur_incompatible_vendor(tmp_path: Path) -> None:
+    # S4 : moteur nvidia-only (tensorrt-llm) assigné à un nœud AMD => ABORT [SEL] (choix filtré).
+    sel = {"models": [{"hf_id": "Qwen/Qwen3.6-27B", "node": "worker-amd",
+                       "engine": "tensorrt-llm", "vendor": "amd"}]}
+    res = _run_wizard(sel, tmp_path)
+    assert res.returncode == 8, res.stdout + res.stderr
+    assert "incompatible avec le vendor" in res.stderr
+
+
 def test_v2_embedding_mauvaise_famille(tmp_path: Path) -> None:
     sel = {"embeddings": [{"hf_id": "Qwen/Qwen3.6-27B", "node": "auto", "engine": "llama-cpp"}]}
     res = _run_wizard(sel, tmp_path)
```
## Preuve déterministe
```
..............                                                           [100%]
........................................................................ [ 89%]
...s................................................................     [100%]
All checks passed!
(cli.py : 17 fixables sur origin/main ET HEAD — aucun nouveau problème introduit)
```
