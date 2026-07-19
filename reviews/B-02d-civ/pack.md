# Story B-02d — Page Noeuds multi-machines (Tier T2 — bootstrap SSH + secret ephemere)

## Criteres (spec-web-ui §5 B-02d ; exigence Nathan : 'ecran d'ajout de noeud IP/user/mot de passe ephemere')
- GET /api/nodes/status : cluster_status live ; graceful (200 {nodes:[],detail} si pas de cluster).
- POST /api/nodes {ip,user,password} : add_node (mdp UNE fois -> bascule cle ed25519 -> empreinte seule au registre) ; champs manquants=400 sans reflet ; echec bootstrap=400 clair ; outil/cle absent=500 JSON propre ; JAMAIS de crash handler.
- Confidentialite du mdp — n'apparait dans AUCUN fichier (teste par parcours recursif) ; vide du DOM des soumission cote client.
- Frontend : table cluster, formulaire, i18n FR/EN.

## PREUVE D'EXECUTION (suite + no-stub + NAVIGATEUR REEL + API live)
```
### SUITE COMPLETE
........................................................................ [ 92%]
...............................                                          [100%]

### no_stub
NO-STUB-SCAN : OK (3 fichiers scannés, zéro violation)

### VERIFICATION NAVIGATEUR REEL (Chrome preview, localhost:8877)
Section Noeuds rendue ; liste cluster peuplee (cluster_status live : pc1-x870e-taichi control-plane).
Formulaire IP/user/mot de passe soumis vers 192.0.2.199 (TEST-NET, non routable).
HYGIENE : mot de passe VIDE DU DOM des la soumission (avant meme la reponse).
Bootstrap SSH REEL tente -> sshpass absent sur ce poste -> 500 JSON PROPRE "outil requis absent : sshpass"
affiche en style erreur. AUCUN crash du handler (correctif orchestrateur : FileNotFoundError + Exception -> 500 JSON, jamais de RemoteDisconnected).

### API live
GET /api/nodes/status -> 200 : 4 noeud(s)
POST sans password -> 400 : {"error": "champs manquants", "missing": ["password"]}
```

## Note correctifs orchestrateur (par difficulte : robustesse handler)
- Le codeur ne rattrapait que NodeAddError/KeyError_ ; un outil absent (sshpass) => FileNotFoundError => crash silencieux du handler (RemoteDisconnected cote client). Ajout : FileNotFoundError -> 500 'outil requis absent' + Exception -> 500 generique (aucune valeur reflechie).
- Tests : champs registre alignes (type/payload) ; pragmas proof:allow sur identifiants password (faux positifs du filet anti-secret).

## DIFF COMPLET (main...HEAD — 4 fichiers)
```diff
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index ba180d9..bef441c 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -59,7 +59,17 @@
       testing_route: 'Test de connexion en cours…',
       route_added: 'Route ajoutée — test réel réussi.',
       no_models: 'Aucune route configurée pour l\'instant.',
-      fingerprint_label: 'empreinte'
+      fingerprint_label: 'empreinte',
+      nodes_title: 'Nœuds — cluster multi-machines',
+      nodes_subtitle: 'Ajoutez un nœud avec son IP, utilisateur et mot de passe — utilisé une seule fois au bootstrap, puis bascule sur clé ed25519. Jamais écrit sur disque.',
+      f_node_ip: 'Adresse IP',
+      f_node_user: 'Utilisateur',
+      f_node_password: 'Mot de passe (éphémère)', // proof:allow (libellé i18n)
+      node_key_note: '🔑 Le mot de passe sert une seule fois : installation de la clé publique, bascule immédiate sur ed25519, puis seule l\'empreinte est journalisée au registre.',
+      add_node: 'Ajouter le nœud',
+      adding_node: 'Bootstrap du nœud en cours…',
+      node_added: 'Nœud ajouté — bascule clé ed25519 réussie.',
+      no_nodes: 'Aucun nœud dans le cluster pour l\'instant.'
     },
     en: {
       title: 'ForgeAI Toolkit',
@@ -104,7 +114,17 @@
       testing_route: 'Connection test running…',
       route_added: 'Route added — real test passed.',
       no_models: 'No route configured yet.',
-      fingerprint_label: 'fingerprint'
+      fingerprint_label: 'fingerprint',
+      nodes_title: 'Nodes — multi-machine cluster',
+      nodes_subtitle: 'Add a node with its IP, user and password — used once at bootstrap, then switches to an ed25519 key. Never written to disk.',
+      f_node_ip: 'IP address',
+      f_node_user: 'User',
+      f_node_password: 'Password (ephemeral)', // proof:allow (libellé i18n)
+      node_key_note: '🔑 The password is used once: public key install, immediate switch to ed25519, then only the fingerprint is logged to the ledger.',
+      add_node: 'Add node',
+      adding_node: 'Node bootstrap running…',
+      node_added: 'Node added — ed25519 key switch succeeded.',
+      no_nodes: 'No node in the cluster yet.'
     }
   };
 
@@ -157,6 +177,7 @@
       renderBricks();
     }
     if (state.models !== undefined) renderModels();
+    if (state.nodes !== undefined) renderNodes();
   }
 
   async function fetchJson(path) {
@@ -456,6 +477,72 @@
     `).join('');
   }
 
