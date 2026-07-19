from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sphere:
    num: int
    id: str
    name_fr: str
    name_en: str


SPHERES: tuple[Sphere, ...] = (
    Sphere(1, "S1", "Compute & runtime", "Compute & runtime"),
    Sphere(2, "S2", "Inférence & serving", "Inference & serving"),
    Sphere(3, "S3", "Modèles", "Models"),
    Sphere(4, "S4", "Gateway & routage", "Gateway & routing"),
    Sphere(5, "S5", "Orchestration & agents", "Orchestration & agents"),
    Sphere(6, "S6", "Mémoire & vecteurs", "Memory & vectors"),
    Sphere(7, "S7", "Connaissance & RAG", "Knowledge & RAG"),
    Sphere(8, "S8", "Outils & MCP", "Tools & MCP"),
    Sphere(9, "S9", "Guardrails & sûreté", "Guardrails & safety"),
    Sphere(10, "S10", "Sécurité & secrets", "Security & secrets"),
    Sphere(11, "S11", "Gouvernance & audit", "Governance & audit"),
    Sphere(12, "S12", "Observabilité", "Observability"),
    Sphere(13, "S13", "Évaluation", "Evaluation"),
    Sphere(14, "S14", "Déploiement", "Deployment"),
    Sphere(15, "VOIX", "Voix — temps réel", "Voice — real-time"),
)

SPHERE_IDS = frozenset(s.id for s in SPHERES)

_BASE: dict[str, str] = {
    "Orchestration, agents et interfaces": "S5",
    "MCP et protocoles d'interopérabilité": "S8",
    "Modèles d'embeddings et de reranking": "S3",
    "Entraînement, fine-tuning, quantization et fusion": "S3",
    "Auto-amélioration et recherche expérimentale": "S13",
    "Données, stockage et messagerie": "S6",
    "Blueprints, starters et plateformes spécialisées": "S5",
    "Orchestration / agents": "S5",
    "Mémoire / contexte": "S6",
}

_VOICE_RE = re.compile(
    r"\b("
    r"pipecat|livekit|whisper|parakeet|kokoro|xtts|f5-tts|chatts|tts|stt|vad|voix|voice|speech|audio\s+temps\s+réel"
    r")\b",
    flags=re.IGNORECASE,
)


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(kw in text for kw in keywords)


def classify_sphere(entry: dict) -> str:
    cat = entry.get("category", "")
    text = " ".join(
        str(entry.get(k, "")) for k in ("id", "name", "description_fr", "description_en")
    ).lower()

    if _VOICE_RE.search(text):
        return "VOIX"

    if cat == "Inférence, serving et gateway modèles":
        gateway_kws = {
            "gateway",
            "litellm",
            "router",
            "routing",
            "portkey",
            "higress",
            "bifrost",
            "openrouter",
            "proxy",
            "archgw",
            "plano",
        }
        return "S4" if _contains_any(text, gateway_kws) else "S2"

    if cat == "RAG, vecteurs, ingestion et mémoire agentique":
        memory_kws = {
            "mem0",
            "memos",
            "zep",
            "letta",
            "cognee",
            "graphiti",
            "langmem",
            "hipporag",
            "memary",
            "memobase",
            "memoripy",
            "motorhead",
            "memory",
            "mémoire",
            "vector",
            "vecteur",
            "qdrant",
            "weaviate",
            "milvus",
            "pgvector",
            "chroma",
            "faiss",
            "lancedb",
            "redis",
        }
        return "S6" if _contains_any(text, memory_kws) else "S7"

    if cat == "Infrastructure, Kubernetes, IaC et livraison":
        deploy_kws = {
            "gitops",
            "argo",
            "flux",
            "terraform",
            "opentofu",
            "pulumi",
            "helm",
            "ci/cd",
            "ci-cd",
            "delivery",
            "livraison",
            "kserve",
            "bentoml",
            "kustomize",
        }
        return "S14" if _contains_any(text, deploy_kws) else "S1"

    if cat == "Évaluation, observabilité, guardrails et sécurité":
        sec_kws = {
            "secret",
            "vault",
            "openbao",
            "sops",
            "infisical",
            "sandbox",
            "gvisor",
            "firecracker",
            "e2b",
            "cert-manager",
            "keycloak",
            "spiffe",
            "spire",
        }
        if _contains_any(text, sec_kws):
            return "S10"

        guard_kws = {
            "guardrail",
            "guard",
            "presidio",
            "pii",
            "rebuff",
            "garak",
            "jailbreak",
            "injection",
            "llama-guard",
            "nemo-guardrail",
            "vigil",
            "lakera",
        }
        if _contains_any(text, guard_kws):
            return "S9"

        obs_kws = {
            "observ",
            "trace",
            "tracing",
            "langfuse",
            "phoenix",
            "opik",
            "prometheus",
            "grafana",
            "telemetry",
            "otel",
            "openlit",
            "metering",
            "loki",
            "tempo",
        }
        if _contains_any(text, obs_kws):
            return "S12"

        eval_kws = {
            "eval",
            "évalu",
            "benchmark",
            "ragas",
            "deepeval",
            "promptfoo",
            "giskard",
            "trulens",
            "harness",
        }
        if _contains_any(text, eval_kws):
            return "S13"

        return "S9"

    if cat == "Harness de codage, méthodologies et gouvernance":
        gov_kws = {
            "governance",
            "gouvernance",
            "policy",
            "opa",
            "rego",
            "audit",
            "registre",
            "ledger",
            "sign",
            "cosign",
            "sigstore",
            "lineage",
            "datahub",
            "openlineage",
            "immudb",
            "kyverno",
        }
        return "S11" if _contains_any(text, gov_kws) else "S5"

    return _BASE.get(cat, "S5")


def spheres_index(entries: list[dict]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {sid: [] for sid in SPHERE_IDS}
    for entry in entries:
        sid = classify_sphere(entry)
        index[sid].append(entry.get("id", ""))
    for sid in index:
        index[sid].sort()
    return index


def sphere_of(brick_id: str, entries: list[dict]) -> str | None:
    for entry in entries:
        if entry.get("id") == brick_id:
            return classify_sphere(entry)
    return None
