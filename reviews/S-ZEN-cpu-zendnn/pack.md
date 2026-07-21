# Story S-ZEN — brique moteur CPU AMD Zen via ZenDNN + rendu env k3s

## Exigence (Nathan) : déployer des modèles sur CPU AMD Zen en utilisant ZenDNN.

## Changements
- deploy-specs.json : brique `cpu-zendnn` : image AMD `amdih/zendnn_zentorch:vllm_...` (vLLM + plugin
  zentorch, plug-and-play), **gpu:false** (CPU), command `vllm serve Qwen2.5-0.5B --dtype bfloat16`
  (API OpenAI :8000), env de tuning ZenDNN (ZENDNNL_MATMUL_ALGO=1, TORCHINDUCTOR_FREEZING=1,
  VLLM_USE_AOT_COMPILE=0, TORCHINDUCTOR_AUTOGRAD_CACHE=0, VLLM_CPU_KVCACHE_SPACE=8).
- renderers/k3s.py : rend le champ `env` (bloc env k8s, PARITÉ compose ; clés/valeurs via `_safe`).
  GAP corrigé : sans ça les tunings ZenDNN (et l'env de toute brique) seraient perdus au déploiement k3s.

## Critères (testés — tests/test_cpu_zendnn_runtime.py)
1. Brique cpu-zendnn : image zendnn/zentorch, gpu:false, command 'vllm serve', env ZENDNNL_MATMUL_ALGO.
2. render_k3s émet le bloc env (clés+valeurs).
3. assemble('minimal-cpu', extra_bricks=('cpu-zendnn',)) -> gpu=False ; render contient vllm + ZENDNNL.

## Preuve serving RÉELLE sur le CPU Zen5 de pc4 (Ryzen 9 9950X3D, znver5) VIA la toolkit
deploy-spec -> assemble -> render_k3s(env) -> kubectl apply -> logs 'Platform plugin zentorch is
activated' + complétion OpenAI réelle :
```
RÉPONSE: Bien sûr ! Pourriez-vous me donner le nombre que vous souhaitez que je mettez en compte ? Je ser
usage: {'prompt_tokens': 38, 'total_tokens': 63, 'completion_tokens': 25, 'prompt_tokens_details': None}
zentorch activé (via env rendu par render_k3s de la toolkit)
```
## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/data/deploy-specs.json b/src/forgeai/data/deploy-specs.json
index 33c466b..7d075d3 100644
--- a/src/forgeai/data/deploy-specs.json
+++ b/src/forgeai/data/deploy-specs.json
@@ -142,5 +142,31 @@
       "8080"
     ],
     "depends": []
+  },
+  "cpu-zendnn": {
+    "image": "amdih/zendnn_zentorch:vllm_v0.23.0_zentorch_v2.11.0.2_ubuntu22.04_v2.11.0.2",
+    "container_port": 8000,
+    "health_path": "/health",
+    "gpu": false,
+    "volumes": [],
+    "env": {
+      "ZENDNNL_MATMUL_ALGO": "1",
+      "TORCHINDUCTOR_FREEZING": "1",
+      "VLLM_USE_AOT_COMPILE": "0",
+      "TORCHINDUCTOR_AUTOGRAD_CACHE": "0",
+      "VLLM_CPU_KVCACHE_SPACE": "8"
+    },
+    "command": [
+      "vllm",
+      "serve",
+      "Qwen/Qwen2.5-0.5B-Instruct",
+      "--dtype",
+      "bfloat16",
+      "--host",
+      "0.0.0.0",
+      "--port",
+      "8000"
+    ],
+    "depends": []
   }
 }
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index 44e9aeb..65ad84a 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -118,7 +118,16 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
     if svc.command:
         items = "".join(f"\n            - \"{_safe(str(a), 'arg')}\"" for a in svc.command)
         command_block = f"\n          args:{items}"
