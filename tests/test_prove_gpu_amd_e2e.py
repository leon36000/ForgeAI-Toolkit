"""Tests CI de LAB-033A pour scripts/proof/prove_gpu_amd_e2e.py.

Ces tests n'utilisent aucun cluster, réseau, SSH ou subprocess : ils exercent
uniquement les fonctions pures du script (parsing, dérivation, rendu,
extraction de namespace, détection d'usage GPU).

La constante _JSON_SONDE_AMD_SYNTHETIQUE fournit des données SYNTHÉTIQUES
imitant la forme de `forgeai hardware` — jamais présentées comme mesures réelles.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_spec = importlib.util.spec_from_file_location(
    "prove_gpu_amd_e2e",
    _REPO / "scripts" / "proof" / "prove_gpu_amd_e2e.py",
)
prove = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prove)


# Données SYNTHÉTIQUES imitant la forme de `forgeai hardware`
# — jamais présentées comme mesures réelles.
_JSON_SONDE_AMD_SYNTHETIQUE = """
{
  "cpu_model": "AMD Ryzen 9 9950X3D2 x86",
  "cpu_cores": 32,
  "cpu_arch": "x86_64",
  "ram_gb": 45.1,
  "os_name": "Linux",
  "gpus": [
    {"vendor": "amd", "name": "AMD Radeon AI PRO R9700 [1002:7551]", "vram_mb": 0},
    {"vendor": "amd", "name": "AMD Radeon RX 9070 XT [1002:7550]", "vram_mb": 0},
    {"vendor": "amd", "name": "AMD Granite Ridge [1002:13c0] [integrated]", "vram_mb": 0}
  ],
  "disks": [
    {"path": "/", "total_gb": 936.0, "free_gb": 747.0}
  ]
}
"""


def _hardware_from_json(json_text: str) -> object:
    """Reconstruit un HardwareProfile depuis une chaîne JSON."""
    return prove.reconstruct_hardware(json.loads(json_text))


def test_derive_profile_amd():
    """Le profil dérivé d'une sonde AMD avec deux dGPU doit être minimal-gpu-rocm."""
    hw = _hardware_from_json(_JSON_SONDE_AMD_SYNTHETIQUE)
    assert prove.require_gpu_profile(hw) == "minimal-gpu-rocm"


def test_manifeste_rendu_amd():
    """Le manifeste AMD utilise la ressource de device plugin amd.com/gpu (LAB-033A).
    Le passthrough hostPath /dev/kfd+/dev/dri est supprimé : le cgroup devices refuse
    l'accès au char device. Le niveau PSA enforce passe à baseline pour un plan GPU."""
    hw = _hardware_from_json(_JSON_SONDE_AMD_SYNTHETIQUE)
    prove.require_gpu_profile(hw)
    manifest = prove.render_manifest("minimal-gpu-rocm", "noeud-test-amd", hw)

    assert 'amd.com/gpu: "1"' in manifest
    assert "nvidia.com/gpu" not in manifest
    assert "enforce: baseline" in manifest
    assert "kubernetes.io/hostname: noeud-test-amd" in manifest
    assert "allowPrivilegeEscalation: false" in manifest
    # Vérification YAML : aucun volume ne porte la clé hostPath.
    for doc in yaml.safe_load_all(manifest):
        if doc and doc.get("kind") == "Deployment":
            for vol in doc["spec"]["template"]["spec"].get("volumes") or []:
                assert "hostPath" not in vol, f"volume hostPath interdit : {vol}"


def test_namespace_extraction():
    """Le namespace extrait du manifeste rendu est forgeai-minimal."""
    hw = _hardware_from_json(_JSON_SONDE_AMD_SYNTHETIQUE)
    manifest = prove.render_manifest("minimal-gpu-rocm", "noeud-test-amd", hw)
    assert prove.namespace_from_manifest(manifest) == "forgeai-minimal"


def test_refus_igpu_seul():
    """Un JSON avec pour seul GPU l'iGPU AMD intégré est refusé (pas de manifeste GPU)."""
    json_igpu = """
    {
      "cpu_model": "AMD Ryzen 9 9950X3D2 x86",
      "cpu_cores": 32,
      "cpu_arch": "x86_64",
      "ram_gb": 45.1,
      "os_name": "Linux",
      "gpus": [
        {"vendor": "amd", "name": "AMD Granite Ridge [1002:13c0] [integrated]", "vram_mb": 0}
      ],
      "disks": [
        {"path": "/", "total_gb": 936.0, "free_gb": 747.0}
      ]
    }
    """
    hw = _hardware_from_json(json_igpu)
    with pytest.raises(SystemExit) as exc_info:
        prove.require_gpu_profile(hw)
    assert exc_info.value.code == 2


def test_usage_gpu_amd_detecte():
    """usage_gpu_amd_detecte valide uniquement l'activité d'un dGPU AMD, jamais l'iGPU seul."""
    repos = {
        "card0": {
            "pci_id": "0x7550",
            "vram_used": 60 * 1024 * 1024,
            "busy": 0,
            "integrated": False,
        },
        "card1": {
            "pci_id": "0x7551",
            "vram_used": 89 * 1024 * 1024,
            "busy": 0,
            "integrated": False,
        },
        "card2": {
            "pci_id": "0x13c0",
            "vram_used": 17 * 1024 * 1024,
            "busy": 0,
            "integrated": True,
        },
    }

    # (a) Croissance de VRAM >= 256 Mio sur une carte discrète.
    echantillons_vram = [
        {
            "card0": {
                "pci_id": "0x7550",
                "vram_used": (60 + 300) * 1024 * 1024,
                "busy": 0,
                "integrated": False,
            }
        }
    ]
    assert prove.usage_gpu_amd_detecte(repos, echantillons_vram) is True

    # (b) gpu_busy_percent > 0 sur une carte discrète.
    echantillons_busy = [
        {
            "card1": {
                "pci_id": "0x7551",
                "vram_used": 89 * 1024 * 1024,
                "busy": 5,
                "integrated": False,
            }
        }
    ]
    assert prove.usage_gpu_amd_detecte(repos, echantillons_busy) is True

    # (c) Seule l'iGPU bouge : refusé.
    echantillons_igpu = [
        {
            "card2": {
                "pci_id": "0x13c0",
                "vram_used": (17 + 300) * 1024 * 1024,
                "busy": 5,
                "integrated": True,
            }
        }
    ]
    assert prove.usage_gpu_amd_detecte(repos, echantillons_igpu) is False

    # (d) Échantillons vides ou identiques au repos : pas d'usage détecté.
    assert prove.usage_gpu_amd_detecte(repos, []) is False
    assert prove.usage_gpu_amd_detecte(repos, [repos]) is False
