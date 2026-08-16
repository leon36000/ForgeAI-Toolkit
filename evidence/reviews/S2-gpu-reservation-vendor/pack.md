# Story S2 — profil GPU vendor-aware + réservation GPU PAR VENDOR

## Problème corrigé
Sur main : (1) derive_profile exigeait AMD≥8Go / Intel≥4Go de VRAM, mais lspci renvoie
vram_mb=0 pour les GPU AMD/Intel → un nœud AMD réel retombait TOUJOURS sur minimal-cpu ;
(2) assemble ne posait gpu=True que si profile==minimal-gpu-cuda (NVIDIA) ; (3) compose
rendait une réservation nvidia hardcodée. Résultat : un GPU AMD/Intel détecté servait en CPU muet.

## Changements
- profile.py : presence-based. dGPU AMD/Intel à VRAM inconnue (0) → profil vendor (rocm/intel).
  NVIDIA reste strict (nvidia-smi donne la VRAM réelle). iGPU AMD faible (nom 'iGPU'/'integrated')
  ignoré — ROCm ne cible pas les APU (frontière test_igpu_amd_sans_vram_ignore préservée).
- core/models.py : ServiceSpec.gpu_vendor (nvidia|amd|intel|None).
- assemble.py : _profile_vendor(profil) ; gpu=True pour tout profil GPU ; propage gpu_vendor ;
  bricks châssis honorent spec.get('gpu').
- renderers/compose.py : réservation PAR VENDOR — nvidia=deploy.resources(driver nvidia),
  amd=devices /dev/kfd + /dev/dri (ROCm), intel=devices /dev/dri. gpu sans vendor => nvidia (rétrocompat).

## Critères d'acceptation (tous testés)
1. AMD/Intel dGPU VRAM=0 → rocm/intel ; NVIDIA VRAM=0 → cpu ; iGPU AMD VRAM=0 → cpu ; priorité nvidia>amd>intel.
2. render nvidia => 'driver: nvidia'+'capabilities: [gpu]' ; amd => '/dev/kfd'+'/dev/dri' sans nvidia ; intel => '/dev/dri' seul.
3. assemble profil rocm => service gpu=True, gpu_vendor='amd', rendu contient /dev/kfd. cpu => gpu=False.
4. Non-régression : gpu sans vendor => nvidia ; sans gpu => aucune réservation ; suite complète verte.

## Frontière S2 / codeur
S2 = profil + mécanisme de réservation. Les SPECS déployables AMD réelles (rocm/vllm, ollama:rocm,
llama.cpp rocm/vulkan avec ces montages) = S3, prouvables e2e sur les nœuds AMD de Nathan.
Codeur : ORCHESTRATEUR (tier 'dur', changement 4 fichiers précis interdépendants).

## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/core/models.py b/src/forgeai/core/models.py
index 31f53a0..dc0fc1a 100644
--- a/src/forgeai/core/models.py
+++ b/src/forgeai/core/models.py
@@ -74,6 +74,7 @@ class ServiceSpec:
     env: dict[str, str] = field(default_factory=dict)
     healthcheck_url: Optional[str] = None
     gpu: bool = False
+    gpu_vendor: Optional[str] = None  # "nvidia"|"amd"|"intel" — réservation GPU au rendu
     depends: tuple[str, ...] = ()
     command: tuple[str, ...] = ()  # arguments passés à l'entrypoint du conteneur (ex. litellm --config …)
     node: Optional[str] = None  # nœud cible de CE service (hostname K3s) ; None = suit le nœud global du plan ou le scheduler
diff --git a/src/forgeai/planner/assemble.py b/src/forgeai/planner/assemble.py
index 1211682..ba38602 100644
--- a/src/forgeai/planner/assemble.py
+++ b/src/forgeai/planner/assemble.py
@@ -19,6 +19,19 @@ from forgeai.stacks import deploy_ids
 PREFERRED_PORT_OFFSET = 10000  # 11434 → 21434 : évite les stacks existantes
 CHASSIS_PORT_START = 8100
 
+# Profils GPU → vendor pour la réservation (S2). cpu/inconnu → pas de vendor.
+_GPU_PROFILES = {"minimal-gpu-cuda", "minimal-gpu-rocm", "minimal-gpu-intel"}
+_PROFILE_VENDOR = {
+    "minimal-gpu-cuda": "nvidia",
+    "minimal-gpu-rocm": "amd",
+    "minimal-gpu-intel": "intel",
+}
+
+
+def _profile_vendor(profile: str) -> str | None:
+    """Vendor GPU d'un profil de déploiement (None hors profil GPU)."""
+    return _PROFILE_VENDOR.get(profile)
+
 
 def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
     with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
