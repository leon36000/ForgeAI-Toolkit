"""Tests S01 — détection hardware sur fixtures réelles capturées (machine forge, 2026-07-14)."""
import platform
import sys
from pathlib import Path

import pytest

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


def test_cpu_lscpu_partiellement_invalide_conserve_les_champs_deja_extraits(
    capsys: pytest.CaptureFixture,
) -> None:
    """Round 32 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : le behavior_contract de
    site:src/forgeai/hardware/detect.py:47 affirmait un repli COMPLET vers ("unknown", 0,
    platform.machine()) — faux pour un échec PARTIEL. model/cores/arch sont assignés
    SÉQUENTIELLEMENT ; un Model name valide suivi d'un CPU(s) non convertible lève APRÈS que
    `model` a déjà été réassigné avec succès — `model` reste donc la vraie valeur extraite, PAS
    "unknown", contrairement à l'ancien texte du contrat (corrigé dans le même commit)."""
    lscpu_partiellement_invalide = (
        '{"lscpu": ['
        '{"field": "Model name:", "data": "Un CPU bien réel"},'
        '{"field": "CPU(s):", "data": "pas-un-nombre"}'
        ']}'
    )
    detector = _detector(lscpu=lscpu_partiellement_invalide)
    model, cores, arch = detector.detect_cpu()
    assert model == "Un CPU bien réel"  # PAS "unknown" — déjà extrait avant l'échec
    assert cores == 0  # jamais assigné, reste au défaut initial
    assert arch == platform.machine()  # jamais atteint, reste au défaut initial
    captured = capsys.readouterr()
    assert "lscpu -J illisible" in captured.err


# --- RC1-456-iter3 : même famille que #482/#492/#527/#528 — `lscpu -J` documenté variable
# inter-distro/locale (gestion FR/EN déjà présente dans le fichier) ; la clé "lscpu" PRÉSENTE
# avec une valeur `null` (ou une entrée `null` au sein de la liste) fait actuellement lever
# TypeError, hors du tuple `except (JSONDecodeError, KeyError, ValueError)`. ---
def test_cpu_lscpu_cle_null_ne_leve_pas():
    """RC1-456-iter3 : {"lscpu": null} (clé présente, valeur null) ne doit jamais lever
    TypeError — dégradation propre vers les valeurs par défaut, comme un JSON invalide."""
    import json
    model, cores, arch = _detector(lscpu=json.dumps({"lscpu": None})).detect_cpu()
    assert model == "unknown"
    assert cores == 0


def test_cpu_lscpu_entree_null_dans_la_liste_ne_leve_pas():
    """RC1-456-iter3 : une entrée `null` au milieu d'une liste `lscpu` par ailleurs valide ne
    doit jamais lever AttributeError — l'entrée malformée est ignorée, les autres examinées."""
    import json
    brut = json.dumps({"lscpu": [None, {"field": "Architecture:", "data": "x86_64"}]})
    model, cores, arch = _detector(lscpu=brut).detect_cpu()
    assert arch == "x86_64"


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


def test_cpu_lscpu_illisible_journalise_et_replie(capsys: pytest.CaptureFixture) -> None:
    """Vérifie le repli sur les valeurs par défaut et le log stderr si lscpu est invalide."""
    detector = _detector(lscpu="ceci n'est pas du JSON")
    model, cores, arch = detector.detect_cpu()
    assert model == "unknown"
    assert cores == 0
    assert arch == platform.machine()
    captured = capsys.readouterr()
    assert "lscpu -J illisible" in captured.err


