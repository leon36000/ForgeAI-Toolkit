# Story S6 — API surface du « choix filtré » par vendor (GET /api/engines/compatible)

## Objet
Expose à l'UI (web + CLI potentiel) la liste de moteurs FILTRÉE par le vendor GPU du nœud, en
s'appuyant sur le primitif S4 (forgeai.engines.compatible_engines / moteurs-inference.json gpu_vendors).
Complète la valeur utilisateur de S4 : le choix n'est plus seulement validé, il est proposé filtré.

## Changement (web/server.py)
- Nouvel endpoint `GET /api/engines/compatible?vendor=<amd|nvidia|intel|cpu>` -> {vendor, moteurs:[ids]}.
  Stdlib (parse_qs). Aucune nouvelle dépendance.

## Critères (testés en LIVE — tests/test_placement_noeud.py)
1. ?vendor=amd => contient llama-cpp, vllm ; EXCLUT tensorrt-llm (nvidia-only).
2. ?vendor=nvidia => tensorrt-llm réapparaît.

## Périmètre
S6 = l'API du choix filtré (testable). Le câblage du DROPDOWN JS (engineOptions filtré par le vendor
du nœud sélectionné) demande le plumbing node->vendor côté UI (non testable pytest) = suivi S6b.
Codeur : orchestrateur.
## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index ed55363..2e04b0f 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -349,6 +349,14 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             self._send_json(200, data)
             return
 
+        if path == "/api/engines/compatible":
+            # S6 : liste de choix FILTRÉE par vendor du nœud (?vendor=amd|nvidia|intel|cpu).
+            # S'appuie sur forgeai.engines.compatible_engines (moteurs-inference.json gpu_vendors).
+            from forgeai.engines import compatible_engines
+            vendor = (urllib.parse.parse_qs(parsed.query).get("vendor") or [""])[0]
+            self._send_json(200, {"vendor": vendor, "moteurs": compatible_engines(vendor)})
+            return
+
         if path == "/api/models":
             store = RouteStore(_models_home())
             self._send_json(200, [r.public_dict() for r in store.list()])
diff --git a/tests/test_placement_noeud.py b/tests/test_placement_noeud.py
index a665d6b..814f15b 100644
--- a/tests/test_placement_noeud.py
+++ b/tests/test_placement_noeud.py
@@ -77,6 +77,30 @@ def test_api_engines() -> None:
         server.server_close()
 
 
+def test_api_engines_compatible_filtre_par_vendor() -> None:
+    # S6 : le choix FILTRÉ exposé à l'UI — /api/engines/compatible?vendor=amd
+    server = build_server("127.0.0.1", 0)
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+    try:
+        host, port = server.server_address
+        conn = HTTPConnection(host, port)
+        conn.request("GET", "/api/engines/compatible?vendor=amd")
+        response = conn.getresponse()
+        assert response.status == 200
+        data = json.loads(response.read().decode("utf-8"))
+        assert data["vendor"] == "amd"
+        assert "llama-cpp" in data["moteurs"] and "vllm" in data["moteurs"]
+        assert "tensorrt-llm" not in data["moteurs"]  # nvidia-only exclu du choix AMD
+        # vendor nvidia : tensorrt-llm réapparaît
+        conn.request("GET", "/api/engines/compatible?vendor=nvidia")
+        nv = json.loads(conn.getresponse().read().decode("utf-8"))
+        assert "tensorrt-llm" in nv["moteurs"]
+    finally:
+        server.shutdown()
+        server.server_close()
+
+
 def test_choix_jamais_impose() -> None:
     moteurs = _read_data_json("moteurs-inference.json")
     vendors: set[str] = set()
```
## Preuve déterministe
```
......                                                                   [100%]
........................................................................ [ 89%]
.....s................................................................   [100%]
[*] 4 fixable with the `--fix` option.
```
