from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "proof"
    / "prove_gpu_intel_e2e.py"
)

spec = importlib.util.spec_from_file_location("prove_gpu_intel_e2e", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules["prove_gpu_intel_e2e"] = module
spec.loader.exec_module(module)

from prove_gpu_intel_e2e import (
    reconstruct_hardware,
    render_manifest,
    namespace_from_manifest,
    acces_device_intel_prouve,
    charge_gt_observee,
)
from forgeai.planner.profile import derive_profile, ProfileError

_JSON_SONDE_INTEL_SYNTHETIQUE = {
    "cpu_model": "13th Gen Intel(R) Core(TM) i9-13900H",
    "cpu_cores": 20,
    "cpu_arch": "x86_64",
    "ram_gb": 30.6,
    "os_name": "Linux",
    "gpus": [
        {
            "vendor": "intel",
            "name": "Intel Corporation Raptor Lake-P [8086:a7a0]",
            "vram_mb": 0,
        },
        {
            "vendor": "nvidia",
            "name": "NVIDIA Corporation AD106M [10de:2860] [unqualified]",
            "vram_mb": 0,
        },
    ],
    "disks": [{"path": "/", "total_gb": 98.0, "free_gb": 29.0}],
}


@pytest.fixture
def json_sonde_intel():
    """Données SYNTHÉTIQUES imitant la forme d'une sonde `forgeai hardware`."""
    return _JSON_SONDE_INTEL_SYNTHETIQUE.copy()


def test_profil_derive_intel(json_sonde_intel):
    """Le profil dérivé est minimal-gpu-intel car l'Intel iGPU est présent
    et le NVIDIA [unqualified] est ignoré par la garde HW-010."""
    hw = reconstruct_hardware(json_sonde_intel)
    assert derive_profile(hw) == "minimal-gpu-intel"


def test_manifeste_intel_render(json_sonde_intel):
    """Le manifeste Intel expose gpu.intel.com/i915, épingle le nœud,
    enforce baseline, et ne contient aucune ressource AMD/NVIDIA ni hostPath."""
    hw = reconstruct_hardware(json_sonde_intel)
    manifest = render_manifest("minimal-gpu-intel", "noeud-test-intel", hw)
    assert "gpu.intel.com/i915" in manifest
    assert "enforce: baseline" in manifest
    assert "kubernetes.io/hostname: noeud-test-intel" in manifest
    assert "amd.com/gpu" not in manifest
    assert "nvidia.com/gpu" not in manifest
    for line in manifest.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("hostPath:"):
            pytest.fail(f"hostPath trouvé dans le manifeste : {line}")


def test_namespace_extraction(json_sonde_intel):
    """Le premier Namespace du manifeste est forgeai-minimal."""
    hw = reconstruct_hardware(json_sonde_intel)
    manifest = render_manifest("minimal-gpu-intel", "noeud-test-intel", hw)
    assert namespace_from_manifest(manifest) == "forgeai-minimal"


def test_refus_gpu_inutilisable():
    """Un NVIDIA [unqualified] seul déclenche ProfileError (garde HW-010)
    car aucun GPU utilisable n'est disponible."""
    data = {
        "cpu_model": "Generic CPU",
        "cpu_cores": 4,
        "cpu_arch": "x86_64",
        "ram_gb": 16.0,
        "os_name": "Linux",
        "gpus": [
            {
                "vendor": "nvidia",
                "name": "NVIDIA Corporation AD106M [10de:2860] [unqualified]",
                "vram_mb": 0,
            },
        ],
        "disks": [{"path": "/", "total_gb": 100.0, "free_gb": 30.0}],
    }
    hw = reconstruct_hardware(data)
    with pytest.raises(ProfileError):
        derive_profile(hw)


def test_acces_device_intel_prouve():
    """Vrai uniquement si le marqueur d'ouverture rw est présent et l'allocation
    i915 est passée de >=1 à 0."""
    sortie_ok = "INTEL-DEVICE-OK /dev/dri/renderD128\n"
    assert acces_device_intel_prouve(sortie_ok, 1, 0) is True
    assert acces_device_intel_prouve(sortie_ok, 0, 0) is False
    assert acces_device_intel_prouve(sortie_ok, 1, 1) is False
    assert acces_device_intel_prouve("", 1, 0) is False


def test_charge_gt_observee():
    """L'indice GT est positif si la fréquence effective d'au moins une carte
    dépasse franchement son niveau de repos ; faux au repos ou si les valeurs
    sont absentes/illisibles."""
    repos = {"card0": {"gt_act_freq_mhz": 200}}
    assert charge_gt_observee(repos, [{"card0": {"gt_act_freq_mhz": 500}}]) is True
    assert charge_gt_observee(repos, [{"card0": {"gt_act_freq_mhz": 200}}]) is False
    assert charge_gt_observee(repos, [{"card0": {"gt_act_freq_mhz": None}}]) is False
    assert charge_gt_observee({}, [{}]) is False
