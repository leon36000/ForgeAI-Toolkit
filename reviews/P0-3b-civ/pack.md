# Story P0.3b — La selection complete de l'utilisateur consommee par le deploiement (cloture P0)

## Criteres : briques cochees + modeles choisis VALIDES (fond au wizard, forme au serveur) -> manifeste selection.json trace tout -> briques a deploy-spec fusionnees au plan -> zero mock dans les tests.

## PREUVE
```
### SUITE COMPLETE (213 tests)
.....................................................................    [100%]
### no_stub : OK 161 fichiers

### TESTS REELS P0.3b (6/6, zero mock de commande)
wizard --selection : dry-run exit 0 avec "selection=2+1" + manifeste selection.json (bricks qdrant+litellm, modele Qwen3.6-27B, litellm dans deployables) ; brique inconnue -> exit 8 SANS manifeste ; modele inconnu -> exit 8 ; e2e web POST bricks+models -> SSE exit 0 + manifeste dans FORGEAI_HOME ; selection invalide (a;b) -> 400 sans reflet ; sans selection -> inchange.

### PREUVE NAVIGATEUR REELLE — parcours installateur COMPLET
Etape 2 : stack agentique choisi. Etape 3 : Qwen/Qwen3.6-27B coche. Etape 4 (sphere S6) : brique additionnelle affaan-m-ecc cochee. POST du chemin client (dry_run) -> 202 -> vrai wizard -> ~/.forgeai/deploy/selection.json :
{"stack":"agentique","bricks":["affaan-m-ecc"],"models":["Qwen/Qwen3.6-27B"],"deployables":[],"provisionnement_futur":["affaan-m-ecc"]}
Les choix de l utilisateur atteignent le deploiement et sont TRACES honnetement (deployable maintenant vs provisionnement futur).

### Note : sortie crew tronquee (32k tokens dont 24k raisonnement, 1 marqueur incomplet) -> implementation orchestrateur par edits chirurgicaux (partie dure), revue scellee en garde-fou. 2 fixes en cours de route : import json manquant, Brick.id (objet, pas dict).
```

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/src/forgeai/cli.py b/src/forgeai/cli.py
index 3f0ec6a..5aa3a3a 100644
--- a/src/forgeai/cli.py
+++ b/src/forgeai/cli.py
@@ -8,6 +8,7 @@ erreur avec code de sortie non nul — jamais de faux succès.
 from __future__ import annotations
 
 import argparse
+import json
 import importlib.resources
 import os
 import re
@@ -127,11 +128,51 @@ def wizard_ci(args: argparse.Namespace) -> int:
         stack = load_stack(args.stack)
         stack_label = stack.get("name", args.stack)
 
+    # P0.3b — sélection utilisateur (briques cochées + modèles choisis dans l'UI)
+    selection_bricks: list[str] = []
+    selection_models: list[str] = []
+    if getattr(args, "selection", None):
+        from importlib import resources as _res
+        try:
+            sel = json.loads(Path(args.selection).read_text(encoding="utf-8"))
+            selection_bricks = [str(b) for b in sel.get("bricks", [])]
+            selection_models = [str(m) for m in sel.get("models", [])]
+        except (OSError, ValueError) as exc:
+            print(f"ABORT [SEL] sélection illisible : {exc}", file=sys.stderr)
+            return 8
+        ids_catalogue = {e.id for e in bricks}
+        inconnues = sorted(b for b in selection_bricks if b not in ids_catalogue)
+        if inconnues:
+            print(f"ABORT [SEL] briques inconnues au catalogue : {inconnues}", file=sys.stderr)
+            return 8
+        registre_modeles = json.loads(
+            (_res.files("forgeai.data") / "modeles-locaux.json").read_text(encoding="utf-8"))
+        hf_ids = {m["hf_id"] for m in registre_modeles["modeles"]}
+        inconnus_m = sorted(m for m in selection_models if m not in hf_ids)
+        if inconnus_m:
+            print(f"ABORT [SEL] modèles inconnus au registre : {inconnus_m}", file=sys.stderr)
+            return 8
+
     _step(t("wizard.s04"))