def test_ram_meminfo_illisible_journalise_et_replie(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Vérifie le repli à 0.0 Go et le log stderr si meminfo est illisible ou absent."""
    bad_meminfo = tmp_path / "meminfo_absent.txt"
    detector = HardwareDetector(_runner(), meminfo_path=str(bad_meminfo))
    ram = detector.detect_ram_gb()
    assert ram == 0.0
    captured = capsys.readouterr()
    assert "illisible" in captured.err


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


# --- HW-009 (FAI-U-009) : classification iGPU par PCI, pas par sous-chaîne de nom ---
from forgeai.core.models import Disk, HardwareProfile  # noqa: E402
from forgeai.planner.profile import derive_profile  # noqa: E402


def _hw(gpus):
    return HardwareProfile(cpu_model="x", cpu_cores=8, cpu_arch="x86_64", ram_gb=46.0,
                           os_name="Linux", gpus=tuple(gpus),
                           disks=(Disk(path="/", total_gb=500.0, free_gb=400.0),))


def test_igpu_amd_reel_non_promu_en_dgpu():
    """lspci réel : AMD [1002:13c0] = iGPU Raphael, VRAM inconnue. Le nom produit par lspci
    ('Advanced Micro Devices, Inc. ... Device') ne contient JAMAIS 'igpu'/'integrated' :
    l'ancienne heuristique de sous-chaîne le PROMEUT à tort en dGPU (minimal-gpu-rocm).
    Après classification PCI, l'iGPU est exclu -> minimal-cpu."""
    # fixture AMD-iGPU-only : isole le concern « iGPU non promu » (le scénario RTX-cassé+iGPU
    # est couvert par test_nvidia_present_mais_non_qualifie, HW-010, qui exige un refus explicite).
    lspci = (FIXTURES / "lspci_nn_amd_igpu_only.txt").read_text(encoding="utf-8")
    gpus = _detector(**{"nvidia-smi": "", "lspci": lspci}).detect_gpus()
    amd = [g for g in gpus if g.vendor == "amd"]
    assert amd, "iGPU AMD 13c0 non détecté"
    assert derive_profile(_hw(gpus)) == "minimal-cpu"  # iGPU exclu, aucun NVIDIA -> pas de refus


def test_dgpu_amd_discret_reste_utilisable():
    """Garde de précision : un dGPU AMD discret (Navi 31 [1002:744c], VRAM inconnue via lspci)
    NE doit PAS être exclu par erreur -> minimal-gpu-rocm reste."""
    lspci = (FIXTURES / "lspci_nn_amd_dgpu.txt").read_text(encoding="utf-8")
    gpus = _detector(**{"nvidia-smi": "", "lspci": lspci}).detect_gpus()
    amd = [g for g in gpus if g.vendor == "amd"]
    assert amd and amd[0].vram_mb == 0
    assert derive_profile(_hw(gpus)) == "minimal-gpu-rocm"


def test_nvidia_present_mais_non_qualifie_ne_disparait_pas():
    """FAI-U-010 : nvidia-smi cassé/absent -> VRAM inconnue via lspci. Le GPU NVIDIA
    [10de:2b85] reste INVENTORIÉ (présence PCI), et le plan REFUSE de dégrader
    silencieusement en minimal-cpu : derive_profile lève ProfileError avec un diagnostic
    orientant vers la vérification driver/runtime (VRAM inconnue != 0 réel)."""
    import pytest
    from forgeai.planner.profile import ProfileError
    lspci = (FIXTURES / "lspci_nn_nvidia_only.txt").read_text(encoding="utf-8")
    gpus = _detector(**{"nvidia-smi": "", "lspci": lspci}).detect_gpus()
    nv = [g for g in gpus if g.vendor == "nvidia"]
    assert nv, "GPU NVIDIA a disparu quand nvidia-smi échoue (régression FAI-U-010)"
    with pytest.raises(ProfileError) as exc:
        derive_profile(_hw(gpus))
    msg = str(exc.value).lower()
    assert ("driver" in msg or "nvidia-smi" in msg or "qualifi" in msg), msg


def test_machine_reellement_sans_gpu_reste_cpu():
    """Garde : une machine SANS aucun GPU (ni nvidia-smi ni lspci) reste minimal-cpu,
    sans lever (le refus ne concerne QUE les GPU présents-mais-non-qualifiés)."""
    gpus = _detector(**{"nvidia-smi": "", "lspci": ""}).detect_gpus()
    assert not gpus  # aucun GPU (tuple vide)
    assert derive_profile(_hw(gpus)) == "minimal-cpu"


def test_print_stderr_fallback_ascii_si_encodage_incompatible(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que l'échec d'encodage sur stderr se replie proprement sans lever d'exception."""
    import io

    raw_buffer = io.BytesIO()
    fake_stderr = io.TextIOWrapper(raw_buffer, encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    detector = _detector(lscpu="ceci n'est pas du JSON")
    model, cores, arch = detector.detect_cpu()
    assert model == "unknown"
    assert cores == 0

    fake_stderr.flush()
    sortie = raw_buffer.getvalue()
    assert len(sortie) > 0
    assert b"lscpu" in sortie
