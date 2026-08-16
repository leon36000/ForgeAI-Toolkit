# Story B-02e — Resume & Deploiement + preuve SSE live (friction FORCER)

## Criteres (spec-web-ui §5 B-02e ; UX : resume pre-deploiement + friction FORCER + preuve live)
- GET /api/summary?stack : stack (n_deploy reel), materiel, backends preflight reels, taille chassis ; 404/400 propres.
- POST /api/deploy : confirm==FORCER obligatoire (sinon 400, rien lance) ; backend valide ; UN SEUL run (409 sinon) ; subprocess = wizard --ci par defaut, hook _DEPLOY_CMD pour tests (documente).
- GET /api/deploy/events : SSE conforme (rejoue le buffer puis streame, event end + exit_code, robuste au client parti).
- Frontend : resume rendu, friction verifiee, journal live EventSource, statut final code 0/echec, i18n FR/EN.

## PREUVE D'EXECUTION (suite + no-stub + NAVIGATEUR REEL + streaming progressif prouve)
```
### SUITE COMPLETE (181 tests)
........................................................................ [ 90%]
.....................................                                    [100%]

### no_stub
NO-STUB-SCAN : OK (3 fichiers scannés, zéro violation)

### VERIFICATION NAVIGATEUR REEL (Chrome preview) — flux complet Resume -> FORCER -> SSE live
Selection stack agentique -> section Resume & Deploiement VISIBLE.
Resume rendu : "Stack: Agentique 72 briques deployees · 24 chassis commun · CPU AMD Ryzen 9 9950X3D · GPU: 2 · RAM: 46.1 GB · Backends prets: ..." (donnees reelles).
FRICTION UX : confirmation "oui" -> REFUSEE ("Tapez exactement FORCER pour confirmer.") ; rien lance.
FORCER -> POST 202 -> EventSource /api/deploy/events : STREAMING AUTHENTIQUE prouve — a 1,2 s le journal ne contenait que 3 lignes sur 6 (flux progressif, pas un dump final).
Journal final : etape 1/6 detection ... etape 6/6 sante OK. Statut : "Deploiement termine — code 0 (prouve)".
NOTE HONNETE : pour cette verification navigateur, _DEPLOY_CMD (hook de test documente) remplacait le wizard par 6 etapes simulees — on ne lance PAS un vrai docker compose a l insu de Nathan sur son poste. Le chemin par DEFAUT du code livre = python3 -m forgeai wizard --ci (moteur reel prouve par S01-S10 et la CI). Le mecanisme SSE/subprocess est identique dans les deux cas et teste par test_deploy_et_sse.

### API live (hook test, sous pytest)
test_deploy_et_sse : POST FORCER -> 202 ; flux SSE contient les 3 etapes + event: end {"exit_code": 0}.
test_deploy_deja_en_cours : 2e POST pendant run -> 409. test_summary : n_deploy=72, backends liste, cpu_model present.
```

## Note correctif orchestrateur
- Helper _request des tests crew ne rattrapait pas HTTPError (urllib leve sur 4xx) -> try/except retournant (code, corps), aligne sur les autres fichiers de test. Le serveur etait correct.

