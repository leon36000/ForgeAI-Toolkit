# Story IMPL-1 — Couche 14 spheres du catalogue ForgeAI

## Objectif
Classer chaque brique du catalogue (948) dans UNE des 14 spheres d'infra IA. Module stdlib pur + tests.

## Criteres d'acceptation testables
- SPHERES = 14 (ids S1..S14 uniques).
- classify_sphere(entry) retourne TOUJOURS un id in {S1..S14} ; 948/948 briques classees (verifie).
- Ancres: litellm->S4, vllm->S2, qdrant->S6, ragflow->S7, bge-m3->S3, openbao->S10, nemo-guardrails->S9, langfuse->S12, ragas->S13, argo-cd->S14, k3s->S1, n8n->S5, mcp-servers->S8.
- spheres_index couvre toutes les entrees ; sphere_of(inexistant)->None ; stdlib pure ; no-stub.
- Preuve locale: 5/5 tests pytest verts, no-stub OK, 948/948 classees.

## Diff (main...impl/sphere-layer)
```diff
diff --git a/src/forgeai/catalogue/spheres.py b/src/forgeai/catalogue/spheres.py
new file mode 100644
index 0000000..a8e404c
--- /dev/null
+++ b/src/forgeai/catalogue/spheres.py
@@ -0,0 +1,229 @@
+from __future__ import annotations
+
+from dataclasses import dataclass
+
+
+@dataclass(frozen=True)
+class Sphere:
+    num: int
+    id: str
+    name_fr: str
+    name_en: str
+
+
+SPHERES: tuple[Sphere, ...] = (
+    Sphere(1, "S1", "Compute & runtime", "Compute & runtime"),
+    Sphere(2, "S2", "Inférence & serving", "Inference & serving"),
+    Sphere(3, "S3", "Modèles", "Models"),
+    Sphere(4, "S4", "Gateway & routage", "Gateway & routing"),
+    Sphere(5, "S5", "Orchestration & agents", "Orchestration & agents"),
+    Sphere(6, "S6", "Mémoire & vecteurs", "Memory & vectors"),
+    Sphere(7, "S7", "Connaissance & RAG", "Knowledge & RAG"),
+    Sphere(8, "S8", "Outils & MCP", "Tools & MCP"),
+    Sphere(9, "S9", "Guardrails & sûreté", "Guardrails & safety"),
+    Sphere(10, "S10", "Sécurité & secrets", "Security & secrets"),
+    Sphere(11, "S11", "Gouvernance & audit", "Governance & audit"),
+    Sphere(12, "S12", "Observabilité", "Observability"),
+    Sphere(13, "S13", "Évaluation", "Evaluation"),
+    Sphere(14, "S14", "Déploiement", "Deployment"),
+)
+
+SPHERE_IDS = frozenset(s.id for s in SPHERES)
+
+_BASE: dict[str, str] = {
+    "Orchestration, agents et interfaces": "S5",
+    "MCP et protocoles d'interopérabilité": "S8",
+    "Modèles d'embeddings et de reranking": "S3",
+    "Entraînement, fine-tuning, quantization et fusion": "S3",
+    "Auto-amélioration et recherche expérimentale": "S13",
+    "Données, stockage et messagerie": "S6",
+    "Blueprints, starters et plateformes spécialisées": "S5",
+    "Orchestration / agents": "S5",
+    "Mémoire / contexte": "S6",
+}
+
+
+def _contains_any(text: str, keywords: set[str]) -> bool:
+    return any(kw in text for kw in keywords)
+
+
+def classify_sphere(entry: dict) -> str:
+    cat = entry.get("category", "")
+    text = " ".join(
+        str(entry.get(k, "")) for k in ("id", "name", "description_fr", "description_en")
+    ).lower()
+
+    if cat == "Inférence, serving et gateway modèles":
+        gateway_kws = {
+            "gateway",
+            "litellm",
+            "router",
+            "routing",
+            "portkey",
+            "higress",
+            "bifrost",
+            "openrouter",
+            "proxy",
+            "archgw",
+            "plano",
+        }
+        return "S4" if _contains_any(text, gateway_kws) else "S2"
+
+    if cat == "RAG, vecteurs, ingestion et mémoire agentique":
+        memory_kws = {
+            "mem0",
+            "memos",
+            "zep",
+            "letta",
+            "cognee",
+            "graphiti",
+            "langmem",
+            "hipporag",
+            "memary",
+            "memobase",
+            "memoripy",
+            "motorhead",
+            "memory",
+            "mémoire",
+            "vector",
+            "vecteur",
+            "qdrant",
+            "weaviate",
+            "milvus",
+            "pgvector",
+            "chroma",
+            "faiss",
+            "lancedb",
+            "redis",
+        }
+        return "S6" if _contains_any(text, memory_kws) else "S7"
+
+    if cat == "Infrastructure, Kubernetes, IaC et livraison":
+        deploy_kws = {
+            "gitops",
+            "argo",
+            "flux",
+            "terraform",
+            "opentofu",
+            "pulumi",
+            "helm",
+            "ci/cd",
+            "ci-cd",
+            "delivery",
+            "livraison",
+            "kserve",
+            "bentoml",
+            "kustomize",
+        }
+        return "S14" if _contains_any(text, deploy_kws) else "S1"
+
+    if cat == "Évaluation, observabilité, guardrails et sécurité":
+        sec_kws = {
+            "secret",
+            "vault",
+            "openbao",
+            "sops",
+            "infisical",
+            "sandbox",
+            "gvisor",
+            "firecracker",
+            "e2b",
+            "cert-manager",
+            "keycloak",
+            "spiffe",
+            "spire",
+        }
+        if _contains_any(text, sec_kws):
+            return "S10"
+
+        guard_kws = {
+            "guardrail",
+            "guard",
+            "presidio",
+            "pii",
+            "rebuff",
+            "garak",
+            "jailbreak",
+            "injection",
+            "llama-guard",
+            "nemo-guardrail",
+            "vigil",
+            "lakera",
+        }
+        if _contains_any(text, guard_kws):
+            return "S9"
+
+        obs_kws = {
+            "observ",
+            "trace",
+            "tracing",
+            "langfuse",
+            "phoenix",
+            "opik",
+            "prometheus",
+            "grafana",
+            "telemetry",
+            "otel",
+            "openlit",
+            "metering",
+            "loki",
+            "tempo",
+        }
+        if _contains_any(text, obs_kws):
+            return "S12"
+
+        eval_kws = {
+            "eval",
+            "évalu",
+            "benchmark",
+            "ragas",
+            "deepeval",
+            "promptfoo",
+            "giskard",
+            "trulens",
+            "harness",
+        }
+        if _contains_any(text, eval_kws):
+            return "S13"
+
+        return "S9"
+
+    if cat == "Harness de codage, méthodologies et gouvernance":
+        gov_kws = {
+            "governance",
+            "gouvernance",
+            "policy",
+            "opa",
+            "rego",
+            "audit",
+            "registre",
+            "ledger",
+            "sign",
+            "cosign",
+            "sigstore",
+            "lineage",
+            "datahub",
+            "openlineage",
+            "immudb",
+            "kyverno",
+        }
+        return "S11" if _contains_any(text, gov_kws) else "S5"
+
+    return _BASE.get(cat, "S5")
+
+
+def spheres_index(entries: list[dict]) -> dict[str, list[str]]:
+    index: dict[str, list[str]] = {sid: [] for sid in SPHERE_IDS}
+    for entry in entries:
+        sid = classify_sphere(entry)
+        index[sid].append(entry.get("id", ""))
+    for sid in index:
+        index[sid].sort()
+    return index
+
+
+def sphere_of(brick_id: str, entries: list[dict]) -> str | None:
+    for entry in entries:
+        if entry.get("id") == brick_id:
+            return classify_sphere(entry)
+    return None
diff --git a/tests/test_spheres.py b/tests/test_spheres.py
new file mode 100644
index 0000000..4f7f3b4
--- /dev/null
+++ b/tests/test_spheres.py
@@ -0,0 +1,200 @@
+import json
+
+import pytest
+
+from forgeai.catalogue.spheres import (
+    SPHERES,
+    SPHERE_IDS,
+    classify_sphere,
+    spheres_index,
+    sphere_of,
+)
+from forgeai.resources import catalogue_path
+
+
+def _entries() -> list[dict]:
+    data = json.loads(catalogue_path().read_text(encoding="utf-8"))
+    return data if isinstance(data, list) else data["entries"]
+
+
+def test_14_spheres() -> None:
+    assert len(SPHERES) == 14
+    assert {s.id for s in SPHERES} == SPHERE_IDS
+    assert len(SPHERE_IDS) == 14
+
+
+def test_catalogue_reel_tout_classe() -> None:
+    for entry in _entries():
+        assert classify_sphere(entry) in SPHERE_IDS
+
+
+def test_ancres() -> None:
+    assert (
+        classify_sphere(
+            {
+                "category": "Inférence, serving et gateway modèles",
+                "id": "litellm",
+                "name": "LiteLLM",
+                "description_en": "unified gateway proxy",
+            }
+        )
+        == "S4"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Inférence, serving et gateway modèles",
+                "id": "vllm",
+                "name": "vLLM",
+                "description_en": "inference serving engine",
+            }
+        )
+        == "S2"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "RAG, vecteurs, ingestion et mémoire agentique",
+                "id": "qdrant",
+                "name": "Qdrant",
+                "description_en": "vector database",
+            }
+        )
+        == "S6"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "RAG, vecteurs, ingestion et mémoire agentique",
+                "id": "ragflow",
+                "name": "RAGFlow",
+                "description_en": "rag retrieval engine",
+            }
+        )
+        == "S7"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Modèles d'embeddings et de reranking",
+                "id": "bge-m3",
+                "name": "BGE-M3",
+                "description_en": "embedding model",
+            }
+        )
+        == "S3"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Évaluation, observabilité, guardrails et sécurité",
+                "id": "openbao",
+                "name": "OpenBao",
+                "description_en": "secrets vault",
+            }
+        )
+        == "S10"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Évaluation, observabilité, guardrails et sécurité",
+                "id": "nemo-guardrails",
+                "name": "NeMo Guardrails",
+                "description_en": "guardrails",
+            }
+        )
+        == "S9"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Évaluation, observabilité, guardrails et sécurité",
+                "id": "langfuse",
+                "name": "Langfuse",
+                "description_en": "observability tracing",
+            }
+        )
+        == "S12"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Évaluation, observabilité, guardrails et sécurité",
+                "id": "ragas",
+                "name": "Ragas",
+                "description_en": "eval benchmark",
+            }
+        )
+        == "S13"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Infrastructure, Kubernetes, IaC et livraison",
+                "id": "argo-cd",
+                "name": "Argo CD",
+                "description_en": "gitops continuous delivery",
+            }
+        )
+        == "S14"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Infrastructure, Kubernetes, IaC et livraison",
+                "id": "k3s",
+                "name": "K3s",
+                "description_en": "lightweight kubernetes",
+            }
+        )
+        == "S1"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "Orchestration, agents et interfaces",
+                "id": "n8n",
+                "name": "n8n",
+                "description_en": "workflow automation",
+            }
+        )
+        == "S5"
+    )
+
+    assert (
+        classify_sphere(
+            {
+                "category": "MCP et protocoles d'interopérabilité",
+                "id": "mcp-servers",
+                "name": "MCP Servers",
+                "description_en": "model context protocol servers",
+            }
+        )
+        == "S8"
+    )
+
+
+def test_index_couvre_tout() -> None:
+    entries = _entries()
+    idx = spheres_index(entries)
+    assert set(idx) == SPHERE_IDS
+    assert sum(len(v) for v in idx.values()) == len(entries)
+
+
+def test_sphere_of() -> None:
+    entries = _entries()
+    real_id = entries[0]["id"]
+    assert sphere_of(real_id, entries) in SPHERE_IDS
+    assert sphere_of("id-inexistant-xyz", entries) is None
```