-    plan = assemble_plan(profile, Path(args.overlay), stack=stack)
+    plan = assemble_plan(profile, Path(args.overlay), stack=stack,
+                         extra_bricks=tuple(selection_bricks))
     (workdir / "plan.json").write_text(plan.to_json(), encoding="utf-8")
     ports = {s.name: s.host_port for s in plan.services}
     print(f"  stack: {stack_label} | services: {ports} | modèle: {plan.model}")
+    if getattr(args, "selection", None):
+        from importlib import resources as _res
+        specs_ids = set(json.loads(
+            (_res.files("forgeai.data") / "deploy-specs.json").read_text(encoding="utf-8")))
+        deployables = [b for b in selection_bricks if b in specs_ids]
+        (workdir / "selection.json").write_text(json.dumps({
+            "stack": args.stack,
+            "bricks": selection_bricks,
+            "models": selection_models,
+            "deployables": deployables,
+            "provisionnement_futur": [b for b in selection_bricks if b not in specs_ids],
+        }, ensure_ascii=False, indent=1), encoding="utf-8")
+        print(f"  sélection: {len(selection_bricks)} briques "
+              f"({len(deployables)} déployables maintenant) + {len(selection_models)} modèles")
 
     _step(t("wizard.s05"))
     bootstrap_secrets(workdir)
@@ -155,7 +196,8 @@ def wizard_ci(args: argparse.Namespace) -> int:
     (workdir / "k3s.yaml").write_text(render_k3s(plan, node=effective_node), encoding="utf-8")
 
     if args.dry_run:
-        print(f"DRY-RUN OK: {len(plan.services)} services, stack={stack_label}, node={node_label}", flush=True)
+        print(f"DRY-RUN OK: {len(plan.services)} services, stack={stack_label}, node={node_label}, "
+              f"selection={len(selection_bricks)}+{len(selection_models)}", flush=True)
         return 0
 
     backend = args.backend
@@ -855,6 +897,8 @@ def main(argv: list[str] | None = None) -> int:
                        help="cible K3s : 'local' (hostname courant), 'auto' (scheduler libre), ou hostname exact")
     p_wiz.add_argument("--probe-host", default="127.0.0.1", dest="probe_host",
                        help="hôte de sondage santé/RAG (défaut 127.0.0.1)")
+    p_wiz.add_argument("--selection", default=None,
+                       help="JSON {bricks:[ids], models:[hf_ids]} — sélection UI validée puis tracée (selection.json)")
     p_wiz.add_argument("--dry-run", action="store_true",
                        help="génère les manifestes et s'arrête sans déployer")
     p_wiz.add_argument("--registre", default=str(DEFAULT_REGISTRE))
diff --git a/src/forgeai/planner/assemble.py b/src/forgeai/planner/assemble.py
index 457534e..08b7d4b 100644
--- a/src/forgeai/planner/assemble.py
+++ b/src/forgeai/planner/assemble.py
@@ -65,6 +65,7 @@ def assemble_plan(
     *,
     target: RenderTarget = RenderTarget.COMPOSE,
     stack: dict | None = None,
+    extra_bricks: tuple[str, ...] = (),
     is_free=port_is_free,
 ) -> DeploymentPlan:
     overlay = json.loads(deploy_overlay.read_text(encoding="utf-8"))
@@ -84,11 +85,14 @@ def assemble_plan(
             gpu=bool(svc.get("gpu_capable")) and profile == "minimal-gpu-cuda",
         ))
 
-    if stack is not None:
+    if stack is not None or extra_bricks:
         specs = _load_deploy_specs()
         existing_names = {s.name for s in services}
         used_ports = {s.host_port for s in services}
-        for brick_id in deploy_ids(stack):
+        candidats = list(deploy_ids(stack)) if stack is not None else []
+        # briques cochées par l'utilisateur (P0.3b) : même mécanique, dédupliquée
+        candidats += [b for b in extra_bricks if b not in candidats]
+        for brick_id in candidats:
             if brick_id in existing_names:
                 continue
             spec = specs.get(brick_id)
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index 5f20426..cbff2c8 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -687,6 +687,8 @@
             backend: form.elements.backend.value,
             node: form.elements.node ? form.elements.node.value : 'local',
             models: Object.keys(state.modelsChosen),