## DIFF COMPLET (main...HEAD — 5 fichiers)
```diff
diff --git a/src/forgeai/web/assets/app.css b/src/forgeai/web/assets/app.css
index 99297ab..9aface6 100644
--- a/src/forgeai/web/assets/app.css
+++ b/src/forgeai/web/assets/app.css
@@ -326,3 +326,12 @@ code {
 .form-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
 .form-status { font-size: 12.5px; }
 .form-status.error { color: #E5533D; }
+
+/* ---------- Résumé & Déploiement (B-02e) ---------- */
+.deploy-log {
+  margin-top: 12px; padding: 12px 14px; border-radius: 10px;
+  border: 1px solid var(--line, #38434F); background: #10151B; color: #C9D4DE;
+  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px;
+  line-height: 1.55; max-height: 320px; overflow-y: auto; white-space: pre-wrap;
+}
+:root[data-theme="light"] .deploy-log { background: #1A2027; }
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index bef441c..7ff7561 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -69,7 +69,21 @@
       add_node: 'Ajouter le nœud',
       adding_node: 'Bootstrap du nœud en cours…',
       node_added: 'Nœud ajouté — bascule clé ed25519 réussie.',
-      no_nodes: 'Aucun nœud dans le cluster pour l\'instant.'
+      no_nodes: 'Aucun nœud dans le cluster pour l\'instant.',
+      deploy_title: 'Résumé & Déploiement',
+      deploy_subtitle: 'Vérifiez le résumé, puis tapez FORCER pour lancer le déploiement réel — chaque étape est prouvée en direct.',
+      f_backend: 'Backend',
+      f_confirm: 'Confirmation (tapez FORCER)',
+      launch_deploy: 'Déployer le stack',
+      deploy_running: 'Déploiement en cours — journal live ci-dessous.',
+      deploy_done_ok: 'Déploiement terminé — code 0 (prouvé).',
+      deploy_done_fail: 'Déploiement en échec — code {code}. Journal ci-dessus.',
+      deploy_need_forcer: 'Tapez exactement FORCER pour confirmer.',
+      s_stack: 'Stack',
+      s_bricks: 'briques déployées',
+      s_backends: 'Backends prêts',
+      s_chassis: 'châssis commun',
+      s_none: 'aucun'
     },
     en: {
       title: 'ForgeAI Toolkit',
@@ -124,7 +138,21 @@
       add_node: 'Add node',
       adding_node: 'Node bootstrap running…',
       node_added: 'Node added — ed25519 key switch succeeded.',
-      no_nodes: 'No node in the cluster yet.'
+      no_nodes: 'No node in the cluster yet.',
+      deploy_title: 'Summary & Deployment',
+      deploy_subtitle: 'Check the summary, then type FORCER to start the real deployment — every step is proven live.',
+      f_backend: 'Backend',
+      f_confirm: 'Confirmation (type FORCER)',
+      launch_deploy: 'Deploy the stack',
+      deploy_running: 'Deployment running — live log below.',
+      deploy_done_ok: 'Deployment finished — exit code 0 (proven).',
+      deploy_done_fail: 'Deployment failed — exit code {code}. Log above.',
+      deploy_need_forcer: 'Type exactly FORCER to confirm.',
+      s_stack: 'Stack',
+      s_bricks: 'deployed bricks',
+      s_backends: 'Ready backends',
+      s_chassis: 'shared chassis',
+      s_none: 'none'
     }
   };
 
@@ -178,6 +206,7 @@
     }
     if (state.models !== undefined) renderModels();
     if (state.nodes !== undefined) renderNodes();
+    if (state.summary) renderSummary();
   }
 
   async function fetchJson(path) {
@@ -272,6 +301,7 @@
       state.stackDetail = full;
       renderDetail(summary, full);
       showBricksSection();
+      showDeploySection();
     } catch (e) {
       const detail = document.getElementById('stack-detail');
       detail.classList.remove('hidden');
@@ -290,6 +320,7 @@
     detail.classList.add('hidden');
     detail.innerHTML = '';
     hideBricksSection();
+    hideDeploySection();
   }
 
   function renderDetail(summary, full) {
@@ -477,6 +508,112 @@
     `).join('');
   }
 