-    container_extra = f"{command_block}{resources_block}{security_block}{volume_mount}{volume_def}"
+    # env → bloc env k8s (parité compose) ; valeurs littérales (k8s n'expanse pas ${...}).
+    env_block = ""
+    if svc.env:
+        items = "".join(
+            f"\n            - name: {_safe(str(k), 'env-key')}"
+            f"\n              value: \"{_safe(str(v), 'env-val')}\""
+            for k, v in svc.env.items())
+        env_block = f"\n          env:{items}"
+    container_extra = (command_block + env_block + resources_block
+                       + security_block + volume_mount + volume_def)
     return f"""---
 apiVersion: apps/v1
 kind: Deployment
diff --git a/tests/test_cpu_zendnn_runtime.py b/tests/test_cpu_zendnn_runtime.py
new file mode 100644
index 0000000..6154a1a
--- /dev/null
+++ b/tests/test_cpu_zendnn_runtime.py
@@ -0,0 +1,57 @@
+"""Story S-ZEN — inférence CPU AMD Zen via ZenDNN : brique `cpu-zendnn` + rendu `env` k3s.
+
+Image AMD `amdih/zendnn_zentorch` (vLLM + plugin zentorch, plug-and-play), gpu:false (CPU), env de
+tuning ZENDNNL_*. Le renderer k3s doit rendre le champ `env` (parité compose) sinon les réglages
+ZenDNN sont perdus. Serving réel prouvé sur le CPU Zen5 de pc4 (zentorch activé, complétion OpenAI).
+"""
+import json
+import sys
+from importlib.resources import files
+from pathlib import Path
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
+from forgeai.planner.assemble import assemble_plan
+from forgeai.renderers.k3s import render_k3s
+
+BRICK = "cpu-zendnn"
+
+
+def test_brique_cpu_zendnn_deployable():
+    specs = json.loads((files("forgeai.data") / "deploy-specs.json").read_text(encoding="utf-8"))
+    assert BRICK in specs, "la brique cpu-zendnn doit être déployable (deploy-specs)"
+    s = specs[BRICK]
+    assert "zendnn" in s["image"].lower() or "zentorch" in s["image"].lower()
+    assert s.get("gpu", False) is False, "ZenDNN = inférence CPU (pas GPU)"
+    cmd = " ".join(str(c) for c in s.get("command", []))
+    assert "vllm" in cmd and "serve" in cmd, "vllm serve (API OpenAI)"
+    assert "ZENDNNL_MATMUL_ALGO" in s.get("env", {}), "tuning ZenDNN présent"
+
+
+def test_k3s_rend_le_champ_env():
+    # GAP corrigé : le renderer k3s doit émettre le bloc env (parité compose).
+    svc = ServiceSpec(name="e", image="i", host_port=1, container_port=1,
+                      env={"ZENDNNL_MATMUL_ALGO": "1", "FOO": "bar"})
+    out = render_k3s(DeploymentPlan(plan_id="p", profile="x", target=RenderTarget.K3S,
+                                    services=(svc,), model="m", embed_model="e"))
+    assert "env:" in out
+    assert "ZENDNNL_MATMUL_ALGO" in out and "FOO" in out and "bar" in out
+
+
+def _overlay(tmp_path):
+    ov = tmp_path / "ov.json"
+    ov.write_text(json.dumps({"profile": "x", "engine_default": "ollama", "services": [
+        {"name": "ollama", "brick_id": "ollama", "image": "ollama/ollama:latest",
+         "container_port": 11434, "healthcheck_path": "/api/tags"}],
+        "models": {"llm": "q", "embed": "b"}}))
+    return ov
+
+
+def test_cpu_zendnn_assemble_sans_gpu(tmp_path):
+    # ZenDNN = CPU : la brique ne doit PAS être marquée GPU quel que soit le profil.
+    plan = assemble_plan("minimal-cpu", _overlay(tmp_path), extra_bricks=(BRICK,))
+    svc = next((s for s in plan.services if s.name == BRICK), None)
+    assert svc is not None and svc.gpu is False
+    out = render_k3s(plan)
+    assert "vllm" in out and "ZENDNNL_MATMUL_ALGO" in out
```
## Preuve déterministe
```
....................                                                     [100%]
...............................................................s........ [ 91%]
........................................................                 [100%]
All checks passed!
```
