# Prise en charge des drivers GPU

Ce document aligne les affirmations du projet sur les preuves réellement disponibles.

Les fonctions `recommend_driver` et `plan_driver_op` de `src/forgeai/hardware/drivers.py`
sont implémentées pour les trois vendeurs définis par `VENDORS = ("nvidia", "amd", "intel")`.
Le niveau de preuve diffère selon les vendeurs.

| Vendeur | Implémentation | Preuve laboratoire | Tests |
|---|---|---|---|
| NVIDIA | `recommend_driver("nvidia")` et `plan_driver_op("nvidia", ...)` implémentées. | Qualifié sur matériel réel — détection : registre HW-010 ; déploiement e2e k3s en laboratoire : LAB-033N (evidence `reviews/LAB-033N/evidence/`). | `tests/test_k3s_gpu_vendor.py` (parties NVIDIA), `tests/test_gpu_reservation_vendor.py` (parties NVIDIA). |
| AMD | `recommend_driver("amd", model=...)` et `plan_driver_op("amd", ...)` implémentées (sélection ROCm/Vulkan selon l'architecture). | Qualifié sur matériel réel — registre HW-037, PR #290. | `tests/test_k3s_gpu_vendor.py` (parties AMD), `tests/test_gpu_reservation_vendor.py` (parties AMD), `tests/test_drivers.py`. |
| Intel | `recommend_driver("intel")` et `plan_driver_op("intel", ...)` implémentées. | Implémenté — qualification laboratoire de bout en bout à réaliser. Suivi : issue `LAB-033I`. | `tests/test_intel_openvino_runtime.py`, `tests/test_gpu_reservation_vendor.py::test_render_intel_reserve_dri`, `tests/test_k3s_gpu_vendor.py::test_k3s_intel_sans_privileged`, `tests/test_k3s_gpu_vendor.py::test_k3s_intel_passthrough_dri`. |

_Note : `LAB-033I` dépendait de `CAP-033A` (ce document) avant sa fusion. Cette dépendance
étant levée une fois `CAP-033A` intégré, ce tableau ne réaffirme pas un statut de dépendance
qui deviendrait obsolète dès la fusion — se référer à `coordination/work-packages.json` pour
le statut vivant de `LAB-033I`._

