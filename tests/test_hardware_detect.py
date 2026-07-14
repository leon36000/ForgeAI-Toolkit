"""Tests S01 — détection hardware sur fixtures réelles capturées (machine forge, 2026-07-14)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.runner import FixtureRunner
from forgeai.hardware.detect import HardwareDetector

FIXTURES = Path(__file__).parent / "fixtures" / "hardware"


def _runner(**overrides):
    outputs = {
        "lscpu": (FIXTURES / "lscpu_amd64.json").read_text(encoding="utf-8"),
        "nvidia-smi": (FIXTURES / "nvidia_smi_rtx5090.txt").read_text(encoding="utf-8"),
        "lspci": (FIXTURES / "lspci_nn_gpu.txt").read_text(encoding="utf-8"),
        "df": (FIXTURES / "df_root.txt").read_text(encoding="utf-8"),
    }
    outputs.update(overrides)
    return FixtureRunner(outputs)


def _detector(**overrides):
    return HardwareDetector(_runner(**overrides),
                            meminfo_path=str(FIXTURES / "meminfo_46g.txt"))


def test_cpu_detecte_depuis_lscpu_json():
    model, cores, arch = _detector().detect_cpu()
    assert cores > 0
    assert arch in ("x86_64", "amd64")
    assert model != "unknown"


def test_ram_detectee_depuis_meminfo():
    ram = _detector().detect_ram_gb()
    assert 40 < ram < 50  # fixture réelle : 48371672 kB ≈ 46.1 GiB


def test_gpu_nvidia_avec_vram_exacte():
    gpus = _detector().detect_gpus()
    nvidia = [g for g in gpus if g.vendor == "nvidia"]
    assert len(nvidia) == 1
    assert nvidia[0].vram_mb == 32607
    assert "RTX 5090" in nvidia[0].name


def test_gpu_amd_detecte_via_lspci():
    gpus = _detector().detect_gpus()
    assert any(g.vendor == "amd" for g in gpus)


def test_machine_sans_gpu_retourne_vide():
    detector = _detector(**{"nvidia-smi": "", "lspci": ""})
    detector.runner.outputs.pop("nvidia-smi")
    detector.runner.outputs.pop("lspci")
    assert detector.detect_gpus() == ()


def test_source_defaillante_ne_bloque_pas_le_reste():
    detector = _detector(lscpu="pas du json {{{")
    profile = detector.full_report()
    assert profile.cpu_model == "unknown"      # source CPU dégradée…
    assert profile.ram_gb > 40                 # …les autres sources répondent
    assert len(profile.gpus) >= 1


def test_disque_racine_detecte():
    disks = _detector().detect_disks()
    assert len(disks) == 1
    assert disks[0].path == "/"
    assert disks[0].total_gb > disks[0].free_gb > 0


def test_full_report_serialise_en_json():
    import json
    profile = _detector().full_report()
    data = json.loads(profile.to_json())
    assert {"cpu_model", "cpu_cores", "ram_gb", "gpus", "disks", "os_name"} <= set(data)
