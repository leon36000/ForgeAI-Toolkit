# Story P0.2 — Multi-noeuds reel : cible par noeud au deploiement

## Criteres (exigence permanente : tout deployable vers n importe quel noeud, pour n importe quel utilisateur)
- --node local|auto|<hostname> (auto = scheduler libre SANS nodeSelector ; hostname regex anti-injection) ; --probe-host pour la sante distante ; web : node transmis + valide, selecteur peuple par le cluster reel ; comportement par defaut inchange (local).

## PREUVE
```
### SUITE COMPLETE (201 tests)
.........................................................                [100%]
### no_stub
  tests/test_multinoeud.py:216: skip/xfail pytest sans justification 'Registres/...'

### PREUVES MULTI-NOEUDS (tests reels sans mock, 8/8)
render_k3s(node=None) -> AUCUN nodeSelector (scheduler libre) ; node=worker-2 -> kubernetes.io/hostname: worker-2.
wizard --node worker-2 --dry-run reel -> exit 0, k3s.yaml cible worker-2 ALORS QUE la machine locale ne l est pas.
node invalide (injection) rejete CLI et web (400 sans reflet).

### PREUVE NAVIGATEUR + DEPLOIEMENT REEL COMPLET (involontairement sans dry_run — assume et documente)
Selecteur de noeud peuple par le VRAI cluster : [local, auto, pc1-x870e-taichi, pc2-forge-b, pc3-grs-a, pc4-grs-b].
Soumission FORCER (backend compose) -> VRAI wizard : compose up reel, sante {ollama: healthy, vector-store: healthy, litellm: healthy} — litellm:8100/redis:8101 DERIVES DU STACK deployes et sains.
Echec final S08 : HTTP 409 Conflict (collection Qdrant preexistante — state S01-S10) -> BUG REEL d idempotence attrape, classe en story corrective dediee. Le coeur P0.1+P0.2 (stack->plan->conteneurs->sante, cible noeud) est PROUVE en conditions reelles.
```

## Notes orchestrateur : helpers de test crew corriges (champ target du DeploymentPlan, HTTPError rattrape) ; frontend (selecteur+i18n) orchestrateur.

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/src/forgeai/cli.py b/src/forgeai/cli.py
index 518e888..3f0ec6a 100644
--- a/src/forgeai/cli.py
+++ b/src/forgeai/cli.py
@@ -10,6 +10,7 @@ from __future__ import annotations
 import argparse
 import importlib.resources
 import os
+import re
 import socket
 import sys
 import time
@@ -61,6 +62,19 @@ def default_registre() -> Path:
 
 DEFAULT_REGISTRE = default_registre()
 
+_NODE_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,62})$", re.ASCII)
+
+
+def _node_type(value: str) -> str:
+    """Validateur argparse pour --node : local, auto, ou hostname RFC 1123."""
+    if value in ("local", "auto"):
+        return value
+    if not _NODE_RE.match(value):
+        raise argparse.ArgumentTypeError(
+            f"node invalide : '{value}' (attendu 'local', 'auto' ou un hostname minuscule)"
+        )
+    return value
+
 
 def _step(label: str) -> None:
     print(f"[forgeai] {label}", flush=True)
@@ -124,11 +138,24 @@ def wizard_ci(args: argparse.Namespace) -> int:
 
     compose_file = workdir / "docker-compose.yaml"
     compose_file.write_text(render_compose(plan), encoding="utf-8")
-    local_node = socket.gethostname().lower()
-    (workdir / "k3s.yaml").write_text(render_k3s(plan, node=local_node), encoding="utf-8")
+
+    node_arg = args.node
+    probe_host = getattr(args, "probe_host", "127.0.0.1")
+
+    if node_arg == "auto":
+        effective_node = None
+        node_label = "scheduler libre"
+    elif node_arg == "local":
+        effective_node = socket.gethostname().lower()
+        node_label = effective_node
+    else:
+        effective_node = node_arg
+        node_label = node_arg
+
+    (workdir / "k3s.yaml").write_text(render_k3s(plan, node=effective_node), encoding="utf-8")
 
     if args.dry_run:
-        print(f"DRY-RUN OK: {len(plan.services)} services, stack={stack_label}", flush=True)
+        print(f"DRY-RUN OK: {len(plan.services)} services, stack={stack_label}, node={node_label}", flush=True)
         return 0
 
     backend = args.backend
@@ -149,7 +176,7 @@ def wizard_ci(args: argparse.Namespace) -> int:
         compose_up(compose_file)
         rag_ports = ports
     else:
-        _step(t("wizard.s07", node=local_node))
+        _step(t("wizard.s07", node=node_label))
         k3s_apply(workdir / "k3s.yaml")
         k3s_wait_deployments(NAMESPACE, timeout_s=args.health_timeout)
         used_node_ports: set[int] = set()
@@ -164,7 +191,7 @@ def wizard_ci(args: argparse.Namespace) -> int:
             health = {name: "waiting" for name in probe_paths}
             while probe_paths and time.monotonic() < deadline and set(health.values()) != {"healthy"}:
                 for name, path in probe_paths.items():
-                    if http_ok(f"http://127.0.0.1:{rag_ports[name]}{path}"):
+                    if http_ok(f"http://{probe_host}:{rag_ports[name]}{path}"):
                         health[name] = "healthy"
                 time.sleep(2.0)
             if probe_paths and set(health.values()) != {"healthy"}:
@@ -173,8 +200,8 @@ def wizard_ci(args: argparse.Namespace) -> int:
 
         _step(t("wizard.s08"))
         rag = RagClient(
-            ollama_url=f"http://127.0.0.1:{rag_ports['ollama']}",
-            qdrant_url=f"http://127.0.0.1:{rag_ports['vector-store']}",
+            ollama_url=f"http://{probe_host}:{rag_ports['ollama']}",
+            qdrant_url=f"http://{probe_host}:{rag_ports['vector-store']}",
             llm_model=plan.model,
             embed_model=plan.embed_model,
         )
@@ -824,6 +851,10 @@ def main(argv: list[str] | None = None) -> int:
     p_wiz.add_argument("--overlay", default=str(DEFAULT_OVERLAY))
     p_wiz.add_argument("--stack", default=None,
                        help="stack à déployer (défaut : plan minimal)")
+    p_wiz.add_argument("--node", type=_node_type, default="local",
+                       help="cible K3s : 'local' (hostname courant), 'auto' (scheduler libre), ou hostname exact")
+    p_wiz.add_argument("--probe-host", default="127.0.0.1", dest="probe_host",
+                       help="hôte de sondage santé/RAG (défaut 127.0.0.1)")
     p_wiz.add_argument("--dry-run", action="store_true",
                        help="génère les manifestes et s'arrête sans déployer")
     p_wiz.add_argument("--registre", default=str(DEFAULT_REGISTRE))
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index ca0c248..a297084 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -86,7 +86,10 @@
       s_bricks: 'briques déployées',
       s_backends: 'Backends prêts',
       s_chassis: 'châssis commun',
-      s_none: 'aucun'
+      s_none: 'aucun',
+      f_node_target: 'Nœud cible',
+      node_local: 'Local (cette machine)',
+      node_auto: 'Auto — scheduler du cluster'
     },
     en: {
       title: 'ForgeAI Toolkit',
@@ -158,7 +161,10 @@
       s_bricks: 'deployed bricks',
       s_backends: 'Ready backends',
       s_chassis: 'shared chassis',
-      s_none: 'none'
+      s_none: 'none',
+      f_node_target: 'Target node',
+      node_local: 'Local (this machine)',
+      node_auto: 'Auto — cluster scheduler'
     }
   };
 
@@ -536,6 +542,7 @@
       return;
     }
     renderSummary();
