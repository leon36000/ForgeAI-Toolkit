import json

import pytest

from forgeai.catalogue.spheres import (
    SPHERES,
    SPHERE_IDS,
    classify_sphere,
    spheres_index,
    sphere_of,
)
from forgeai.resources import catalogue_path


def _entries() -> list[dict]:
    data = json.loads(catalogue_path().read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data["entries"]


def test_14_spheres() -> None:
    assert len(SPHERES) == 15
    assert {s.id for s in SPHERES} == SPHERE_IDS
    assert len(SPHERE_IDS) == 15


def test_catalogue_reel_tout_classe() -> None:
    for entry in _entries():
        assert classify_sphere(entry) in SPHERE_IDS


def test_ancres() -> None:
    assert (
        classify_sphere(
            {
                "category": "Inférence, serving et gateway modèles",
                "id": "litellm",
                "name": "LiteLLM",
                "description_en": "unified gateway proxy",
            }
        )
        == "S4"
    )

    assert (
        classify_sphere(
            {
                "category": "Inférence, serving et gateway modèles",
                "id": "vllm",
                "name": "vLLM",
                "description_en": "inference serving engine",
            }
        )
        == "S2"
    )

    assert (
        classify_sphere(
            {
                "category": "RAG, vecteurs, ingestion et mémoire agentique",
                "id": "qdrant",
                "name": "Qdrant",
                "description_en": "vector database",
            }
        )
        == "S6"
    )

    assert (
        classify_sphere(
            {
                "category": "RAG, vecteurs, ingestion et mémoire agentique",
                "id": "ragflow",
                "name": "RAGFlow",
                "description_en": "rag retrieval engine",
            }
        )
        == "S7"
    )

    assert (
        classify_sphere(
            {
                "category": "Modèles d'embeddings et de reranking",
                "id": "bge-m3",
                "name": "BGE-M3",
                "description_en": "embedding model",
            }
        )
        == "S3"
    )

    assert (
        classify_sphere(
            {
                "category": "Évaluation, observabilité, guardrails et sécurité",
                "id": "openbao",
                "name": "OpenBao",
                "description_en": "secrets vault",
            }
        )
        == "S10"
    )

    assert (
        classify_sphere(
            {
                "category": "Évaluation, observabilité, guardrails et sécurité",
                "id": "nemo-guardrails",
                "name": "NeMo Guardrails",
                "description_en": "guardrails",
            }
        )
        == "S9"
    )

    assert (
        classify_sphere(
            {
                "category": "Évaluation, observabilité, guardrails et sécurité",
                "id": "langfuse",
                "name": "Langfuse",
                "description_en": "observability tracing",
            }
        )
        == "S12"
    )

    assert (
        classify_sphere(
            {
                "category": "Évaluation, observabilité, guardrails et sécurité",
                "id": "ragas",
                "name": "Ragas",
                "description_en": "eval benchmark",
            }
        )
        == "S13"
    )

    assert (
        classify_sphere(
            {
                "category": "Infrastructure, Kubernetes, IaC et livraison",
                "id": "argo-cd",
                "name": "Argo CD",
                "description_en": "gitops continuous delivery",
            }
        )
        == "S14"
    )

    assert (
        classify_sphere(
            {
                "category": "Infrastructure, Kubernetes, IaC et livraison",
                "id": "k3s",
                "name": "K3s",
                "description_en": "lightweight kubernetes",
            }
        )
        == "S1"
    )

    assert (
        classify_sphere(
            {
                "category": "Orchestration, agents et interfaces",
                "id": "n8n",
                "name": "n8n",
                "description_en": "workflow automation",
            }
        )
        == "S5"
    )

    assert (
        classify_sphere(
            {
                "category": "MCP et protocoles d'interopérabilité",
                "id": "mcp-servers",
                "name": "MCP Servers",
                "description_en": "model context protocol servers",
            }
        )
        == "S8"
    )


def test_index_couvre_tout() -> None:
    entries = _entries()
    idx = spheres_index(entries)
    assert set(idx) == SPHERE_IDS
    assert sum(len(v) for v in idx.values()) == len(entries)


def test_sphere_of() -> None:
    entries = _entries()
    real_id = entries[0]["id"]
    assert sphere_of(real_id, entries) in SPHERE_IDS
    assert sphere_of("id-inexistant-xyz", entries) is None
