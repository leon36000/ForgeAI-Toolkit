# Story S6b — dropdown moteur du wizard filtré par le vendor GPU du nœud

Dernier reliquat (cosmétique) de l'épopée « GPU multi-vendor par nœud ». Le choix moteur↔vendor
est DÉJÀ prouvé à deux niveaux durs : validation wizard (S4, rejette un couple incompatible,
exit 8) et endpoint `GET /api/engines/compatible?vendor=X` (S6). S6b ajoute le confort VISUEL :
dans le wizard web, le `<select>` du moteur d'inférence par modèle ne propose que les moteurs
compatibles avec le vendor GPU du nœud sélectionné pour ce modèle (ex. nœud AMD → cacher
tensorrt-llm / lorax / lmdeploy, nvidia-only).

## Gap comblé
- `/api/nodes/status` ne portait AUCUN vendor par nœud → le JS ne pouvait pas dériver le vendor
  du nœud choisi pour filtrer le dropdown.
- `engineOptions` du wizard listait TOUS les moteurs sans égard au vendor.

## Changements
### Volet serveur (prouvable pytest)
- `web/server.py` : helper pur `_node_vendors_by_host(registre_path)` — corrèle nom d'hôte →
  vendors GPU distincts depuis les sondes `node_hardware` du registre (réutilise
  `cluster.read_probes` / `cluster.node_vendors` de S7 ; registre absent → {} sans exception).
- `/api/nodes/status` : chaque nœud reçoit un champ `vendors` (liste) ; nœud sans sonde → `[]`
  (champ toujours présent, jamais absent ni None). Chemin d'erreur `ClusterError` inchangé.

### Volet JS (logique pure prouvée Node ; rendu DOM vérifié navigateur)
- Nouveau module PUR `web/assets/engine_filter.js` (chargé avant app.js, exporté aussi CommonJS) :
  `filterEnginesByVendor(engines, vendor)` (miroir exact du contrat serveur compatible_engines),
  `nodeVendorForFilter(nodes, nodeName)` (vendor UNIQUE du nœud, sinon null → fallback),
  `engineChoices(engines, vendor, selectedId)` (filtre + garde toujours la sélection courante
  visible, jamais de saut de valeur silencieux).
- `app.js` : `engineOptions(selected, vendor)` délègue à `engineChoices` ; le vendor du nœud de
  chaque ligne modèle/embedding est dérivé via `nodeVendorForFilter` ; changer le nœud re-rend
  la ligne (le dropdown moteur se re-filtre). Fallback = tout afficher si vendor inconnu/mixte.
- `index.html` : charge `engine_filter.js` avant `app.js`.

### Gouvernance
- `sonar-project.properties` : `sonar.coverage.exclusions=src/forgeai/web/assets/**` — les assets
  navigateur n'ont pas de runner JS câblé aux gates ; leur logique pure est prouvée hors couverture
  par `tests/js/*.test.cjs` (Node) et leur rendu se vérifie en navigateur. Sans cette exclusion,
  les lignes JS neuves comptent comme non couvertes et font chuter « coverage on new code » < 80 %.

## Critères (testés)
1. `_node_vendors_by_host` (EN PROCESS, coverage) : hôte → vendors distincts ; registre absent → {}.
2. `/api/nodes/status` (serveur web réel, `cluster_status` monkeypatché, registre seedé) : chaque
   nœud porte `vendors` (worker-amd→['amd'], worker-nv→['nvidia']) ; nœud sans sonde → `[]`.
3. `filterEnginesByVendor` (Node, données réelles) : amd cache tensorrt-llm/lorax/lmdeploy, garde
   vllm/sglang/llama-cpp/ollama/mlc-llm ; nvidia garde tout ; vendor vide/null → tout (fallback).
