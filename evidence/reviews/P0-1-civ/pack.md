# Story P0.1 — Le wizard consomme le stack : commande reparee + plan derive + dry-run + tests e2e sans mock

## Contexte : audit 2026-07-19 (48 constats, 10 critiques). Cette story repare les 4 critiques du deploiement :
wizard exit 2 systematique (args requis manquants dans la commande serveur) ; stack valide puis jete ; plan toujours minimal ; tests masquant tout via monkeypatch _DEPLOY_CMD.

## Criteres
- La commande PAR DEFAUT construite par POST /api/deploy s execute reellement (defauts embarques) et transmet --stack.
- assemble_plan(stack=...) ajoute les services des briques du stack presentes dans data/deploy-specs.json (v1 litellm+redis — IMAGES OFFICIELLES uniquement : ghcr.io/berriai/litellm:main-stable, redis:7-alpine — a verifier), ports sans collision, overlay conserve.
- --dry-run : assemble + rend compose/k3s + exit 0 sans deployer (permet l e2e sans docker en CI).
- tests/test_deploy_reel.py : AUCUN mock de commande — exigence explicite post-audit.

## PREUVE D'EXECUTION
```
### SUITE COMPLETE (193 tests)
........................................................................ [ 88%]
.................................................                        [100%]

### no_stub
NO-STUB-SCAN : OK (5 fichiers scannés, zéro violation)

### PREUVE CHAINE REELLE (exécution directe, ZERO mock)
POST /api/deploy {stack: agentique, dry_run} -> 202 -> sous-processus REEL python -m forgeai wizard --ci --stack agentique --dry-run :
  "stack: Agentique (agents autonomes outilles) | services: {ollama: 21434, vector-store: 16333, litellm: 8100, redis: 8101} | modele: qwen2.5:0.5b"
  "DRY-RUN OK: 4 services, stack=Agentique" ; done=True exit=0.
AVANT (audit critique): la meme commande sortait en exit 2 (args requis manquants) et le stack etait jete — le plan etait toujours minimal.
Les 5 tests de test_deploy_reel.py n utilisent NI _DEPLOY_CMD NI aucun monkeypatch de commande — la classe de bug masquee par les mocks ne peut plus passer.
```

## Note orchestrateur : correctif du parser SSE du test crew (event: end PRECEDE data:) — le serveur etait correct.

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/pyproject.toml b/pyproject.toml
index 6f5bd60..6faf34d 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -27,7 +27,7 @@ package-dir = {"" = "src"}
 where = ["src"]
 
 [tool.setuptools.package-data]
-"forgeai.data" = ["*.json", "*.sha256", "locales/*.json", "templates/*.json", "stacks/*.json"]
+"forgeai.data" = ["*.json", "*.sha256", "locales/*.json", "templates/*.json", "stacks/*.json", "smoke/*.md"]
 "forgeai.web" = ["assets/*"]
 
 [tool.pytest.ini_options]
diff --git a/src/forgeai/cli.py b/src/forgeai/cli.py
index 0477e2d..b0f1256 100644
--- a/src/forgeai/cli.py
+++ b/src/forgeai/cli.py
@@ -8,6 +8,7 @@ erreur avec code de sortie non nul — jamais de faux succès.
 from __future__ import annotations
 
 import argparse
+import importlib.resources
 import os
 import socket
 import sys
@@ -41,6 +42,7 @@ from forgeai.renderers.k3s import NAMESPACE, node_port_for, render_k3s
 from forgeai.resources import catalogue_path, deploy_overlay_path
 from forgeai.i18n import t, set_locale, available_locales
 from forgeai.ide import SUPPORTED_IDES
+from forgeai.stacks import load_stack
 
 # Données embarquées dans le paquet → portables après pip install (P3).
 DEFAULT_CATALOGUE = catalogue_path()
@@ -98,15 +100,30 @@ def wizard_ci(args: argparse.Namespace) -> int:
     bricks = load_catalogue(Path(args.catalogue))
     print(f"  {len(bricks)} briques, sha256 {digest[:16]}…")
 
+    stack = None
+    stack_label = "minimal"
+    if args.stack:
+        stack = load_stack(args.stack)
+        stack_label = stack.get("name", args.stack)
+
     _step(t("wizard.s04"))
-    plan = assemble_plan(profile, Path(args.overlay))
+    plan = assemble_plan(profile, Path(args.overlay), stack=stack)
     (workdir / "plan.json").write_text(plan.to_json(), encoding="utf-8")
     ports = {s.name: s.host_port for s in plan.services}
-    print(f"  services: {ports} | modèle: {plan.model}")
+    print(f"  stack: {stack_label} | services: {ports} | modèle: {plan.model}")
 
     _step(t("wizard.s05"))
     bootstrap_secrets(workdir)
 