+  /* ---------- Résumé & Déploiement (B-02e) ---------- */
+
+  async function loadSummary() {
+    if (!state.selectedId) return;
+    const box = document.getElementById('deploy-summary');
+    try {
+      state.summary = await fetchJson(`/api/summary?stack=${encodeURIComponent(state.selectedId)}`);
+    } catch (e) {
+      box.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
+      return;
+    }
+    renderSummary();
+  }
+
+  function renderSummary() {
+    const box = document.getElementById('deploy-summary');
+    const s = state.summary;
+    if (!s) { box.innerHTML = ''; return; }
+    const backends = (s.backends && s.backends.length) ? s.backends.join(', ') : t('s_none');
+    box.innerHTML = `
+      <div class="model-row">
+        <span class="brick-name">${escapeHtml(t('s_stack'))}: ${escapeHtml(s.stack.name)}</span>
+        <span class="def-pill">${s.stack.n_deploy} ${escapeHtml(t('s_bricks'))}</span>
+        <span class="def-pill">${s.chassis} ${escapeHtml(t('s_chassis'))}</span>
+      </div>
+      <div class="model-row">
+        <span class="brick-name">${escapeHtml(t('hardware_cpu'))}: ${escapeHtml(s.hardware.cpu_model || '—')}</span>
+        <span class="def-pill">GPU: ${s.hardware.gpus}</span>
+        <span class="def-pill">RAM: ${escapeHtml(String(s.hardware.ram_gb))} GB</span>
+      </div>
+      <div class="model-row">
+        <span class="brick-name">${escapeHtml(t('s_backends'))}: ${escapeHtml(backends)}</span>
+      </div>
+    `;
+  }
+
+  function showDeploySection() {
+    document.getElementById('deploy').classList.remove('hidden');
+    loadSummary();
+  }
+
+  function hideDeploySection() {
+    document.getElementById('deploy').classList.add('hidden');
+    state.summary = null;
+  }
+
+  function streamDeployLog() {
+    const log = document.getElementById('deploy-log');
+    const status = document.getElementById('deploy-form-status');
+    log.classList.remove('hidden');
+    log.textContent = '';
+    const es = new EventSource('/api/deploy/events');
+    es.onmessage = (ev) => {
+      log.textContent += ev.data + '\n';
+      log.scrollTop = log.scrollHeight;
+    };
+    es.addEventListener('end', (ev) => {
+      es.close();
+      let code = null;
+      try { code = JSON.parse(ev.data).exit_code; } catch (e) { /* fin sans code */ }
+      if (code === 0) {
+        status.textContent = t('deploy_done_ok');
+        status.classList.remove('error');
+      } else {
+        status.textContent = t('deploy_done_fail').replace('{code}', String(code));
+        status.classList.add('error');
+      }
+    });
+    es.onerror = () => { es.close(); };
+  }
+
+  function initDeployForm() {
+    const form = document.getElementById('deploy-form');
+    if (!form) return;
+    form.addEventListener('submit', async (ev) => {
+      ev.preventDefault();
+      const status = document.getElementById('deploy-form-status');
+      const confirm = form.elements.confirm.value.trim();
+      if (confirm !== 'FORCER') {
+        status.textContent = t('deploy_need_forcer');
+        status.classList.add('error');
+        return;
+      }
+      status.classList.remove('error');
+      status.textContent = t('deploy_running');
+      try {
+        const res = await fetch('/api/deploy', {
+          method: 'POST',
+          headers: { 'Content-Type': 'application/json' },
+          body: JSON.stringify({
+            stack: state.selectedId,
+            backend: form.elements.backend.value,
+            confirm: confirm
+          })
+        });
+        const body = await res.json();
+        if (!res.ok) throw new Error(body.error || res.status);
+        form.elements.confirm.value = '';
+        streamDeployLog();
+      } catch (e) {
+        status.textContent = String(e.message || e);
+        status.classList.add('error');
+      }
+    });
+  }
+
   /* ---------- Nœuds (B-02d) ---------- */
 
   async function loadNodes() {
@@ -609,6 +746,7 @@
     }
     initModelForm();
     initNodeForm();
+    initDeployForm();
     setTheme(state.theme);
     setLang(state.lang);
   }
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index 0039fe3..cca0b1c 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -45,6 +45,28 @@
       <div id="bricks-list" class="bricks-list" aria-live="polite"></div>
     </section>
 