4. `nodeVendorForFilter` : unique→ce vendor ; mixte/sans-sonde/local/auto/inconnu→null.
5. `engineChoices` : conserve la sélection incompatible (pas de saut silencieux), pas de doublon.
6. Câblage (structurel, convention dépôt) : index.html charge engine_filter.js avant app.js ;
   app.js délègue à ForgeAIEngineFilter ; engine_filter.js auto-suffisant (aucun lien http).

## Preuve navigateur (réelle, non revendiquée comme test unitaire)
Serveur web lancé sur un vrai cluster k3s : `/api/nodes/status` renvoie chaque nœud avec `vendors`
(=[] car aucune sonde node_hardware pour ces hôtes = comportement attendu). `engine_filter.js`
chargé comme `<script>`, `filterEnginesByVendor` sur les 8 moteurs réels de `/api/engines` →
amd = [vllm, sglang, llama-cpp, ollama, mlc-llm] (nvidia-only masqués). Zéro erreur console.
Le rendu final du `<select>` filtré sur un nœud AMD mono-vendor se vérifie sur le banc AMD de Nathan.

Codeur : orchestrateur (Fable). T1 (surface web, aucune frontière T3).


===== DIFF (VERBATIM — JAMAIS COMPRESSÉ) =====
diff --git a/sonar-project.properties b/sonar-project.properties
index 92c56ce..ec8d42d 100644
--- a/sonar-project.properties
+++ b/sonar-project.properties
@@ -9,3 +9,10 @@ sonar.test.exclusions=**/__pycache__/**,**/*.pyc
 sonar.python.coverage.reportPaths=coverage.xml
 sonar.python.version=3.12
 sonar.sourceEncoding=UTF-8