+            bricks: Object.entries(state.overrides[overrideKey()] || {})
+              .filter(([, coche]) => coche).map(([id]) => id),
             confirm: confirm
           })
         });
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 13fa9fd..fe34e89 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -167,6 +167,13 @@ _NODE_KEYS_DIR: Path | None = None
 
 # Hook déploiement : remplace la commande wizard par défaut dans les tests.
 _DEPLOY_CMD: list[str] | None = None
+_SELECTION_ITEM_RE = re.compile(r"^[A-Za-z0-9._/:-]{1,200}$")
+
+
+def _selection_valide(lst: object) -> bool:
+    """Validation de FORME seulement (P0.3b) — l'existence est validée par le wizard."""
+    return (isinstance(lst, list) and len(lst) <= 2000
+            and all(isinstance(x, str) and _SELECTION_ITEM_RE.match(x) for x in lst))
 
 _DEPLOY_STATE = {
     "proc": None,
@@ -536,6 +543,12 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
                 self._send_json(400, {"error": "node invalide"})
                 return
 
+            bricks_sel = data.get("bricks", [])
+            models_sel = data.get("models", [])
+            if not _selection_valide(bricks_sel) or not _selection_valide(models_sel):
+                self._send_json(400, {"error": "selection invalide"})
+                return
+
             try:
                 load_stack(stack_id)
             except FileNotFoundError:
@@ -569,6 +582,14 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
                         "--stack",
                         stack_id,
                     ]
+                    if bricks_sel or models_sel:
+                        workdir = forgeai_home() / "deploy"
+                        workdir.mkdir(parents=True, exist_ok=True)
+                        sel_path = workdir / "selection-demande.json"
+                        sel_path.write_text(json.dumps(
+                            {"bricks": bricks_sel, "models": models_sel},
+                            ensure_ascii=False), encoding="utf-8")
+                        cmd += ["--selection", str(sel_path)]
                     if data.get("dry_run"):
                         cmd.append("--dry-run")
 
