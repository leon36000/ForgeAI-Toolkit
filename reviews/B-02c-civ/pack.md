# Story B-02c — Page Modeles & cles API (T2) — REVISION 2 (objections Grok corrigees)

## Boucle corrective : REJECT 2/3 -> fixes
1. [majeure Grok] frontend lisait m.fingerprint (inexistant) -> m.key_fingerprint (champ reel de public_dict) : les empreintes s'affichent.
2. [mineures Qwen+Grok] echec registre n'est plus avale en silence : le 201 porte registre_journalise:true/false.
SWAP journalise : GLM-5.2 (zhipu) 408 x3 -> Grok-4.5 (xai). Trio vise : google/alibaba/xai.

## Criteres (inchanges)
- GET /api/models (jamais les cles) ; POST add_cloud test reel (echec=400 rien ecrit ; succes=201+registre signale) ; secrets memoire->vault, jamais persistes en clair (teste sur TOUS les fichiers) ; frontend formulaire+liste empreintes+i18n.

## PREUVE D'EXECUTION
```
### SUITE COMPLETE (170 tests)
........................................................................ [ 93%]
..........................                                               [100%]

### no_stub
NO-STUB-SCAN : OK (3 fichiers scannés, zéro violation)

### VERIFICATION NAVIGATEUR REEL (Chrome preview, localhost:8877)
Section Modeles & cles API rendue ; etat vide "Aucune route configuree".
base_url CACHE pour openrouter, VISIBLE pour direct/autre (champ conditionnel OK).
Soumission avec fausse cle -> SONDE RESEAU REELLE vers OpenRouter -> 401 -> message clair
"test de connexion RED : cle API refusee (401/403)" en style erreur ; AUCUNE route cassee ajoutee (liste toujours vide) — exigence DM-5.
HYGIENE SECRETS : champs api_key/passphrase VIDES DU DOM des la soumission (avant meme la reponse).

### Note correctifs orchestrateur (2)
1. placeholder https:// retire du HTML (contrat auto-suffisance strict : zero http(s):// dans les assets).
2. test champs_manquants du codeur corrige : valeurs distinctives au lieu de "m" (1 char, assertion vide de sens contre "champs manquants").
```

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/src/forgeai/web/assets/app.css b/src/forgeai/web/assets/app.css
index 58bac95..99297ab 100644
--- a/src/forgeai/web/assets/app.css
+++ b/src/forgeai/web/assets/app.css
@@ -305,3 +305,24 @@ code {
 .badge-installed { background: color-mix(in srgb, var(--accent, #EA6A2E) 18%, transparent); color: var(--accent, #EA6A2E); }
 .badge-locked { border: 1px solid var(--line, #38434F); opacity: .85; }
 .badge-default { background: color-mix(in srgb, #2E9E5B 18%, transparent); color: #2E9E5B; }
+
+/* ---------- Modèles & clés API (B-02c) ---------- */
+.models-list { display: flex; flex-direction: column; gap: 6px; margin: 10px 0; }
+.model-row {
+  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
+  padding: 8px 12px; border-radius: 10px;
+  border: 1px solid var(--line, #38434F); background: var(--panel, #1A2027);
+}
+.model-form { margin-top: 12px; }
+.form-grid {
+  display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px;
+}
+.form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }
+.form-grid input, .form-grid select {
+  padding: 8px 10px; border-radius: 8px;
+  border: 1px solid var(--line, #38434F); background: var(--panel, #1A2027); color: inherit;
+}
+.form-note { font-size: 12px; opacity: .7; margin: 10px 0 6px; }
+.form-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
+.form-status { font-size: 12.5px; }
+.form-status.error { color: #E5533D; }
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index 9a885b9..ba180d9 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -43,7 +43,23 @@
       default_badge: 'Défaut de sphère',
       counts_tpl: '{installed} installées avec le stack · {checked} cochées · {total} disponibles',
       no_results: 'Aucune brique ne correspond au filtre.',
-      stars_label: 'étoiles'
+      stars_label: 'étoiles',
+      models_title: 'Modèles & clés API',
+      models_subtitle: 'Routes modèle cloud — test de connexion réel obligatoire ; la clé est scellée au coffre, seule l\'empreinte est conservée.',
+      f_name: 'Nom de la route',
+      f_provenance: 'Provenance',
+      f_model_id: 'Identifiant du modèle',
+      f_base_url: 'Base URL (OpenAI-compatible)',
+      f_api_key: 'Clé API', // proof:allow (libellé i18n, pas un secret)
+      f_passphrase: 'Passphrase du coffre',
+      prov_direct: 'Direct fournisseur',
+      prov_autre: 'Autre (URL)',
+      key_note: 'La clé transite en mémoire vers le serveur local (127.0.0.1) puis est scellée au coffre chiffré — jamais écrite en clair, jamais réaffichée.',
+      add_route: 'Ajouter la route (test réel)',
+      testing_route: 'Test de connexion en cours…',
+      route_added: 'Route ajoutée — test réel réussi.',
+      no_models: 'Aucune route configurée pour l\'instant.',
+      fingerprint_label: 'empreinte'
     },
     en: {
       title: 'ForgeAI Toolkit',
@@ -72,7 +88,23 @@
       default_badge: 'Sphere default',
       counts_tpl: '{installed} installed with the stack · {checked} checked · {total} available',
       no_results: 'No brick matches the filter.',
-      stars_label: 'stars'
+      stars_label: 'stars',
+      models_title: 'Models & API keys',
+      models_subtitle: 'Cloud model routes — real connection test required; the key is sealed in the vault, only its fingerprint is kept.',
+      f_name: 'Route name',
+      f_provenance: 'Provenance',
+      f_model_id: 'Model identifier',
+      f_base_url: 'Base URL (OpenAI-compatible)',
+      f_api_key: 'API key', // proof:allow (libellé i18n, pas un secret)
+      f_passphrase: 'Vault passphrase',
+      prov_direct: 'Direct provider',
+      prov_autre: 'Other (URL)',
+      key_note: 'The key transits in memory to the local server (127.0.0.1) then is sealed in the encrypted vault — never written in clear, never shown again.',
+      add_route: 'Add route (real test)',
+      testing_route: 'Connection test running…',
+      route_added: 'Route added — real test passed.',
+      no_models: 'No route configured yet.',
+      fingerprint_label: 'fingerprint'
     }
   };
 
@@ -124,6 +156,7 @@
       renderSphereSteps();
       renderBricks();
     }
+    if (state.models !== undefined) renderModels();
   }
 
   async function fetchJson(path) {
@@ -393,6 +426,86 @@
     state.bricks = null;
   }
 
+  /* ---------- Modèles & clés API (B-02c) ---------- */
+
+  async function loadModels() {
+    const list = document.getElementById('models-list');
+    try {
+      state.models = await fetchJson('/api/models');
+    } catch (e) {
+      list.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
+      return;
+    }
+    renderModels();
+  }
+
+  function renderModels() {
+    const list = document.getElementById('models-list');
+    const models = state.models || [];
+    if (!models.length) {
+      list.innerHTML = `<p class="form-note">${escapeHtml(t('no_models'))}</p>`;
+      return;
+    }
+    list.innerHTML = models.map((m) => `
+      <div class="model-row">
+        <span class="brick-name">${escapeHtml(m.name)}</span>
+        <span class="def-pill">${escapeHtml(m.provenance)}</span>
+        <span class="def-pill">${escapeHtml(m.model_id)}</span>
+        ${m.key_fingerprint ? `<span class="brick-stars" title="${escapeHtml(t('fingerprint_label'))}">${escapeHtml(String(m.key_fingerprint).slice(0, 16))}…</span>` : ''}
+      </div>
+    `).join('');
+  }
+
+  function initModelForm() {
+    const form = document.getElementById('model-form');
+    if (!form) return;
+    const provenance = form.elements.provenance;
+    const baseUrlField = document.getElementById('base-url-field');
+    const syncBaseUrl = () => {
+      const need = provenance.value === 'direct' || provenance.value === 'autre';
+      baseUrlField.classList.toggle('hidden', !need);
+      form.elements.base_url.required = need;
+    };
+    provenance.addEventListener('change', syncBaseUrl);
+    syncBaseUrl();
+
+    form.addEventListener('submit', async (ev) => {
+      ev.preventDefault();
+      const status = document.getElementById('model-form-status');
+      const payload = {
+        name: form.elements.name.value.trim(),
+        provenance: provenance.value,
+        model_id: form.elements.model_id.value.trim(),
+        api_key: form.elements.api_key.value, // proof:allow (champ payload, valeur jamais litterale)
+        passphrase: form.elements.passphrase.value
+      };
+      const baseUrl = form.elements.base_url.value.trim();
+      if (baseUrl) payload.base_url = baseUrl;
+      // hygiène : vider les champs secrets AVANT l'appel — jamais conservés dans le DOM
+      form.elements.api_key.value = '';
+      form.elements.passphrase.value = '';
+      status.textContent = t('testing_route');
+      status.classList.remove('error');
+      try {
+        const res = await fetch('/api/models', {
+          method: 'POST',
+          headers: { 'Content-Type': 'application/json' },
+          body: JSON.stringify(payload)
+        });
+        const body = await res.json();
+        if (!res.ok) throw new Error(body.error || res.status);
+        status.textContent = t('route_added');
+        form.elements.name.value = '';
+        form.elements.model_id.value = '';
+        form.elements.base_url.value = '';
+        loadModels();
+      } catch (e) {
+        status.textContent = String(e.message || e);
+        status.classList.add('error');
+      }
+    });
+  }
+
   function initControls() {
     document.querySelectorAll('#theme-toggle button[data-theme]').forEach((btn) => {
       btn.addEventListener('click', () => setTheme(btn.dataset.theme));
@@ -407,12 +520,14 @@
         renderBricks();
       });
     }
+    initModelForm();
     setTheme(state.theme);
     setLang(state.lang);
   }
 
   async function boot() {
     initControls();
+    loadModels();
     try {
       const [detect, stacks, spheres] = await Promise.all([
         fetchJson('/api/detect'),
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index 8770fef..962e032 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -44,6 +44,39 @@
       </div>
       <div id="bricks-list" class="bricks-list" aria-live="polite"></div>
     </section>
+
+    <section id="models" class="card">
+      <h2 data-i18n="models_title">Modèles &amp; clés API</h2>
+      <p data-i18n="models_subtitle">Routes modèle cloud — test de connexion réel obligatoire ; la clé est scellée au coffre, seule l'empreinte est conservée.</p>
+      <div id="models-list" class="models-list" aria-live="polite"></div>
+      <form id="model-form" class="model-form" autocomplete="off">
+        <div class="form-grid">
+          <label><span data-i18n="f_name">Nom de la route</span>
+            <input name="name" required placeholder="openrouter-glm"></label>
+          <label><span data-i18n="f_provenance">Provenance</span>
+            <select name="provenance">
+              <option value="openrouter">OpenRouter</option>
+              <option value="deepinfra">DeepInfra</option>
+              <option value="nim">NVIDIA NIM</option>
+              <option value="direct" data-i18n="prov_direct">Direct fournisseur</option>
+              <option value="autre" data-i18n="prov_autre">Autre (URL)</option>
+            </select></label>
+          <label><span data-i18n="f_model_id">Identifiant du modèle</span>
+            <input name="model_id" required placeholder="z-ai/glm-4.6"></label>
+          <label id="base-url-field" class="hidden"><span data-i18n="f_base_url">Base URL (OpenAI-compatible)</span>
+            <input name="base_url" placeholder="api.exemple.com/v1"></label>
+          <label><span data-i18n="f_api_key">Clé API</span>
+            <input name="api_key" type="password" required autocomplete="new-password"></label>
+          <label><span data-i18n="f_passphrase">Passphrase du coffre</span>
+            <input name="passphrase" type="password" required autocomplete="new-password"></label>
+        </div>
+        <p class="form-note" data-i18n="key_note">La clé transite en mémoire vers le serveur local (127.0.0.1) puis est scellée au coffre chiffré — jamais écrite en clair, jamais réaffichée.</p>
+        <div class="form-actions">
+          <button type="submit" class="btn" data-i18n="add_route">Ajouter la route (test réel)</button>
+          <span id="model-form-status" class="form-status" aria-live="polite"></span>
+        </div>
+      </form>
+    </section>
   </main>
 
   <script src="app.js"></script>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index c438cce..7697429 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -2,13 +2,18 @@ from __future__ import annotations
 
 import importlib.resources
 import json
+import os
 import urllib.parse
 import webbrowser
 from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
+from pathlib import Path
 
 from forgeai.catalogue.spheres import SPHERES, classify_sphere, spheres_index
+from forgeai.core import registre
 from forgeai.core.runner import SubprocessRunner
 from forgeai.hardware.detect import HardwareDetector
+from forgeai.models.probe import Transport
+from forgeai.models.routes import RouteError, RouteStore
 from forgeai.resources import catalogue_path
 from forgeai.stacks import deploy_ids, list_stacks, load_stack
 
@@ -130,6 +135,29 @@ def bricks_payload(sphere_id: str, stack_id: str | None) -> dict | None:
     }
 
 
+def forgeai_home() -> Path:
+    """Répertoire utilisateur ForgeAI (FORGEAI_HOME ou ~/.forgeai)."""
+    return Path(os.environ.get("FORGEAI_HOME", Path.home() / ".forgeai"))
+
+
+# Hooks pour les tests (valeurs par défaut si non posés).
+_MODELS_HOME: Path | None = None
+_PROBE_TRANSPORT: Transport | None = None
+_REGISTRE_PATH: Path | None = None
+
+
+def _models_home() -> Path:
+    return _MODELS_HOME if _MODELS_HOME is not None else forgeai_home() / "models"
+
+
+def _probe_transport() -> Transport | None:
+    return _PROBE_TRANSPORT
+
+
+def _registre_path() -> Path:
+    return _REGISTRE_PATH if _REGISTRE_PATH is not None else forgeai_home() / "Registres" / "mission.jsonl"
+
+
 class ForgeAIHandler(BaseHTTPRequestHandler):
     server_version = "ForgeAI/0.1"
 
@@ -172,6 +200,11 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             )
             return
 
+        if path == "/api/models":
+            store = RouteStore(_models_home())
+            self._send_json(200, [r.public_dict() for r in store.list()])
+            return
+
         if path == "/api/stacks":
             stack_ids = list_stacks()
             ordered = [sid for sid in stack_ids if sid != "tout-en-un"]
@@ -246,6 +279,98 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
         payload = json.dumps({"error": "not found", "path": path}, ensure_ascii=False).encode("utf-8")
         self._send(404, payload, "application/json; charset=utf-8")
 
+    def do_POST(self) -> None:  # noqa: N802
+        parsed = urllib.parse.urlparse(self.path)
+        path = parsed.path
+
+        if path != "/api/models":
+            self._send_json(404, {"error": "not found"})
+            return
+
+        length_hdr = self.headers.get("Content-Length")
+        if length_hdr is None:
+            self._send_json(413, {"error": "Content-Length requis"})
+            return
+
+        try:
+            length = int(length_hdr)
+        except ValueError:
+            self._send_json(400, {"error": "Content-Length invalide"})
+            return
+
+        if length < 0 or length > 65536:
+            self._send_json(413, {"error": "corps trop grand"})
+            return
+
+        try:
+            body = self.rfile.read(length)
+            data = json.loads(body.decode("utf-8"))
+        except (json.JSONDecodeError, UnicodeDecodeError):
+            self._send_json(400, {"error": "JSON invalide"})
+            return
+
+        if not isinstance(data, dict):
+            self._send_json(400, {"error": "JSON invalide"})
+            return
+
+        required = ["name", "provenance", "model_id", "api_key", "passphrase"]
+        missing = [field for field in required if field not in data]
+        if missing:
+            self._send_json(400, {"error": "champs manquants", "missing": missing})
+            return
+
+        name = data["name"]
+        provenance = data["provenance"]
+        model_id = data["model_id"]
+        api_key = data["api_key"]  # proof:allow (identifiant ; la valeur n'est jamais journalisee)
+        passphrase = data["passphrase"]
+        base_url = data.get("base_url")
+
+        try:
+            store = RouteStore(_models_home())
+            route, result = store.add_cloud(
+                name,
+                provenance,
+                model_id,
+                api_key,
+                passphrase,
+                base_url=base_url,
+                transport=_probe_transport(),
+            )
+        except RouteError as exc:
+            self._send_json(400, {"error": str(exc)})
+            return
+
+        # Journalisation best-effort : la route EST créée (clé scellée) même si le
+        # registre échoue, mais l'échec est SIGNALÉ au client (objection revue B-02c —
+        # jamais avalé en silence).
+        registre_journalise = True
+        try:
+            reg_path = _registre_path()
+            reg_path.parent.mkdir(parents=True, exist_ok=True)
+            registre.append(
+                reg_path,
+                "route_cloud_ajoutee",
+                "web",
+                {
+                    "name": route.name,
+                    "provenance": route.provenance,
+                    "model_id": route.model_id,
+                    "key_fingerprint": route.key_fingerprint,
+                },
+            )
+        except Exception:
+            registre_journalise = False
+
+        self._send_json(
+            201,
+            {
+                "route": route.public_dict(),
+                "probe": {"light": result.light, "detail": result.detail},
+                "registre_journalise": registre_journalise,
+            },
+        )
+
     def log_message(self, *args) -> None:  # noqa: ARG002
         return
 
diff --git a/tests/test_web_models.py b/tests/test_web_models.py
new file mode 100644
index 0000000..7494234
--- /dev/null
+++ b/tests/test_web_models.py
@@ -0,0 +1,224 @@
+from __future__ import annotations
+
+import json
+import threading
+import time
+import urllib.error
+import urllib.request
+from contextlib import contextmanager
+from pathlib import Path
+
+import pytest
+
+import forgeai.web.server as server_mod
+
+
+@contextmanager
+def _running_server():
+    server = server_mod.build_server("127.0.0.1", 0)
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+    host, port = server.server_address
+    url = f"http://{host}:{port}"
+    time.sleep(0.05)
+    try:
+        yield url
+    finally:
+        server.shutdown()
+        server.server_close()
+
+
+def _request(req: urllib.request.Request):
+    try:
+        with urllib.request.urlopen(req) as resp:
+            return resp.status, json.loads(resp.read().decode("utf-8"))
+    except urllib.error.HTTPError as exc:
+        body = exc.read().decode("utf-8")
+        try:
+            data = json.loads(body)
+        except json.JSONDecodeError:
+            data = body
+        return exc.code, data
+
+
+def _get(url: str):
+    return _request(urllib.request.Request(url, method="GET"))
+
+
+def _post(url: str, payload: dict):
+    data = json.dumps(payload).encode("utf-8")
+    req = urllib.request.Request(
+        url,
+        data=data,
+        headers={"Content-Type": "application/json"},
+        method="POST",
+    )
+    return _request(req)
+
+
+@pytest.fixture
+def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
+    monkeypatch.setattr(server_mod, "_MODELS_HOME", tmp_path / "models")
+    monkeypatch.setattr(server_mod, "_REGISTRE_PATH", tmp_path / "r.jsonl")
+    return tmp_path
+
+
+@pytest.fixture
+def GREEN(monkeypatch: pytest.MonkeyPatch):
+    class GreenTransport:
+        def post(self, url, headers, body, timeout):
+            return (200, '{"choices":[{"message":{"content":"pong"}}]}')
+
+    monkeypatch.setattr(server_mod, "_PROBE_TRANSPORT", GreenTransport())
+    return GreenTransport
+
+
+@pytest.fixture
+def RED(monkeypatch: pytest.MonkeyPatch):
+    class RedTransport:
+        def post(self, url, headers, body, timeout):
+            return (401, '{"error":"unauthorized"}')
+
+    monkeypatch.setattr(server_mod, "_PROBE_TRANSPORT", RedTransport())
+    return RedTransport
+
+
+def test_models_liste_vide(tmp_home: Path):
+    with _running_server() as url:
+        status, body = _get(f"{url}/api/models")
+        assert status == 200
+        assert body == []
+
+
+def test_add_cloud_green(tmp_home: Path, GREEN):
+    key = "sk-TEST-XYZ"
+    payload = {
+        "name": "r1",
+        "provenance": "openrouter",
+        "model_id": "m",
+        "api_key": key,
+        "passphrase": "pp",
+    }
+    with _running_server() as url:
+        status, body = _post(f"{url}/api/models", payload)
+        assert status == 201
+        route = body["route"]
+        assert route["name"] == "r1"
+        assert route["provenance"] == "openrouter"
+        assert route["model_id"] == "m"
+        assert route["key_fingerprint"].startswith("sha256:")
+        assert key not in json.dumps(body)
+
+        status2, list_body = _get(f"{url}/api/models")
+        assert status2 == 200
+        assert len(list_body) == 1
+        assert list_body[0]["name"] == "r1"
+
+    for path in tmp_home.rglob("*"):
+        if path.is_file():
+            text = path.read_text(encoding="utf-8", errors="ignore")
+            assert key not in text, f"clé API trouvée dans {path}"
+
+    reg = tmp_home / "r.jsonl"
+    if reg.exists():
+        assert key not in reg.read_text(encoding="utf-8", errors="ignore")
+
+
+def test_add_cloud_red_rien_ecrit(tmp_home: Path, RED):
+    key = "sk-TEST-RED"
+    payload = {
+        "name": "r1",
+        "provenance": "openrouter",
+        "model_id": "m",
+        "api_key": key,
+        "passphrase": "pp",
+    }
+    with _running_server() as url:
+        status, body = _post(f"{url}/api/models", payload)
+        assert status == 400
+        status2, list_body = _get(f"{url}/api/models")
+        assert list_body == []
+
+    assert not (tmp_home / "models" / "routes.json").exists()
+
+
+def test_add_cloud_champs_manquants(tmp_home: Path, GREEN):
+    """Le 400 liste les champs manquants SANS refléter les valeurs soumises.
+    (Valeurs DISTINCTIVES — une valeur d'un caractère rendrait l'assertion vide de sens.)"""
+    payload = {
+        "name": "route-distinctive-r1",
+        "provenance": "openrouter",
+        "model_id": "modele-distinctif-xyz",
+        "passphrase": "passphrase-distinctive-pp",
+    }
+    with _running_server() as url:
+        status, body = _post(f"{url}/api/models", payload)
+        assert status == 400
+        response_text = json.dumps(body)
+        assert "api_key" in response_text
+        assert "route-distinctive-r1" not in response_text
+        assert "modele-distinctif-xyz" not in response_text
+        assert "passphrase-distinctive-pp" not in response_text
+
+
+def test_add_cloud_doublon(tmp_home: Path, GREEN):
+    payload = {
+        "name": "r1",
+        "provenance": "openrouter",
+        "model_id": "m",
+        "api_key": "sk-1",
+        "passphrase": "pp",
+    }
+    with _running_server() as url:
+        status1, _ = _post(f"{url}/api/models", payload)
+        assert status1 == 201
+        status2, body2 = _post(f"{url}/api/models", payload)
+        assert status2 == 400
+        assert "existe" in str(body2.get("error", "")).lower()
+
+
+def test_registre_journalise(tmp_home: Path, GREEN):
+    key = "sk-REG-TEST"
+    payload = {
+        "name": "r1",
+        "provenance": "openrouter",
+        "model_id": "m",
+        "api_key": key,
+        "passphrase": "pp",
+    }
+    with _running_server() as url:
+        status, body = _post(f"{url}/api/models", payload)
+        assert status == 201
+        fp = body["route"]["key_fingerprint"]
+
+    reg = tmp_home / "r.jsonl"
+    assert reg.exists()
+    lines = [
+        json.loads(line)
+        for line in reg.read_text(encoding="utf-8").strip().split("\n")
+        if line
+    ]
+    assert any(
+        line.get("type") == "route_cloud_ajoutee"
+        and line.get("payload", {}).get("key_fingerprint") == fp
+        for line in lines
+    )
+    assert key not in reg.read_text(encoding="utf-8")
+
+
+def test_post_inconnu(tmp_home: Path):
+    with _running_server() as url:
+        status, body = _post(f"{url}/api/nope", {"x": 1})
+        assert status == 404
+        assert "error" in body
+
+
+def test_non_regression_get(tmp_home: Path):
+    with _running_server() as url:
+        status, body = _get(f"{url}/api/stacks")
+        assert status == 200
+        assert isinstance(body, list)
+
+        status2, body2 = _get(f"{url}/api/bricks?sphere=S4")
+        assert status2 == 200
+        assert "bricks" in body2
```
