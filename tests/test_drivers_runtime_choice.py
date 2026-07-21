"""Story S1 — Recommandation de runtime GPU par vendor : ROCm débloqué (AMD) + choix
multi-runtime avec DÉFAUT INTELLIGENT et surchargeable.

Spec exécutable (TDD). Fige les décisions Nathan (2026-07-20) :
  - AMD : ROCm + Vulkan offerts AU CHOIX (ROCm plus bloqué en dur) ; défaut auto =
    ROCm sur Instinct/CDNA, Vulkan sur Radeon/RDNA ; Vulkan (sûr) si arch inconnue.
  - Défaut intelligent PAR VENDOR, toujours surchargeable : le défaut est simplement le
    premier runtime OFFERT ; l'appelant peut piocher un autre runtime de la liste offerte.
  - NVIDIA garde CUDA par défaut mais offre aussi Vulkan (runtime universel llama.cpp).
  - Intel garde OpenVINO par défaut, offre aussi Vulkan/SYCL.
Aucune régression : les champs existants (runtime/operator/notes) restent présents.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.hardware.drivers import DriverError, recommend_driver


# --- AMD : ROCm débloqué + les deux runtimes offerts ------------------------------
def test_amd_rocm_debloque():
    rec = recommend_driver("amd")
    assert rec.rocm_allowed is True, "ROCm ne doit plus être bloqué en dur pour AMD"
    assert "non proposé" not in rec.notes.lower(), "la note 'ROCm non proposé' doit disparaître"


def test_amd_offre_rocm_et_vulkan():
    rec = recommend_driver("amd")
    assert {"rocm", "vulkan"} <= set(rec.runtimes), (
        f"AMD doit offrir ROCm ET Vulkan au choix, obtenu {rec.runtimes}"
    )


def test_amd_operator_est_amd_gpu_operator():
    rec = recommend_driver("amd")
    assert rec.operator == "amd-gpu-operator", (
        f"AMD doit pointer l'AMD GPU Operator (ROCm), pas 'none' — obtenu {rec.operator!r}"
    )


# --- Défaut INTELLIGENT par architecture (défaut = premier runtime offert) ---------
def test_amd_defaut_rocm_sur_instinct():
    rec = recommend_driver("amd", model="AMD Instinct MI300X")
    assert rec.runtime == "rocm", "Instinct/CDNA → défaut ROCm (perf max)"
    assert rec.runtimes[0] == "rocm", "le défaut doit être le 1er runtime offert"


def test_amd_defaut_vulkan_sur_radeon():
    rec = recommend_driver("amd", model="AMD Radeon RX 7900 XTX")
    assert rec.runtime == "vulkan", "Radeon/RDNA → défaut Vulkan (compat)"
    assert rec.runtimes[0] == "vulkan"


def test_amd_defaut_vulkan_si_arch_inconnue():
    rec = recommend_driver("amd", model=None)
    assert rec.runtime == "vulkan", "arch AMD inconnue → défaut Vulkan (sûr)"
    assert "rocm" in rec.runtimes, "ROCm reste OFFERT même si non défaut"


# --- NVIDIA : CUDA défaut mais Vulkan universel offert -----------------------------
def test_nvidia_defaut_cuda_offre_vulkan():
    rec = recommend_driver("nvidia")
    assert rec.runtime == "cuda"
    assert rec.runtimes[0] == "cuda"
    assert "vulkan" in rec.runtimes, "NVIDIA doit aussi offrir Vulkan (llama.cpp universel)"
    assert rec.rocm_allowed is False


# --- Intel : OpenVINO défaut, Vulkan/SYCL offert -----------------------------------
def test_intel_defaut_openvino():
    rec = recommend_driver("intel")
    assert rec.runtime == "openvino"
    assert rec.runtimes[0] == "openvino"
    assert rec.operator == "intel-device-plugins"
    assert rec.rocm_allowed is False


# --- Invariants transverses --------------------------------------------------------
@pytest.mark.parametrize("vendor", ["nvidia", "amd", "intel"])
def test_defaut_est_premier_offert(vendor):
    rec = recommend_driver(vendor)
    assert rec.runtime == rec.runtimes[0], (
        "invariant : le runtime par défaut est le premier de la liste offerte"
    )
    assert len(rec.runtimes) >= 1


@pytest.mark.parametrize("vendor", ["nvidia", "amd", "intel"])
def test_runtimes_sans_doublon_et_non_vide(vendor):
    rec = recommend_driver(vendor)
    assert all(isinstance(r, str) and r for r in rec.runtimes)
    assert len(set(rec.runtimes)) == len(rec.runtimes), "pas de runtime dupliqué"


def test_retrocompat_champs_preserves():
    rec = recommend_driver("amd")
    # les champs historiques restent exposés (aucune régression d'API)
    assert isinstance(rec.runtime, str) and rec.runtime
    assert isinstance(rec.operator, str)
    assert isinstance(rec.notes, str)


def test_vendor_inconnu_leve():
    with pytest.raises(DriverError):
        recommend_driver("apple")
