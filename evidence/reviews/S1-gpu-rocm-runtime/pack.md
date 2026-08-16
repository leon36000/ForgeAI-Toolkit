# Story S1 — Recommandation runtime GPU par vendor : ROCm débloqué + choix multi-runtime (défaut intelligent)

## Contexte / problème
Sur origin/main, `hardware/drivers.py` forçait AMD → Vulkan avec `rocm_allowed=False` (« ROCm non
proposé »), EN CONTRADICTION avec `network/prepare.py` qui installe pourtant l'AMD GPU Operator basé
ROCm. Résultat : l'utilisateur AMD n'avait PAS le choix ROCm que le produit prétend offrir.

## Décisions Nathan verrouillées (2026-07-20)
- AMD = ROCm + Vulkan AU CHOIX, débloqués ; défaut auto = ROCm sur Instinct/CDNA, Vulkan sur Radeon/RDNA.
- Défaut intelligent par vendor, TOUJOURS surchargeable (le défaut = premier runtime offert).

## Critères d'acceptation (tous testés)
1. AMD `rocm_allowed=True`, note sans « non proposé », `operator="amd-gpu-operator"`.
2. AMD offre {rocm, vulkan} ; défaut ROCm si modèle Instinct/CDNA/MI/gfx9 ; Vulkan si Radeon/RX/RDNA/gfx10/11 ; Vulkan si arch inconnue.
3. NVIDIA défaut cuda + offre vulkan (universel) ; rocm_allowed False.
4. Intel défaut openvino + offre vulkan ; operator intel-device-plugins ; rocm_allowed False.
5. Invariant : `runtime == runtimes[0]`, pas de doublon, non vide.
6. Non-régression : `plan_driver_op` inchangé (host apt reste vulkan — ROCm hôte hors périmètre S1) ; vendor inconnu lève DriverError ; detect_driver_state OK.

## Périmètre / frontière explicite
S1 = RECOMMANDATION uniquement. L'install réelle des drivers ROCm hôte et le câblage vendor→moteur
(filtrage sélection) sont des stories ultérieures (S2/S3). Codeur = crew-coder-long (Kimi/Moonshot).

## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/hardware/drivers.py b/src/forgeai/hardware/drivers.py
index 86a9df5..fef5f49 100644
--- a/src/forgeai/hardware/drivers.py
+++ b/src/forgeai/hardware/drivers.py
@@ -14,6 +14,7 @@ class DriverRecommendation:

## Correctif suite revue (tour 2)
Objection Qwen (majeure) TRAITÉE : marqueur AMD par mots entiers (tokenisation re.findall),
plus de faux positif sous-chaîne "mi". +2 tests adversariaux (sous_chaine_mi, mi_serie).

## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/hardware/drivers.py b/src/forgeai/hardware/drivers.py
index 86a9df5..8330440 100644
--- a/src/forgeai/hardware/drivers.py
+++ b/src/forgeai/hardware/drivers.py
@@ -1,3 +1,4 @@
+import re
 from dataclasses import dataclass
 
 VENDORS = ("nvidia", "amd", "intel")
@@ -14,6 +15,7 @@ class DriverRecommendation:
     operator: str
     rocm_allowed: bool
     notes: str
+    runtimes: tuple[str, ...]
 
 
 @dataclass(frozen=True)
@@ -33,9 +35,40 @@ class DriverOpPlan:
     notes: str
 
 
