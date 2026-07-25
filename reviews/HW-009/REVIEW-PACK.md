# PACK DE REVUE — HW-009 (FAI-U-009) — classification iGPU par identifiant PCI
## Contexte : profile._is_igpu classait par sous-chaine de nom ; lspci tronque -> iGPU AMD [1002:13c0] promu a tort en dGPU (minimal-gpu-rocm au lieu de minimal-cpu).
## Contrainte : GPU dataclass (core/models.py) HORS scope -> classification encodee dans le nom via marqueur canonique [integrated] emis par detect a partir de l'id PCI.

## DIFF INTÉGRAL vs origin/main
```diff
diff --git a/src/forgeai/hardware/detect.py b/src/forgeai/hardware/detect.py
index e757cc9..9d895e2 100644
--- a/src/forgeai/hardware/detect.py
+++ b/src/forgeai/hardware/detect.py
@@ -1,14 +1,8 @@
-"""Story P1-S01 — détection hardware multi-vendor (codeur : fable).
-
-Sources user-space, sans privilèges : lscpu -J (CPU), /proc/meminfo (RAM),
-df (disque), nvidia-smi (GPU NVIDIA), lspci -nn (GPU AMD/Intel en repli).
-Chaque source défaillante dégrade proprement — jamais d'exception fatale (CA :
-« échec d'une source n'empêche pas le reste »).
-"""
 from __future__ import annotations
 
 import json
 import platform
+import re
 from pathlib import Path
 
 from forgeai.core.models import GPU, Disk, HardwareProfile
@@ -16,6 +10,23 @@ from forgeai.core.runner import CommandRunner
 
 _PCI_VENDORS = {"1002": "amd", "8086": "intel", "10de": "nvidia"}
 
+# iGPU/APU connus, par identifiant PCI « vendor:device » en minuscules. ROCm ne
+# cible pas ces puces intégrées : elles ne doivent jamais être promues en dGPU.
+# Liste extensible — ajouter ici tout nouvel iGPU rencontré sur le terrain.
+_INTEGRATED_PCI_DEVICE_IDS = frozenset({
+    "1002:13c0",  # Raphael (APU Ryzen 7000)
+    "1002:164e",  # Renoir
+    "1002:1636",
+    "1002:15bf",
+    "1002:15c8",
+    "1002:1681",
+    "1002:164c",
+    "1002:1900",
+    "1002:13fe",
+    "1002:15d8",
+    "1002:15dd",  # AMD APU/iGPU connus (extensible)
+})
+
 
 class HardwareDetector:
     def __init__(self, runner: CommandRunner, meminfo_path: str = "/proc/meminfo") -> None:
@@ -105,11 +116,20 @@ class HardwareDetector:
         for line in out.splitlines():
             if "VGA compatible controller" not in line and "3D controller" not in line:
                 continue
-            for pci_id, vendor in _PCI_VENDORS.items():
-                if f"[{pci_id}:" in line:
-                    name = line.split("controller", 1)[-1].split(":", 1)[-1].split("[")[0].strip()
-                    gpus.append(GPU(vendor=vendor, name=name or "unknown", vram_mb=0))
-                    break
+            ids = re.findall(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", line)
+            if not ids:
+                continue
+            vendor_hex, device_hex = ids[-1]
+            vendor_hex = vendor_hex.lower()
+            device_hex = device_hex.lower()
+            vendor = _PCI_VENDORS.get(vendor_hex)
+            if vendor is None:
+                continue
+            base = line.split("controller", 1)[-1].split(":", 1)[-1].split("[")[0].strip()
+            name = f"{base or 'unknown'} [{vendor_hex}:{device_hex}]"
+            if f"{vendor_hex}:{device_hex}" in _INTEGRATED_PCI_DEVICE_IDS:
+                name += " [integrated]"
+            gpus.append(GPU(vendor=vendor, name=name, vram_mb=0))
         return gpus
 
     def full_report(self) -> HardwareProfile:
diff --git a/src/forgeai/planner/profile.py b/src/forgeai/planner/profile.py
index ef14352..b12ff04 100644
--- a/src/forgeai/planner/profile.py
+++ b/src/forgeai/planner/profile.py
@@ -32,15 +32,21 @@ def derive_profile(hw: HardwareProfile) -> str:
     # PRÉSENCE du vendor. NVIDIA reste strict (nvidia-smi donne toujours la VRAM réelle,
     # donc 0 = pas de GPU utilisable). Un iGPU AMD faible (VRAM 0) est ignoré : ROCm ne
     # cible pas les APU intégrés — seul un dGPU AMD à VRAM inconnue déclenche le profil.
-    def _is_igpu(name: str) -> bool:
+    # La distinction iGPU/dGPU repose sur le marqueur canonique « [integrated] » émis par
+    # detect.py à partir de l'identifiant PCI « vendor:device » (HW-009).
+    def _est_integre(name: str) -> bool:
         low = name.lower()
+        # source d'autorité : marqueur canonique émis par detect.py à partir de l'identifiant PCI
+        if "[integrated]" in low:
+            return True
+        # repli défensif (noms explicites éventuels)
         return "igpu" in low or "integrated" in low
 
     def _usable(gpu) -> bool:
         if gpu.vendor == "nvidia":
             return gpu.vram_mb >= 8192
         if gpu.vendor == "amd":
-            return gpu.vram_mb >= 8192 or (gpu.vram_mb == 0 and not _is_igpu(gpu.name))
+            return gpu.vram_mb >= 8192 or (gpu.vram_mb == 0 and not _est_integre(gpu.name))
         if gpu.vendor == "intel":
             return gpu.vram_mb >= 4096 or gpu.vram_mb == 0
         return False
diff --git a/tests/fixtures/hardware/lspci_nn_amd_dgpu.txt b/tests/fixtures/hardware/lspci_nn_amd_dgpu.txt
new file mode 100644
index 0000000..fa423f1
--- /dev/null
+++ b/tests/fixtures/hardware/lspci_nn_amd_dgpu.txt
@@ -0,0 +1 @@
+03:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 31 [Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M] [1002:744c] (rev cc)
diff --git a/tests/test_hardware_detect.py b/tests/test_hardware_detect.py
index ab3fae2..56cc84d 100644
--- a/tests/test_hardware_detect.py
+++ b/tests/test_hardware_detect.py
@@ -78,3 +78,35 @@ def test_full_report_serialise_en_json():
     profile = _detector().full_report()
     data = json.loads(profile.to_json())
     assert {"cpu_model", "cpu_cores", "ram_gb", "gpus", "disks", "os_name"} <= set(data)
+
+
+# --- HW-009 (FAI-U-009) : classification iGPU par PCI, pas par sous-chaîne de nom ---
+from forgeai.core.models import Disk, HardwareProfile  # noqa: E402
+from forgeai.planner.profile import derive_profile  # noqa: E402
+
+
+def _hw(gpus):
+    return HardwareProfile(cpu_model="x", cpu_cores=8, cpu_arch="x86_64", ram_gb=46.0,
+                           os_name="Linux", gpus=tuple(gpus),
+                           disks=(Disk(path="/", total_gb=500.0, free_gb=400.0),))
+
+
+def test_igpu_amd_reel_non_promu_en_dgpu():
+    """lspci réel : AMD [1002:13c0] = iGPU Raphael, VRAM inconnue. Le nom produit par lspci
+    ('Advanced Micro Devices, Inc. ... Device') ne contient JAMAIS 'igpu'/'integrated' :
+    l'ancienne heuristique de sous-chaîne le PROMEUT à tort en dGPU (minimal-gpu-rocm).
+    Après classification PCI, l'iGPU est exclu -> minimal-cpu."""
+    gpus = _detector(**{"nvidia-smi": ""}).detect_gpus()
+    amd = [g for g in gpus if g.vendor == "amd"]
+    assert amd, "iGPU AMD 13c0 non détecté"
+    assert derive_profile(_hw(gpus)) == "minimal-cpu"  # RED avant fix (retourne rocm)
+
+
+def test_dgpu_amd_discret_reste_utilisable():
+    """Garde de précision : un dGPU AMD discret (Navi 31 [1002:744c], VRAM inconnue via lspci)
+    NE doit PAS être exclu par erreur -> minimal-gpu-rocm reste."""
+    lspci = (FIXTURES / "lspci_nn_amd_dgpu.txt").read_text(encoding="utf-8")
+    gpus = _detector(**{"nvidia-smi": "", "lspci": lspci}).detect_gpus()
+    amd = [g for g in gpus if g.vendor == "amd"]
+    assert amd and amd[0].vram_mb == 0
+    assert derive_profile(_hw(gpus)) == "minimal-gpu-rocm"
```
## ROUGE (avant)
```
E       AssertionError: assert 'minimal-gpu-rocm' == 'minimal-cpu'
E         
E         - minimal-cpu
E         + minimal-gpu-rocm

tests/test_hardware_detect.py:102: AssertionError
=========================== short test summary info ============================
FAILED tests/test_hardware_detect.py::test_igpu_amd_reel_non_promu_en_dgpu - ...
```
## VERTE (après) + rollback baseline vert + suite complète verte + gitleaks 0
```
.................                                                        [100%]
```
