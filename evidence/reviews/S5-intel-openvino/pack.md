# Story S5 — brique moteur Intel/OpenVINO déployable (OpenVINO Model Server / OVMS)

## Objet (complète le trio vendor nvidia/amd/intel)
Brique `intel-openvino` : OpenVINO Model Server, le runtime d'inférence Intel, exposé en API OpenAI /v3.

## Choix (universel — pc4 = banc d'essai, pas de HW Intel)
- Image `openvino/model_server:latest`. `--task text_generation` -> /v3/chat/completions.
- Modèle OV pré-converti auto-fetch : `--source_model OpenVINO/Qwen2.5-1.5B-Instruct-int4-ov` (repo HF PUBLIC ;
  le 0.5B est gated 401). `--target_device AUTO` : GPU Intel si présent, sinon CPU.
- volume emptyDir /models (writable) : sans lui OVMS -> 'failed to make directory /models: Permission denied'.
- gpu:false par défaut. Accélération GPU Intel = nœud Intel + passthrough intel (S3) + --target_device GPU.

## Critères (testés)
1. Brique déployable : image openvino/model_server, command --source_model + --task text_generation.
2. assemble+render_k3s : manifeste contient openvino + text_generation + volume /models.

## Preuve serving RÉELLE sur pc4 (CPU) VIA la toolkit
deploy-spec -> assemble_plan -> render_k3s(node=pc4) -> kubectl apply -> OVMS /v3/models=200 + complétion :
```
RÉPONSE: Toronto
usage: {'prompt_tokens': 39, 'completion_tokens': 2, 'total_tokens': 41}
OpenVINO Model Server via la toolkit (deploy-spec->assemble->render_k3s->apply) — /v3 OpenAI sur CPU pc4
```
## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/data/deploy-specs.json b/src/forgeai/data/deploy-specs.json
index 7d075d3..2c73fef 100644
--- a/src/forgeai/data/deploy-specs.json
+++ b/src/forgeai/data/deploy-specs.json
@@ -168,5 +168,32 @@
       "8000"
     ],
     "depends": []
+  },
+  "intel-openvino": {
+    "image": "openvino/model_server:latest",
+    "container_port": 8000,
+    "health_path": "/v3/models",
+    "gpu": false,
+    "volumes": [
+      "ovms-models:/models"
+    ],
+    "env": {},
+    "command": [
+      "--source_model",
+      "OpenVINO/Qwen2.5-1.5B-Instruct-int4-ov",
+      "--model_repository_path",
+      "/models",
+      "--model_name",
+      "qwen",
+      "--rest_port",
+      "8000",
+      "--task",
+      "text_generation",
+      "--target_device",
+      "AUTO",
+      "--cache_size",
+      "2"
+    ],
+    "depends": []
   }
 }
diff --git a/tests/test_intel_openvino_runtime.py b/tests/test_intel_openvino_runtime.py
new file mode 100644
index 0000000..36697b4
--- /dev/null
+++ b/tests/test_intel_openvino_runtime.py
@@ -0,0 +1,47 @@
+"""Story S5 — brique moteur Intel/OpenVINO déployable (OpenVINO Model Server / OVMS).
+
+Image OVMS, API OpenAI `/v3/chat/completions`, modèle OV pré-converti (repo HF public), auto-fetch
+via --source_model. `--target_device AUTO` = universel (GPU Intel si présent, sinon CPU). gpu:false
+par défaut (CPU/AUTO ; l'accélération GPU Intel s'obtient sur un nœud Intel via le passthrough
+intel de S3 + --target_device GPU). Serving réel prouvé sur le CPU de pc4 (OVMS sert /v3).
+"""
+import json
+import sys
+from importlib.resources import files
+from pathlib import Path
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.planner.assemble import assemble_plan
+from forgeai.renderers.k3s import render_k3s
+
+BRICK = "intel-openvino"
+
+
+def test_brique_intel_openvino_deployable():
+    specs = json.loads((files("forgeai.data") / "deploy-specs.json").read_text(encoding="utf-8"))
+    assert BRICK in specs, "la brique intel-openvino doit être déployable (deploy-specs)"
+    s = specs[BRICK]
+    assert "openvino" in s["image"] or "model_server" in s["image"]
+    cmd = " ".join(str(c) for c in s.get("command", []))
+    assert "text_generation" in cmd, "OVMS servi en génération de texte (API OpenAI)"
+    assert "--source_model" in cmd, "auto-fetch du modèle OV via --source_model"
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
+def test_intel_openvino_rendu_k3s(tmp_path):
+    plan = assemble_plan("minimal-cpu", _overlay(tmp_path), extra_bricks=(BRICK,))
+    svc = next((s for s in plan.services if s.name == BRICK), None)
+    assert svc is not None, "la brique doit être au plan"
+    out = render_k3s(plan)
+    assert "openvino" in out.lower() or "model_server" in out
+    assert "text_generation" in out  # command OVMS propagée en args
+    assert "/models" in out  # volume writable pour le download du modèle (sinon Permission denied)
```
## Preuve déterministe
```
..                                                                       [100%]
............s........................................................... [ 99%]
.....                                                                    [100%]
All checks passed!
deploy-specs.json JSON valide
```
