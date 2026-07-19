# Story IMPL-4 — Page briques additionnelles (catalogue par sphere, cases, chassis verrouille)

## Criteres (exigence Nathan verbatim : sous-etapes par sphere, catalogue COMPLET expose avec descriptions, cases a cocher, briques du stack marquees 'installe', chassis non-decochable, 100% modulable)
- GET /api/bricks?sphere=SN[&stack=id] -> briques de la sphere avec installed/locked/default/stars ; tri installed puis stars ; 400 sans sphere ; 404 sphere/stack inconnu.
- chassis_ids() = intersection CALCULEE des deploy des 5 stacks (pas de liste en dur) ; locked = chassis ET installe.
- Frontend : 14 sous-etapes, descriptions FR/EN, pre-cochage, verrou disabled, badges, recherche, compteurs, i18n in-place.

## PREUVE D'EXECUTION (suite complete + no-stub + NAVIGATEUR REEL + API live)
```
### SUITE COMPLETE
........................................................................ [ 95%]
..................                                                       [100%]

### no_stub
NO-STUB-SCAN : OK (3 fichiers scannés, zéro violation)

### VERIFICATION NAVIGATEUR REEL (Chrome preview, localhost:8877) — parcours complet
Selection stack agentique -> section briques VISIBLE ; 14 sous-etapes de sphere rendues.
Sphere S6 (memoire/vecteurs) : 118 briques affichees AVEC descriptions ; 10 marquees "Installe avec le stack" ; 4 verrouillees "Chassis" (checkbox disabled — ex. Redis ★75469).
Compteur : "10 installees avec le stack · 10 cochees · 118 disponibles".
Decocher lightrag (installee, non verrouillee) -> "9 cochees" (override fonctionne) ; re-cochee.
Verrou chassis INFRANCHISSABLE (input disabled=true).
Recherche "mem0" -> 2 resultats (Mem0 Pro, Mem0 local).

### API live
GET /api/bricks?sphere=S6&stack=agentique -> 200 : total=118 installed=['redis', 'lightrag', 'qdrant', 'graphiti', 'cognee', 'letta']... locked=['redis', 'qdrant', 'immudb', 'bge-m3']
chassis_ids() = 24 briques (intersection des 5 stacks), litellm in: True
sphere invalide -> 404
```

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/src/forgeai/web/assets/app.css b/src/forgeai/web/assets/app.css
index 11953de..58bac95 100644
--- a/src/forgeai/web/assets/app.css
+++ b/src/forgeai/web/assets/app.css
@@ -256,3 +256,52 @@ code {
     justify-content: space-between;
   }
 }