@@ -72,6 +85,7 @@ def assemble_plan(
     services = []
     for svc in minimal_stack(deploy_overlay):
         host_port = find_free_port(svc["container_port"] + PREFERRED_PORT_OFFSET, is_free)
+        svc_gpu = bool(svc.get("gpu_capable")) and profile in _GPU_PROFILES
         services.append(ServiceSpec(
             name=svc["name"],
             image=svc["image"],
@@ -82,7 +96,8 @@ def assemble_plan(
                 f"http://127.0.0.1:{host_port}{svc['healthcheck_path']}"
                 if svc.get("healthcheck_path") else None
             ),
-            gpu=bool(svc.get("gpu_capable")) and profile == "minimal-gpu-cuda",
+            gpu=svc_gpu,
+            gpu_vendor=_profile_vendor(profile) if svc_gpu else None,
         ))
 
     if stack is not None or extra_bricks:
@@ -112,6 +127,7 @@ def assemble_plan(
             # On ne conserve que les dépendances réellement présentes dans le
             # plan final (indépendant de l'ordre de traitement des briques).
             depends = tuple(d for d in spec.get("depends", []) if d in planned_names)
+            brick_gpu = bool(spec.get("gpu", False))
             services.append(ServiceSpec(
                 name=brick_id,
                 image=spec["image"],
@@ -122,7 +138,8 @@ def assemble_plan(
                 healthcheck_url=healthcheck_url,
                 depends=depends,
                 command=tuple(spec.get("command", [])),
-                gpu=False,
+                gpu=brick_gpu,
+                gpu_vendor=_profile_vendor(profile) if brick_gpu else None,
             ))
             existing_names.add(brick_id)
 
diff --git a/src/forgeai/planner/profile.py b/src/forgeai/planner/profile.py
index 59cc688..ef14352 100644
--- a/src/forgeai/planner/profile.py
+++ b/src/forgeai/planner/profile.py
@@ -28,13 +28,27 @@ def derive_profile(hw: HardwareProfile) -> str:
         raise ProfileError(
             f"Disque libre insuffisant : {free} Go < {MIN_DISK_FREE_GB} Go requis")
 
-    for gpu in hw.gpus:
-        if gpu.vendor == "nvidia" and gpu.vram_mb >= 8192:
-            return "minimal-gpu-cuda"
-    for gpu in hw.gpus:
-        if gpu.vendor == "amd" and gpu.vram_mb >= 8192:
-            return "minimal-gpu-rocm"
-    for gpu in hw.gpus:
-        if gpu.vendor == "intel" and gpu.vram_mb >= 4096:
-            return "minimal-gpu-intel"
+    # VRAM inconnue (vram_mb == 0, ex. dGPU AMD/Intel vus par lspci) : on se fie à la
+    # PRÉSENCE du vendor. NVIDIA reste strict (nvidia-smi donne toujours la VRAM réelle,
+    # donc 0 = pas de GPU utilisable). Un iGPU AMD faible (VRAM 0) est ignoré : ROCm ne
+    # cible pas les APU intégrés — seul un dGPU AMD à VRAM inconnue déclenche le profil.
+    def _is_igpu(name: str) -> bool:
+        low = name.lower()
+        return "igpu" in low or "integrated" in low
+
+    def _usable(gpu) -> bool:
+        if gpu.vendor == "nvidia":
+            return gpu.vram_mb >= 8192
+        if gpu.vendor == "amd":
+            return gpu.vram_mb >= 8192 or (gpu.vram_mb == 0 and not _is_igpu(gpu.name))
+        if gpu.vendor == "intel":
+            return gpu.vram_mb >= 4096 or gpu.vram_mb == 0
+        return False
+
+    usable = [g for g in hw.gpus if _usable(g)]
+    for vendor, profile in (("nvidia", "minimal-gpu-cuda"),
+                            ("amd", "minimal-gpu-rocm"),
+                            ("intel", "minimal-gpu-intel")):
+        if any(g.vendor == vendor for g in usable):
+            return profile
     return "minimal-cpu"
diff --git a/src/forgeai/renderers/compose.py b/src/forgeai/renderers/compose.py
index 3def5d5..80490fb 100644
--- a/src/forgeai/renderers/compose.py
+++ b/src/forgeai/renderers/compose.py
@@ -53,15 +53,22 @@ def render_compose(plan: DeploymentPlan, project: str = "forgeai-minimal") -> st
                 if not source.startswith((".", "/")):
                     volumes.add(source)
         if svc.gpu:
-            lines += [
-                "    deploy:",
-                "      resources:",
-                "        reservations:",
-                "          devices:",
-                "            - driver: nvidia",
-                "              count: 1",
-                "              capabilities: [gpu]",
-            ]
+            vendor = svc.gpu_vendor or "nvidia"
+            if vendor == "amd":
+                # ROCm : accès direct aux devices noyau (pas de driver compose nvidia)
+                lines += ["    devices:", "      - /dev/kfd", "      - /dev/dri"]
+            elif vendor == "intel":
+                lines += ["    devices:", "      - /dev/dri"]
+            else:  # nvidia (défaut, rétrocompatible)
+                lines += [
+                    "    deploy:",
+                    "      resources:",
+                    "        reservations:",
+                    "          devices:",
+                    "            - driver: nvidia",
+                    "              count: 1",
+                    "              capabilities: [gpu]",
+                ]
     if volumes:
         lines.append("volumes:")
         for volume in sorted(volumes):
diff --git a/tests/test_gpu_reservation_vendor.py b/tests/test_gpu_reservation_vendor.py
new file mode 100644
index 0000000..2ee0b66
--- /dev/null
+++ b/tests/test_gpu_reservation_vendor.py
@@ -0,0 +1,86 @@
+"""Story S2 — réservation GPU PAR VENDOR au rendu compose (corrige le « CPU muet » AMD/Intel).
+
+NVIDIA  = deploy.resources.reservations (driver nvidia, capabilities [gpu]).
+AMD ROCm = passthrough devices /dev/kfd + /dev/dri.
+Intel    = passthrough device /dev/dri.
+Piloté par ServiceSpec.gpu_vendor, dérivé du profil (cuda→nvidia, rocm→amd, intel→intel).
+Rétrocompat : gpu=True sans vendor → réservation nvidia (comportement historique préservé).
+"""
+import json
+import sys
+from pathlib import Path
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
+from forgeai.planner.assemble import assemble_plan
+from forgeai.renderers.compose import render_compose
+
+
+def _plan(svc):
+    return DeploymentPlan(plan_id="p", profile="x", target=RenderTarget.COMPOSE,
+                          services=(svc,), model="m", embed_model="e")
+
+
+def _gpu_svc(vendor):
+    return ServiceSpec(name="engine", image="img:latest", host_port=8000,
+                       container_port=8000, gpu=True, gpu_vendor=vendor)
+
+
+def test_render_nvidia_reserve_driver_nvidia():
+    out = render_compose(_plan(_gpu_svc("nvidia")))
+    assert "driver: nvidia" in out and "capabilities: [gpu]" in out
+    assert "/dev/kfd" not in out
+
+
+def test_render_amd_reserve_kfd_et_dri():
+    out = render_compose(_plan(_gpu_svc("amd")))
+    assert "/dev/kfd" in out and "/dev/dri" in out
+    assert "driver: nvidia" not in out
+
+
+def test_render_intel_reserve_dri():
+    out = render_compose(_plan(_gpu_svc("intel")))
+    assert "/dev/dri" in out
+    assert "driver: nvidia" not in out and "/dev/kfd" not in out
+
+
+def test_render_gpu_sans_vendor_reste_nvidia_retrocompat():
+    out = render_compose(_plan(
+        ServiceSpec(name="e", image="i", host_port=1, container_port=1, gpu=True)))
+    assert "driver: nvidia" in out
+
+
+def test_render_sans_gpu_aucune_reservation():
+    out = render_compose(_plan(
+        ServiceSpec(name="e", image="i", host_port=1, container_port=1, gpu=False)))
+    assert "driver: nvidia" not in out and "/dev/kfd" not in out and "/dev/dri" not in out
+
+
+# --- assemblage : le profil vendor propage gpu=True + gpu_vendor -------------------
+def _overlay(tmp_path):
+    ov = tmp_path / "ov.json"
+    ov.write_text(json.dumps({"profile": "x", "engine_default": "ollama", "services": [
+        {"name": "ollama", "brick_id": "ollama", "image": "ollama/ollama:rocm",
+         "container_port": 11434, "healthcheck_path": "/api/tags", "gpu_capable": True}],
+        "models": {"llm": "qwen2.5:0.5b", "embed": "bge-m3"}}), encoding="utf-8")
+    return ov
+
+
+def test_assemble_profil_rocm_marque_gpu_amd(tmp_path):
+    plan = assemble_plan("minimal-gpu-rocm", _overlay(tmp_path))
+    ollama = next(s for s in plan.services if s.name == "ollama")
+    assert ollama.gpu is True and ollama.gpu_vendor == "amd"
+    assert "/dev/kfd" in render_compose(plan)
+
+
+def test_assemble_profil_cuda_marque_gpu_nvidia(tmp_path):
+    plan = assemble_plan("minimal-gpu-cuda", _overlay(tmp_path))
+    ollama = next(s for s in plan.services if s.name == "ollama")
+    assert ollama.gpu is True and ollama.gpu_vendor == "nvidia"
+
+
+def test_assemble_profil_cpu_pas_de_gpu(tmp_path):
+    plan = assemble_plan("minimal-cpu", _overlay(tmp_path))
+    ollama = next(s for s in plan.services if s.name == "ollama")
+    assert ollama.gpu is False
diff --git a/tests/test_profile_presence.py b/tests/test_profile_presence.py
new file mode 100644
index 0000000..867bba9
--- /dev/null
+++ b/tests/test_profile_presence.py
@@ -0,0 +1,54 @@
+"""Story S2 — profil GPU vendor-aware : un GPU AMD/Intel détecté SANS VRAM connue
+(lspci renvoie vram_mb=0) doit quand même donner le profil vendor, pas retomber sur CPU.
+NVIDIA reste strict (nvidia-smi donne toujours la VRAM réelle → 0 = pas de GPU utilisable).
+Corrige le gap : sur un nœud AMD réel, derive_profile retombait toujours sur minimal-cpu.
+"""
+import sys
+from pathlib import Path
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.core.models import GPU, Disk, HardwareProfile
+from forgeai.planner.profile import derive_profile
+
+
+def _hw(*gpus):
+    return HardwareProfile(
+        cpu_model="x", cpu_cores=8, cpu_arch="x86_64", ram_gb=32.0, os_name="ubuntu",
+        gpus=tuple(gpus), disks=(Disk(path="/", total_gb=500.0, free_gb=200.0),),
+    )
+
+
+def test_amd_vram_inconnue_donne_rocm():
+    assert derive_profile(_hw(GPU("amd", "AMD Radeon RX 7900 XTX", 0))) == "minimal-gpu-rocm"
+
+
+def test_intel_vram_inconnue_donne_intel():
+    assert derive_profile(_hw(GPU("intel", "Intel Arc A770", 0))) == "minimal-gpu-intel"
+
+
+def test_amd_avec_vram_reste_rocm():
+    assert derive_profile(_hw(GPU("amd", "AMD Instinct MI300X", 65536))) == "minimal-gpu-rocm"
+
+
+def test_nvidia_vram_zero_ne_fabrique_pas_de_gpu():
+    # nvidia-smi donne toujours la VRAM réelle : 0 = pas de VRAM utilisable → CPU.
+    assert derive_profile(_hw(GPU("nvidia", "carte", 0))) == "minimal-cpu"
+
+
+def test_priorite_nvidia_sur_amd():
+    hw = _hw(GPU("amd", "rx", 0), GPU("nvidia", "rtx", 16384))
+    assert derive_profile(hw) == "minimal-gpu-cuda"
+
+
+def test_priorite_amd_sur_intel():
+    assert derive_profile(_hw(GPU("intel", "arc", 0), GPU("amd", "rx", 0))) == "minimal-gpu-rocm"
+
+
+def test_amd_igpu_sans_vram_reste_cpu():
+    # frontière : un iGPU AMD faible (VRAM 0) ne déclenche PAS ROCm (seul un dGPU le fait)
+    assert derive_profile(_hw(GPU("amd", "Raphael iGPU", 0))) == "minimal-cpu"
+
+
+def test_aucun_gpu_reste_cpu():
+    assert derive_profile(_hw()) == "minimal-cpu"
```
## Preuve d’exécution
```
.......................                                                  [100%]
--- suite complète ---
..................................................s..................... [ 93%]
...........................................                              [100%]
All checks passed!
NO-STUB-SCAN : OK (3 fichiers scannés, zéro violation)
```