+    <section id="deploy" class="card hidden">
+      <h2 data-i18n="deploy_title">Résumé &amp; Déploiement</h2>
+      <p data-i18n="deploy_subtitle">Vérifiez le résumé, puis tapez FORCER pour lancer le déploiement réel — chaque étape est prouvée en direct.</p>
+      <div id="deploy-summary" class="models-list" aria-live="polite"></div>
+      <form id="deploy-form" class="model-form" autocomplete="off">
+        <div class="form-grid">
+          <label><span data-i18n="f_backend">Backend</span>
+            <select name="backend">
+              <option value="compose">Docker Compose</option>
+              <option value="k3s">K3s</option>
+            </select></label>
+          <label><span data-i18n="f_confirm">Confirmation (tapez FORCER)</span>
+            <input name="confirm" required placeholder="FORCER" autocomplete="off" spellcheck="false"></label>
+        </div>
+        <div class="form-actions">
+          <button type="submit" class="btn" data-i18n="launch_deploy">Déployer le stack</button>
+          <span id="deploy-form-status" class="form-status" aria-live="polite"></span>
+        </div>
+      </form>
+      <pre id="deploy-log" class="deploy-log hidden" aria-live="polite"></pre>
+    </section>
+
     <section id="nodes" class="card">
       <h2 data-i18n="nodes_title">Nœuds — cluster multi-machines</h2>
       <p data-i18n="nodes_subtitle">Ajoutez un nœud avec son IP, utilisateur et mot de passe — utilisé une seule fois au bootstrap, puis bascule sur clé ed25519. Jamais écrit sur disque.</p>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 6f2fb2e..207dde1 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -3,6 +3,10 @@ from __future__ import annotations
 import importlib.resources
 import json
 import os
+import subprocess
+import sys
+import threading
+import time
 import urllib.parse
 import webbrowser
 from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
@@ -11,12 +15,14 @@ from pathlib import Path
 from forgeai.catalogue.spheres import SPHERES, classify_sphere, spheres_index
 from forgeai.core import registre
 from forgeai.core.runner import SubprocessRunner, CommandRunner
+from forgeai.deploy.compose import http_ok
 from forgeai.hardware.detect import HardwareDetector
 from forgeai.models.probe import Transport
 from forgeai.models.routes import RouteError, RouteStore
 from forgeai.network.keys import generate_keypair, KeyError_
 from forgeai.network.node_add import add_node, Bootstrapper, NodeAddError, SshBootstrapper
 from forgeai.network.nodes import cluster_status, ClusterError
+from forgeai.preflight import available_backends, run_checks
 from forgeai.resources import catalogue_path
 from forgeai.stacks import deploy_ids, list_stacks, load_stack
 
@@ -151,6 +157,17 @@ _REGISTRE_PATH: Path | None = None
 _NODE_BOOTSTRAPPER: Bootstrapper | None = None
 _NODE_KEYS_DIR: Path | None = None
 
+# Hook déploiement : remplace la commande wizard par défaut dans les tests.
+_DEPLOY_CMD: list[str] | None = None
+
+_DEPLOY_STATE = {
+    "proc": None,
+    "lines": [],
+    "done": False,
+    "exit_code": None,
+    "lock": threading.Lock(),
+}
+
 
 def _models_home() -> Path:
     return _MODELS_HOME if _MODELS_HOME is not None else forgeai_home() / "models"
@@ -174,6 +191,31 @@ def _node_keys(runner: CommandRunner) -> tuple[Path, Path]:
     return public, private
 
 
+def _available_backends() -> list[str]:
+    return available_backends(
+        run_checks(SubprocessRunner(), HardwareDetector(SubprocessRunner()), http_ok)
+    )
+
+
+def _summary_payload(stack_id: str) -> dict:
+    stack = load_stack(stack_id)
+    profile = HardwareDetector(SubprocessRunner()).full_report()
+    return {
+        "stack": {
+            "id": stack.get("id", stack_id),
+            "name": stack.get("name", stack_id),
+            "n_deploy": len(deploy_ids(stack)),
+        },
+        "hardware": {
+            "cpu_model": getattr(profile, "cpu_model", ""),
+            "gpus": len(getattr(profile, "gpus", [])),
+            "ram_gb": getattr(profile, "ram_gb", 0),
+        },
+        "backends": _available_backends(),
+        "chassis": len(chassis_ids()),
+    }
+
+
 class ForgeAIHandler(BaseHTTPRequestHandler):
     server_version = "ForgeAI/0.1"
 
@@ -187,6 +229,35 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
     def _send_json(self, code: int, obj: object) -> None:
         self._send(code, _json_body(obj), "application/json; charset=utf-8")
 