-def recommend_driver(vendor: str) -> DriverRecommendation:
-    if vendor not in VENDORS:
-        raise DriverError(f"Unknown vendor: {vendor}")
+def _amd_runtimes(model: str | None) -> tuple[str, ...]:
+    """Choix de runtimes AMD selon le modèle détecté (insensible à la casse, par mots entiers)."""
+    if model:
+        lowered = model.lower()
+        tokens = re.findall(r"[a-z0-9]+", lowered)
+
+        def _is_mi(token: str) -> bool:
+            return bool(re.fullmatch(r"mi\d+[a-z0-9]*", token))
+
+        rocm_markers = (
+            "instinct",
+            "cdna",
+        )
+        if any(
+            token in rocm_markers
+            or _is_mi(token)
+            or token.startswith("gfx9")
+            for token in tokens
+        ):
+            return ("rocm", "vulkan")
+
+        vulkan_markers = ("radeon", "rx", "rdna")
+        if any(
+            token in vulkan_markers
+            or token.startswith("gfx10")
+            or token.startswith("gfx11")
+            for token in tokens
+        ):
+            return ("vulkan", "rocm")
+
+    return ("vulkan", "rocm")
+
+
+def recommend_driver(vendor: str, *, model: str | None = None) -> DriverRecommendation:
     if vendor == "nvidia":
         return DriverRecommendation(
             vendor="nvidia",
@@ -43,24 +76,30 @@ def recommend_driver(vendor: str) -> DriverRecommendation:
             operator="nvidia-gpu-operator",
             rocm_allowed=False,
             notes="",
+            runtimes=("cuda", "vulkan"),
         )
-    elif vendor == "amd":
+
+    if vendor == "amd":
+        runtimes = _amd_runtimes(model)
         return DriverRecommendation(
             vendor="amd",
-            runtime="vulkan",
-            operator="none",
-            rocm_allowed=False,
-            notes="Vulkan forcé, ROCm non proposé",
+            runtime=runtimes[0],
+            operator="amd-gpu-operator",
+            rocm_allowed=True,
+            notes="ROCm + Vulkan au choix ; défaut selon l'architecture",
+            runtimes=runtimes,
         )
-    elif vendor == "intel":
+
+    if vendor == "intel":
         return DriverRecommendation(
             vendor="intel",
             runtime="openvino",
             operator="intel-device-plugins",
             rocm_allowed=False,
             notes="",
+            runtimes=("openvino", "vulkan"),
         )
-    # Dead branch – kept for completeness
+
     raise DriverError(f"Unknown vendor: {vendor}")
 
 
@@ -108,7 +147,7 @@ def plan_driver_op(vendor: str, action: str, *, version: str | None = None) -> D
     elif vendor == "amd":
         install_argv = ["apt-get", "install", "-y", "mesa-vulkan-drivers", "vulkan-tools"]
         rollback_argv = ["apt-get", "install", "-y", "--reinstall", "mesa-vulkan-drivers"]
-        notes = "Vulkan forcé, ROCm non proposé"
+        notes = "ROCm + Vulkan au choix ; défaut selon l'architecture"
     else:  # intel
         install_argv = ["apt-get", "install", "-y", "intel-opencl-icd"]
         rollback_argv = ["apt-get", "install", "-y", "--reinstall", "intel-opencl-icd"]
diff --git a/tests/test_drivers.py b/tests/test_drivers.py
index e68ab37..aab57e8 100644
--- a/tests/test_drivers.py
+++ b/tests/test_drivers.py
@@ -1,15 +1,12 @@
 import pytest
+from forgeai.core.runner import FixtureRunner
 from forgeai.hardware.drivers import (
-    DriverError,
     VENDORS,
-    DriverRecommendation,
-    DriverState,
-    DriverOpPlan,
-    recommend_driver,
+    DriverError,
     detect_driver_state,
     plan_driver_op,
+    recommend_driver,
 )
-from forgeai.core.runner import FixtureRunner
 
 
 def test_recommend_par_vendor():
@@ -18,21 +15,25 @@ def test_recommend_par_vendor():
     assert nvidia.operator == "nvidia-gpu-operator"
 
     amd = recommend_driver("amd")
-    assert amd.runtime == "vulkan"
-    assert amd.rocm_allowed is False
+    assert amd.runtime == "vulkan"  # arch inconnue -> defaut Vulkan (sur)
+    assert amd.rocm_allowed is True  # S1 : ROCm debloque (offert au choix)
 
     intel = recommend_driver("intel")
     assert intel.runtime == "openvino"
     assert intel.operator == "intel-device-plugins"
 
 