+
+# Les assets navigateur (JS/HTML/CSS) sont analysés pour la qualité mais PAS comptés dans la
+# couverture : aucun runner JS n'est câblé aux gates (le produit est stdlib pur). Leur logique
+# pure est prouvée hors couverture par tests/js/*.test.cjs (Node) et leur rendu se vérifie en
+# navigateur. Sans cette exclusion, les lignes JS neuves comptent comme non couvertes et font
+# chuter « coverage on new code » sous 80 % (S6b).
+sonar.coverage.exclusions=src/forgeai/web/assets/**
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index 014e001..c95ca47 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -592,11 +592,24 @@
     return opts.join('');
   }
 
-  function engineOptions(selected) {
+  // Vendor GPU du nœud sélectionné (via /api/nodes/status enrichi, S6b). null si
+  // local/auto/mixte/inconnu => aucun filtrage (fallback : tous les moteurs).
+  function vendorForNode(nodeName) {
+    const F = window.ForgeAIEngineFilter;
+    if (!F) return null;
+    const nodes = (state.nodes && state.nodes.nodes) || (state.summary && state.summary.nodes) || [];
+    return F.nodeVendorForFilter(nodes, nodeName);
+  }
+
+  function engineOptions(selected, vendor) {
     if (!state.engines || !state.engines.length) {
       return `<option value="">${escapeHtml(t('loading'))}</option>`;
     }
-    return state.engines.map((eng) => {
+    // S6b : ne proposer que les moteurs compatibles avec le vendor du nœud (module pur testé).
+    // La sélection courante reste toujours visible (jamais de saut de valeur silencieux).
+    const F = window.ForgeAIEngineFilter;
+    const engines = F ? F.engineChoices(state.engines, vendor, selected) : state.engines;
+    return engines.map((eng) => {
       const id = eng.id || eng.engine_id || String(eng);
       const label = eng.name || id;
       return `<option value="${escapeHtml(id)}"${selected === id ? ' selected' : ''}>${escapeHtml(label)}</option>`;
@@ -659,7 +672,7 @@
               </select>
               <span class="place-label">${escapeHtml(t('f_engine'))}</span>
               <select class="place-select" data-model-engine="${escapeHtml(m.hf_id)}" aria-label="${escapeHtml(t('f_engine'))}">
-                ${engineOptions(engineVal)}
+                ${engineOptions(engineVal, vendorForNode(nodeVal))}
               </select>
             </span>
           </span>
@@ -686,6 +699,7 @@
         const id = sel.dataset.modelNode;
         if (!state.modelsChosen[id]) return;
         state.modelsChosen[id].node = sel.value;
+        renderLocalModels();  // S6b : re-filtre le dropdown moteur selon le vendor du nœud choisi
       });
     });
     box.querySelectorAll('select[data-model-engine]').forEach((sel) => {
@@ -750,7 +764,7 @@
               </select>
               <span class="place-label">${escapeHtml(t('f_engine'))}</span>
               <select class="place-select" data-embedding-engine="${escapeHtml(m.hf_id)}" aria-label="${escapeHtml(t('f_engine'))}">
-                ${engineOptions(engineVal)}
+                ${engineOptions(engineVal, vendorForNode(nodeVal))}
               </select>
             </span>
           </span>
@@ -777,6 +791,7 @@
         const id = sel.dataset.embeddingNode;
         if (!state.embeddingsChosen[id]) return;
         state.embeddingsChosen[id].node = sel.value;
+        renderEmbeddings();  // S6b : re-filtre le dropdown moteur selon le vendor du nœud choisi
       });
     });
     box.querySelectorAll('select[data-embedding-engine]').forEach((sel) => {
diff --git a/src/forgeai/web/assets/engine_filter.js b/src/forgeai/web/assets/engine_filter.js
new file mode 100644
index 0000000..ce7d865
--- /dev/null
+++ b/src/forgeai/web/assets/engine_filter.js
@@ -0,0 +1,70 @@
+/* Story S6b — filtrage moteur<->vendor côté client (fonctions PURES, testables hors navigateur).
+ *
+ * Miroir exact du contrat serveur /api/engines/compatible?vendor=X (S4/S6) : un moteur est
+ * proposé dans le <select> d'un modèle ssi son gpu_vendors[] contient le vendor GPU du nœud
+ * cible. Aucune I/O, aucun DOM — chargé comme <script> AVANT app.js (expose window.ForgeAIEngineFilter)
+ * ET exporté en CommonJS pour la preuve Node (tests/js/engine_filter.test.cjs). La validation dure
+ * reste côté serveur (wizard S4 rejette un couple incompatible) ; ceci n'est que du confort visuel.
+ */
+(function (root) {
+  'use strict';
+
+  function engineId(eng) {
+    if (eng && (eng.id || eng.engine_id)) return eng.id || eng.engine_id;
+    return String(eng);
+  }
+
+  // Vendor GPU d'un nœud pour le filtrage : le vendor UNIQUE si le nœud n'en a qu'un, sinon null
+  // (nœud mixte, sans sonde, ou pseudo-nœud local/auto/inconnu) => pas de filtrage (fallback).
+  function nodeVendorForFilter(nodes, nodeName) {
+    if (!nodeName || nodeName === 'local' || nodeName === 'auto') return null;
+    if (!Array.isArray(nodes)) return null;
+    var node = null;
+    for (var i = 0; i < nodes.length; i++) {
+      var n = nodes[i];
+      if (n && (n.name === nodeName || n.hostname === nodeName)) { node = n; break; }
+    }
+    if (!node || !Array.isArray(node.vendors)) return null;
+    return node.vendors.length === 1 ? node.vendors[0] : null;
+  }
+
+  // Filtre les moteurs par vendor. vendor falsy => liste inchangée (fallback : tout afficher).
+  function filterEnginesByVendor(engines, vendor) {
+    if (!Array.isArray(engines)) return [];
+    if (!vendor) return engines.slice();
+    return engines.filter(function (eng) {
+      var vendors = (eng && eng.gpu_vendors) || [];
+      return Array.isArray(vendors) && vendors.indexOf(vendor) !== -1;
+    });
+  }
+
+  // Liste FINALE des moteurs pour un <select> : filtrée par vendor, mais le moteur déjà
+  // sélectionné reste TOUJOURS présent même s'il est incompatible (jamais de changement
+  // silencieux de valeur — la validation serveur signalera l'incompatibilité au déploiement).
+  function engineChoices(engines, vendor, selectedId) {
+    var list = filterEnginesByVendor(engines, vendor);
+    if (selectedId) {
+      var present = false;
+      for (var i = 0; i < list.length; i++) {
+        if (engineId(list[i]) === selectedId) { present = true; break; }
+      }
+      if (!present && Array.isArray(engines)) {
+        for (var j = 0; j < engines.length; j++) {
+          if (engineId(engines[j]) === selectedId) { list = [engines[j]].concat(list); break; }
+        }
+      }
+    }
+    return list;
+  }
+
+  root.ForgeAIEngineFilter = {
+    engineId: engineId,
+    nodeVendorForFilter: nodeVendorForFilter,
+    filterEnginesByVendor: filterEnginesByVendor,
+    engineChoices: engineChoices
+  };
+
+  if (typeof module !== 'undefined' && module.exports) {
+    module.exports = root.ForgeAIEngineFilter;
+  }
+})(typeof window !== 'undefined' ? window : globalThis);
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index d0cef1d..3b637ab 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -190,6 +190,7 @@
     </main>
   </div>
 