+  /* ---------- Nœuds (B-02d) ---------- */
+
+  async function loadNodes() {
+    const list = document.getElementById('nodes-list');
+    if (!list) return;
+    try {
+      state.nodes = await fetchJson('/api/nodes/status');
+    } catch (e) {
+      list.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
+      return;
+    }
+    renderNodes();
+  }
+
+  function renderNodes() {
+    const list = document.getElementById('nodes-list');
+    if (!list) return;
+    const nodes = (state.nodes && state.nodes.nodes) || [];
+    if (!nodes.length) {
+      list.innerHTML = `<p class="form-note">${escapeHtml(t('no_nodes'))}</p>`;
+      return;
+    }
+    list.innerHTML = nodes.map((n) => `
+      <div class="model-row">
+        <span class="brick-name">${escapeHtml(n.name || n.hostname || n.ip || '?')}</span>
+        ${n.ip ? `<span class="def-pill">${escapeHtml(n.ip)}</span>` : ''}
+        ${n.status ? `<span class="def-pill">${escapeHtml(n.status)}</span>` : ''}
+        ${n.roles ? `<span class="def-pill">${escapeHtml(String(n.roles))}</span>` : ''}
+      </div>
+    `).join('');
+  }
+
+  function initNodeForm() {
+    const form = document.getElementById('node-form');
+    if (!form) return;
+    form.addEventListener('submit', async (ev) => {
+      ev.preventDefault();
+      const status = document.getElementById('node-form-status');
+      const payload = {
+        ip: form.elements.ip.value.trim(),
+        user: form.elements.user.value.trim(),
+        password: form.elements.password.value // proof:allow (champ payload, valeur jamais litterale)
+      };
+      // hygiène : mot de passe vidé du DOM AVANT l'appel — strictement éphémère
+      form.elements.password.value = '';
+      status.textContent = t('adding_node');
+      status.classList.remove('error');
+      try {
+        const res = await fetch('/api/nodes', {
+          method: 'POST',
+          headers: { 'Content-Type': 'application/json' },
+          body: JSON.stringify(payload)
+        });
+        const body = await res.json();
+        if (!res.ok) throw new Error(body.error || res.status);
+        status.textContent = `${t('node_added')} (${body.node.key_fingerprint})`;
+        form.elements.ip.value = '';
+        form.elements.user.value = '';
+        loadNodes();
+      } catch (e) {
+        status.textContent = String(e.message || e);
+        status.classList.add('error');
+      }
+    });
+  }
+
   function initModelForm() {
     const form = document.getElementById('model-form');
     if (!form) return;
@@ -521,6 +608,7 @@
       });
     }
     initModelForm();
+    initNodeForm();
     setTheme(state.theme);
     setLang(state.lang);
   }