-def test_amd_rocm_jamais_propose():
+def test_amd_rocm_debloque_host_install_reste_vulkan():
+    """S1 : ROCm est DÉBLOQUÉ (offert au choix), mais l'install driver HÔTE par défaut
+    reste Vulkan (mesa) — l'install des drivers ROCm est gérée côté cluster par l'AMD
+    GPU Operator (network/prepare.py), pas par apt hôte. Frontière de périmètre S1."""
     rec = recommend_driver("amd")
-    assert rec.rocm_allowed is False
+    assert rec.rocm_allowed is True
+    assert "rocm" in rec.runtimes  # ROCm bien proposé
 
     plan = plan_driver_op("amd", "install")
     all_argv = plan.install_argv + plan.rollback_argv
-    assert not any("rocm" in arg.lower() for arg in all_argv)
+    assert not any("rocm" in arg.lower() for arg in all_argv)  # host apt reste vulkan (S1)
 
 
 def test_vendor_inconnu_leve():
diff --git a/tests/test_drivers_runtime_choice.py b/tests/test_drivers_runtime_choice.py
new file mode 100644
index 0000000..562c81b
--- /dev/null
+++ b/tests/test_drivers_runtime_choice.py
@@ -0,0 +1,126 @@
+"""Story S1 — Recommandation de runtime GPU par vendor : ROCm débloqué (AMD) + choix
+multi-runtime avec DÉFAUT INTELLIGENT et surchargeable.
+
+Spec exécutable (TDD). Fige les décisions Nathan (2026-07-20) :
+  - AMD : ROCm + Vulkan offerts AU CHOIX (ROCm plus bloqué en dur) ; défaut auto =
+    ROCm sur Instinct/CDNA, Vulkan sur Radeon/RDNA ; Vulkan (sûr) si arch inconnue.
+  - Défaut intelligent PAR VENDOR, toujours surchargeable : le défaut est simplement le
+    premier runtime OFFERT ; l'appelant peut piocher un autre runtime de la liste offerte.
+  - NVIDIA garde CUDA par défaut mais offre aussi Vulkan (runtime universel llama.cpp).
+  - Intel garde OpenVINO par défaut, offre aussi Vulkan/SYCL.
+Aucune régression : les champs existants (runtime/operator/notes) restent présents.
+"""
+import sys
+from pathlib import Path
+
+import pytest
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.hardware.drivers import DriverError, recommend_driver
+
+
+# --- AMD : ROCm débloqué + les deux runtimes offerts ------------------------------
+def test_amd_rocm_debloque():
+    rec = recommend_driver("amd")
+    assert rec.rocm_allowed is True, "ROCm ne doit plus être bloqué en dur pour AMD"
+    assert "non proposé" not in rec.notes.lower(), "la note 'ROCm non proposé' doit disparaître"
+
+
+def test_amd_offre_rocm_et_vulkan():
+    rec = recommend_driver("amd")
+    assert {"rocm", "vulkan"} <= set(rec.runtimes), (
+        f"AMD doit offrir ROCm ET Vulkan au choix, obtenu {rec.runtimes}"
+    )
+
+
+def test_amd_operator_est_amd_gpu_operator():
+    rec = recommend_driver("amd")
+    assert rec.operator == "amd-gpu-operator", (
+        f"AMD doit pointer l'AMD GPU Operator (ROCm), pas 'none' — obtenu {rec.operator!r}"
+    )
+
+
+# --- Défaut INTELLIGENT par architecture (défaut = premier runtime offert) ---------
+def test_amd_defaut_rocm_sur_instinct():
+    rec = recommend_driver("amd", model="AMD Instinct MI300X")
+    assert rec.runtime == "rocm", "Instinct/CDNA → défaut ROCm (perf max)"
+    assert rec.runtimes[0] == "rocm", "le défaut doit être le 1er runtime offert"
+
+
+def test_amd_defaut_vulkan_sur_radeon():
+    rec = recommend_driver("amd", model="AMD Radeon RX 7900 XTX")
+    assert rec.runtime == "vulkan", "Radeon/RDNA → défaut Vulkan (compat)"
+    assert rec.runtimes[0] == "vulkan"
+
+
+def test_amd_defaut_vulkan_si_arch_inconnue():
+    rec = recommend_driver("amd", model=None)
+    assert rec.runtime == "vulkan", "arch AMD inconnue → défaut Vulkan (sûr)"
+    assert "rocm" in rec.runtimes, "ROCm reste OFFERT même si non défaut"
+
+
+# --- Adversarial (objection revue Qwen majeure) : le marqueur 'mi' ne doit PAS
+#     matcher en sous-chaîne ('family', 'mini', 'omni'...) et forcer ROCm à tort ---
+def test_amd_radeon_sous_chaine_mi_reste_vulkan():
+    for model in ("AMD Radeon RX 6800 family", "Radeon RX 7600 mini", "AMD Radeon RX 9070"):
+        rec = recommend_driver("amd", model=model)
+        assert rec.runtime == "vulkan", (
+            f"{model!r} (Radeon/RDNA) doit rester Vulkan, pas ROCm — obtenu {rec.runtime}"
+        )
+
+
+def test_amd_mi_serie_reste_rocm():
+    for model in ("AMD Instinct MI250", "AMD Instinct MI300X", "Instinct MI325X"):
+        rec = recommend_driver("amd", model=model)
+        assert rec.runtime == "rocm", (
+            f"{model!r} (Instinct/CDNA) doit être ROCm — obtenu {rec.runtime}"
+        )
+
+
+# --- NVIDIA : CUDA défaut mais Vulkan universel offert -----------------------------
+def test_nvidia_defaut_cuda_offre_vulkan():
+    rec = recommend_driver("nvidia")
+    assert rec.runtime == "cuda"
+    assert rec.runtimes[0] == "cuda"
+    assert "vulkan" in rec.runtimes, "NVIDIA doit aussi offrir Vulkan (llama.cpp universel)"
+    assert rec.rocm_allowed is False
+
+
+# --- Intel : OpenVINO défaut, Vulkan/SYCL offert -----------------------------------
+def test_intel_defaut_openvino():
+    rec = recommend_driver("intel")
+    assert rec.runtime == "openvino"
+    assert rec.runtimes[0] == "openvino"
+    assert rec.operator == "intel-device-plugins"
+    assert rec.rocm_allowed is False
+
+
+# --- Invariants transverses --------------------------------------------------------
+@pytest.mark.parametrize("vendor", ["nvidia", "amd", "intel"])
+def test_defaut_est_premier_offert(vendor):
+    rec = recommend_driver(vendor)
+    assert rec.runtime == rec.runtimes[0], (
+        "invariant : le runtime par défaut est le premier de la liste offerte"
+    )
+    assert len(rec.runtimes) >= 1
+
+
+@pytest.mark.parametrize("vendor", ["nvidia", "amd", "intel"])
+def test_runtimes_sans_doublon_et_non_vide(vendor):
+    rec = recommend_driver(vendor)
+    assert all(isinstance(r, str) and r for r in rec.runtimes)
+    assert len(set(rec.runtimes)) == len(rec.runtimes), "pas de runtime dupliqué"
+
+
+def test_retrocompat_champs_preserves():
+    rec = recommend_driver("amd")
+    # les champs historiques restent exposés (aucune régression d'API)
+    assert isinstance(rec.runtime, str) and rec.runtime
+    assert isinstance(rec.operator, str)
+    assert isinstance(rec.notes, str)
+
+
+def test_vendor_inconnu_leve():
+    with pytest.raises(DriverError):
+        recommend_driver("apple")
```
## Preuve d’exécution
```
..........................                                               [100%]
All checks passed!
NO-STUB-SCAN : OK (2 fichiers scannés, zéro violation)
```