+    def _read_json_body(self, max_length: int = 65536) -> dict | None:
+        length_hdr = self.headers.get("Content-Length")
+        if length_hdr is None:
+            self._send_json(413, {"error": "Content-Length requis"})
+            return None
+
+        try:
+            length = int(length_hdr)
+        except ValueError:
+            self._send_json(400, {"error": "Content-Length invalide"})
+            return None
+
+        if length < 0 or length > max_length:
+            self._send_json(413, {"error": "corps trop grand"})
+            return None
+
+        try:
+            body = self.rfile.read(length)
+            data = json.loads(body.decode("utf-8"))
+        except (json.JSONDecodeError, UnicodeDecodeError):
+            self._send_json(400, {"error": "JSON invalide"})
+            return None
+
+        if not isinstance(data, dict):
+            self._send_json(400, {"error": "JSON invalide"})
+            return None
+
+        return data
+
     def do_GET(self) -> None:  # noqa: N802
         parsed = urllib.parse.urlparse(self.path)
         path = parsed.path
@@ -286,6 +357,57 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             self._send_json(200, payload)
             return
 
+        if path == "/api/summary":
+            query = urllib.parse.parse_qs(parsed.query)
+            stack_list = query.get("stack")
+            if not stack_list:
+                self._send_json(400, {"error": "stack requis"})
+                return
+            stack_id = stack_list[0]
+            try:
+                self._send_json(200, _summary_payload(stack_id))
+            except FileNotFoundError:
+                self._send_json(404, {"error": "stack not found"})
+            return
+
+        if path == "/api/deploy/events":
+            self.send_response(200)
+            self.send_header("Content-Type", "text/event-stream")
+            self.send_header("Cache-Control", "no-cache")
+            self.end_headers()
+
+            if _DEPLOY_STATE["proc"] is None:
+                payload = json.dumps({"exit_code": None}, ensure_ascii=False)
+                try:
+                    self.wfile.write(f"event: end\ndata: {payload}\n\n".encode("utf-8"))
+                    self.wfile.flush()
+                except (BrokenPipeError, ConnectionResetError):
+                    pass
+                return
+
+            idx = 0
+            while True:
+                with _DEPLOY_STATE["lock"]:
+                    lines = _DEPLOY_STATE["lines"]
+                    done = _DEPLOY_STATE["done"]
+                    exit_code = _DEPLOY_STATE["exit_code"]
+                    while idx < len(lines):
+                        try:
+                            self.wfile.write(f"data: {lines[idx]}\n\n".encode("utf-8"))
+                            self.wfile.flush()
+                        except (BrokenPipeError, ConnectionResetError):
+                            return
+                        idx += 1
+                    if done:
+                        payload = json.dumps({"exit_code": exit_code}, ensure_ascii=False)
+                        try:
+                            self.wfile.write(f"event: end\ndata: {payload}\n\n".encode("utf-8"))
+                            self.wfile.flush()
+                        except (BrokenPipeError, ConnectionResetError):
+                            pass
+                        return
+                time.sleep(0.2)
+
         if path == "/api/nodes/status":
             runner = SubprocessRunner()
             try:
@@ -309,30 +431,8 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
         path = parsed.path
 
         if path == "/api/nodes":
-            length_hdr = self.headers.get("Content-Length")
-            if length_hdr is None:
-                self._send_json(413, {"error": "Content-Length requis"})
-                return
-
-            try:
-                length = int(length_hdr)
-            except ValueError:
-                self._send_json(400, {"error": "Content-Length invalide"})
-                return
-
-            if length < 0 or length > 65536:
-                self._send_json(413, {"error": "corps trop grand"})
-                return
-
-            try:
-                body = self.rfile.read(length)
-                data = json.loads(body.decode("utf-8"))
-            except (json.JSONDecodeError, UnicodeDecodeError):
-                self._send_json(400, {"error": "JSON invalide"})
-                return
-
-            if not isinstance(data, dict):
-                self._send_json(400, {"error": "JSON invalide"})
+            data = self._read_json_body()
+            if data is None:
                 return
 
             required = ["ip", "user", "password"]
@@ -387,34 +487,96 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             )
             return
 
