"""Tests S02 — dérivation de profil."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import GPU, Disk, HardwareProfile
from forgeai.planner.profile import ProfileError, derive_profile


def _hw(ram=32.0, free=500.0, gpus=()):
    return HardwareProfile(
        cpu_model="test", cpu_cores=8, cpu_arch="x86_64", ram_gb=ram,
        os_name="Linux", gpus=tuple(gpus),
        disks=(Disk(path="/", total_gb=1000.0, free_gb=free),),
    )


def test_nvidia_8go_donne_cuda():
    assert derive_profile(_hw(gpus=[GPU("nvidia", "RTX 5090", 32607)])) == "minimal-gpu-cuda"


def test_amd_8go_donne_rocm():
    assert derive_profile(_hw(gpus=[GPU("amd", "RX 6800", 16384)])) == "minimal-gpu-rocm"


def test_igpu_amd_sans_vram_ignore():
    assert derive_profile(_hw(gpus=[GPU("amd", "Raphael iGPU", 0)])) == "minimal-cpu"


def test_sans_gpu_donne_cpu():
    assert derive_profile(_hw()) == "minimal-cpu"


def test_ram_insuffisante_leve_err_hw_min():
    with pytest.raises(ProfileError) as exc:
        derive_profile(_hw(ram=2.0))
    assert exc.value.code == "ERR_HW_MIN"


def test_disque_insuffisant_leve_err_hw_min():
    with pytest.raises(ProfileError):
        derive_profile(_hw(free=10.0))


def test_nvidia_et_amd_presents_prefere_cuda():
    gpus = [GPU("nvidia", "RTX 5090", 32607), GPU("amd", "iGPU", 0)]
    assert derive_profile(_hw(gpus=gpus)) == "minimal-gpu-cuda"
