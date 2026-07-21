"""Story S2 — profil GPU vendor-aware : un GPU AMD/Intel détecté SANS VRAM connue
(lspci renvoie vram_mb=0) doit quand même donner le profil vendor, pas retomber sur CPU.
NVIDIA reste strict (nvidia-smi donne toujours la VRAM réelle → 0 = pas de GPU utilisable).
Corrige le gap : sur un nœud AMD réel, derive_profile retombait toujours sur minimal-cpu.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import GPU, Disk, HardwareProfile
from forgeai.planner.profile import derive_profile


def _hw(*gpus):
    return HardwareProfile(
        cpu_model="x", cpu_cores=8, cpu_arch="x86_64", ram_gb=32.0, os_name="ubuntu",
        gpus=tuple(gpus), disks=(Disk(path="/", total_gb=500.0, free_gb=200.0),),
    )


def test_amd_vram_inconnue_donne_rocm():
    assert derive_profile(_hw(GPU("amd", "AMD Radeon RX 7900 XTX", 0))) == "minimal-gpu-rocm"


def test_intel_vram_inconnue_donne_intel():
    assert derive_profile(_hw(GPU("intel", "Intel Arc A770", 0))) == "minimal-gpu-intel"


def test_amd_avec_vram_reste_rocm():
    assert derive_profile(_hw(GPU("amd", "AMD Instinct MI300X", 65536))) == "minimal-gpu-rocm"


def test_nvidia_vram_zero_ne_fabrique_pas_de_gpu():
    # nvidia-smi donne toujours la VRAM réelle : 0 = pas de VRAM utilisable → CPU.
    assert derive_profile(_hw(GPU("nvidia", "carte", 0))) == "minimal-cpu"


def test_priorite_nvidia_sur_amd():
    hw = _hw(GPU("amd", "rx", 0), GPU("nvidia", "rtx", 16384))
    assert derive_profile(hw) == "minimal-gpu-cuda"


def test_priorite_amd_sur_intel():
    assert derive_profile(_hw(GPU("intel", "arc", 0), GPU("amd", "rx", 0))) == "minimal-gpu-rocm"


def test_amd_igpu_sans_vram_reste_cpu():
    # frontière : un iGPU AMD faible (VRAM 0) ne déclenche PAS ROCm (seul un dGPU le fait)
    assert derive_profile(_hw(GPU("amd", "Raphael iGPU", 0))) == "minimal-cpu"


def test_aucun_gpu_reste_cpu():
    assert derive_profile(_hw()) == "minimal-cpu"