-        if path != "/api/models":
-            self._send_json(404, {"error": "not found"})
-            return
+        if path == "/api/deploy":
+            data = self._read_json_body()
+            if data is None:
+                return
 
-        length_hdr = self.headers.get("Content-Length")
-        if length_hdr is None:
-            self._send_json(413, {"error": "Content-Length requis"})
-            return
+            required = ["stack", "backend", "confirm"]
+            missing = [field for field in required if field not in data]
+            if missing:
+                self._send_json(400, {"error": "champs manquants", "missing": missing})
+                return
 
-        try:
-            length = int(length_hdr)
-        except ValueError:
-            self._send_json(400, {"error": "Content-Length invalide"})
-            return
+            stack_id = data["stack"]
+            backend = data["backend"]
+            confirm = data["confirm"]
 
-        if length < 0 or length > 65536:
-            self._send_json(413, {"error": "corps trop grand"})
+            if confirm != "FORCER":
+                self._send_json(400, {"error": "confirmation 'FORCER' requise"})
+                return
+
+            if backend not in {"compose", "k3s"}:
+                self._send_json(400, {"error": "backend invalide"})
+                return
+
+            try:
+                load_stack(stack_id)
+            except FileNotFoundError:
+                self._send_json(404, {"error": "stack not found"})
+                return
+
+            with _DEPLOY_STATE["lock"]:
+                proc = _DEPLOY_STATE["proc"]
+                if proc is not None and proc.poll() is None:
+                    self._send_json(409, {"error": "déploiement déjà en cours"})
+                    return
+
+                _DEPLOY_STATE["lines"].clear()
+                _DEPLOY_STATE["done"] = False
+                _DEPLOY_STATE["exit_code"] = None
+
+                cmd = _DEPLOY_CMD if _DEPLOY_CMD is not None else [
+                    sys.executable,
+                    "-m",
+                    "forgeai",
+                    "wizard",
+                    "--ci",
+                    "--workdir",
+                    str(forgeai_home() / "deploy"),
+                    "--backend",
+                    backend,
+                ]
+
+                new_proc = subprocess.Popen(
+                    cmd,
+                    stdout=subprocess.PIPE,
+                    stderr=subprocess.STDOUT,
+                    text=True,
+                    bufsize=1,
+                )
+                _DEPLOY_STATE["proc"] = new_proc
+
+            def _reader() -> None:
+                try:
+                    for line in new_proc.stdout:
+                        with _DEPLOY_STATE["lock"]:
+                            _DEPLOY_STATE["lines"].append(line.rstrip("\r\n"))
+                    new_proc.wait()
+                    with _DEPLOY_STATE["lock"]:
+                        _DEPLOY_STATE["exit_code"] = new_proc.returncode
+                        _DEPLOY_STATE["done"] = True
+                except Exception:
+                    with _DEPLOY_STATE["lock"]:
+                        if new_proc.returncode is None:
+                            try:
+                                new_proc.kill()
+                                new_proc.wait()
+                            except Exception:
+                                pass
+                        _DEPLOY_STATE["exit_code"] = new_proc.returncode if new_proc.returncode is not None else -1
+                        _DEPLOY_STATE["done"] = True
+
+            threading.Thread(target=_reader, daemon=True).start()
+            self._send_json(202, {"started": True})
             return
 
-        try:
-            body = self.rfile.read(length)
-            data = json.loads(body.decode("utf-8"))
-        except (json.JSONDecodeError, UnicodeDecodeError):
-            self._send_json(400, {"error": "JSON invalide"})
+        if path != "/api/models":
+            self._send_json(404, {"error": "not found"})
             return
 
-        if not isinstance(data, dict):
-            self._send_json(400, {"error": "JSON invalide"})
+        data = self._read_json_body()
+        if data is None:
             return
 
         required = ["name", "provenance", "model_id", "api_key", "passphrase"]
