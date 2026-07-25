from __future__ import annotations

from forgeai.core.models import HardwareProfile

MIN_RAM_GB = 4.0
MIN_DISK_FREE_GB = 25.0


class ProfileError(Exception):
    def __init__(self, message: str, code: str = "ERR_HW_MIN") -> None:
        super().__init__(message)
        self.code = code


def derive_profile(hw: HardwareProfile) -> str:
    """Dérive le profil de déploiement minimal à partir du profil matériel.

    Seuils Minimal : RAM ≥ 4 Go, disque libre ≥ 25 Go.
    Variantes GPU : minimal-gpu-cuda (NVIDIA ≥ 8 Go VRAM),
    minimal-gpu-rocm (AMD ≥ 8 Go), minimal-gpu-intel (Intel ≥ 4 Go).
    Échec matériel = ProfileError(code ERR_HW_MIN).

    HW-010 : un GPU NVIDIA visible par lspci mais non qualifié (marqueur
    [unqualified] dans le nom, c'est-à-dire nvidia-smi absent ou en échec)
    n'est pas silencieusement ignoré : s'il est présent et qu'aucun GPU
    utilisable n'est trouvé, une ProfileError oriente l'utilisateur vers
    le driver/runtime NVIDIA.
    """
    if hw.ram_gb < MIN_RAM_GB:
        raise ProfileError(
            f"RAM insuffisante : {hw.ram_gb} Go < {MIN_RAM_GB} Go requis")
    free = max((d.free_gb for d in hw.disks), default=0.0)
    if free < MIN_DISK_FREE_GB:
        raise ProfileError(
            f"Disque libre insuffisant : {free} Go < {MIN_DISK_FREE_GB} Go requis")

    # VRAM inconnue (vram_mb == 0, ex. dGPU AMD/Intel vus par lspci) : on se fie à la
    # PRÉSENCE du vendor. NVIDIA reste strict (nvidia-smi donne toujours la VRAM réelle,
    # donc 0 = pas de GPU utilisable). Un iGPU AMD faible (VRAM 0) est ignoré : ROCm ne
    # cible pas les APU intégrés — seul un dGPU AMD à VRAM inconnue déclenche le profil.
    # La distinction iGPU/dGPU repose sur le marqueur canonique « [integrated] » émis par
    # detect.py à partir de l'identifiant PCI « vendor:device » (HW-009).
    def _est_integre(name: str) -> bool:
        low = name.lower()
        # source d'autorité : marqueur canonique émis par detect.py à partir de l'identifiant PCI
        if "[integrated]" in low:
            return True
        # repli défensif (noms explicites éventuels)
        return "igpu" in low or "integrated" in low

    def _usable(gpu) -> bool:
        if gpu.vendor == "nvidia":
            return gpu.vram_mb >= 8192
        if gpu.vendor == "amd":
            return gpu.vram_mb >= 8192 or (gpu.vram_mb == 0 and not _est_integre(gpu.name))
        if gpu.vendor == "intel":
            return gpu.vram_mb >= 4096 or gpu.vram_mb == 0
        return False

    usable = [g for g in hw.gpus if _usable(g)]
    for vendor, profile in (("nvidia", "minimal-gpu-cuda"),
                            ("amd", "minimal-gpu-rocm"),
                            ("intel", "minimal-gpu-intel")):
        if any(g.vendor == vendor for g in usable):
            return profile

    # HW-010 : refuser de faire disparaître un NVIDIA présent mais non qualifié.
    non_qualifies = [g for g in hw.gpus if g.vendor == "nvidia" and "[unqualified]" in g.name]
    if not usable and non_qualifies:
        raise ProfileError(
            "GPU NVIDIA présent mais non qualifié : nvidia-smi indisponible "
            "(driver/runtime NVIDIA). VRAM inconnue (non nulle). Vérifiez l'installation du driver "
            "NVIDIA (`nvidia-smi`) puis relancez — le déploiement d'un workload GPU est refusé tant "
            "que le GPU n'est pas qualifié.")

    return "minimal-cpu"
