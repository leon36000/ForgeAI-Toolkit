# Story S3b — brique moteur AMD Vulkan déployable (llama.cpp server-vulkan)

## Objet
Ajoute au catalogue déployable (deploy-specs.json) une brique moteur AMD nommée `llama-cpp-vulkan`,
consommée par le pipeline S2 (assemble : gpu:true -> gpu_vendor=amd sur profil rocm) + S3 (renderer
k3s : passthrough /dev/kfd+/dev/dri + command->args). C'est la 1re brique GPU AMD end-user.

## Choix (vocation universelle — cf. pc4 = banc d'essai, pas de hardcode)
- Image `ghcr.io/ggml-org/llama.cpp:server-vulkan` (Vulkan/RADV = chemin le plus fiable sur RDNA4,
  confirmé par recherche + serving réel). `gpu: true`.
- Auto-fetch du modèle par `-hf Qwen/Qwen2.5-0.5B-Instruct-GGUF:Q8_0` (repo HF PUBLIC — le renderer
  ne fait pas d'initContainer, la brique s'auto-fournit). Petit modèle par défaut (surchargeable).
- `-ngl 99` + AUCUN `--tensor-split` hardcodé : llama.cpp auto-répartit sur TOUS les GPU Vulkan
  présents (universel, marche sur 1 ou N GPU quelle que soit la VRAM).

## Critères (testés — tests/test_amd_vulkan_runtime.py)
1. Brique déployable : dans deploy-specs, image vulkan, gpu:true, command contient -hf, pas de tensor-split.
2. assemble('minimal-gpu-rocm', extra_bricks=('llama-cpp-vulkan',)) -> service gpu=True, gpu_vendor='amd' ;
   render_k3s -> manifeste contient /dev/kfd + /dev/dri + l'arg -hf.

## Preuve serving RÉELLE sur pc4 (dual RDNA4) VIA la toolkit
deploy-spec -> assemble_plan -> render_k3s(node=pc4-grs-b) -> kubectl apply :
```
RÉPONSE: Il semble que vous cherchez des informations sur la déclaration d'IA d'un nouveau service ou produit. Pourriez-vous préciser ce qui vous est attendu ? Je suis disponible pour des
usage: {'completion_tokens': 40, 'prompt_tokens': 42, 'total_tokens': 82, 'prompt_tokens_details': {'cached_tokens': 0}}
health_path /health => HTTP 200 (readiness confirmée)
```
## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/data/deploy-specs.json b/src/forgeai/data/deploy-specs.json
index 08b52ff..33c466b 100644
--- a/src/forgeai/data/deploy-specs.json
+++ b/src/forgeai/data/deploy-specs.json
@@ -123,5 +123,24 @@
     "depends": [
       "postgres"
     ]
+  },
+  "llama-cpp-vulkan": {
+    "image": "ghcr.io/ggml-org/llama.cpp:server-vulkan",
+    "container_port": 8080,
+    "health_path": "/health",
+    "gpu": true,
+    "volumes": [],
+    "env": {},
+    "command": [
+      "-hf",
+      "Qwen/Qwen2.5-0.5B-Instruct-GGUF:Q8_0",
+      "-ngl",
+      "99",
+      "--host",
+      "0.0.0.0",
+      "--port",
+      "8080"
+    ],
+    "depends": []
   }
 }
diff --git a/tests/test_amd_vulkan_runtime.py b/tests/test_amd_vulkan_runtime.py
new file mode 100644
index 0000000..4915f7e
--- /dev/null
+++ b/tests/test_amd_vulkan_runtime.py
@@ -0,0 +1,49 @@
+"""Story S3b — brique moteur AMD Vulkan déployable (llama.cpp server-vulkan).
+
+Auto-fetch du modèle via `-hf` (repo HF public), auto-split multi-GPU (AUCUN --tensor-split
+hardcodé = universel : llama.cpp répartit sur tous les GPU Vulkan présents). `gpu: true` => sur
+profil rocm, assemble (S2) pose gpu_vendor=amd et le renderer k3s (S3) ajoute le passthrough
+/dev/kfd+/dev/dri + la command en args. Serving réel prouvé sur pc4 (dual RDNA4).
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
+BRICK = "llama-cpp-vulkan"
+
+
+def test_brique_amd_vulkan_deployable():
+    specs = json.loads((files("forgeai.data") / "deploy-specs.json").read_text(encoding="utf-8"))
+    assert BRICK in specs, "la brique llama-cpp-vulkan doit être déployable (deploy-specs)"
+    s = specs[BRICK]
+    assert "vulkan" in s["image"], "image llama.cpp Vulkan"
+    assert s.get("gpu") is True, "brique GPU"
+    cmd = " ".join(str(c) for c in s.get("command", []))
+    assert "-hf" in cmd, "auto-fetch du modèle via -hf (pas d'initContainer requis)"
+    assert "--tensor-split" not in cmd, "pas de tensor-split hardcodé (universel, auto-split)"
+
+
+def _overlay(tmp_path):
+    ov = tmp_path / "ov.json"
+    ov.write_text(json.dumps({"profile": "x", "engine_default": "ollama", "services": [
+        {"name": "ollama", "brick_id": "ollama", "image": "ollama/ollama:latest",
+         "container_port": 11434, "healthcheck_path": "/api/tags"}],
+        "models": {"llm": "q", "embed": "b"}}), encoding="utf-8")
+    return ov
+
+
+def test_amd_vulkan_rendu_k3s_avec_passthrough(tmp_path):
+    # profil rocm => vendor amd ; le renderer S3 ajoute le passthrough + la command en args.
+    plan = assemble_plan("minimal-gpu-rocm", _overlay(tmp_path), extra_bricks=(BRICK,))
+    svc = next((s for s in plan.services if s.name == BRICK), None)
+    assert svc is not None, "la brique doit être au plan"
+    assert svc.gpu is True and svc.gpu_vendor == "amd"
+    out = render_k3s(plan)
+    assert "/dev/kfd" in out and "/dev/dri" in out  # passthrough AMD (S3)
+    assert "-hf" in out  # command propagée en args (S3)
```
## Preuve déterministe
```
..                                                                       [100%]
............................................................s........... [ 91%]
.....................................................                    [100%]
All checks passed!
deploy-specs.json JSON valide
```
