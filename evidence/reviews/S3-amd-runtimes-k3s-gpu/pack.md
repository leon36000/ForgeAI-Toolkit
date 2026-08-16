# Story S3 — renderer k3s : passthrough GPU PAR VENDOR + command→args

## Problème
Le renderer k3s ne gérait le GPU que pour NVIDIA (ressource `nvidia.com/gpu`), modèle device-plugin
qui échoue sur un nœud NU (sans plugin AMD installé, ex. pc4 réinitialisé). Il n'émettait pas non plus
`command`. Impossible de déployer un runtime AMD serving via la toolkit sur k3s.

## Changements (src/forgeai/renderers/k3s.py)
- GPU PAR VENDOR (parité avec le renderer compose de S2) : nvidia -> `nvidia.com/gpu: "1"` ;
  amd -> hostPath `/dev/kfd` + `/dev/dri` + `securityContext.privileged` (marche sur nœud nu) ;
  intel -> `/dev/dri` ; gpu sans vendor => nvidia (rétrocompat).
- FUSION : montages device GPU + volume data = UN seul bloc `volumeMounts` et UN `volumes`
  (sinon clé YAML dupliquée = manifeste invalide).
- `command` -> `args:` k8s (parité compose), chaque arg passé par `_safe` (garde injection).
- Garde-fous d'injection existants (`_safe`, allowlist service_type) PRÉSERVÉS.

## Critères d'acceptation (tous testés — tests/test_k3s_gpu_vendor.py)
1. nvidia => nvidia.com/gpu, pas de /dev/kfd. amd => /dev/kfd+/dev/dri+privileged, pas nvidia.
   intel => /dev/dri seul. gpu sans vendor => nvidia. sans gpu => aucun device/privileged.
2. amd + volume data => UN volumeMounts + UN volumes (les deux montages présents).
3. command => args k8s avec chaque argument.

## Périmètre / codeur
S3 = renderer k3s (le mécanisme). Les specs déployables AMD nommées (deploy-specs rocm/vllm etc.) +
le wizard bout-en-bout = S3b/S4. Codeur : ORCHESTRATEUR (dur). Nœud nu -> hostPath privileged ;
quand l'AMD GPU Operator est installé (prepare.py), une story future pourra basculer sur amd.com/gpu.

## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py

## Correctif suite revue (tour 2)
Objection Qwen (SyntaxError sur `"1\""""`) : le code COMPILAIT et TOURNAIT déjà (py_compile OK,
tests verts, déploiement pc4 réel) — affirmation SyntaxError factuellement fausse. MAIS construct
illisible (mal lu par 2 relecteurs) → réécrit en concat de lignes. + finding : rendre TOUS les
volumes (boucle). Chemin AMD INCHANGÉ → preuve e2e pc4 conservée.

## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index ef91309..44e9aeb 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -57,29 +57,68 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
                 node_port: int | None = None, service_type: str = "NodePort") -> str:
     name = _safe(svc.name, "name")
     image = _safe(svc.image, "image")
-    gpu_limits = """
-          resources:
-            limits:
-              nvidia.com/gpu: "1"ifgpu""".replace("ifgpu", "") if svc.gpu else ""
+    # GPU par vendor (S3) : nvidia -> ressource device-plugin ; amd/intel -> passthrough hostPath
+    # des devices noyau + privileged (marche sur un nœud NU, sans device-plugin installé).
+    vendor = (svc.gpu_vendor or "nvidia") if svc.gpu else None
+    resources_block, security_block, gpu_mounts, gpu_vols = "", "", [], []
+    if vendor == "nvidia":
+        resources_block = (
+            "\n          resources:"
+            "\n            limits:"
+            '\n              nvidia.com/gpu: "1"'
+        )
+    elif vendor == "amd":
+        security_block = """
+          securityContext:
+            privileged: true"""
+        gpu_mounts = [("dev-kfd", "/dev/kfd"), ("dev-dri", "/dev/dri")]
+        gpu_vols = list(gpu_mounts)
+    elif vendor == "intel":
+        security_block = """
+          securityContext:
+            privileged: true"""
+        gpu_mounts = [("dev-dri", "/dev/dri")]
+        gpu_vols = list(gpu_mounts)
     node_selector = ""
     if effective_node and effective_node != "auto":
         node_selector = f"""
       nodeSelector:
         kubernetes.io/hostname: {_safe(effective_node, 'node')}"""
