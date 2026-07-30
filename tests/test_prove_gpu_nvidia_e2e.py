"""Tests CI de LAB-033N pour scripts/proof/prove_gpu_nvidia_e2e.py.

Ces tests n'utilisent aucun cluster, réseau, SSH ou subprocess : ils exercent
uniquement les fonctions pures du script (parsing, dérivation, rendu,
extraction de namespace, détection d'usage GPU).

La constante _JSON_SONDE_SYNTHETIQUE fournit des données SYNTHÉTIQUES
imitant la forme de `forgeai hardware` — jamais présentées comme mesures réelles.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_spec = importlib.util.spec_from_file_location(
    "prove_gpu_nvidia_e2e",
    _REPO / "scripts" / "proof" / "prove_gpu_nvidia_e2e.py",
)
prove = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prove)


# Données SYNTHÉTIQUES imitant la forme de `forgeai hardware`
# — jamais présentées comme mesures réelles.
_JSON_SONDE_SYNTHETIQUE = """
{
  "cpu_model": "CPU-TEST x86",
  "cpu_cores": 8,
  "cpu_arch": "x86_64",
  "ram_gb": 32.0,
  "os_name": "Linux",
  "gpus": [
    {"vendor": "nvidia", "name": "GPU-TEST-16G", "vram_mb": 16303},
    {"vendor": "nvidia", "name": "GPU-TEST-8G", "vram_mb": 8192}
  ],
  "disks": [
    {"path": "/", "total_gb": 1000.0, "free_gb": 500.0}
  ]
}
"""


def _hardware_from_json(json_text: str) -> object:
    """Reconstruit un HardwareProfile depuis une chaîne JSON."""
    return prove.reconstruct_hardware(json.loads(json_text))


def test_parse_puis_profil_cuda() -> None:
    """Le JSON synthétique à deux GPU NVIDIA doit dériver exactement vers minimal-gpu-cuda."""
    hw = _hardware_from_json(_JSON_SONDE_SYNTHETIQUE)
    assert prove.require_gpu_profile(hw) == "minimal-gpu-cuda"


def test_render_only_manifeste_gpu_complet() -> None:
    """Le rendu K3s pour le profil GPU CUDA doit contenir l'annotation GPU, le placement,
    les labels PSS, le service ollama et la NetworkPolicy."""
    hw = _hardware_from_json(_JSON_SONDE_SYNTHETIQUE)
    manifest = prove.render_manifest("minimal-gpu-cuda", "noeud-test-nvidia", hw)

    assert "nvidia.com/gpu" in manifest
    assert re.search(r'nvidia\.com/gpu:\s*["\']?1["\']?', manifest) is not None
    assert "pod-security.kubernetes.io/enforce" in manifest
    assert "kubernetes.io/hostname: noeud-test-nvidia" in manifest
    assert "app: ollama" in manifest
    assert "kind: NetworkPolicy" in manifest


def test_namespace_extrait_du_manifeste() -> None:
    """Le namespace rendu par render_k3s est forgeai-minimal."""
    hw = _hardware_from_json(_JSON_SONDE_SYNTHETIQUE)
    manifest = prove.render_manifest("minimal-gpu-cuda", "noeud-test-nvidia", hw)
    assert prove.namespace_from_manifest(manifest) == "forgeai-minimal"


def test_refus_sans_gpu_nvidia_utilisable() -> None:
    """Un GPU NVIDIA sous le seuil CUDA doit être refusé par require_gpu_profile."""
    data = json.loads(_JSON_SONDE_SYNTHETIQUE)
    data["gpus"] = [{"vendor": "nvidia", "name": "petit", "vram_mb": 2048}]
    hw = prove.reconstruct_hardware(data)

    with pytest.raises((SystemExit, prove.ProfileError)):
        prove.require_gpu_profile(hw)


def test_detection_usage_gpu_csv() -> None:
    """usage_gpu_detecte reconnaît un processus ollama avec mémoire GPU positive et
    rejette les en-têtes, les valeurs nulles et les marqueurs [N/A]."""
    sample_avec_usage = "pid, process_name, used_memory\n12345, ollama, 512 MiB"
    sample_entete_seul = "pid, process_name, used_memory"
    sample_zero = "12345, ollama, 0 MiB"
    sample_na = "pid, type, process_name, used_memory\n[N/A], [N/A], ollama, 1024 MiB"

    assert prove.usage_gpu_detecte([sample_avec_usage]) is True
    assert prove.usage_gpu_detecte([sample_entete_seul]) is False
    assert prove.usage_gpu_detecte([sample_zero]) is False
    assert prove.usage_gpu_detecte([sample_entete_seul, sample_zero]) is False
    assert prove.usage_gpu_detecte([sample_na]) is False
