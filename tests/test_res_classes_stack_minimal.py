"""Tests RED du correctif LAB-033N — assignation des classes de ressources du stack minimal.

Pourquoi : le finding LAB-033N a montré que le moteur ollama héritait de la classe
par défaut « utilitaire » (limits 256 Mi), ce qui provoquait un OOMKilled au
chargement des bibliothèques GPU. Ces tests vérifient que l'overlay minimal
déclare les classes « llm » et « db » et que `assemble_plan` les propage
correctement jusqu'au rendu K3s, sans régresser la réservation GPU.
"""
from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

import pytest

from forgeai.core.models import NodeInventaire, RenderTarget
from forgeai.planner.assemble import assemble_plan
from forgeai.renderers.k3s import render_k3s


def _minimal_overlay() -> Path:
    """Chemin de l'overlay minimal embarqué dans le package forgeai.data."""
    return Path(str(importlib.resources.files("forgeai.data") / "deploy-minimal.json"))


def test_ollama_du_stack_minimal_en_classe_llm():
    """ollama doit obtenir les ressources de la classe llm (limits 8Gi / requests 4Gi)."""
    plan = assemble_plan("minimal-gpu-cuda", _minimal_overlay(), target=RenderTarget.K3S)
    ollama = next(s for s in plan.services if s.name == "ollama")
    assert ollama.ressources_effectives["limits"]["memory"] == "8Gi"
    assert ollama.ressources_effectives["requests"]["memory"] == "4Gi"


def test_vector_store_du_stack_minimal_en_classe_db():
    """vector-store doit obtenir les ressources de la classe db (limits 2Gi)."""
    plan = assemble_plan("minimal-gpu-cuda", _minimal_overlay(), target=RenderTarget.K3S)
    vector_store = next(s for s in plan.services if s.name == "vector-store")
    assert vector_store.ressources_effectives["limits"]["memory"] == "2Gi"


def test_rendu_k3s_ollama_8gi_et_gpu_conserve():
    """Le rendu K3s doit conserver 8Gi pour ollama ET la réservation nvidia.com/gpu."""
    plan = assemble_plan("minimal-gpu-cuda", _minimal_overlay(), target=RenderTarget.K3S)
    rendered = render_k3s(
        plan,
        node="noeud-x",
        inventaire=(NodeInventaire(hostname="noeud-x", gpu_vendor="nvidia", vram_mib=16303),),
    )
    assert 'memory: "8Gi"' in rendered
    assert 'nvidia.com/gpu: "1"' in rendered


def test_service_sans_classe_reste_utilitaire(tmp_path):
    """Un service sans champ resource_class reste en classe utilitaire (rétrocompatibilité)."""
    overlay = tmp_path / "overlay.json"
    overlay.write_text(
        json.dumps(
            {
                "profile": "minimal",
                "engine_default": "ollama",
                "services": [
                    {
                        "name": "ollama",
                        "brick_id": "ollama",
                        "image": "ollama/ollama:latest@sha256:0000000000000000000000000000000000000000000000000000000000000000",
                        "container_port": 11434,
                        "healthcheck_path": "/api/tags",
                        "gpu_capable": True,
                    }
                ],
                "models": {"llm": "qwen2.5:0.5b", "embed": "nomic-embed-text"},
            }
        ),
        encoding="utf-8",
    )
    plan = assemble_plan("minimal-gpu-cuda", overlay, target=RenderTarget.K3S)
    svc = plan.services[0]
    assert svc.resource_class == "utilitaire"
    assert svc.ressources_effectives["limits"]["memory"] == "256Mi"