-    volume_mount, volume_def = "", ""
-    if svc.volumes:
-        parts = svc.volumes[0].split(":", 1)
+    # Fusion volume data + devices GPU en UN bloc volumeMounts et UN bloc volumes (sinon clé YAML
+    # dupliquée). mounts: (claim, mountPath) ; vols: (claim, hostPath|None) — None => emptyDir data.
+    mounts, vols = [], []
+    for volume in svc.volumes:  # TOUS les volumes data (plus seulement le premier — finding revue)
+        parts = volume.split(":", 1)
         if len(parts) != 2:  # format attendu 'nom:chemin' -> erreur claire (pas d'IndexError)
-            raise ValueError(f"volume mal formé (attendu 'nom:chemin') : {svc.volumes[0]!r}")
+            raise ValueError(f"volume mal formé (attendu 'nom:chemin') : {volume!r}")
         claim, mount_path = _safe(parts[0], "volume-claim"), _safe(parts[1], "volume-path")
-        volume_mount = f"""
-          volumeMounts:
-            - name: {claim}
-              mountPath: {mount_path}"""
-        volume_def = f"""
-      volumes:
-        - name: {claim}
-          emptyDir: {{}}"""
+        mounts.append((claim, mount_path))
+        vols.append((claim, None))
+    for claim, path in gpu_mounts:
+        mounts.append((claim, path))
+    for claim, path in gpu_vols:
+        vols.append((claim, path))
+    volume_mount = ""
+    if mounts:
+        items = "".join(
+            f"\n            - name: {c}\n              mountPath: {m}" for c, m in mounts)
+        volume_mount = f"\n          volumeMounts:{items}"
+    volume_def = ""
+    if vols:
+        items = ""
+        for claim, hostpath in vols:
+            if hostpath is None:
+                items += f"\n        - name: {claim}\n          emptyDir: {{}}"
+            else:
+                items += (f"\n        - name: {claim}"
+                          f"\n          hostPath:\n            path: {hostpath}")
+        volume_def = f"\n      volumes:{items}"
+    # command → args k8s (parité avec le renderer compose) ; chaque arg passé par _safe (injection).
+    command_block = ""
+    if svc.command:
+        items = "".join(f"\n            - \"{_safe(str(a), 'arg')}\"" for a in svc.command)
+        command_block = f"\n          args:{items}"
+    container_extra = f"{command_block}{resources_block}{security_block}{volume_mount}{volume_def}"
     return f"""---
 apiVersion: apps/v1
 kind: Deployment
@@ -98,7 +137,7 @@ spec:
         - name: {name}
           image: {image}
           ports:
-            - containerPort: {svc.container_port}{gpu_limits}{volume_mount}{volume_def}
+            - containerPort: {svc.container_port}{container_extra}
 ---
 apiVersion: v1
 kind: Service
diff --git a/tests/test_k3s_gpu_vendor.py b/tests/test_k3s_gpu_vendor.py
new file mode 100644
index 0000000..05e733e
--- /dev/null
+++ b/tests/test_k3s_gpu_vendor.py
@@ -0,0 +1,85 @@
+"""Story S3 — renderer k3s : passthrough GPU PAR VENDOR (parallèle du renderer compose de S2).
+
+AMD  = hostPath /dev/kfd + /dev/dri + privileged (marche sur un nœud NU, sans device-plugin AMD
+       installé — c'est ce qui a servi le dual-GPU RDNA4 sur pc4).
+Intel = hostPath /dev/dri + privileged.
+NVIDIA = ressource nvidia.com/gpu (modèle device-plugin, inchangé). gpu sans vendor => nvidia.
+Prouve la FUSION propre : montages device GPU + volume data = UN seul bloc volumeMounts / volumes
+(sinon YAML invalide par clé dupliquée).
+"""
+import sys
+from pathlib import Path
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
+from forgeai.renderers.k3s import render_k3s
+
+
+def _plan(svc):
+    return DeploymentPlan(plan_id="p1-test", profile="minimal-gpu-rocm", target=RenderTarget.K3S,
+                          services=(svc,), model="m", embed_model="e")
+
+
+def _gpu(vendor, volumes=()):
+    return ServiceSpec(name="engine", image="img:latest", host_port=8000, container_port=8000,
+                       gpu=True, gpu_vendor=vendor, volumes=volumes)
+
+
+def test_k3s_nvidia_garde_resource():
+    out = render_k3s(_plan(_gpu("nvidia")))
+    assert 'nvidia.com/gpu: "1"' in out
+    assert "/dev/kfd" not in out
+
+
+def test_k3s_amd_passthrough_kfd_dri_privileged():
+    out = render_k3s(_plan(_gpu("amd")))
+    assert "/dev/kfd" in out and "/dev/dri" in out
+    assert "privileged: true" in out
+    assert "nvidia.com/gpu" not in out
+
+
+def test_k3s_intel_passthrough_dri():
+    out = render_k3s(_plan(_gpu("intel")))
+    assert "/dev/dri" in out
+    assert "/dev/kfd" not in out and "nvidia.com/gpu" not in out
+
+
+def test_k3s_amd_avec_volume_data_fusionne_un_seul_bloc():
+    # piège YAML : montages device + volume data DOIVENT fusionner en UN volumeMounts + UN volumes
+    out = render_k3s(_plan(_gpu("amd", volumes=("data:/root/.cache",))))
+    assert out.count("volumeMounts:") == 1, "un seul bloc volumeMounts (sinon YAML invalide)"
+    assert out.count("\n      volumes:") == 1, "un seul bloc volumes (sinon YAML invalide)"
+    assert "/root/.cache" in out and "/dev/kfd" in out and "/dev/dri" in out
+    assert "name: data" in out  # le volume data reste présent
+
+
+def test_k3s_sans_gpu_aucun_device_ni_privileged():
+    out = render_k3s(_plan(
+        ServiceSpec(name="x", image="i", host_port=1, container_port=1, gpu=False)))
+    assert "/dev/kfd" not in out and "privileged" not in out and "nvidia.com/gpu" not in out
+
+
+def test_k3s_gpu_sans_vendor_reste_nvidia():
+    out = render_k3s(_plan(
+        ServiceSpec(name="x", image="i", host_port=1, container_port=1, gpu=True)))
+    assert 'nvidia.com/gpu: "1"' in out
+
+
+def test_k3s_tous_les_volumes_rendus():
+    # finding revue : TOUS les volumes data doivent être rendus, pas seulement le premier.
+    svc = ServiceSpec(name="e", image="i", host_port=1, container_port=1,
+                      volumes=("data:/a", "cache:/b"))
+    out = render_k3s(_plan(svc))
+    assert "/a" in out and "/b" in out
+    assert "name: data" in out and "name: cache" in out
+    assert out.count("volumeMounts:") == 1 and out.count("\n      volumes:") == 1
+
+
+def test_k3s_command_rendu_en_args():
+    # parité compose : svc.command doit apparaître comme `args:` k8s (serving llama.cpp etc.)
+    svc = ServiceSpec(name="e", image="i", host_port=1, container_port=1,
+                      command=("--model", "/m.gguf", "--tensor-split", "32,16"))
+    out = render_k3s(_plan(svc))
+    assert "args:" in out
+    assert '- "--model"' in out and '- "/m.gguf"' in out and '- "32,16"' in out
```
## Preuve déterministe
```
.................                                                        [100%]
..........................................................s............. [ 91%]
...................................................                      [100%]
All checks passed!
```
## Preuve e2e RÉELLE sur pc4 (dual RDNA4) VIA la toolkit (render_k3s -> apply -> devices)
```
Available devices:
  Vulkan0: AMD Radeon AI PRO R9700 (RADV GFX1201) (32624 MiB, 32538 MiB free)
  Vulkan1: AMD Radeon RX 9070 XT (RADV GFX1201) (16304 MiB, 16246 MiB free)
  Vulkan2: AMD Ryzen 9 9950X3D2 16-Core Processor (RADV RAPHAEL_MENDOCINO) (23616 MiB, 23587 MiB free)
```