+
+/* ---------- Briques additionnelles (IMPL-4) ---------- */
+.sphere-steps {
+  display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0;
+}
+.sphere-step {
+  display: inline-flex; align-items: center; gap: 6px;
+  padding: 5px 10px; border-radius: 8px; cursor: pointer;
+  border: 1px solid var(--line, #38434F); background: var(--panel-2, #212934);
+  color: inherit; font-size: 12px;
+}
+.sphere-step .sphere-num {
+  font-weight: 700; color: var(--accent, #EA6A2E);
+}
+.sphere-step .sphere-count { opacity: .6; font-size: 11px; }
+.sphere-step.active {
+  border-color: var(--accent, #EA6A2E);
+  box-shadow: 0 0 0 1px var(--accent, #EA6A2E);
+}
+.bricks-toolbar {
+  display: flex; align-items: center; gap: 12px; margin: 10px 0; flex-wrap: wrap;
+}
+.bricks-toolbar input[type="search"] {
+  flex: 1; min-width: 220px; padding: 8px 12px; border-radius: 8px;
+  border: 1px solid var(--line, #38434F); background: var(--panel, #1A2027); color: inherit;
+}
+.bricks-counts { font-size: 12.5px; opacity: .8; }
+.bricks-list { display: flex; flex-direction: column; gap: 6px; }
+.brick-row {
+  display: flex; align-items: flex-start; gap: 10px;
+  padding: 9px 12px; border-radius: 10px;
+  border: 1px solid var(--line, #38434F); background: var(--panel, #1A2027);
+  cursor: pointer;
+}
+.brick-row input[type="checkbox"] { margin-top: 3px; accent-color: var(--accent, #EA6A2E); }
+.brick-row.installed { border-color: color-mix(in srgb, var(--accent, #EA6A2E) 45%, transparent); }
+.brick-row.locked { opacity: .92; }
+.brick-main { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
+.brick-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
+.brick-name { font-weight: 600; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; }
+.brick-stars { font-size: 11.5px; opacity: .7; }
+.brick-desc { font-size: 12.5px; opacity: .75; line-height: 1.4; }
+.badge-installed, .badge-locked, .badge-default {
+  font-size: 10px; letter-spacing: .04em; text-transform: uppercase;
+  padding: 2px 7px; border-radius: 999px; white-space: nowrap;
+}
+.badge-installed { background: color-mix(in srgb, var(--accent, #EA6A2E) 18%, transparent); color: var(--accent, #EA6A2E); }
+.badge-locked { border: 1px solid var(--line, #38434F); opacity: .85; }
+.badge-default { background: color-mix(in srgb, #2E9E5B 18%, transparent); color: #2E9E5B; }
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index 7e30269..9a885b9 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -8,7 +8,11 @@
     stacks: [],
     spheres: [],
     recommendedId: null,
-    selectedId: null
+    selectedId: null,
+    sphereId: 'S1',
+    bricks: null,
+    overrides: {},
+    search: ''
   };
 
   const i18n = {
@@ -30,7 +34,16 @@
       wiring_title: 'Câblage synergique',
       close: 'Fermer',
       error_load: 'Impossible de charger les données.',
-      select_stack: 'Sélectionnez un profil pour voir le détail.'
+      select_stack: 'Sélectionnez un profil pour voir le détail.',
+      bricks_title: 'Briques additionnelles',
+      bricks_subtitle: 'Catalogue complet, classé par sphère. Les briques du stack sont pré-cochées ; le châssis commun est verrouillé.',
+      search_placeholder: 'Filtrer les briques…',
+      installed_badge: 'Installé avec le stack',
+      locked_badge: 'Châssis — verrouillé',
+      default_badge: 'Défaut de sphère',
+      counts_tpl: '{installed} installées avec le stack · {checked} cochées · {total} disponibles',
+      no_results: 'Aucune brique ne correspond au filtre.',
+      stars_label: 'étoiles'
     },
     en: {
       title: 'ForgeAI Toolkit',
@@ -50,7 +63,16 @@
       wiring_title: 'Synergistic wiring',
       close: 'Close',
       error_load: 'Unable to load data.',
-      select_stack: 'Select a profile to view details.'
+      select_stack: 'Select a profile to view details.',
+      bricks_title: 'Additional bricks',
+      bricks_subtitle: 'Full catalogue, sorted by sphere. Stack bricks are pre-checked; the shared chassis is locked.',
+      search_placeholder: 'Filter bricks…',
+      installed_badge: 'Installed with the stack',
+      locked_badge: 'Chassis — locked',
+      default_badge: 'Sphere default',
+      counts_tpl: '{installed} installed with the stack · {checked} checked · {total} available',
+      no_results: 'No brick matches the filter.',
+      stars_label: 'stars'
     }
   };
 
@@ -96,6 +118,12 @@
         renderDetail(stack, full);
       }
     }
+    const search = document.getElementById('brick-search');
+    if (search) search.placeholder = t('search_placeholder');
+    if (state.bricks) {
+      renderSphereSteps();
+      renderBricks();
+    }
   }
 
   async function fetchJson(path) {
@@ -189,6 +217,7 @@
       const full = await fetchJson(`/api/stacks/${encodeURIComponent(stackId)}`);
       state.stackDetail = full;
       renderDetail(summary, full);
+      showBricksSection();
     } catch (e) {
       const detail = document.getElementById('stack-detail');
       detail.classList.remove('hidden');
@@ -206,6 +235,7 @@
     const detail = document.getElementById('stack-detail');
     detail.classList.add('hidden');
     detail.innerHTML = '';
+    hideBricksSection();
   }
 
   function renderDetail(summary, full) {
@@ -247,6 +277,122 @@
     document.getElementById('stack-detail-close').addEventListener('click', closeDetail);
   }
 
+  /* ---------- Briques additionnelles (IMPL-4) ---------- */
+
+  function overrideKey() {
+    return state.selectedId || '_none_';
+  }
+
+  function isChecked(brick) {
+    if (brick.locked) return true;
+    const ov = state.overrides[overrideKey()];
+    if (ov && Object.prototype.hasOwnProperty.call(ov, brick.id)) return ov[brick.id];
+    return brick.installed;
+  }
+
+  function renderSphereSteps() {
+    const nav = document.getElementById('sphere-steps');
+    nav.innerHTML = state.spheres.map((sp) => `
+      <button class="sphere-step${sp.id === state.sphereId ? ' active' : ''}" data-sphere="${escapeHtml(sp.id)}"
+              aria-pressed="${sp.id === state.sphereId}">
+        <span class="sphere-num">${sp.num}</span>
+        <span class="sphere-label">${escapeHtml(state.lang === 'en' ? sp.name_en : sp.name_fr)}</span>
+        <span class="sphere-count">${sp.count}</span>
+      </button>
+    `).join('');
+    nav.querySelectorAll('.sphere-step').forEach((btn) => {
+      btn.addEventListener('click', () => {
+        state.sphereId = btn.dataset.sphere;
+        loadBricks();
+      });
+    });
+  }
+
+  async function loadBricks() {
+    renderSphereSteps();
+    const list = document.getElementById('bricks-list');
+    list.innerHTML = `<p>${escapeHtml(t('loading'))}</p>`;
+    try {
+      const stackQ = state.selectedId ? `&stack=${encodeURIComponent(state.selectedId)}` : '';
+      state.bricks = await fetchJson(`/api/bricks?sphere=${encodeURIComponent(state.sphereId)}${stackQ}`);
+    } catch (e) {
+      state.bricks = null;
+      list.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
+      return;
+    }
+    renderBricks();
+  }
+
+  function renderCounts(shown) {
+    const el = document.getElementById('bricks-counts');
+    if (!state.bricks) { el.textContent = ''; return; }
+    const bricks = state.bricks.bricks;
+    const installed = bricks.filter((b) => b.installed).length;
+    const checked = bricks.filter((b) => isChecked(b)).length;
+    el.textContent = t('counts_tpl')
+      .replace('{installed}', installed)
+      .replace('{checked}', checked)
+      .replace('{total}', state.bricks.total) + (shown < bricks.length ? ` (${shown}/${bricks.length})` : '');
+  }
+
+  function renderBricks() {
+    const list = document.getElementById('bricks-list');
+    if (!state.bricks) { list.innerHTML = ''; renderCounts(0); return; }
+    const q = state.search.trim().toLowerCase();
+    const visible = state.bricks.bricks.filter((b) => {
+      if (!q) return true;
+      const desc = state.lang === 'en' ? b.description_en : b.description_fr;
+      return (b.id + ' ' + b.name + ' ' + (desc || '')).toLowerCase().includes(q);
+    });
+    renderCounts(visible.length);
+    if (!visible.length) {
+      list.innerHTML = `<p>${escapeHtml(t('no_results'))}</p>`;
+      return;
+    }
+    list.innerHTML = visible.map((b) => {
+      const desc = state.lang === 'en' ? b.description_en : b.description_fr;
+      const checked = isChecked(b);
+      const badges = [
+        b.installed ? `<span class="badge-installed">${escapeHtml(t('installed_badge'))}</span>` : '',
+        b.locked ? `<span class="badge-locked">${escapeHtml(t('locked_badge'))}</span>` : '',
+        b.default ? `<span class="badge-default">${escapeHtml(t('default_badge'))}</span>` : ''
+      ].join('');
+      return `
+        <label class="brick-row${b.installed ? ' installed' : ''}${b.locked ? ' locked' : ''}">
+          <input type="checkbox" data-brick-id="${escapeHtml(b.id)}"
+                 ${checked ? 'checked' : ''} ${b.locked ? 'disabled' : ''}
+                 aria-label="${escapeHtml(b.name)}">
+          <span class="brick-main">
+            <span class="brick-head">
+              <span class="brick-name">${escapeHtml(b.name)}</span>
+              <span class="brick-stars" title="${escapeHtml(t('stars_label'))}">★ ${b.stars}</span>
+              ${badges}
+            </span>
+            <span class="brick-desc">${escapeHtml(desc || '')}</span>
+          </span>
+        </label>
+      `;
+    }).join('');
+    list.querySelectorAll('input[type="checkbox"]:not([disabled])').forEach((cb) => {
+      cb.addEventListener('change', () => {
+        const key = overrideKey();
+        if (!state.overrides[key]) state.overrides[key] = {};
+        state.overrides[key][cb.dataset.brickId] = cb.checked;
+        renderCounts(visible.length);
+      });
+    });
+  }
+
+  function showBricksSection() {
+    document.getElementById('bricks').classList.remove('hidden');
+    loadBricks();
+  }
+
+  function hideBricksSection() {
+    document.getElementById('bricks').classList.add('hidden');
+    state.bricks = null;
+  }
+
   function initControls() {
     document.querySelectorAll('#theme-toggle button[data-theme]').forEach((btn) => {
       btn.addEventListener('click', () => setTheme(btn.dataset.theme));
@@ -254,6 +400,13 @@
     document.querySelectorAll('#lang-toggle button[data-lang]').forEach((btn) => {
       btn.addEventListener('click', () => setLang(btn.dataset.lang));
     });
+    const search = document.getElementById('brick-search');
+    if (search) {
+      search.addEventListener('input', () => {
+        state.search = search.value;
+        renderBricks();
+      });
+    }
     setTheme(state.theme);
     setLang(state.lang);
   }
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index f393091..8770fef 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -33,6 +33,17 @@
       <div id="stacks-grid" class="stacks-grid"></div>
       <div id="stack-detail" class="stack-detail hidden" aria-live="polite"></div>
     </section>
+
+    <section id="bricks" class="hidden">
+      <h2 data-i18n="bricks_title">Briques additionnelles</h2>
+      <p data-i18n="bricks_subtitle">Catalogue complet, classé par sphère. Les briques du stack sont pré-cochées ; le châssis commun est verrouillé.</p>
+      <nav id="sphere-steps" class="sphere-steps" aria-label="Sous-étapes par sphère"></nav>
+      <div class="bricks-toolbar">
+        <input id="brick-search" type="search" placeholder="Filtrer les briques…" aria-label="Filtrer">
+        <span id="bricks-counts" class="bricks-counts" aria-live="polite"></span>
+      </div>
+      <div id="bricks-list" class="bricks-list" aria-live="polite"></div>
+    </section>
   </main>
 
   <script src="app.js"></script>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 202c0d4..c438cce 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -6,12 +6,23 @@ import urllib.parse
 import webbrowser
 from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
 
-from forgeai.catalogue.spheres import SPHERES, spheres_index
+from forgeai.catalogue.spheres import SPHERES, classify_sphere, spheres_index
 from forgeai.core.runner import SubprocessRunner
 from forgeai.hardware.detect import HardwareDetector
 from forgeai.resources import catalogue_path
 from forgeai.stacks import deploy_ids, list_stacks, load_stack
 
+try:
+    from forgeai.catalogue.loader import parse_stars
+except Exception:  # pragma: no cover
+    import re
+
+    def parse_stars(popularity: str | None) -> int:
+        if popularity is None:
+            return 0
+        match = re.search(r"★\s*(\d+)", popularity)
+        return int(match.group(1)) if match else 0
+
 
 _MIME_TYPES = {
     ".html": "text/html; charset=utf-8",
@@ -21,6 +32,8 @@ _MIME_TYPES = {
     ".svg": "image/svg+xml",
 }
 
+_CHASSIS_CACHE: frozenset[str] | None = None
+
 
 def _mime(name: str) -> str:
     lower = name.lower()
@@ -53,6 +66,70 @@ def _json_body(obj: object) -> bytes:
     return json.dumps(obj, ensure_ascii=False).encode("utf-8")
 
 
+def chassis_ids() -> frozenset[str]:
+    """Intersection des briques déployées par tous les stacks hors 'tout-en-un'."""
+    global _CHASSIS_CACHE
+    if _CHASSIS_CACHE is not None:
+        return _CHASSIS_CACHE
+
+    profiles = [sid for sid in list_stacks() if sid != "tout-en-un"]
+    common: set[str] | None = None
+    for sid in profiles:
+        deployed = set(deploy_ids(load_stack(sid)))
+        common = deployed if common is None else common & deployed
+
+    _CHASSIS_CACHE = frozenset(common) if common is not None else frozenset()
+    return _CHASSIS_CACHE
+
+
+def bricks_payload(sphere_id: str, stack_id: str | None) -> dict | None:
+    """Catalogue d'une sphère, enrichi de l'état par rapport à un stack optionnel."""
+    valid_spheres = {s.id for s in SPHERES}
+    if sphere_id not in valid_spheres:
+        return None
+
+    entries = _catalogue_entries()
+    deployed: set[str] = set()
+    sphere_defaults: dict[str, str] = {}
+
+    if stack_id is not None:
+        try:
+            stack = load_stack(stack_id)
+        except FileNotFoundError:
+            return None
+        deployed = set(deploy_ids(stack))
+        sphere_defaults = stack.get("default_by_sphere", {})
+
+    locked = chassis_ids()
+    bricks = []
+    for entry in entries:
+        if classify_sphere(entry) != sphere_id:
+            continue
+        brick_id = entry["id"]
+        installed = brick_id in deployed
+        bricks.append(
+            {
+                "id": brick_id,
+                "name": entry["name"],
+                "description_fr": entry.get("description_fr", ""),
+                "description_en": entry.get("description_en", ""),
+                "stars": parse_stars(entry.get("popularity")),
+                "license": entry.get("license", ""),
+                "installed": installed,
+                "locked": (brick_id in locked) and installed,
+                "default": sphere_defaults.get(sphere_id) == brick_id,
+            }
+        )
+
+    bricks.sort(key=lambda b: (not b["installed"], -b["stars"], b["id"]))
+    return {
+        "sphere": sphere_id,
+        "stack": stack_id,
+        "total": len(bricks),
+        "bricks": bricks,
+    }
+
+
 class ForgeAIHandler(BaseHTTPRequestHandler):
     server_version = "ForgeAI/0.1"
 
@@ -67,7 +144,8 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
         self._send(code, _json_body(obj), "application/json; charset=utf-8")
 
     def do_GET(self) -> None:  # noqa: N802
-        path = urllib.parse.urlparse(self.path).path
+        parsed = urllib.parse.urlparse(self.path)
+        path = parsed.path
 
         if path in ("/", "/index.html"):
             data = _asset_bytes("index.html")
@@ -144,6 +222,21 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             self._send_json(200, spheres)
             return
 
+        if path == "/api/bricks":
+            query = urllib.parse.parse_qs(parsed.query)
+            sphere_list = query.get("sphere")
+            if not sphere_list:
+                self._send_json(400, {"error": "sphere requis"})
+                return
+            sphere_id = sphere_list[0]
+            stack_id = query.get("stack", [None])[0]
+            payload = bricks_payload(sphere_id, stack_id)
+            if payload is None:
+                self._send_json(404, {"error": "not found"})
+                return
+            self._send_json(200, payload)
+            return
+
         basename = path.rsplit("/", 1)[-1]
         data = _asset_bytes(basename)
         if data is not None:
diff --git a/tests/test_web_bricks.py b/tests/test_web_bricks.py
new file mode 100644
index 0000000..8e775fc
--- /dev/null
+++ b/tests/test_web_bricks.py
@@ -0,0 +1,135 @@
+from __future__ import annotations
+
+import json
+import threading
+import urllib.error
+import urllib.request
+
+import pytest
+
+from forgeai.stacks import deploy_ids, list_stacks, load_stack
+from forgeai.web.server import build_server, chassis_ids
+
+
+@pytest.fixture(scope="module")
+def base_url():
+    server = build_server("127.0.0.1", 0)
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+    host, port = server.server_address
+    yield f"http://{host}:{port}"
+    server.shutdown()
+    server.server_close()
+
+
+def _get(base_url: str, path: str):
+    with urllib.request.urlopen(base_url + path, timeout=30) as resp:
+        return resp.status, json.loads(resp.read().decode("utf-8"))
+
+
+def _get_status(base_url: str, path: str):
+    try:
+        with urllib.request.urlopen(base_url + path, timeout=30) as resp:
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
+def test_bricks_sphere_seule(base_url):
+    status, data = _get(base_url, "/api/bricks?sphere=S6")
+    assert status == 200
+    assert data["sphere"] == "S6"
+    assert data["stack"] is None
+    assert data["total"] > 30
+
+    required_keys = {
+        "id",
+        "name",
+        "description_fr",
+        "description_en",
+        "stars",
+        "installed",
+        "locked",
+    }
+    for brick in data["bricks"]:
+        assert required_keys.issubset(brick.keys())
+        assert brick["installed"] is False
+        assert brick["locked"] is False
+
+    order_keys = [(-brick["stars"], brick["id"]) for brick in data["bricks"]]
+    assert order_keys == sorted(order_keys)
+
+
+def test_bricks_avec_stack(base_url):
+    status, data = _get(base_url, "/api/bricks?sphere=S6&stack=agentique")
+    assert status == 200
+    bricks = data["bricks"]
+    assert any(brick["installed"] for brick in bricks)
+
+    qdrant = next((b for b in bricks if b["id"] == "qdrant"), None)
+    assert qdrant is not None
+    assert qdrant["installed"] is True
+
+    first_not_installed = next(
+        (i for i, b in enumerate(bricks) if not b["installed"]), None
+    )
+    if first_not_installed is not None:
+        assert all(b["installed"] for b in bricks[:first_not_installed])
+    else:
+        assert all(b["installed"] for b in bricks)
+
+
+def test_bricks_chassis_verrouille(base_url):
+    status, data = _get(base_url, "/api/bricks?sphere=S4&stack=agentique")
+    assert status == 200
+    litellm = next(b for b in data["bricks"] if b["id"] == "litellm")
+    assert litellm["installed"] is True
+    assert litellm["locked"] is True
+
+
+def test_bricks_hors_deploy_decochables(base_url):
+    status, data = _get(base_url, "/api/bricks?sphere=S6&stack=agentique")
+    assert status == 200
+    for brick in data["bricks"]:
+        if not brick["installed"]:
+            assert brick["locked"] is False
+
+
+def test_bricks_sphere_invalide(base_url):
+    status, data = _get_status(base_url, "/api/bricks?sphere=S99")
+    assert status == 404
+
+    status, data = _get_status(base_url, "/api/bricks")
+    assert status == 400
+
+    status, data = _get_status(base_url, "/api/bricks?sphere=S6&stack=xyz")
+    assert status == 404
+
+
+def test_chassis_intersection():
+    chassis = chassis_ids()
+    assert "litellm" in chassis
+    assert len(chassis) >= 20
+
+    profiles = [sid for sid in list_stacks() if sid != "tout-en-un"]
+    assert len(profiles) >= 5
+    for brick_id in chassis:
+        for sid in profiles:
+            assert brick_id in deploy_ids(load_stack(sid))
+
+
+def test_non_regression(base_url):
+    status, data = _get(base_url, "/api/stacks")
+    assert status == 200
+    assert len(data) == 6
+
+    status, _ = _get(base_url, "/api/detect")
+    assert status == 200
+
+    status, _ = _get_status(base_url, "/nope")
+    assert status == 404
```
