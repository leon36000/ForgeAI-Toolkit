# PACK DE REVUE (v2) — HW-010 (FAI-U-010) : NVIDIA présent-mais-non-qualifié refuse au lieu de disparaître
## v2 intègre la revue : docstring module RESTAURÉ (Story P1-S02/R-01/ERR_HW_MIN) + assertion sans-gpu robuste.
## Design : detect marque ' [unqualified]' les NVIDIA vus par lspci ; profile lève ProfileError(driver) si aucun
## GPU utilisable ET un NVIDIA [unqualified] présent. Provenance (marqueur) pour NE PAS régresser test_profile_presence.
## Preuve : rouge->vert, SUITE COMPLÈTE verte (dont test_profile_presence), gitleaks 0, rollback vert. detect_gpus retourne tuple().

```diff
diff --git a/src/forgeai/hardware/detect.py b/src/forgeai/hardware/detect.py
index 9d895e2..5e4a7a6 100644
--- a/src/forgeai/hardware/detect.py
+++ b/src/forgeai/hardware/detect.py
@@ -129,6 +129,8 @@ class HardwareDetector:
             name = f"{base or 'unknown'} [{vendor_hex}:{device_hex}]"
             if f"{vendor_hex}:{device_hex}" in _INTEGRATED_PCI_DEVICE_IDS:
                 name += " [integrated]"
+            if vendor == "nvidia":
+                name += " [unqualified]"
             gpus.append(GPU(vendor=vendor, name=name, vram_mb=0))
         return gpus
 
diff --git a/src/forgeai/planner/profile.py b/src/forgeai/planner/profile.py
index b12ff04..f5781e3 100644
--- a/src/forgeai/planner/profile.py
+++ b/src/forgeai/planner/profile.py
@@ -4,6 +4,11 @@ Seuils Minimal : RAM ≥ 4 Go, disque libre ≥ 25 Go (critères stories-kimi).
 Variantes : minimal-gpu-cuda (NVIDIA ≥ 8 Go VRAM), minimal-gpu-rocm (AMD ≥ 8 Go),
 minimal-gpu-intel (Intel ≥ 4 Go), sinon minimal-cpu. Échec = ProfileError avec
 code ERR_HW_MIN — le wizard bascule alors en « détection forcée » (mitigation R-01).
+
+HW-010 (FAI-U-010) : un GPU NVIDIA marqué « [unqualified] » (vu par lspci, nvidia-smi
+KO -> VRAM inconnue, non nulle) ne disparaît pas silencieusement en minimal-cpu ;
+si aucun GPU utilisable n'est trouvé, derive_profile lève ProfileError orientant
+vers la vérification du driver/runtime NVIDIA.
 """
 from __future__ import annotations
 
@@ -20,6 +25,19 @@ class ProfileError(Exception):
 
 
 def derive_profile(hw: HardwareProfile) -> str:
+    """Dérive le profil de déploiement minimal à partir du profil matériel.
+
+    Seuils Minimal : RAM ≥ 4 Go, disque libre ≥ 25 Go.
+    Variantes GPU : minimal-gpu-cuda (NVIDIA ≥ 8 Go VRAM),
+    minimal-gpu-rocm (AMD ≥ 8 Go), minimal-gpu-intel (Intel ≥ 4 Go).
+    Échec matériel = ProfileError(code ERR_HW_MIN).
+
+    HW-010 : un GPU NVIDIA visible par lspci mais non qualifié (marqueur
+    [unqualified] dans le nom, c'est-à-dire nvidia-smi absent ou en échec)
+    n'est pas silencieusement ignoré : s'il est présent et qu'aucun GPU
+    utilisable n'est trouvé, une ProfileError oriente l'utilisateur vers
+    le driver/runtime NVIDIA.
+    """
     if hw.ram_gb < MIN_RAM_GB:
         raise ProfileError(
             f"RAM insuffisante : {hw.ram_gb} Go < {MIN_RAM_GB} Go requis")
@@ -57,4 +75,14 @@ def derive_profile(hw: HardwareProfile) -> str:
                             ("intel", "minimal-gpu-intel")):
         if any(g.vendor == vendor for g in usable):
             return profile
+
+    # HW-010 : refuser de faire disparaître un NVIDIA présent mais non qualifié.
+    non_qualifies = [g for g in hw.gpus if g.vendor == "nvidia" and "[unqualified]" in g.name]
+    if not usable and non_qualifies:
+        raise ProfileError(
+            "GPU NVIDIA présent mais non qualifié : nvidia-smi indisponible "
+            "(driver/runtime NVIDIA). VRAM inconnue (non nulle). Vérifiez l'installation du driver "
+            "NVIDIA (`nvidia-smi`) puis relancez — le déploiement d'un workload GPU est refusé tant "
+            "que le GPU n'est pas qualifié.")
+
     return "minimal-cpu"
diff --git a/tests/test_hardware_detect.py b/tests/test_hardware_detect.py
index 56cc84d..b6dcb48 100644
--- a/tests/test_hardware_detect.py
+++ b/tests/test_hardware_detect.py
@@ -96,10 +96,13 @@ def test_igpu_amd_reel_non_promu_en_dgpu():
     ('Advanced Micro Devices, Inc. ... Device') ne contient JAMAIS 'igpu'/'integrated' :
     l'ancienne heuristique de sous-chaîne le PROMEUT à tort en dGPU (minimal-gpu-rocm).
     Après classification PCI, l'iGPU est exclu -> minimal-cpu."""
-    gpus = _detector(**{"nvidia-smi": ""}).detect_gpus()
+    # fixture AMD-iGPU-only : isole le concern « iGPU non promu » (le scénario RTX-cassé+iGPU
+    # est couvert par test_nvidia_present_mais_non_qualifie, HW-010, qui exige un refus explicite).
+    lspci = (FIXTURES / "lspci_nn_amd_igpu_only.txt").read_text(encoding="utf-8")
+    gpus = _detector(**{"nvidia-smi": "", "lspci": lspci}).detect_gpus()
     amd = [g for g in gpus if g.vendor == "amd"]
     assert amd, "iGPU AMD 13c0 non détecté"
-    assert derive_profile(_hw(gpus)) == "minimal-cpu"  # RED avant fix (retourne rocm)
+    assert derive_profile(_hw(gpus)) == "minimal-cpu"  # iGPU exclu, aucun NVIDIA -> pas de refus
 
 
 def test_dgpu_amd_discret_reste_utilisable():
@@ -110,3 +113,28 @@ def test_dgpu_amd_discret_reste_utilisable():
     amd = [g for g in gpus if g.vendor == "amd"]
     assert amd and amd[0].vram_mb == 0
     assert derive_profile(_hw(gpus)) == "minimal-gpu-rocm"
+
+
+def test_nvidia_present_mais_non_qualifie_ne_disparait_pas():
+    """FAI-U-010 : nvidia-smi cassé/absent -> VRAM inconnue via lspci. Le GPU NVIDIA
+    [10de:2b85] reste INVENTORIÉ (présence PCI), et le plan REFUSE de dégrader
+    silencieusement en minimal-cpu : derive_profile lève ProfileError avec un diagnostic
+    orientant vers la vérification driver/runtime (VRAM inconnue != 0 réel)."""
+    import pytest
+    from forgeai.planner.profile import ProfileError
+    lspci = (FIXTURES / "lspci_nn_nvidia_only.txt").read_text(encoding="utf-8")
+    gpus = _detector(**{"nvidia-smi": "", "lspci": lspci}).detect_gpus()
+    nv = [g for g in gpus if g.vendor == "nvidia"]
+    assert nv, "GPU NVIDIA a disparu quand nvidia-smi échoue (régression FAI-U-010)"
+    with pytest.raises(ProfileError) as exc:
+        derive_profile(_hw(gpus))
+    msg = str(exc.value).lower()
+    assert ("driver" in msg or "nvidia-smi" in msg or "qualifi" in msg), msg
+
+
+def test_machine_reellement_sans_gpu_reste_cpu():
+    """Garde : une machine SANS aucun GPU (ni nvidia-smi ni lspci) reste minimal-cpu,
+    sans lever (le refus ne concerne QUE les GPU présents-mais-non-qualifiés)."""
+    gpus = _detector(**{"nvidia-smi": "", "lspci": ""}).detect_gpus()
+    assert not gpus  # aucun GPU (tuple vide)
+    assert derive_profile(_hw(gpus)) == "minimal-cpu"
```