+    compose_file = workdir / "docker-compose.yaml"
+    compose_file.write_text(render_compose(plan), encoding="utf-8")
+    local_node = socket.gethostname().lower()
+    (workdir / "k3s.yaml").write_text(render_k3s(plan, node=local_node), encoding="utf-8")
+
+    if args.dry_run:
+        print(f"DRY-RUN OK: {len(plan.services)} services, stack={stack_label}", flush=True)
+        return 0
+
     backend = args.backend
     if not args.skip_preflight:
         from forgeai.deploy.compose import http_ok
@@ -120,11 +137,6 @@ def wizard_ci(args: argparse.Namespace) -> int:
                   file=sys.stderr)
             return 6
 
-    compose_file = workdir / "docker-compose.yaml"
-    compose_file.write_text(render_compose(plan), encoding="utf-8")
-    local_node = socket.gethostname().lower()
-    (workdir / "k3s.yaml").write_text(render_k3s(plan, node=local_node), encoding="utf-8")
-
     if backend == "compose":
         _step(t("wizard.s06"))
         compose_up(compose_file)
@@ -160,8 +172,16 @@ def wizard_ci(args: argparse.Namespace) -> int:
             embed_model=plan.embed_model,
         )
         rag.pull_models()
-        doc = Path(args.document).read_text(encoding="utf-8")
-        chunks = rag.ingest(doc, source=Path(args.document).name)
+
+        if args.document:
+            doc_path = Path(args.document)
+            source_name = doc_path.name
+        else:
+            doc_path = importlib.resources.files("forgeai.data") / "smoke" / "verification.md"
+            source_name = "verification.md"
+        doc = doc_path.read_text(encoding="utf-8")
+
+        chunks = rag.ingest(doc, source=source_name)
         print(f"  {chunks} chunks ingérés")
 
         _step(t("wizard.s09"))
@@ -795,10 +815,15 @@ def main(argv: list[str] | None = None) -> int:
     p_wiz.add_argument("--workdir", default="run")
     p_wiz.add_argument("--catalogue", default=str(DEFAULT_CATALOGUE))
     p_wiz.add_argument("--overlay", default=str(DEFAULT_OVERLAY))
+    p_wiz.add_argument("--stack", default=None,
+                       help="stack à déployer (défaut : plan minimal)")
+    p_wiz.add_argument("--dry-run", action="store_true",
+                       help="génère les manifestes et s'arrête sans déployer")
     p_wiz.add_argument("--registre", default=str(DEFAULT_REGISTRE))
-    p_wiz.add_argument("--document", required=True)
-    p_wiz.add_argument("--question", required=True)
-    p_wiz.add_argument("--expected-fact", required=True)
+    p_wiz.add_argument("--document", default=None,
+                       help="document de test (défaut : smoke embarqué)")
+    p_wiz.add_argument("--question", default="Quelle est la capitale de la France ?")
+    p_wiz.add_argument("--expected-fact", default="Paris")
     p_wiz.add_argument("--health-timeout", type=float, default=180.0)
     p_wiz.add_argument("--teardown", action="store_true")
     p_wiz.add_argument("--teardown-volumes", action="store_true")
