"""B-14 — validation des 3 templates souverains (RAG / Lab fine-tuning / Production)."""
import json

import pytest

from forgeai.resources import catalogue_path
from forgeai.templates import (
    load_template, validate_template, resolve_template, deployable_bricks, list_templates,
)

ENTRIES = json.loads(catalogue_path().read_text(encoding="utf-8"))["entries"]
B14 = ["rag-souverain", "lab-fine-tuning", "production-souveraine"]


@pytest.mark.parametrize("name", B14)
def test_template_valide_contre_catalogue(name):
    """Toutes les briques existent au catalogue et sont bilingues."""
    assert validate_template(load_template(name), ENTRIES) == []


@pytest.mark.parametrize("name", B14)
def test_template_liste_et_coeur_deployable(name):
    assert name in list_templates()
    t = load_template(name)
    assert len(t["bricks"]) >= 15
    assert deployable_bricks(t, has_gpu=False), "un cœur runtime déployable est requis (CPU)"


def test_rag_souverain_couvre_inference_embeddings_rag():
    roles = {b["role"] for b in load_template("rag-souverain")["bricks"]}
    assert {"inference", "embedding", "rag"} <= roles


def test_lab_fine_tuning_filtrage_gpu():
    t = load_template("lab-fine-tuning")
    cpu = {b["id"] for b in resolve_template(t, has_gpu=False)}
    assert "deepspeed" not in cpu and "unsloth" not in cpu  # entraînement gpu-only exclu sans GPU
    assert "deepspeed" in {b["id"] for b in resolve_template(t, has_gpu=True)}


def test_production_souveraine_vllm_gpu_only():
    t = load_template("production-souveraine")
    assert "vllm" not in {b["id"] for b in resolve_template(t, has_gpu=False)}
    assert "vllm" in {b["id"] for b in resolve_template(t, has_gpu=True)}
