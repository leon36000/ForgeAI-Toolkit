"""Story P1-S02 — dérivation déterministe du profil de déploiement (codeur : fable).

Seuils Minimal : RAM ≥ 4 Go, disque libre ≥ 25 Go (critères stories-kimi).
Variantes : minimal-gpu-cuda (NVIDIA ≥ 8 Go VRAM), minimal-gpu-rocm (AMD ≥ 8 Go),
minimal-gpu-intel (Intel ≥ 4 Go), sinon minimal-cpu. Échec = ProfileError avec
code ERR_HW_MIN — le wizard bascule alors en « détection forcée » (mitigation R-01).
"""
from __future__ import annotations

from forgeai.core.models import HardwareProfile

MIN_RAM_GB = 4.0
MIN_DISK_FREE_GB = 25.0


class ProfileError(Exception):
    def __init__(self, message: str, code: str = "ERR_HW_MIN") -> None:
        super().__init__(message)
        self.code = code


def derive_profile(hw: HardwareProfile) -> str:
    if hw.ram_gb < MIN_RAM_GB:
        raise ProfileError(
            f"RAM insuffisante : {hw.ram_gb} Go < {MIN_RAM_GB} Go requis")
    free = max((d.free_gb for d in hw.disks), default=0.0)
    if free < MIN_DISK_FREE_GB:
        raise ProfileError(
            f"Disque libre insuffisant : {free} Go < {MIN_DISK_FREE_GB} Go requis")

    for gpu in hw.gpus:
        if gpu.vendor == "nvidia" and gpu.vram_mb >= 8192:
            return "minimal-gpu-cuda"
    for gpu in hw.gpus:
        if gpu.vendor == "amd" and gpu.vram_mb >= 8192:
            return "minimal-gpu-rocm"
    for gpu in hw.gpus:
        if gpu.vendor == "intel" and gpu.vram_mb >= 4096:
            return "minimal-gpu-intel"
    return "minimal-cpu"