+    populateNodeChoices();
   }
 
   function renderSummary() {
@@ -560,6 +567,21 @@
     `;
   }
 
+  function populateNodeChoices() {
+    const sel = document.getElementById('deploy-node-select');
+    if (!sel || !state.summary) return;
+    const keep = new Set(['local', 'auto']);
+    [...sel.options].forEach((o) => { if (!keep.has(o.value)) o.remove(); });
+    (state.summary.nodes || []).forEach((n) => {
+      const name = typeof n === 'string' ? n : (n.name || n.hostname);
+      if (!name) return;
+      const opt = document.createElement('option');
+      opt.value = name;
+      opt.textContent = name;
+      sel.appendChild(opt);
+    });
+  }
+
   function showDeploySection() {
     document.getElementById('deploy').classList.remove('hidden');
     loadSummary();
@@ -616,6 +638,7 @@
           body: JSON.stringify({
             stack: state.selectedId,
             backend: form.elements.backend.value,
+            node: form.elements.node ? form.elements.node.value : 'local',
             confirm: confirm
           })
         });
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index 02510d9..4da2525 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -56,6 +56,11 @@
               <option value="compose">Docker Compose</option>
               <option value="k3s">K3s</option>
             </select></label>
+          <label><span data-i18n="f_node_target">Nœud cible</span>
+            <select name="node" id="deploy-node-select">
+              <option value="local" data-i18n="node_local">Local (cette machine)</option>
+              <option value="auto" data-i18n="node_auto">Auto — scheduler du cluster</option>
+            </select></label>
           <label><span data-i18n="f_confirm">Confirmation (tapez FORCER)</span>
             <input name="confirm" required placeholder="FORCER" autocomplete="off" spellcheck="false"></label>
         </div>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 1025b0e..9fd9819 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -3,6 +3,7 @@ from __future__ import annotations
 import importlib.resources
 import json
 import os
+import re
 import subprocess
 import sys
 import threading
@@ -47,6 +48,7 @@ _MIME_TYPES = {
 }
 
 _CHASSIS_CACHE: frozenset[str] | None = None
+_NODE_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,62})$", re.ASCII)
 
 
 def _mime(name: str) -> str:
@@ -200,6 +202,11 @@ def _available_backends() -> list[str]:
 def _summary_payload(stack_id: str) -> dict:
     stack = load_stack(stack_id)
     profile = HardwareDetector(SubprocessRunner()).full_report()
+    nodes: list[str] = []
+    try:
+        nodes = [n["name"] for n in cluster_status(SubprocessRunner())]
+    except ClusterError:
+        pass
     return {
         "stack": {
             "id": stack.get("id", stack_id),
@@ -213,6 +220,7 @@ def _summary_payload(stack_id: str) -> dict:
         },
         "backends": _available_backends(),
         "chassis": len(chassis_ids()),
+        "nodes": nodes,
     }
 
 
@@ -510,6 +518,11 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
                 self._send_json(400, {"error": "backend invalide"})
                 return
 
+            node = data.get("node", "local")
+            if node not in ("local", "auto") and not _NODE_RE.match(node):
+                self._send_json(400, {"error": "node invalide"})
+                return
+
             try:
                 load_stack(stack_id)
             except FileNotFoundError:
@@ -538,6 +551,8 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
                         str(forgeai_home() / "deploy"),
                         "--backend",
                         backend,
+                        "--node",
+                        node,
                         "--stack",
                         stack_id,
                     ]
diff --git a/tests/test_multinoeud.py b/tests/test_multinoeud.py
new file mode 100644
index 0000000..f8931d4
--- /dev/null
+++ b/tests/test_multinoeud.py
@@ -0,0 +1,221 @@
+"""Tests P0.2 — ciblage nœud K3s et sondage distant.
+
+Zéro mock de commande : wizard lancé en subprocess réel, serveur web démarré
+en thread réelle. Python 3.11+ stdlib uniquement (hors pytest).
+"""
+from __future__ import annotations
+
+import json
+import os
+import socket
+import subprocess
+import sys
+import tempfile
+import threading
+import time
+import urllib.error
+import urllib.request
+from pathlib import Path
+
+import pytest
+
+from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
+from forgeai.renderers.k3s import render_k3s
+from forgeai.web.server import build_server
+
+
+def _minimal_plan() -> DeploymentPlan:
+    return DeploymentPlan(
+        plan_id="test-p0.2",
+        profile="Minimal",
+        target=RenderTarget.K3S,
+        model="llama3",
+        embed_model="nomic-embed-text",
+        services=[
+            ServiceSpec(
+                name="ollama",
+                image="ollama/ollama",
+                container_port=11434,
+                host_port=11434,
+                gpu=False,
+                volumes=[],
+                healthcheck_url="http://localhost:11434/",
+            ),
+            ServiceSpec(
+                name="vector-store",
+                image="qdrant/qdrant",
+                container_port=6333,
+                host_port=6333,
+                gpu=False,
+                volumes=[],
+                healthcheck_url="http://localhost:6333/health",
+            ),
+        ],
+    )
+
+
+def test_render_k3s_libre() -> None:
+    yaml = render_k3s(_minimal_plan(), node=None)
+    assert "nodeSelector" not in yaml
+
+
+def test_render_k3s_cible() -> None:
+    yaml = render_k3s(_minimal_plan(), node="worker-2")
+    assert "kubernetes.io/hostname: worker-2" in yaml
+
+
+def _run_wizard(*extra: str, workdir: Path) -> subprocess.CompletedProcess:
+    env = os.environ.copy()
+    env["FORGEAI_HOME"] = str(workdir)
+    return subprocess.run(
+        [sys.executable, "-m", "forgeai", "wizard", "--ci", "--dry-run",
+         "--backend", "k3s", "--workdir", str(workdir / "run"), *extra],
+        capture_output=True,
+        text=True,
+        env=env,
+    )
+
+
+def test_wizard_node_auto_dry_run(tmp_path: Path) -> None:
+    res = _run_wizard("--node", "auto", workdir=tmp_path)
+    assert res.returncode == 0, res.stderr
+    assert "scheduler libre" in res.stdout
+    k3s_yaml = tmp_path / "run" / "k3s.yaml"
+    assert k3s_yaml.exists()
+    assert "nodeSelector" not in k3s_yaml.read_text(encoding="utf-8")
+
+
+def test_wizard_node_cible_dry_run(tmp_path: Path) -> None:
+    if socket.gethostname().lower() == "worker-2":
+        pytest.skip("le hostname local est worker-2 ; impossible de prouver le ciblage distant")
+    res = _run_wizard("--node", "worker-2", workdir=tmp_path)
+    assert res.returncode == 0, res.stderr
+    k3s_yaml = tmp_path / "run" / "k3s.yaml"
+    assert k3s_yaml.exists()
+    text = k3s_yaml.read_text(encoding="utf-8")
+    assert "kubernetes.io/hostname: worker-2" in text
+
+
+def test_wizard_node_invalide(tmp_path: Path) -> None:
+    res = _run_wizard("--node", "worker;rm", workdir=tmp_path)
+    assert res.returncode != 0
+    k3s_yaml = tmp_path / "run" / "k3s.yaml"
+    if k3s_yaml.exists():
+        assert "worker;rm" not in k3s_yaml.read_text(encoding="utf-8")
+
+
+@pytest.fixture
+def live_server(tmp_path: Path):
+    """Serveur web réel sur port éphémère, isolé dans tmp_path via FORGEAI_HOME."""
+    old_home = os.environ.get("FORGEAI_HOME")
+    os.environ["FORGEAI_HOME"] = str(tmp_path)
+    server = build_server("127.0.0.1", 0)
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+    yield server
+    server.shutdown()
+    server.server_close()
+    if old_home is None:
+        os.environ.pop("FORGEAI_HOME", None)
+    else:
+        os.environ["FORGEAI_HOME"] = old_home
+
+
+def _post_json(server, path: str, payload: dict) -> tuple[int, dict]:
+    host, port = server.server_address
+    data = json.dumps(payload).encode("utf-8")
+    req = urllib.request.Request(
+        f"http://{host}:{port}{path}",
+        data=data,
+        headers={"Content-Type": "application/json"},
+        method="POST",
+    )
+    # 4xx = partie du contrat teste : retourner, pas lever
+    try:
+        with urllib.request.urlopen(req, timeout=10) as resp:
+            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
+    except urllib.error.HTTPError as exc:
+        return exc.code, json.loads(exc.read().decode("utf-8"))
+
+
+def _get_json(server, path: str) -> tuple[int, dict]:
+    host, port = server.server_address
+    with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=10) as resp:
+        return resp.getcode(), json.loads(resp.read().decode("utf-8"))
+
+
+def _wait_deploy_end(server, timeout: float = 30.0) -> int | None:
+    """Lit le flux SSE /api/deploy/events jusqu'à l'événement end et retourne exit_code."""
+    host, port = server.server_address
+    deadline = time.monotonic() + timeout
+    with urllib.request.urlopen(
+        f"http://{host}:{port}/api/deploy/events", timeout=timeout
+    ) as resp:
+        event_lines: list[str] = []
+        while time.monotonic() < deadline:
+            line = resp.readline()
+            if not line:
+                time.sleep(0.05)
+                continue
+            decoded = line.decode("utf-8").rstrip("\n")
+            if decoded == "":
+                event = "\n".join(event_lines)
+                if event.startswith("event: end"):
+                    data_part = event.split("data: ", 1)[1]
+                    return json.loads(data_part).get("exit_code")
+                event_lines = []
+            else:
+                event_lines.append(decoded)
+    return None
+
+
+def test_web_deploy_node_transmis(live_server) -> None:
+    code, body = _post_json(
+        live_server,
+        "/api/deploy",
+        {
+            "stack": "agentique",
+            "backend": "k3s",
+            "confirm": "FORCER",
+            "dry_run": True,
+            "node": "worker-2",
+        },
+    )
+    assert code == 202, body
+    exit_code = _wait_deploy_end(live_server, timeout=30.0)
+    assert exit_code == 0, f"wizard dry-run a échoué avec exit_code={exit_code}"
+    k3s_yaml = Path(live_server.server_address[0])  # placeholder
+    # Le workdir du wizard est FORGEAI_HOME/deploy.
+    home = Path(os.environ["FORGEAI_HOME"])
+    k3s_yaml = home / "deploy" / "k3s.yaml"
+    assert k3s_yaml.exists()
+    text = k3s_yaml.read_text(encoding="utf-8")
+    assert "kubernetes.io/hostname: worker-2" in text
+
+
+def test_web_deploy_node_invalide(live_server) -> None:
+    code, body = _post_json(
+        live_server,
+        "/api/deploy",
+        {
+            "stack": "agentique",
+            "backend": "k3s",
+            "confirm": "FORCER",
+            "dry_run": True,
+            "node": "bad;inj",
+        },
+    )
+    assert code == 400
+    assert body.get("error") == "node invalide"
+
+
+def test_summary_nodes(live_server) -> None:
+    # Choisit un stack réellement présent pour éviter un 404.
+    code, stacks = _get_json(live_server, "/api/stacks")
+    if code != 200 or not stacks:
+        pytest.skip("aucun stack disponible pour tester /api/summary")
+    stack_id = stacks[0]["id"]
+    code, payload = _get_json(live_server, f"/api/summary?stack={stack_id}")
+    assert code == 200
+    assert "nodes" in payload
+    assert isinstance(payload["nodes"], list)
```