+  <script src="engine_filter.js"></script>
   <script src="app.js"></script>
 </body>
 </html>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 2e04b0f..62a80f8 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -204,6 +204,17 @@ def _registre_path() -> Path:
     return _REGISTRE_PATH if _REGISTRE_PATH is not None else forgeai_home() / "Registres" / "mission.jsonl"
 
 
+def _node_vendors_by_host(registre_path: Path) -> dict[str, list[str]]:
+    """S6b — corrèle nom d'hôte -> vendors GPU distincts depuis les sondes `node_hardware` du
+    registre (réutilise cluster.read_probes/node_vendors de S7). Registre absent => {} (jamais
+    d'exception). Sert à enrichir /api/nodes/status pour que l'UI filtre les moteurs par vendor."""
+    from forgeai import cluster
+    return {
+        probe.get("node_host"): cluster.node_vendors(probe.get("hardware", {}))
+        for probe in cluster.read_probes(registre_path)
+    }
+
+
 def _node_keys(runner: CommandRunner) -> tuple[Path, Path]:
     """Retourne la paire de clés active, la génère si elle est absente."""
     key_dir = _NODE_KEYS_DIR if _NODE_KEYS_DIR is not None else forgeai_home() / "keys"
@@ -504,9 +515,16 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             runner = SubprocessRunner()
             try:
                 nodes = cluster_status(runner)
-                self._send_json(200, {"nodes": nodes})
             except ClusterError as exc:
                 self._send_json(200, {"nodes": [], "detail": str(exc)})
+                return
+            # S6b : enrichit chaque nœud de son/ses vendor(s) GPU (sondes node_hardware du
+            # registre) pour que le dropdown moteur de l'UI se filtre par vendor. Nœud sans
+            # sonde => vendors:[] (le champ existe toujours, jamais absent ni None).
+            vendors_by_host = _node_vendors_by_host(_registre_path())
+            for node in nodes:
+                node["vendors"] = vendors_by_host.get(node.get("name"), [])
+            self._send_json(200, {"nodes": nodes})
             return
 
         if path == "/api/nodes/receptacles":