@@ -528,6 +616,7 @@
   async function boot() {
     initControls();
     loadModels();
+    loadNodes();
     try {
       const [detect, stacks, spheres] = await Promise.all([
         fetchJson('/api/detect'),
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index 962e032..0039fe3 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -45,6 +45,27 @@
       <div id="bricks-list" class="bricks-list" aria-live="polite"></div>
     </section>
 
+    <section id="nodes" class="card">
+      <h2 data-i18n="nodes_title">Nœuds — cluster multi-machines</h2>
+      <p data-i18n="nodes_subtitle">Ajoutez un nœud avec son IP, utilisateur et mot de passe — utilisé une seule fois au bootstrap, puis bascule sur clé ed25519. Jamais écrit sur disque.</p>
+      <div id="nodes-list" class="models-list" aria-live="polite"></div>
+      <form id="node-form" class="model-form" autocomplete="off">
+        <div class="form-grid">
+          <label><span data-i18n="f_node_ip">Adresse IP</span>
+            <input name="ip" required placeholder="192.168.1.31" spellcheck="false"></label>
+          <label><span data-i18n="f_node_user">Utilisateur</span>
+            <input name="user" required placeholder="forge" spellcheck="false"></label>
+          <label><span data-i18n="f_node_password">Mot de passe (éphémère)</span>
+            <input name="password" type="password" required autocomplete="new-password"></label>
+        </div>
+        <p class="form-note" data-i18n="node_key_note">🔑 Le mot de passe sert une seule fois : installation de la clé publique, bascule immédiate sur ed25519, puis seule l'empreinte est journalisée au registre.</p>
+        <div class="form-actions">
+          <button type="submit" class="btn" data-i18n="add_node">Ajouter le nœud</button>
+          <span id="node-form-status" class="form-status" aria-live="polite"></span>
+        </div>
+      </form>
+    </section>
+
     <section id="models" class="card">
       <h2 data-i18n="models_title">Modèles &amp; clés API</h2>
       <p data-i18n="models_subtitle">Routes modèle cloud — test de connexion réel obligatoire ; la clé est scellée au coffre, seule l'empreinte est conservée.</p>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 7697429..6f2fb2e 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -10,10 +10,13 @@ from pathlib import Path
 
 from forgeai.catalogue.spheres import SPHERES, classify_sphere, spheres_index
 from forgeai.core import registre
-from forgeai.core.runner import SubprocessRunner
+from forgeai.core.runner import SubprocessRunner, CommandRunner
 from forgeai.hardware.detect import HardwareDetector
 from forgeai.models.probe import Transport
 from forgeai.models.routes import RouteError, RouteStore
+from forgeai.network.keys import generate_keypair, KeyError_
+from forgeai.network.node_add import add_node, Bootstrapper, NodeAddError, SshBootstrapper
+from forgeai.network.nodes import cluster_status, ClusterError
 from forgeai.resources import catalogue_path
 from forgeai.stacks import deploy_ids, list_stacks, load_stack
 
@@ -145,6 +148,9 @@ _MODELS_HOME: Path | None = None
 _PROBE_TRANSPORT: Transport | None = None
 _REGISTRE_PATH: Path | None = None
 
+_NODE_BOOTSTRAPPER: Bootstrapper | None = None
+_NODE_KEYS_DIR: Path | None = None
+
 
 def _models_home() -> Path:
     return _MODELS_HOME if _MODELS_HOME is not None else forgeai_home() / "models"
@@ -158,6 +164,16 @@ def _registre_path() -> Path:
     return _REGISTRE_PATH if _REGISTRE_PATH is not None else forgeai_home() / "Registres" / "mission.jsonl"
 
 
+def _node_keys(runner: CommandRunner) -> tuple[Path, Path]:
+    """Retourne la paire de clés active, la génère si elle est absente."""
+    key_dir = _NODE_KEYS_DIR if _NODE_KEYS_DIR is not None else forgeai_home() / "keys"
+    private = key_dir / "forgeai_ed25519"
+    public = private.with_suffix(".pub")
+    if not private.exists() or not public.exists():
+        generate_keypair(key_dir, runner)
+    return public, private
+
+
 class ForgeAIHandler(BaseHTTPRequestHandler):
     server_version = "ForgeAI/0.1"
 
@@ -270,6 +286,15 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             self._send_json(200, payload)
             return
 
+        if path == "/api/nodes/status":
+            runner = SubprocessRunner()
+            try:
+                nodes = cluster_status(runner)
+                self._send_json(200, {"nodes": nodes})
+            except ClusterError as exc:
+                self._send_json(200, {"nodes": [], "detail": str(exc)})
+            return
+
         basename = path.rsplit("/", 1)[-1]
         data = _asset_bytes(basename)
         if data is not None:
@@ -283,6 +308,85 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
         parsed = urllib.parse.urlparse(self.path)
         path = parsed.path
 
+        if path == "/api/nodes":
+            length_hdr = self.headers.get("Content-Length")
+            if length_hdr is None:
+                self._send_json(413, {"error": "Content-Length requis"})
+                return
+
+            try:
+                length = int(length_hdr)
+            except ValueError:
+                self._send_json(400, {"error": "Content-Length invalide"})
+                return
+
+            if length < 0 or length > 65536:
+                self._send_json(413, {"error": "corps trop grand"})
+                return
+
+            try:
+                body = self.rfile.read(length)
+                data = json.loads(body.decode("utf-8"))
+            except (json.JSONDecodeError, UnicodeDecodeError):
+                self._send_json(400, {"error": "JSON invalide"})
+                return
+
+            if not isinstance(data, dict):
+                self._send_json(400, {"error": "JSON invalide"})
+                return
+
+            required = ["ip", "user", "password"]
+            missing = [field for field in required if field not in data]
+            if missing:
+                self._send_json(400, {"error": "champs manquants", "missing": missing})
+                return
+
+            ip = data["ip"]
+            user = data["user"]
+            password = data["password"]  # proof:allow (identifiant ; valeur jamais journalisee)
+
+            try:
+                runner = SubprocessRunner()
+                pubkey, privkey = _node_keys(runner)
+                bootstrapper = _NODE_BOOTSTRAPPER if _NODE_BOOTSTRAPPER is not None else SshBootstrapper()
+                record = add_node(
+                    ip,
+                    user,
+                    password,
+                    pubkey=pubkey,
+                    privkey=privkey,
+                    bootstrapper=bootstrapper,
+                    runner=runner,
+                    registre_path=_registre_path(),
+                )
+            except NodeAddError as exc:
+                self._send_json(400, {"error": str(exc)})
+                return
+            except KeyError_:
+                self._send_json(500, {"error": "erreur de gestion des clés"})
+                return
+            except FileNotFoundError as exc:
+                # outil requis absent (ex. sshpass, ssh-keygen) — réponse propre,
+                # jamais de crash silencieux du handler (preuve navigateur B-02d)
+                self._send_json(500, {"error": f"outil requis absent : {exc.filename or exc}"})
+                return
+            except Exception:
+                # aucune valeur soumise n'est reflétée
+                self._send_json(500, {"error": "erreur interne lors de l'ajout du nœud"})
+                return
+
+            self._send_json(
+                201,
+                {
+                    "node": {
+                        "ip": record.ip,
+                        "user": record.user,
+                        "key_fingerprint": record.key_fingerprint,
+                    }
+                },
+            )
+            return
+
         if path != "/api/models":
             self._send_json(404, {"error": "not found"})
             return
diff --git a/tests/test_web_nodes.py b/tests/test_web_nodes.py
new file mode 100644
index 0000000..4566569
--- /dev/null
+++ b/tests/test_web_nodes.py
@@ -0,0 +1,177 @@
+import json
+import threading
+import urllib.error
+import urllib.request
+from pathlib import Path
+
+import pytest
+
+from forgeai.network.node_add import NodeAddError
+from forgeai.web import server as server_module
+
+
+def request_json(url, method="GET", data=None):
+    headers = {}
+    body = None
+    if data is not None:
+        body = json.dumps(data).encode("utf-8")
+        headers["Content-Type"] = "application/json"
+    req = urllib.request.Request(url, data=body, headers=headers, method=method)
+    try:
+        with urllib.request.urlopen(req) as resp:
+            return resp.status, json.loads(resp.read().decode("utf-8"))
+    except urllib.error.HTTPError as exc:
+        response_body = exc.read().decode("utf-8")
+        try:
+            return exc.code, json.loads(response_body)
+        except json.JSONDecodeError:
+            return exc.code, response_body
+
+
+@pytest.fixture
+def tmp_env(monkeypatch, tmp_path):
+    keys_dir = tmp_path / "keys"
+    keys_dir.mkdir()
+    (keys_dir / "forgeai_ed25519").write_text("fake-private-key")
+    (keys_dir / "forgeai_ed25519.pub").write_text(
+        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDIhz2GK fake"
+    )
+    models_dir = tmp_path / "models"
+    models_dir.mkdir()
+
+    monkeypatch.setattr(server_module, "_NODE_KEYS_DIR", keys_dir)
+    monkeypatch.setattr(server_module, "_REGISTRE_PATH", tmp_path / "r.jsonl")
+    monkeypatch.setattr(server_module, "_MODELS_HOME", models_dir)
+    return tmp_path
+
+
+@pytest.fixture
+def fake_bootstrapper(monkeypatch, tmp_env):
+    import forgeai.network.node_add as node_add_module
+
+    class FakeBootstrapper:
+        def __init__(self):
+            self.calls = []
+
+        def install_key(self, ip, user, passwd, pubkey):
+            self.calls.append(("install", ip, user, passwd, str(pubkey)))
+
+        def verify_key(self, ip, user, privkey):
+            self.calls.append(("verify", ip, user, str(privkey)))
+            return True
+
+    bs = FakeBootstrapper()
+    monkeypatch.setattr(server_module, "_NODE_BOOTSTRAPPER", bs)
+    monkeypatch.setattr(
+        node_add_module, "key_fingerprint", lambda pubkey, runner: "SHA256:FAKEFP"
+    )
+    return bs
+
+
+@pytest.fixture
+def base_url(tmp_env):
+    server = server_module.build_server("127.0.0.1", 0)
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+    host, port = server.server_address
+    yield f"http://{host}:{port}"
+    server.shutdown()
+    server.server_close()
+
+
+def test_add_node_ok(base_url, tmp_env, fake_bootstrapper):
+    password = "mdp-Distinctif-9"  # proof:allow (litteral de test : sert a PROUVER la non-persistance)
+    payload = {"ip": "192.168.1.31", "user": "forge", "password": password}
+    status, body = request_json(f"{base_url}/api/nodes", method="POST", data=payload)
+
+    assert status == 201
+    node = body["node"]
+    assert node["ip"] == "192.168.1.31"
+    assert node["user"] == "forge"
+    assert node["key_fingerprint"] == "SHA256:FAKEFP"
+    assert "password" not in body
+
+    assert any(call[0] == "install" for call in fake_bootstrapper.calls)
+    assert any(call[0] == "verify" for call in fake_bootstrapper.calls)
+
+    for path in tmp_env.rglob("*"):
+        if path.is_file():
+            content = path.read_text(errors="ignore")
+            assert password not in content, f"password found in {path}"
+
+    reg_path = tmp_env / "r.jsonl"
+    assert reg_path.exists()
+    events = [json.loads(line) for line in reg_path.read_text(encoding="utf-8").splitlines()]
+    node_events = [e for e in events if e.get("type") == "node_added"]
+    assert len(node_events) == 1
+    data = node_events[0]["payload"]
+    assert data["ip"] == "192.168.1.31"
+    assert data["user"] == "forge"
+    assert data["key_fingerprint"] == "SHA256:FAKEFP"
+    assert password not in str(data)
+
+
+def test_add_node_echec_bootstrap(base_url, tmp_env, monkeypatch):
+    class FailingBootstrapper:
+        def install_key(self, ip, user, passwd, pubkey):
+            raise NodeAddError("auth refusee")
+
+        def verify_key(self, ip, user, privkey):
+            return False
+
+    monkeypatch.setattr(server_module, "_NODE_BOOTSTRAPPER", FailingBootstrapper())
+
+    status, body = request_json(
+        f"{base_url}/api/nodes",
+        method="POST",
+        data={"ip": "192.168.1.31", "user": "forge", "password": "x"},
+    )
+
+    assert status == 400
+    assert "auth refusee" in body["error"]
+
+    reg_path = tmp_env / "r.jsonl"
+    assert not reg_path.exists() or reg_path.read_text() == ""
+
+
+def test_add_node_champs_manquants(base_url):
+    distinctive_ip = "1.2.3.4"
+    distinctive_user = "utilisateur_distinctif_42"
+    status, body = request_json(
+        f"{base_url}/api/nodes",
+        method="POST",
+        data={"ip": distinctive_ip, "user": distinctive_user},
+    )
+
+    assert status == 400
+    assert body["error"] == "champs manquants"
+    assert "password" in body["missing"]
+    assert distinctive_ip not in str(body)
+    assert distinctive_user not in str(body)
+    assert "password" not in str(body.get("password", ""))
+
+
+def test_nodes_status_graceful(base_url, monkeypatch):
+    def boom(runner):
+        raise server_module.ClusterError("pas de cluster")
+
+    monkeypatch.setattr(server_module, "cluster_status", boom)
+
+    status, body = request_json(f"{base_url}/api/nodes/status")
+
+    assert status == 200
+    assert body["nodes"] == []
+    assert "pas de cluster" in body["detail"]
+
+
+def test_non_regression(base_url):
+    status, body = request_json(f"{base_url}/api/models")
+    assert status == 200
+    assert isinstance(body, list)
+
+    status, body = request_json(f"{base_url}/api/stacks")
+    assert status == 200
+    assert isinstance(body, list)
+
+    status, body = request_json(f"{base_url}/api/nope", method="POST", data={})
+    assert status == 404
```
