"""Story S4 — « au choix » FILTRÉ par vendor : un moteur incompatible avec le vendor du nœud
cible est rejeté à la sélection. Source de vérité : moteurs-inference.json (gpu_vendors par moteur).
Ex. tensorrt-llm (nvidia-only) sur un nœud AMD => refusé. Une entrée sans vendor connu = ignorée.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.engines import (
    compatible_engines,
    engine_supports_vendor,
    engine_vendors,
    incompatible_selections,
)


def test_tensorrt_llm_nvidia_pas_amd():
    assert engine_supports_vendor("tensorrt-llm", "nvidia") is True
    assert engine_supports_vendor("tensorrt-llm", "amd") is False


def test_llama_cpp_multi_vendor():
    for v in ("nvidia", "amd", "intel", "cpu"):
        assert engine_supports_vendor("llama-cpp", v) is True


def test_compatible_engines_amd_exclut_nvidia_only():
    amd = compatible_engines("amd")
    assert "llama-cpp" in amd and "vllm" in amd
    assert "tensorrt-llm" not in amd and "lorax" not in amd and "lmdeploy" not in amd


def test_compatible_engines_nvidia_inclut_tensorrt():
    nv = compatible_engines("nvidia")
    assert "tensorrt-llm" in nv and "vllm" in nv


def test_engine_inconnu_aucun_vendor():
    assert engine_vendors("inexistant") == ()
    assert engine_supports_vendor("inexistant", "nvidia") is False


def test_incompatible_selections():
    sels = [
        {"engine": "tensorrt-llm", "vendor": "amd"},  # incompatible -> signalé
        {"engine": "llama-cpp", "vendor": "amd"},     # compatible
        {"engine": "vllm", "vendor": ""},             # vendor inconnu -> ignoré (pas de faux rejet)
    ]
    assert incompatible_selections(sels) == ["tensorrt-llm@amd"]