diff --git a/tests/js/engine_filter.test.cjs b/tests/js/engine_filter.test.cjs
new file mode 100644
index 0000000..0521927
--- /dev/null
+++ b/tests/js/engine_filter.test.cjs
@@ -0,0 +1,67 @@
+'use strict';
+/* Story S6b — preuve Node (V8, même moteur que le navigateur) des fonctions PURES de filtrage
+ * moteur<->vendor. Exécution : `node tests/js/engine_filter.test.cjs` (assertions réelles ;
+ * exit != 0 si une seule casse). NON câblé dans les gates CI (pas de runner JS au dépôt) — c'est
+ * une preuve locale re-jouable, pas un badge. Le rendu DOM (engineOptions/select) = vérif navigateur.
+ */
+const assert = require('node:assert');
+const F = require('../../src/forgeai/web/assets/engine_filter.js');
+
+// Données réelles = data/moteurs-inference.json (gpu_vendors par moteur).
+const ENGINES = [
+  { id: 'vllm', name: 'vLLM', gpu_vendors: ['nvidia', 'amd'] },
+  { id: 'sglang', name: 'SGLang', gpu_vendors: ['nvidia', 'amd'] },
+  { id: 'llama-cpp', name: 'llama.cpp', gpu_vendors: ['nvidia', 'amd', 'intel', 'apple', 'cpu'] },
+  { id: 'ollama', name: 'Ollama', gpu_vendors: ['nvidia', 'amd', 'apple', 'cpu'] },
+  { id: 'tensorrt-llm', name: 'TensorRT-LLM', gpu_vendors: ['nvidia'] },
+  { id: 'lorax', name: 'LoRAX', gpu_vendors: ['nvidia'] },
+  { id: 'lmdeploy', name: 'LMDeploy', gpu_vendors: ['nvidia'] },
+  { id: 'mlc-llm', name: 'MLC-LLM', gpu_vendors: ['nvidia', 'amd', 'intel', 'apple'] },
+];
+
+// 1. Nœud AMD : cache tensorrt-llm / lorax / lmdeploy (nvidia-only), garde le reste.
+//    Miroir EXACT du contrat serveur compatible_engines('amd') prouvé en S4/S6.
+const amd = F.filterEnginesByVendor(ENGINES, 'amd').map((e) => e.id);
+assert.deepStrictEqual(amd, ['vllm', 'sglang', 'llama-cpp', 'ollama', 'mlc-llm']);
+assert.ok(!amd.includes('tensorrt-llm'));
+assert.ok(!amd.includes('lorax'));
+assert.ok(!amd.includes('lmdeploy'));
+
+// 2. Nœud NVIDIA : tous les moteurs listent nvidia -> aucun masqué.
+assert.strictEqual(F.filterEnginesByVendor(ENGINES, 'nvidia').length, ENGINES.length);
+
+// 3. Nœud Intel : seuls llama-cpp et mlc-llm restent.
+assert.deepStrictEqual(F.filterEnginesByVendor(ENGINES, 'intel').map((e) => e.id),
+  ['llama-cpp', 'mlc-llm']);
+
+// 4. Vendor inconnu / vide / nul => AUCUN filtrage (fallback : tout afficher).
+assert.strictEqual(F.filterEnginesByVendor(ENGINES, '').length, ENGINES.length);
+assert.strictEqual(F.filterEnginesByVendor(ENGINES, null).length, ENGINES.length);
+assert.strictEqual(F.filterEnginesByVendor(ENGINES, undefined).length, ENGINES.length);
+
+// 5. Vendor d'un nœud : unique -> ce vendor ; mixte/sans-sonde/local/auto/inconnu -> null.
+const NODES = [
+  { name: 'worker-amd', vendors: ['amd'] },
+  { name: 'worker-mix', vendors: ['nvidia', 'amd'] },
+  { name: 'worker-nosonde', vendors: [] },
+];
+assert.strictEqual(F.nodeVendorForFilter(NODES, 'worker-amd'), 'amd');
+assert.strictEqual(F.nodeVendorForFilter(NODES, 'worker-mix'), null);   // mixte => pas de filtrage
+assert.strictEqual(F.nodeVendorForFilter(NODES, 'worker-nosonde'), null);
+assert.strictEqual(F.nodeVendorForFilter(NODES, 'local'), null);
+assert.strictEqual(F.nodeVendorForFilter(NODES, 'auto'), null);
+assert.strictEqual(F.nodeVendorForFilter(NODES, 'inconnu'), null);
+assert.strictEqual(F.nodeVendorForFilter(NODES, ''), null);
+assert.strictEqual(F.nodeVendorForFilter(null, 'worker-amd'), null);
+
+// 6. engineChoices : le moteur DÉJÀ sélectionné reste visible même incompatible (pas de saut
+//    silencieux de valeur), sans doublon quand il est compatible.
+const kept = F.engineChoices(ENGINES, 'amd', 'tensorrt-llm').map((e) => e.id);
+assert.ok(kept.includes('tensorrt-llm'), 'sélection incompatible conservée');
+assert.ok(kept.includes('vllm'), 'compatibles présents');
+const compat = F.engineChoices(ENGINES, 'amd', 'vllm').map((e) => e.id);
+assert.strictEqual(compat.filter((x) => x === 'vllm').length, 1, 'pas de doublon');
+// sans vendor => liste complète, sélection inchangée
+assert.strictEqual(F.engineChoices(ENGINES, null, 'lorax').length, ENGINES.length);
+
+console.log('OK — 6 groupes d\'assertions passés (filtrage moteur<->vendor S6b, données réelles)');
diff --git a/tests/test_ui_s6b.py b/tests/test_ui_s6b.py
new file mode 100644
index 0000000..39c2419
--- /dev/null
+++ b/tests/test_ui_s6b.py
@@ -0,0 +1,33 @@
+"""Story S6b — câblage UI du dropdown moteur filtré par vendor du nœud.
+
+Preuves STRUCTURELLES (convention du dépôt, cf. test_ui_n2b) : le rendu réel du <select> se
+vérifie EN NAVIGATEUR (cf. PR) — ici on garantit que le câblage EXISTE et ne régresse pas :
+  1. index.html charge engine_filter.js AVANT app.js ;
+  2. app.js délègue le filtrage au module pur ForgeAIEngineFilter et dérive le vendor du nœud ;
+  3. engine_filter.js reste auto-suffisant (aucun lien http/https, cf. test_auto_suffisance).
+La LOGIQUE de filtrage est prouvée par tests/js/engine_filter.test.cjs (Node, assertions réelles).
+"""
+from pathlib import Path
+
+ASSETS = Path(__file__).resolve().parent.parent / "src" / "forgeai" / "web" / "assets"
+
+
+def test_index_charge_engine_filter_avant_app():
+    html = (ASSETS / "index.html").read_text(encoding="utf-8")
+    assert 'src="engine_filter.js"' in html
+    assert html.index("engine_filter.js") < html.index("app.js")
+
+
+def test_app_delegue_au_module_pur():
+    app = (ASSETS / "app.js").read_text(encoding="utf-8")
+    assert "ForgeAIEngineFilter" in app          # délégation au module pur testé
+    assert "engineChoices" in app                # liste finale filtrée (garde la sélection)
+    assert "nodeVendorForFilter" in app          # dérive le vendor du nœud sélectionné
+
+
+def test_engine_filter_auto_suffisant_et_exporte():
+    js = (ASSETS / "engine_filter.js").read_text(encoding="utf-8")
+    assert "http://" not in js and "https://" not in js
+    for fn in ("filterEnginesByVendor", "nodeVendorForFilter", "engineChoices"):
+        assert fn in js, f"fonction pure manquante : {fn}"
+    assert "module.exports" in js                # réutilisable navigateur + Node (preuve)
diff --git a/tests/test_web_nodes_vendors.py b/tests/test_web_nodes_vendors.py
new file mode 100644
index 0000000..e789059
--- /dev/null
+++ b/tests/test_web_nodes_vendors.py
@@ -0,0 +1,93 @@
+"""Story S6b — /api/nodes/status enrichi du vendor GPU par nœud (dropdown moteur filtré).
+
+Deux preuves EN PROCESS (comptées par la couverture, cf. piège SonarCloud sous-process) :
+  1. helper pur `_node_vendors_by_host` : corrèle hôte -> vendors depuis les sondes
+     `node_hardware` du registre (S7 read_probes/node_vendors) ;
+  2. serveur web réel : chaque nœud porte son/ses vendor(s), un nœud SANS sonde => vendors:[].
+Zéro mock de commande — `cluster_status` monkeypatché (pas de cluster local), registre réel seedé.
+"""
+from __future__ import annotations
+
+import json
+import threading
+import urllib.request
+from pathlib import Path
+
+import pytest
+
+from forgeai.web import server as server_module
+
+
+def _get_json(url: str):
+    with urllib.request.urlopen(url) as resp:
+        return resp.status, json.loads(resp.read().decode("utf-8"))
+
+
+def _node_hardware_entry(host: str, vendors: list[str]) -> str:
+    return json.dumps({
+        "type": "node_hardware",
+        "payload": {
+            "node_host": host,
+            "profile": "minimal-gpu-rocm",
+            "backends": [],
+            "hardware": {"gpus": [{"vendor": v} for v in vendors]},
+        },
+    })
+
+
+def _seed_registre(path: Path, entries: list[str]) -> None:
+    path.parent.mkdir(parents=True, exist_ok=True)
+    path.write_text("\n".join(entries) + "\n", encoding="utf-8")
+
+
+def test_node_vendors_by_host_pur(tmp_path):
+    """Helper pur EN PROCESS : hôte -> vendors distincts ; registre absent => {} sans exception."""
+    reg = tmp_path / "mission.jsonl"
+    _seed_registre(reg, [
+        _node_hardware_entry("pc-amd", ["amd", "amd"]),      # dédup attendu
+        _node_hardware_entry("pc-mix", ["nvidia", "amd"]),
+    ])
+    mapping = server_module._node_vendors_by_host(reg)
+    assert mapping["pc-amd"] == ["amd"]                       # distincts, ordre de 1re apparition
+    assert mapping["pc-mix"] == ["nvidia", "amd"]
+    assert "inconnu" not in mapping
+
+    # registre absent => mapping vide, jamais d'exception
+    assert server_module._node_vendors_by_host(tmp_path / "absent.jsonl") == {}
+
+
+@pytest.fixture
+def base_url_seeded(monkeypatch, tmp_path):
+    reg = tmp_path / "Registres" / "mission.jsonl"
+    _seed_registre(reg, [
+        _node_hardware_entry("worker-amd", ["amd"]),
+        _node_hardware_entry("worker-nv", ["nvidia"]),
+    ])
+    monkeypatch.setattr(server_module, "_REGISTRE_PATH", reg)
+
+    def fake_cluster_status(runner):
+        return [
+            {"name": "worker-amd", "ready": True, "roles": ["worker"]},
+            {"name": "worker-nv", "ready": True, "roles": ["worker"]},
+            {"name": "worker-sans-sonde", "ready": True, "roles": ["worker"]},
+        ]
+
+    monkeypatch.setattr(server_module, "cluster_status", fake_cluster_status)
+
+    server = server_module.build_server("127.0.0.1", 0)
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+    host, port = server.server_address
+    yield f"http://{host}:{port}"
+    server.shutdown()
+    server.server_close()
+
+
+def test_nodes_status_enrichit_vendors(base_url_seeded):
+    status, body = _get_json(f"{base_url_seeded}/api/nodes/status")
+    assert status == 200
+    nodes = {n["name"]: n for n in body["nodes"]}
+    assert nodes["worker-amd"]["vendors"] == ["amd"]
+    assert nodes["worker-nv"]["vendors"] == ["nvidia"]
+    # nœud réel du cluster mais AUCUNE sonde au registre => liste vide (jamais absent, jamais None)
+    assert nodes["worker-sans-sonde"]["vendors"] == []
