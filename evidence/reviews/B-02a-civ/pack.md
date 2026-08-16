# Story B-02a — Socle interface web stdlib (serveur + /api/detect + accueil)

## Criteres d'acceptation (CANON/spec-web-ui.md §5 B-02a)
- forgeai web [--host 127.0.0.1] [--port N] [--no-browser] ; GET /api/detect -> 200 JSON materiel reel (HardwareDetector) ; GET / -> 200 coquille d'app ; assets 200 ; route inconnue -> 404.
- AUTO-SUFFISANCE : stdlib pure (aucune dependance), zero reference reseau externe dans les assets (teste), polices systeme, bind 127.0.0.1 par defaut.
- Garde path-traversal sur les assets (teste). Theme sombre/clair + bascule FR/EN in-place (assets).
- Packaging : forgeai.web/assets + forgeai.data/stacks embarques (pip install portable) ; extra [tui] retire (caduc, pivot web acte au canon).

## PREUVE D'EXECUTION (sortie reelle : suite complete + no-stub + CLI + serveur live)
```
### SUITE COMPLETE
........................................................................ [ 98%]
....                                                                     [100%]

### no_stub (nouveaux fichiers)
NO-STUB-SCAN : OK (3 fichiers scannés, zéro violation)

### CLI: forgeai web --help (cablage)
usage: forgeai web [-h] [--host HOST] [--port PORT] [--no-browser]

options:
  -h, --help    show this help message and exit
  --host HOST   bind (défaut 127.0.0.1 — jamais exposé sans action explicite)
  --port PORT
  --no-browser  ne pas ouvrir le navigateur automatiquement

### SERVEUR REEL (build_server port ephemere) : / , /api/detect , /api/health , /app.css , 404
GET / -> 200 text/html; charset=utf-8 (778 octets)
GET /api/detect -> 200 application/json; charset=utf-8 (478 octets)
   cpu: AMD Ryzen 9 9950X3D 16-Core Processor | cores: 32 | ram_gb: 46.1 | gpus: 2
GET /api/health -> 200 application/json; charset=utf-8 (16 octets)
GET /app.css -> 200 text/css; charset=utf-8 (2550 octets)
GET /app.js -> 200 text/javascript; charset=utf-8 (3659 octets)
GET /nope -> 404
serveur arrete proprement
```

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/pyproject.toml b/pyproject.toml
index 9e18a2e..6f5bd60 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -14,7 +14,7 @@ requires-python = ">=3.10"
 dependencies = []
 
 [project.optional-dependencies]
-tui = ["textual>=0.60"]          # wizard interactif (le mode --ci n'en a pas besoin)
+# (extra [tui] retiré — pivot acté : l'interface v1 est la web-app stdlib `forgeai web`, cf. CANON/spec-web-ui.md)
 dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.5", "mypy>=1.10"]
 
 [project.scripts]
@@ -27,7 +27,8 @@ package-dir = {"" = "src"}
 where = ["src"]
 
 [tool.setuptools.package-data]
-"forgeai.data" = ["*.json", "*.sha256", "locales/*.json", "templates/*.json"]
+"forgeai.data" = ["*.json", "*.sha256", "locales/*.json", "templates/*.json", "stacks/*.json"]
+"forgeai.web" = ["assets/*"]
 
 [tool.pytest.ini_options]
 testpaths = ["tests"]
diff --git a/src/forgeai/cli.py b/src/forgeai/cli.py
index 313933c..0477e2d 100644
--- a/src/forgeai/cli.py
+++ b/src/forgeai/cli.py
@@ -982,6 +982,15 @@ def main(argv: list[str] | None = None) -> int:
     p_tmpl_res.add_argument("--registre", default=str(DEFAULT_REGISTRE))
     p_tmpl_res.set_defaults(func=_template_resolve)
 
+    p_web = sub.add_parser("web", help="interface web locale (stdlib, hors-ligne) — B-02a")
+    p_web.add_argument("--host", default="127.0.0.1",
+                       help="bind (défaut 127.0.0.1 — jamais exposé sans action explicite)")
+    p_web.add_argument("--port", type=int, default=8765)
+    p_web.add_argument("--no-browser", action="store_true", dest="no_browser",
+                       help="ne pas ouvrir le navigateur automatiquement")
+    from forgeai.web import web_command
+    p_web.set_defaults(func=web_command)
+
     args = parser.parse_args(argv)
     set_locale(args.lang)   # bascule la langue de l'interface avant dispatch
     try:
diff --git a/src/forgeai/web/__init__.py b/src/forgeai/web/__init__.py
new file mode 100644
index 0000000..8de6bdc
--- /dev/null
+++ b/src/forgeai/web/__init__.py
@@ -0,0 +1,7 @@
+"""Interface web locale de ForgeAI Toolkit.
+
+Ré-exporte les points d'entrée du serveur embarqué.
+"""
+from forgeai.web.server import build_server, serve, web_command
+
+__all__ = ["build_server", "serve", "web_command"]
diff --git a/src/forgeai/web/assets/app.css b/src/forgeai/web/assets/app.css
new file mode 100644
index 0000000..81943e8
--- /dev/null
+++ b/src/forgeai/web/assets/app.css
@@ -0,0 +1,147 @@
+:root {
+  --bg: #f4f5f7;
+  --surface: #ffffff;
+  --text: #1f2328;
+  --muted: #5c646f;
+  --accent: #c45c26;
+  --accent-hover: #a64a1c;
+  --border: #d1d5da;
+  --shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
+  --radius: 0.5rem;
+  --font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
+}
+
+@media (prefers-color-scheme: dark) {
+  :root:not([data-theme="light"]) {
+    --bg: #0d1117;
+    --surface: #161b22;
+    --text: #c9d1d9;
+    --muted: #8b949e;
+    --accent: #e06c33;
+    --accent-hover: #f0883e;
+    --border: #30363d;
+    --shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
+  }
+}
+
+:root[data-theme="dark"] {
+  --bg: #0d1117;
+  --surface: #161b22;
+  --text: #c9d1d9;
+  --muted: #8b949e;
+  --accent: #e06c33;
+  --accent-hover: #f0883e;
+  --border: #30363d;
+  --shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
+}
+
+* {
+  box-sizing: border-box;
+}
+
+body {
+  margin: 0;
+  font-family: var(--font);
+  background: var(--bg);
+  color: var(--text);
+  line-height: 1.5;
+}
+
+.topbar {
+  display: flex;
+  align-items: center;
+  justify-content: space-between;
+  padding: 1rem 1.5rem;
+  background: var(--surface);
+  border-bottom: 1px solid var(--border);
+  box-shadow: var(--shadow);
+}
+
+.topbar h1 {
+  margin: 0;
+  font-size: 1.25rem;
+  letter-spacing: -0.02em;
+}
+
+.actions {
+  display: flex;
+  gap: 0.5rem;
+}
+
+button {
+  cursor: pointer;
+  border: 1px solid var(--border);
+  background: var(--surface);
+  color: var(--text);
+  padding: 0.4rem 0.8rem;
+  border-radius: var(--radius);
+  font: inherit;
+  transition: background 0.15s, border-color 0.15s;
+}
+
+button:hover {
+  border-color: var(--accent);
+  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
+}
+
+#app {
+  max-width: 720px;
+  margin: 2rem auto;
+  padding: 0 1rem;
+}
+
+.card {
+  background: var(--surface);
+  border: 1px solid var(--border);
+  border-radius: var(--radius);
+  padding: 1.5rem;
+  box-shadow: var(--shadow);
+}
+
+.card h2 {
+  margin-top: 0;
+  font-size: 1.1rem;
+  color: var(--accent);
+}
+
+.grid {
+  display: grid;
+  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
+  gap: 1rem;
+  margin-top: 1rem;
+}
+
+.item {
+  display: flex;
+  flex-direction: column;
+  gap: 0.25rem;
+}
+
+.item .label {
+  font-size: 0.8rem;
+  color: var(--muted);
+  text-transform: uppercase;
+  letter-spacing: 0.04em;
+}
+
+.item .value {
+  font-weight: 600;
+  word-break: break-word;
+}
+
+.loading {
+  color: var(--muted);
+  margin: 0;
+}
+
+.error {
+  color: #cf222e;
+}
+
+@media (max-width: 480px) {
+  .topbar {
+    flex-direction: column;
+    gap: 0.75rem;
+    align-items: flex-start;
+  }
+}
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
new file mode 100644
index 0000000..9c95bc8
--- /dev/null
+++ b/src/forgeai/web/assets/app.js
@@ -0,0 +1,120 @@
+(function () {
+  "use strict";
+
+  const i18n = {
+    fr: {
+      loading: "Chargement de la détection matérielle…",
+      title: "Matériel détecté",
+      cpu: "Processeur",
+      cores: "Cœurs",
+      arch: "Architecture",
+      ram: "Mémoire vive",
+      os: "Système",
+      gpus: "GPU(s)",
+      none: "aucun",
+      error: "Impossible de détecter le matériel.",
+      langLabel: "FR",
+    },
+    en: {
+      loading: "Loading hardware detection…",
+      title: "Detected hardware",
+      cpu: "CPU",
+      cores: "Cores",
+      arch: "Architecture",
+      ram: "RAM",
+      os: "Operating system",
+      gpus: "GPU(s)",
+      none: "none",
+      error: "Unable to detect hardware.",
+      langLabel: "EN",
+    },
+  };
+
+  let currentLang = "fr";
+
+  function t(key) {
+    return i18n[currentLang][key] ?? key;
+  }
+
+  function setTexts() {
+    document.querySelectorAll("[data-i18n]").forEach((el) => {
+      const key = el.dataset.i18n;
+      if (key && i18n[currentLang][key]) {
+        el.textContent = i18n[currentLang][key];
+      }
+    });
+    const toggle = document.getElementById("lang-toggle");
+    if (toggle) toggle.textContent = t("langLabel");
+  }
+
+  function formatBytes(gb) {
+    return `${gb.toFixed(1)} Go`;
+  }
+
+  function render(hw) {
+    const container = document.getElementById("hardware");
+    const gpuCount = Array.isArray(hw.gpus) ? hw.gpus.length : 0;
+    const gpuText = gpuCount > 0 ? `${gpuCount}` : t("none");
+
+    container.innerHTML = `
+      <h2>${t("title")}</h2>
+      <div class="grid">
+        <div class="item"><span class="label">${t("cpu")}</span><span class="value">${escapeHtml(hw.cpu_model)}</span></div>
+        <div class="item"><span class="label">${t("cores")}</span><span class="value">${hw.cpu_cores}</span></div>
+        <div class="item"><span class="label">${t("arch")}</span><span class="value">${escapeHtml(hw.cpu_arch)}</span></div>
+        <div class="item"><span class="label">${t("ram")}</span><span class="value">${formatBytes(hw.ram_gb)}</span></div>
+        <div class="item"><span class="label">${t("os")}</span><span class="value">${escapeHtml(hw.os_name)}</span></div>
+        <div class="item"><span class="label">${t("gpus")}</span><span class="value">${gpuText}</span></div>
+      </div>
+    `;
+  }
+
+  function escapeHtml(text) {
+    return String(text)
+      .replace(/&/g, "&amp;")
+      .replace(/</g, "&lt;")
+      .replace(/>/g, "&gt;")
+      .replace(/"/g, "&quot;");
+  }
+
+  async function loadHardware() {
+    const container = document.getElementById("hardware");
+    try {
+      const response = await fetch("/api/detect");
+      if (!response.ok) throw new Error(response.statusText);
+      const data = await response.json();
+      render(data);
+    } catch (err) {
+      container.innerHTML = `<p class="error">${t("error")} (${escapeHtml(err.message)})</p>`;
+    }
+  }
+
+  function initTheme() {
+    const toggle = document.getElementById("theme-toggle");
+    const root = document.documentElement;
+    const updateIcon = () => {
+      toggle.textContent = root.dataset.theme === "dark" ? "☀️" : "🌙";
+    };
+    toggle.addEventListener("click", () => {
+      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
+      updateIcon();
+    });
+    updateIcon();
+  }
+
+  function initLang() {
+    const toggle = document.getElementById("lang-toggle");
+    toggle.addEventListener("click", () => {
+      currentLang = currentLang === "fr" ? "en" : "fr";
+      setTexts();
+      loadHardware();
+    });
+    setTexts();
+  }
+
+  document.addEventListener("DOMContentLoaded", () => {
+    initTheme();
+    initLang();
+    loadHardware();
+  });
+})();
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
new file mode 100644
index 0000000..55310bb
--- /dev/null
+++ b/src/forgeai/web/assets/index.html
@@ -0,0 +1,24 @@
+<!DOCTYPE html>
+<html lang="fr" data-theme="dark">
+<head>
+  <meta charset="UTF-8">
+  <meta name="viewport" content="width=device-width, initial-scale=1.0">
+  <title>ForgeAI Toolkit</title>
+  <link rel="stylesheet" href="app.css">
+  <script src="app.js" defer></script>
+</head>
+<body>
+  <header class="topbar">
+    <h1>ForgeAI Toolkit</h1>
+    <div class="actions">
+      <button id="lang-toggle" type="button" aria-label="Changer de langue">FR</button>
+      <button id="theme-toggle" type="button" aria-label="Changer de thème">🌙</button>
+    </div>
+  </header>
+  <main id="app">
+    <section id="hardware" class="card" aria-live="polite">
+      <p class="loading" data-i18n="loading">Chargement de la détection matérielle…</p>
+    </section>
+  </main>
+</body>
+</html>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
new file mode 100644
index 0000000..73b23d7
--- /dev/null
+++ b/src/forgeai/web/server.py
@@ -0,0 +1,126 @@
+from __future__ import annotations
+
+import importlib.resources
+import json
+import urllib.parse
+import webbrowser
+from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
+
+from forgeai.core.runner import SubprocessRunner
+from forgeai.hardware.detect import HardwareDetector
+
+
+_MIME_TYPES = {
+    ".html": "text/html; charset=utf-8",
+    ".css": "text/css; charset=utf-8",
+    ".js": "text/javascript; charset=utf-8",
+    ".json": "application/json; charset=utf-8",
+    ".svg": "image/svg+xml",
+}
+
+
+def _mime(name: str) -> str:
+    lower = name.lower()
+    for ext, ctype in _MIME_TYPES.items():
+        if lower.endswith(ext):
+            return ctype
+    return "application/octet-stream"
+
+
+def _asset_bytes(name: str) -> bytes | None:
+    """Retourne le contenu d'un asset embarqué, ou None si interdit/absent."""
+    if "/" in name or "\\" in name or ".." in name:
+        return None
+    try:
+        resource = importlib.resources.files("forgeai.web") / "assets" / name
+        return resource.read_bytes()
+    except (FileNotFoundError, ModuleNotFoundError):
+        return None
+
+
+def hardware_json() -> str:
+    return HardwareDetector(SubprocessRunner()).full_report().to_json()
+
+
+class ForgeAIHandler(BaseHTTPRequestHandler):
+    server_version = "ForgeAI/0.1"
+
+    def _send(self, code: int, body: bytes, content_type: str) -> None:
+        self.send_response(code)
+        self.send_header("Content-Type", content_type)
+        self.send_header("Content-Length", str(len(body)))
+        self.end_headers()
+        self.wfile.write(body)
+
+    def do_GET(self) -> None:  # noqa: N802
+        path = urllib.parse.urlparse(self.path).path
+
+        if path in ("/", "/index.html"):
+            data = _asset_bytes("index.html")
+            if data is None:
+                self._send(500, b"index.html missing", "text/plain; charset=utf-8")
+            else:
+                self._send(200, data, "text/html; charset=utf-8")
+            return
+
+        if path == "/api/detect":
+            try:
+                body = hardware_json().encode("utf-8")
+                self._send(200, body, "application/json; charset=utf-8")
+            except Exception as exc:  # noqa: BLE001
+                payload = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
+                self._send(500, payload, "application/json; charset=utf-8")
+            return
+
+        if path == "/api/health":
+            self._send(
+                200,
+                json.dumps({"status": "ok"}, ensure_ascii=False).encode("utf-8"),
+                "application/json; charset=utf-8",
+            )
+            return
+
+        basename = path.rsplit("/", 1)[-1]
+        data = _asset_bytes(basename)
+        if data is not None:
+            self._send(200, data, _mime(basename))
+            return
+
+        payload = json.dumps({"error": "not found", "path": path}, ensure_ascii=False).encode("utf-8")
+        self._send(404, payload, "application/json; charset=utf-8")
+
+    def log_message(self, *args) -> None:  # noqa: ARG002
+        return
+
+
+def build_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
+    return ThreadingHTTPServer((host, port), ForgeAIHandler)
+
+
+def serve(
+    host: str = "127.0.0.1",
+    port: int = 8765,
+    open_browser: bool = True,
+) -> None:
+    server = build_server(host, port)
+    url = f"http://{host}:{server.server_address[1]}"
+    print(url)
+    if open_browser:
+        try:
+            webbrowser.open(url)
+        except Exception:
+            pass
+    try:
+        server.serve_forever()
+    except KeyboardInterrupt:
+        server.shutdown()
+        server.server_close()
+
+
+def web_command(args) -> int:
+    serve(
+        getattr(args, "host", "127.0.0.1"),
+        getattr(args, "port", 8765),
+        open_browser=not getattr(args, "no_browser", False),
+    )
+    return 0
diff --git a/tests/test_web_server.py b/tests/test_web_server.py
new file mode 100644
index 0000000..3a8d1cc
--- /dev/null
+++ b/tests/test_web_server.py
@@ -0,0 +1,82 @@
+from __future__ import annotations
+
+import importlib.resources
+import json
+import threading
+import urllib.request
+
+import pytest
+
+from forgeai.web.server import _asset_bytes, build_server
+
+
+@pytest.fixture
+def server():
+    srv = build_server("127.0.0.1", 0)
+    port = srv.server_address[1]
+    thread = threading.Thread(target=srv.serve_forever, daemon=True)
+    thread.start()
+    yield f"http://127.0.0.1:{port}"
+    srv.shutdown()
+    srv.server_close()
+
+
+def _get(url: str) -> tuple[int, dict[str, str], bytes]:
+    with urllib.request.urlopen(url, timeout=10) as resp:
+        return resp.status, dict(resp.headers), resp.read()
+
+
+def test_detect_endpoint(server):
+    status, headers, body = _get(f"{server}/api/detect")
+    assert status == 200
+    assert "application/json" in headers.get("Content-Type", "")
+    data = json.loads(body.decode("utf-8"))
+    for key in ("cpu_model", "cpu_cores", "cpu_arch", "ram_gb", "os_name", "gpus", "disks"):
+        assert key in data
+
+
+def test_accueil(server):
+    status, headers, body = _get(server)
+    assert status == 200
+    assert "text/html" in headers.get("Content-Type", "")
+    text = body.decode("utf-8")
+    assert "ForgeAI Toolkit" in text
+    assert 'id="app"' in text
+
+
+def test_assets(server):
+    status, headers, body = _get(f"{server}/app.css")
+    assert status == 200
+    assert "text/css" in headers.get("Content-Type", "")
+
+    status, headers, body = _get(f"{server}/app.js")
+    assert status == 200
+    assert "text/javascript" in headers.get("Content-Type", "")
+
+
+def test_health(server):
+    status, headers, body = _get(f"{server}/api/health")
+    assert status == 200
+    assert "application/json" in headers.get("Content-Type", "")
+    assert json.loads(body.decode("utf-8")) == {"status": "ok"}
+
+
+def test_404(server):
+    with pytest.raises(urllib.error.HTTPError) as exc_info:
+        _get(f"{server}/nope")
+    assert exc_info.value.code == 404
+
+
+def test_pas_de_traversal():
+    assert _asset_bytes("../server.py") is None
+    assert _asset_bytes("foo/bar.css") is None
+    assert _asset_bytes("foo\\bar.css") is None
+
+
+def test_auto_suffisance():
+    for name in ("index.html", "app.css", "app.js"):
+        text = (importlib.resources.files("forgeai.web") / "assets" / name).read_text(
+            encoding="utf-8"
+        )
+        assert "http://" not in text, f"{name} contient une référence http://"
+        assert "https://" not in text, f"{name} contient une référence https://"
```
