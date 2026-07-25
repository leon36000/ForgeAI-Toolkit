from __future__ import annotations

import json
import platform
import re
from pathlib import Path

from forgeai.core.models import GPU, Disk, HardwareProfile
from forgeai.core.runner import CommandRunner

_PCI_VENDORS = {"1002": "amd", "8086": "intel", "10de": "nvidia"}

# iGPU/APU connus, par identifiant PCI « vendor:device » en minuscules. ROCm ne
# cible pas ces puces intégrées : elles ne doivent jamais être promues en dGPU.
# Liste extensible — ajouter ici tout nouvel iGPU rencontré sur le terrain.
_INTEGRATED_PCI_DEVICE_IDS = frozenset({
    "1002:13c0",  # Raphael (APU Ryzen 7000)
    "1002:164e",  # Renoir
    "1002:1636",
    "1002:15bf",
    "1002:15c8",
    "1002:1681",
    "1002:164c",
    "1002:1900",
    "1002:13fe",
    "1002:15d8",
    "1002:15dd",  # AMD APU/iGPU connus (extensible)
})


class HardwareDetector:
    def __init__(self, runner: CommandRunner, meminfo_path: str = "/proc/meminfo") -> None:
        self.runner = runner
        self.meminfo_path = meminfo_path

    def detect_cpu(self) -> tuple[str, int, str]:
        code, out = self.runner.run(["lscpu", "-J"])
        model, cores, arch = "unknown", 0, platform.machine()
        if code == 0 and out.strip():
            try:
                entries = self._flatten_lscpu(json.loads(out).get("lscpu", []))
                model = entries.get("Model name", entries.get("Nom de modèle", model))
                cores = int(entries.get("CPU(s)", entries.get("Processeur(s)", "0")))
                arch = entries.get("Architecture", arch)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return model, cores, arch

    @staticmethod
    def _flatten_lscpu(entries: list[dict]) -> dict[str, str]:
        """Aplati la structure lscpu -J (children imbriqués) et normalise les
        clés : espaces insécables retirés, deux-points terminal retiré."""
        flat: dict[str, str] = {}
        stack = list(entries)
        while stack:
            entry = stack.pop()
            field = str(entry.get("field", "")).replace("\xa0", " ").strip().rstrip(":").strip()
            if field:
                flat[field] = str(entry.get("data", ""))
            stack.extend(entry.get("children") or [])
        return flat

    def detect_ram_gb(self) -> float:
        try:
            for line in Path(self.meminfo_path).read_text(encoding="ascii").splitlines():
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
        except (OSError, ValueError, IndexError):
            pass
        return 0.0

    def detect_disks(self) -> tuple[Disk, ...]:
        code, out = self.runner.run(["df", "-B1G", "--output=target,size,avail", "/"])
        if code != 0 or not out.strip():
            return ()
        disks = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    disks.append(Disk(path=parts[0], total_gb=float(parts[1]),
                                      free_gb=float(parts[2])))
                except ValueError:
                    continue
        return tuple(disks)

    def detect_gpus(self) -> tuple[GPU, ...]:
        gpus = list(self._nvidia_gpus())
        seen_nvidia = bool(gpus)
        for gpu in self._pci_gpus():
            if gpu.vendor == "nvidia" and seen_nvidia:
                continue  # déjà rapporté avec la VRAM exacte par nvidia-smi
            gpus.append(gpu)
        return tuple(gpus)

    def _nvidia_gpus(self) -> list[GPU]:
        code, out = self.runner.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
        )
        if code != 0 or not out.strip():
            return []
        gpus = []
        for line in out.strip().splitlines():
            try:
                name, vram = line.rsplit(",", 1)
                gpus.append(GPU(vendor="nvidia", name=name.strip(), vram_mb=int(vram.strip())))
            except ValueError:
                continue
        return gpus

    def _pci_gpus(self) -> list[GPU]:
        code, out = self.runner.run(["lspci", "-nn"])
        if code != 0:
            return []
        gpus = []
        for line in out.splitlines():
            if "VGA compatible controller" not in line and "3D controller" not in line:
                continue
            ids = re.findall(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", line)
            if not ids:
                continue
            vendor_hex, device_hex = ids[-1]
            vendor_hex = vendor_hex.lower()
            device_hex = device_hex.lower()
            vendor = _PCI_VENDORS.get(vendor_hex)
            if vendor is None:
                continue
            base = line.split("controller", 1)[-1].split(":", 1)[-1].split("[")[0].strip()
            name = f"{base or 'unknown'} [{vendor_hex}:{device_hex}]"
            if f"{vendor_hex}:{device_hex}" in _INTEGRATED_PCI_DEVICE_IDS:
                name += " [integrated]"
            gpus.append(GPU(vendor=vendor, name=name, vram_mb=0))
        return gpus

    def full_report(self) -> HardwareProfile:
        model, cores, arch = self.detect_cpu()
        return HardwareProfile(
            cpu_model=model,
            cpu_cores=cores,
            cpu_arch=arch,
            ram_gb=self.detect_ram_gb(),
            os_name=f"{platform.system()} {platform.release()}",
            gpus=self.detect_gpus(),
            disks=self.detect_disks(),
        )