diff --git a/src/forgeai/data/deploy-specs.json b/src/forgeai/data/deploy-specs.json
new file mode 100644
index 0000000..65d2a9e
--- /dev/null
+++ b/src/forgeai/data/deploy-specs.json
@@ -0,0 +1,13 @@
+{
+  "_doc": "registre extensible brique→conteneur ; v1 châssis minimal ; toute nouvelle image doit être sourcée en revue",
+  "litellm": {
+    "image": "ghcr.io/berriai/litellm:main-stable",
+    "container_port": 4000,
+    "health_path": "/health/liveness"
+  },
+  "redis": {
+    "image": "redis:7-alpine",
+    "container_port": 6379,
+    "health_path": null
+  }
+}
diff --git a/src/forgeai/data/smoke/verification.md b/src/forgeai/data/smoke/verification.md
new file mode 100644
index 0000000..197c1e1
--- /dev/null
+++ b/src/forgeai/data/smoke/verification.md
@@ -0,0 +1,15 @@
+# Document de vérification embarqué
+
+Ce fichier sert de document de test par défaut pour le wizard ForgeAI.
+
+Il est court, déterministe et ne contient aucune donnée sensible.
+
+## Fait
+
+La capitale de la France est Paris.
+
+## Détails
+
+- Paris est située dans le nord de la France.
+- C'est la ville la plus peuplée du pays.
+- Le fleuve qui la traverse est la Seine.
diff --git a/src/forgeai/planner/assemble.py b/src/forgeai/planner/assemble.py
index eb17c17..457534e 100644
--- a/src/forgeai/planner/assemble.py
+++ b/src/forgeai/planner/assemble.py
@@ -6,6 +6,7 @@ de l'overlay curé, et fige le tout en DeploymentPlan sérialisable.
 """
 from __future__ import annotations
 
+import importlib.resources
 import json
 import socket
 import uuid
@@ -13,8 +14,10 @@ from pathlib import Path
 
 from forgeai.catalogue.loader import minimal_stack
 from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
+from forgeai.stacks import deploy_ids
 
 PREFERRED_PORT_OFFSET = 10000  # 11434 → 21434 : évite les stacks existantes
+CHASSIS_PORT_START = 8100
 
 
 def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
@@ -34,10 +37,34 @@ def find_free_port(preferred: int, is_free=port_is_free) -> int:
     raise RuntimeError(f"Aucun port libre entre {preferred} et {preferred + 200}")
 
 
+def _next_chassis_port(used_ports: set[int], is_free=port_is_free) -> int:
+    """Port libre suivant à partir de CHASSIS_PORT_START, en évitant les doublons."""
+    for port in range(CHASSIS_PORT_START, CHASSIS_PORT_START + 200):
+        if port in used_ports:
+            continue
+        if is_free(port):
+            return port
+    raise RuntimeError(f"Aucun port libre entre {CHASSIS_PORT_START} et {CHASSIS_PORT_START + 200}")
+
+
+def _load_deploy_specs() -> dict[str, dict]:
+    """Registre brique→conteneur embarqué (package-data)."""
+    try:
+        raw = json.loads(
+            (importlib.resources.files("forgeai.data") / "deploy-specs.json")
+            .read_text(encoding="utf-8")
+        )
+    except FileNotFoundError:
+        return {}
+    return {k: v for k, v in raw.items() if not k.startswith("_")}
+
+
 def assemble_plan(
     profile: str,
     deploy_overlay: Path,
+    *,
     target: RenderTarget = RenderTarget.COMPOSE,
+    stack: dict | None = None,
     is_free=port_is_free,
 ) -> DeploymentPlan:
     overlay = json.loads(deploy_overlay.read_text(encoding="utf-8"))
@@ -56,6 +83,35 @@ def assemble_plan(
             ),
             gpu=bool(svc.get("gpu_capable")) and profile == "minimal-gpu-cuda",
         ))
+
+    if stack is not None:
+        specs = _load_deploy_specs()
+        existing_names = {s.name for s in services}
+        used_ports = {s.host_port for s in services}
+        for brick_id in deploy_ids(stack):
+            if brick_id in existing_names:
+                continue
+            spec = specs.get(brick_id)
+            if spec is None:
+                continue
+            host_port = _next_chassis_port(used_ports, is_free)
+            used_ports.add(host_port)
+            health_path = spec.get("health_path")
+            healthcheck_url = (
+                f"http://127.0.0.1:{host_port}{health_path}"
+                if health_path else None
+            )
+            services.append(ServiceSpec(
+                name=brick_id,
+                image=spec["image"],
+                host_port=host_port,
+                container_port=spec["container_port"],
+                volumes=(),
+                env={},
+                healthcheck_url=healthcheck_url,
+                gpu=False,
+            ))
+
     return DeploymentPlan(
         plan_id=f"p1-{uuid.uuid4().hex[:8]}",
         profile=profile,
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 207dde1..1025b0e 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -526,17 +526,23 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
                 _DEPLOY_STATE["done"] = False
                 _DEPLOY_STATE["exit_code"] = None
 
-                cmd = _DEPLOY_CMD if _DEPLOY_CMD is not None else [
-                    sys.executable,
-                    "-m",
-                    "forgeai",
-                    "wizard",
-                    "--ci",
-                    "--workdir",
-                    str(forgeai_home() / "deploy"),
-                    "--backend",
-                    backend,
-                ]
+                cmd = _DEPLOY_CMD
+                if cmd is None:
+                    cmd = [
+                        sys.executable,
+                        "-m",
+                        "forgeai",
+                        "wizard",
+                        "--ci",
+                        "--workdir",
+                        str(forgeai_home() / "deploy"),
+                        "--backend",
+                        backend,
+                        "--stack",
+                        stack_id,
+                    ]
+                    if data.get("dry_run"):
+                        cmd.append("--dry-run")
 
                 new_proc = subprocess.Popen(
                     cmd,
diff --git a/tests/test_deploy_reel.py b/tests/test_deploy_reel.py
new file mode 100644
index 0000000..6ef6b73
--- /dev/null
+++ b/tests/test_deploy_reel.py
@@ -0,0 +1,159 @@
+"""Tests réels du déploiement : aucun mock de _DEPLOY_CMD."""
+from __future__ import annotations
+
+import json
+import os
+import subprocess
+import sys
+import threading
+import time
+import urllib.request
+from pathlib import Path
+
+import pytest
+
+REPO_ROOT = Path(__file__).resolve().parents[1]
+SRC = REPO_ROOT / "src"
+
+if str(SRC) not in sys.path:
+    sys.path.insert(0, str(SRC))
+
+from forgeai.planner.assemble import assemble_plan
+from forgeai.resources import deploy_overlay_path
+from forgeai.stacks import load_stack
+from forgeai.web.server import build_server
+
+
+def _pythonpath_env() -> dict[str, str]:
+    env = os.environ.copy()
+    env["PYTHONPATH"] = str(SRC)
+    return env
+
+
+def _run_wizard(args: list[str], tmp: Path) -> subprocess.CompletedProcess:
+    cmd = [
+        sys.executable,
+        "-m",
+        "forgeai",
+        "wizard",
+        "--ci",
+        "--workdir",
+        str(tmp),
+    ] + args
+    return subprocess.run(
+        cmd,
+        capture_output=True,
+        text=True,
+        env=_pythonpath_env(),
+        timeout=120,
+    )
+
+
+def test_wizard_dry_run_reel(tmp_path: Path) -> None:
+    workdir = tmp_path / "wd"
+    result = _run_wizard(
+        ["--backend", "compose", "--stack", "agentique", "--dry-run"],
+        workdir,
+    )
+    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
+    assert "DRY-RUN OK" in result.stdout
+    compose = workdir / "docker-compose.yaml"
+    assert compose.exists()
+    text = compose.read_text(encoding="utf-8")
+    assert "litellm" in text
+    assert "redis" in text
+
+
+def test_wizard_dry_run_sans_stack(tmp_path: Path) -> None:
+    workdir = tmp_path / "wd"
+    result = _run_wizard(["--backend", "compose", "--dry-run"], workdir)
+    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
+    assert "DRY-RUN OK" in result.stdout
+    compose = workdir / "docker-compose.yaml"
+    assert compose.exists()
+    text = compose.read_text(encoding="utf-8")
+    assert "litellm" not in text
+    assert "redis" not in text
+
+
+def test_assemble_plan_stack() -> None:
+    overlay = deploy_overlay_path()
+    stack = load_stack("agentique")
+    plan = assemble_plan("minimal-cpu", overlay, stack=stack)
+    names = {s.name for s in plan.services}
+    assert "litellm" in names
+    assert "redis" in names
+    ports = [s.host_port for s in plan.services]
+    assert len(ports) == len(set(ports))
+    # Les services de l'overlay minimal sont conservés
+    assert "ollama" in names
+
+
+def test_defauts_embarques(tmp_path: Path) -> None:
+    workdir = tmp_path / "wd"
+    result = _run_wizard(["--backend", "compose", "--dry-run"], workdir)
+    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
+    assert "DRY-RUN OK" in result.stdout
+
+
+def test_web_deploy_dry_run_e2e(tmp_path: Path) -> None:
+    os.environ["PYTHONPATH"] = str(SRC)
+    server = build_server("127.0.0.1", 0)
+    port = server.server_address[1]
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+
+    base = f"http://127.0.0.1:{port}"
+    body = json.dumps(
+        {
+            "stack": "agentique",
+            "backend": "compose",
+            "confirm": "FORCER",
+            "dry_run": True,
+        },
+        ensure_ascii=False,
+    ).encode("utf-8")
+
+    try:
+        req = urllib.request.Request(
+            f"{base}/api/deploy",
+            data=body,
+            headers={"Content-Type": "application/json"},
+            method="POST",
+        )
+        with urllib.request.urlopen(req, timeout=30) as resp:
+            assert resp.status == 202
+            start_resp = json.loads(resp.read().decode("utf-8"))
+            assert start_resp.get("started") is True
+
+        # Attente que le sous-process wizard ait démarré avant de lire les events
+        time.sleep(0.5)
+
+        events_url = f"{base}/api/deploy/events"
+        with urllib.request.urlopen(events_url, timeout=30) as resp:
+            payload = resp.read().decode("utf-8")
+
+        # Format SSE réel : `event: end` PRÉCÈDE sa ligne `data: {"exit_code": N}`
+        dry_ok = False
+        exit_code = None
+        current_event = "message"
+        for line in payload.splitlines():
+            if line.startswith("event: "):
+                current_event = line[7:]
+            elif line.startswith("data: "):
+                data = line[6:]
+                if "DRY-RUN OK" in data:
+                    dry_ok = True
+                if current_event == "end":
+                    try:
+                        exit_code = json.loads(data).get("exit_code")
+                    except json.JSONDecodeError:
+                        pass
+            elif not line:
+                current_event = "message"
+
+        assert dry_ok, "Le flux SSE ne contient pas 'DRY-RUN OK'"
+        assert exit_code == 0, f"exit_code inattendu : {exit_code}"
+    finally:
+        server.shutdown()
+        server.server_close()
```