diff --git a/tests/test_web_deploy.py b/tests/test_web_deploy.py
new file mode 100644
index 0000000..bdaf56e
--- /dev/null
+++ b/tests/test_web_deploy.py
@@ -0,0 +1,122 @@
+import json
+import sys
+import threading
+import urllib.error
+import urllib.request
+
+import pytest
+
+from forgeai.web.server import _DEPLOY_STATE, build_server
+
+
+def _request(url: str, data: bytes | None = None, method: str | None = None) -> tuple[int, str]:
+    req = urllib.request.Request(url, data=data, method=method)
+    if data is not None:
+        req.add_header("Content-Type", "application/json")
+    try:
+        with urllib.request.urlopen(req, timeout=15) as resp:
+            return resp.status, resp.read().decode("utf-8")
+    except urllib.error.HTTPError as exc:
+        # 4xx/5xx font partie du contrat testé — retournés, pas levés
+        return exc.code, exc.read().decode("utf-8")
+
+
+@pytest.fixture
+def server():
+    srv = build_server("127.0.0.1", 0)
+    thread = threading.Thread(target=srv.serve_forever, daemon=True)
+    thread.start()
+    yield f"http://127.0.0.1:{srv.server_address[1]}"
+    srv.shutdown()
+    srv.server_close()
+
+
+@pytest.fixture
+def fake_deploy(monkeypatch):
+    cmd = [
+        sys.executable,
+        "-u",
+        "-c",
+        "print('etape 1/3 detection'); print('etape 2/3 plan'); print('etape 3/3 sante OK')",
+    ]
+    monkeypatch.setattr("forgeai.web.server._DEPLOY_CMD", cmd)
+
+    with _DEPLOY_STATE["lock"]:
+        proc = _DEPLOY_STATE["proc"]
+        _DEPLOY_STATE["proc"] = None
+        _DEPLOY_STATE["lines"].clear()
+        _DEPLOY_STATE["done"] = False
+        _DEPLOY_STATE["exit_code"] = None
+    if proc is not None and proc.poll() is None:
+        proc.terminate()
+        proc.wait()
+
+    yield
+
+    with _DEPLOY_STATE["lock"]:
+        proc = _DEPLOY_STATE["proc"]
+        _DEPLOY_STATE["proc"] = None
+    if proc is not None and proc.poll() is None:
+        proc.terminate()
+        proc.wait()
+
+
+def test_summary(server):
+    status, body = _request(f"{server}/api/summary?stack=agentique")
+    assert status == 200
+    data = json.loads(body)
+    assert data["stack"]["n_deploy"] == 72
+    assert isinstance(data["backends"], list)
+    assert "cpu_model" in data["hardware"]
+
+
+def test_summary_stack_inconnu(server):
+    status, _ = _request(f"{server}/api/summary?stack=xyz")
+    assert status == 404
+    status, _ = _request(f"{server}/api/summary")
+    assert status == 400
+
+
+def test_deploy_friction_forcer(server, fake_deploy):
+    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "oui"}).encode("utf-8")
+    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")
+    assert status == 400
+    assert "FORCER" in body
+    assert _DEPLOY_STATE["proc"] is None
+
+
+def test_deploy_et_sse(server, fake_deploy):
+    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
+    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")
+    assert status == 202
+    assert json.loads(body)["started"] is True
+
+    req = urllib.request.Request(f"{server}/api/deploy/events")
+    with urllib.request.urlopen(req, timeout=15) as resp:
+        stream = resp.read().decode("utf-8")
+
+    assert "etape 1/3 detection" in stream
+    assert "etape 3/3 sante OK" in stream
+    assert "event: end" in stream
+    assert '"exit_code": 0' in stream
+
+
+def test_deploy_deja_en_cours(server, fake_deploy, monkeypatch):
+    monkeypatch.setattr(
+        "forgeai.web.server._DEPLOY_CMD",
+        [sys.executable, "-u", "-c", "import time; time.sleep(3)"],
+    )
+
+    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
+    status, _ = _request(f"{server}/api/deploy", data=payload, method="POST")
+    assert status == 202
+
+    status2, body2 = _request(f"{server}/api/deploy", data=payload, method="POST")
+    assert status2 == 409
+    assert "déploiement déjà en cours" in body2
+
+
+def test_non_regression(server):
+    for path in ("/api/stacks", "/api/models", "/api/nodes/status"):
+        status, _ = _request(f"{server}{path}")
+        assert status == 200, path
```