diff --git a/tests/test_selection_complete.py b/tests/test_selection_complete.py
new file mode 100644
index 0000000..a625e2b
--- /dev/null
+++ b/tests/test_selection_complete.py
@@ -0,0 +1,130 @@
+"""P0.3b — la sélection utilisateur (briques cochées + modèles choisis) atteint le déploiement.
+
+Zéro mock de commande : wizard en subprocess réel, serveur web réel (règle post-audit)."""
+from __future__ import annotations
+
+import json
+import os
+import subprocess
+import sys
+import threading
+import time
+import urllib.error
+import urllib.request
+from pathlib import Path
+
+import pytest
+
+from forgeai.web.server import _DEPLOY_STATE, build_server
+
+
+def _run_wizard(*extra: str, workdir: Path) -> subprocess.CompletedProcess:
+    env = os.environ.copy()
+    env.setdefault("PYTHONPATH", str(Path(__file__).parent.parent / "src"))
+    return subprocess.run(
+        [sys.executable, "-m", "forgeai", "wizard", "--ci", "--dry-run",
+         "--workdir", str(workdir / "run"), "--stack", "agentique", *extra],
+        capture_output=True, text=True, timeout=120, env=env,
+    )
+
+
+def _selection_file(tmp_path: Path, bricks: list[str], models: list[str]) -> Path:
+    f = tmp_path / "sel.json"
+    f.write_text(json.dumps({"bricks": bricks, "models": models}), encoding="utf-8")
+    return f
+
+
+def test_wizard_selection_dry_run(tmp_path: Path) -> None:
+    sel = _selection_file(tmp_path, ["qdrant", "litellm"], ["Qwen/Qwen3.6-27B"])
+    res = _run_wizard("--selection", str(sel), workdir=tmp_path)
+    assert res.returncode == 0, res.stdout + res.stderr
+    assert "selection=2+1" in res.stdout
+    manifest = json.loads((tmp_path / "run" / "selection.json").read_text(encoding="utf-8"))
+    assert manifest["bricks"] == ["qdrant", "litellm"]
+    assert manifest["models"] == ["Qwen/Qwen3.6-27B"]
+    assert "litellm" in manifest["deployables"]
+
+
+def test_wizard_selection_brique_inconnue(tmp_path: Path) -> None:
+    sel = _selection_file(tmp_path, ["brique-inexistante-xyz"], [])
+    res = _run_wizard("--selection", str(sel), workdir=tmp_path)
+    assert res.returncode == 8
+    assert "brique-inexistante-xyz" in res.stderr
+    assert not (tmp_path / "run" / "selection.json").exists()
+
+
+def test_wizard_selection_modele_inconnu(tmp_path: Path) -> None:
+    sel = _selection_file(tmp_path, [], ["fake/NExiste-Pas"])
+    res = _run_wizard("--selection", str(sel), workdir=tmp_path)
+    assert res.returncode == 8
+    assert "fake/NExiste-Pas" in res.stderr
+
+
+@pytest.fixture()
+def live(tmp_path, monkeypatch):
+    monkeypatch.setenv("FORGEAI_HOME", str(tmp_path))
+    with _DEPLOY_STATE["lock"]:
+        _DEPLOY_STATE["proc"] = None
+        _DEPLOY_STATE["lines"].clear()
+        _DEPLOY_STATE["done"] = False
+        _DEPLOY_STATE["exit_code"] = None
+    srv = build_server("127.0.0.1", 0)
+    threading.Thread(target=srv.serve_forever, daemon=True).start()
+    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
+    with _DEPLOY_STATE["lock"]:
+        proc = _DEPLOY_STATE["proc"]
+    if proc is not None and proc.poll() is None:
+        proc.terminate()
+        proc.wait()
+    srv.shutdown()
+    srv.server_close()
+
+
+def _post(base: str, payload: dict) -> tuple[int, dict]:
+    req = urllib.request.Request(
+        f"{base}/api/deploy", data=json.dumps(payload).encode("utf-8"),
+        headers={"Content-Type": "application/json"}, method="POST")
+    try:
+        with urllib.request.urlopen(req, timeout=15) as r:
+            return r.status, json.loads(r.read().decode("utf-8"))
+    except urllib.error.HTTPError as exc:
+        return exc.code, json.loads(exc.read().decode("utf-8"))
+
+
+def _attendre_fin(timeout_s: float = 120.0) -> int | None:
+    limite = time.monotonic() + timeout_s
+    while time.monotonic() < limite:
+        with _DEPLOY_STATE["lock"]:
+            if _DEPLOY_STATE["done"]:
+                return _DEPLOY_STATE["exit_code"]
+        time.sleep(0.5)
+    return None
+
+
+def test_web_deploy_selection_e2e(live) -> None:
+    base, home = live
+    code, body = _post(base, {"stack": "agentique", "backend": "compose",
+                              "confirm": "FORCER", "dry_run": True,
+                              "bricks": ["qdrant"], "models": ["Qwen/Qwen3.6-27B"]})
+    assert code == 202 and body["started"] is True
+    assert _attendre_fin() == 0
+    manifest = json.loads((home / "deploy" / "selection.json").read_text(encoding="utf-8"))
+    assert manifest["bricks"] == ["qdrant"]
+    assert manifest["models"] == ["Qwen/Qwen3.6-27B"]
+
+
+def test_web_deploy_selection_invalide(live) -> None:
+    base, _ = live
+    code, body = _post(base, {"stack": "agentique", "backend": "compose",
+                              "confirm": "FORCER", "dry_run": True,
+                              "bricks": ["a;b"]})
+    assert code == 400
+    assert "a;b" not in json.dumps(body)
+
+
+def test_sans_selection_inchange(live) -> None:
+    base, _ = live
+    code, _ = _post(base, {"stack": "agentique", "backend": "compose",
+                           "confirm": "FORCER", "dry_run": True})
+    assert code == 202
+    assert _attendre_fin() == 0
```
