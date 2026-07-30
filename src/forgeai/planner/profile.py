"""Story P1-S02 — dérivation déterministe du profil de déploiement (codeur : fable).

Seuils Minimal : RAM ≥ 4 Go, disque libre ≥ 25 Go (critères stories-kimi).
Variantes : minimal-gpu-cuda (NVIDIA ≥ 8 Go VRAM), minimal-gpu-rocm (AMD ≥ 8 Go),
minimal-gpu-intel (Intel ≥ 4 Go), sinon minimal-cpu. Échec = ProfileError avec
code ERR_HW_MIN — le wizard bascule alors en « détection forcée » (mitigation R-01).

HW-010 (FAI-U-010) : un GPU NVIDIA marqué « [unqualified] » (vu par lspci, nvidia-smi
KO -> VRAM inconnue, non nulle) ne disparaît pas silencieusement en minimal-cpu ;
si aucun GPU utilisable n'est trouvé, derive_profile lève ProfileError orientant
vers la vérification du driver/runtime NVIDIA.
"""
from __future__ import annotations

from forgeai.core.models import GPU, HardwareProfile

MIN_RAM_GB = 4.0
MIN_DISK_FREE_GB = 25.0

# Mesuré (LAB-033I, evidence reviews/LAB-033I/evidence/hardware-pc2.json + gpu-feature-
# discovery) : une RTX 4070 Laptop annoncée "8 Go" rapporte 8188 MiB via nvidia-smi/GFD —
# la VRAM utile est toujours < capacité nominale (réservations firmware). Un seuil sur la
# puissance de 2 exacte (8192) ne peut jamais être atteint par cette classe de carte.
MIN_VRAM_DEDIE_8GO_MB = 8100


class ProfileError(Exception):
    def __init__(self, message: str, code: str = "ERR_HW_MIN") -> None:
        super().__init__(message)
        self.code = code


def _est_integre(name: str) -> bool:
    low = name.lower()
    # source d'autorité : marqueur canonique émis par detect.py à partir de l'identifiant PCI
    if "[integrated]" in low:
        return True
    # repli défensif (noms explicites éventuels)
    return "igpu" in low or "integrated" in low


def _usable(gpu: GPU) -> bool:
    if gpu.vendor == "nvidia":
        return gpu.vram_mb >= MIN_VRAM_DEDIE_8GO_MB
    if gpu.vendor == "amd":
        return gpu.vram_mb >= MIN_VRAM_DEDIE_8GO_MB or (gpu.vram_mb == 0 and not _est_integre(gpu.name))
    if gpu.vendor == "intel":
        return gpu.vram_mb >= 4096 or gpu.vram_mb == 0
    return False


def gpus_non_qualifies_ignores(hw: HardwareProfile) -> tuple[str, ...]:
    """Liste les GPU NVIDIA [unqualified] qui seraient IGNORÉS par derive_profile parce
    qu'un AUTRE vendor est utilisable (HW-010 ne bloque alors pas le déploiement — c'est
    la bonne décision produit — mais le GPU cassé disparaît sans signal si personne
    n'appelle cette fonction). Retourne les noms des GPU concernés ; tuple vide si aucun.
    N'appelle PAS derive_profile (pas de risque de double dérivation/incohérence) :
    réplique juste le calcul usable/non_qualifies en lecture seule.
    """
    usable = [g for g in hw.gpus if _usable(g)]
    non_qualifies = [g for g in hw.gpus if g.vendor == "nvidia" and "[unqualified]" in g.name]
    if usable and non_qualifies:
        return tuple(g.name for g in non_qualifies)
    return ()


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
