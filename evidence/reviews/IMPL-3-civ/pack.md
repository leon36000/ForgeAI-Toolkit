# Story IMPL-3 — 6 profils de deploiement synergiques (data/stacks + loader)

## Objectif
Le SET DEPLOYE (ce qui demarre par defaut, cable) de chaque stack, issu de la recherche de perfection sourcee (fichiers *-perfect.md). Le catalogue = univers d'options ; le profil = defauts deployes + cablage.

## Criteres d'acceptation
- 6 profils data/stacks/*.json (assistant/agentique/support/automatisation/mlops/tout-en-un) ; loader stacks.py (list_stacks/load_stack/deploy_ids/validate_stack).
- Tous les ids deployes existent dans catalogue.json (1577) ; base_rag_durci=true + defaut S4=litellm (gateway unique) + hermes-agent deploye partout ; superpowers+openclaw en agentique ; wiring reel (>=3) + config_critique presents ; fondamentaux/weights (default_eligible=false) hors deploy.
- Preuve : 7 tests test_stacks + suite COMPLETE verte ; no-stub OK ; catalogue_gate inchange.

## PREUVE D'EXECUTION (sortie reelle)
```
### pytest tests/test_stacks.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /media/pc1/Storage/Repo/ForgeAI Toolkit
configfile: pyproject.toml
plugins: typeguard-4.4.3, langsmith-0.9.4, anyio-4.14.1, Faker-37.12.0, cov-7.1.0
collected 7 items

tests/test_stacks.py .......                                             [100%]

============================== 7 passed in 0.03s ===============================

### SUITE COMPLETE
........................................................................ [ 80%]
.....................................................................    [100%]

### no_stub
NO-STUB-SCAN : OK (2 fichiers scannés, zéro violation)

### catalogue_gate (non touché)
CATALOGUE-GATE : OK (1577 entrées, zéro ambiguïté)

### résumé profils (nb déployé/profil)
  agentique = 72 briques déployées ; défaut S5= hermes-agent
  assistant-entreprise = 102 briques déployées ; défaut S5= hermes-agent
  automatisation = 69 briques déployées ; défaut S5= n8n
  mlops = 104 briques déployées ; défaut S5= zenml
  support-conversationnel = 55 briques déployées ; défaut S5= langgraph
  tout-en-un = 188 briques déployées ; défaut S5= hermes-agent
```

## DIFF COMPLET (main...HEAD) — 6 profils + loader + tests
```diff
diff --git a/src/forgeai/data/stacks/agentique.json b/src/forgeai/data/stacks/agentique.json
new file mode 100644
index 0000000..8697bbd
--- /dev/null
+++ b/src/forgeai/data/stacks/agentique.json
@@ -0,0 +1,145 @@
+{
+ "id": "agentique",
+ "name": "Agentique (agents autonomes outilles)",
+ "description_fr": "Agents autonomes en boucle event-stream (User->Agent->LLM->Action->Runtime sandbox->Observation), harness Hermes + Superpowers + OpenClaw, outils MCP untrusted en sandbox derriere guardrails, memoire agent 4 couches distincte du RAG.",
+ "description_en": "Autonomous agents on an event-stream loop (User->Agent->LLM->Action->sandbox Runtime->Observation), Hermes + Superpowers + OpenClaw harness, untrusted MCP tools sandboxed behind guardrails, 4-layer agent memory kept distinct from RAG.",
+ "base_rag_durci": true,
+ "deploy_by_sphere": {
+  "S1": [
+   "k3s",
+   "nvidia-gpu-operator",
+   "kueue",
+   "volcano",
+   "longhorn",
+   "cloudnativepg"
+  ],
+  "S2": [
+   "vllm",
+   "sglang",
+   "ollama",
+   "text-embeddings-inference-tei",
+   "infinity"
+  ],
+  "S3": [
+   "bge-m3",
+   "bge-reranker-v2-m3",
+   "sentence-transformers"
+  ],
+  "S4": [
+   "litellm",
+   "redis",
+   "routellm",
+   "vllm-semantic-router"
+  ],
+  "S5": [
+   "hermes-agent",
+   "hermes-workspace",
+   "superpowers",
+   "openclaw",
+   "langgraph",
+   "n8n",
+   "openhands",
+   "langchain"
+  ],
+  "S6": [
+   "mem0",
+   "graphiti",
+   "zep",
+   "letta",
+   "cognee",
+   "langmem",
+   "qdrant",
+   "neo4j"
+  ],
+  "S7": [
+   "ragflow",
+   "lightrag",
+   "graphrag",
+   "markitdown",
+   "docling",
+   "mineru"
+  ],
+  "S8": [
+   "mcp-servers",
+   "langchain-mcp-adapters",
+   "fastmcp-python",
+   "filesystem-mcp",
+   "github-mcp-officiel",
+   "ibm-mcp-context-forge"
+  ],
+  "S9": [
+   "nemo-guardrails",
+   "llama-guard",
+   "llamafirewall",
+   "promptguard",
+   "rebuff",
+   "garak"
+  ],
+  "S10": [
+   "e2b-code-interpreter",
+   "gvisor",
+   "firecracker",
+   "openbao",
+   "external-secrets-operator",
+   "cosign-sigstore",
+   "trivy"
+  ],
+  "S11": [
+   "openmeter",
+   "immudb",
+   "opa-rego",
+   "kyverno"
+  ],
+  "S12": [
+   "langfuse",
+   "arize-phoenix"
+  ],
+  "S13": [
+   "ragas",
+   "deepeval",
+   "swe-bench",
+   "promptfoo"
+  ],
+  "S14": [
+   "argo-cd",
+   "kserve",
+   "kubeai"
+  ]
+ },
+ "default_by_sphere": {
+  "S1": "k3s",
+  "S2": "vllm",
+  "S3": "bge-m3",
+  "S4": "litellm",
+  "S5": "hermes-agent",
+  "S6": "mem0",
+  "S7": "ragflow",
+  "S8": "mcp-servers",
+  "S9": "nemo-guardrails",
+  "S10": "e2b-code-interpreter",
+  "S11": "immudb",
+  "S12": "langfuse",
+  "S13": "ragas",
+  "S14": "argo-cd"
+ },
+ "wiring": [
+  "boucle agent (openhands event-stream) : User->hermes-agent->litellm->Action->runtime sandbox->Observation->Agent ; patterns orchestrator-workers / evaluator-optimizer",
+  "harness : superpowers (methodo/skills IMPOSES) + openclaw + hermes-agent (runtime) ; couches distinctes qui composent",
+  "langgraph = sous-graphes stateful (checkpoint redis, HITL) ; n8n = triggers/integrations declenchant langgraph en HTTP",
+  "tout appel -> litellm (virtual-key/budget par agent) -> vllm/sglang (prod) + ollama (dev) ; routellm/vllm-semantic-router pour le cout",
+  "kueue/volcano ordonnancent le GPU entre vllm/sglang/ollama (time-share) ; poids sur PVC RO ; readiness /health",
+  "spine retrieval : bge-m3 (text-embeddings-inference-tei/infinity) + bge-reranker-v2-m3 + qdrant ; ragflow expose en tool MCP a l'agent ; lightrag/graphrag routes par type de requete",
+  "memoire agent (S6, 4 couches) mem0(perso)+graphiti/zep(KG temporel)+letta(runtime paging)+cognee(doc->KG) sur qdrant+neo4j : distincte du plan RAG (memoire = read-write stateful, RAG = read-only)",
+  "outils MCP untrusted derriere guardrails/allow-list (nemo-guardrails + llama-guard/llamafirewall/promptguard) en sandbox e2b-code-interpreter/gvisor/firecracker ; secrets external-secrets-operator/openbao",
+  "obs/eval/gouv : langfuse trace chaque step ; CI ragas/deepeval/swe-bench ; metering openmeter + ledger immudb ; images signees cosign-sigstore + scan trivy -> argo-cd GitOps"
+ ],
+ "config_critique": {
+  "LITELLM_VIRTUAL_KEY": "1 cle virtuelle par agent : budget + quota + fallback + callback Langfuse",
+  "AGENT_TOOLS_UNTRUSTED": "tout tool MCP = untrusted -> allow-list nemo-guardrails + llamafirewall AVANT execution",
+  "SANDBOX_EXEC": "chaque Action code s'execute en sandbox e2b-code-interpreter / gvisor / firecracker (jamais sur l'hote)",
+  "GPU_TIMESHARE": "kueue/volcano gang-scheduling ; vllm(prod) et ollama(dev) partagent le GPU en time-share, pas en conflit",
+  "LANGGRAPH_CHECKPOINT": "checkpoint Redis + human-in-the-loop (HITL) sur les sous-graphes stateful",
+  "SUPPLY_CHAIN_GATE": "cosign-sigstore (signature image) + trivy (scan) AVANT argo-cd sync"
+ },
+ "surface": "hermes-agent"
+}
\ No newline at end of file
diff --git a/src/forgeai/data/stacks/assistant-entreprise.json b/src/forgeai/data/stacks/assistant-entreprise.json
new file mode 100644
index 0000000..43e49c8
--- /dev/null
+++ b/src/forgeai/data/stacks/assistant-entreprise.json
@@ -0,0 +1,175 @@
+{
+ "id": "assistant-entreprise",
+ "name": "Assistant d'entreprise / Copilote",
+ "description_fr": "Copilote d'entreprise multi-tenant : chat + recherche entreprise permission-aware (ACL), RAG durci profond et memoire multi-couches, Hermes comme cerveau unifiant, gouvernance par tenant au gateway.",
+ "description_en": "Multi-tenant enterprise copilot: chat + permission-aware enterprise search (ACL), hardened deep RAG and multi-layer memory, Hermes as the unifying brain, per-tenant governance at the gateway.",
+ "base_rag_durci": true,
+ "deploy_by_sphere": {
+  "S1": [
+   "k3s",
+   "nvidia-gpu-operator",
+   "kueue",
+   "longhorn",
+   "cloudnativepg",
+   "traefik",
+   "cilium-hubble",
+   "velero"
+  ],
+  "S2": [
+   "vllm",
+   "ollama",
+   "text-embeddings-inference-tei",
+   "infinity",
+   "llama-cpp"
+  ],
+  "S3": [
+   "bge-m3",
+   "bge-reranker-v2-m3",
+   "qwen3-embedding",
+   "colbert",
+   "pylate",
+   "sentence-transformers"
+  ],
+  "S4": [
+   "litellm",
+   "redis"
+  ],
+  "S5": [
+   "hermes-agent",
+   "hermes-workspace",
+   "hermes-orchestrator",
+   "superpowers",
+   "open-webui",
+   "onyx-ex-danswer",
+   "dify",
+   "langgraph",
+   "langchain",
+   "n8n",
+   "llamaindex",
+   "instructor",
+   "outlines",
+   "guidance",
+   "browser-use",
+   "playwright"
+  ],
+  "S6": [
+   "qdrant",
+   "neo4j",
+   "mem0-local",
+   "graphiti",
+   "zep",
+   "letta",
+   "cognee",
+   "langmem"
+  ],
+  "S7": [
+   "ragflow",
+   "docling",
+   "mineru",
+   "unstructured",
+   "chonkie",
+   "late-chunking",
+   "dspy",
+   "llmlingua-2",
+   "graphrag",
+   "lightrag",
+   "meilisearch",
+   "firecrawl",
+   "crawl4ai"
+  ],
+  "S8": [
+   "mcp-servers",
+   "ibm-mcp-context-forge",
+   "filesystem-mcp",
+   "github-mcp-officiel",
+   "slack-mcp-korotovsky",
+   "postgres-mcp-pro",
+   "qdrant-mcp-officiel",
+   "fastmcp-python",
+   "mcp-scan-invariant-labs-snyk"
+  ],
+  "S9": [
+   "nemo-guardrails",
+   "microsoft-presidio",
+   "llama-guard",
+   "llm-guard",
+   "guardrails-ai",
+   "rebuff",
+   "garak"
+  ],
+  "S10": [
+   "openbao",
+   "external-secrets-operator",
+   "spiffe-spire",
+   "keycloak",
+   "cert-manager",
+   "kyverno",
+   "opa-rego",
+   "gvisor",
+   "e2b-code-interpreter"
+  ],
+  "S11": [
+   "langfuse",
+   "mlflow",
+   "openmeter",
+   "immudb",
+   "openmetadata"
+  ],
+  "S12": [
+   "arize-phoenix",
+   "opentelemetry-collector",
+   "prometheus",
+   "grafana",
+   "loki",
+   "tempo"
+  ],
+  "S13": [
+   "ragas",
+   "deepeval",
+   "promptfoo",
+   "giskard"
+  ],
+  "S14": [
+   "argo-cd",
+   "kustomize",
+   "kserve",
+   "kubeai"
+  ]
+ },
+ "default_by_sphere": {
+  "S1": "k3s",
+  "S2": "vllm",
+  "S3": "bge-m3",
+  "S4": "litellm",
+  "S5": "hermes-agent",
+  "S6": "qdrant",
+  "S7": "ragflow",
+  "S8": "mcp-servers",
+  "S9": "nemo-guardrails",
+  "S10": "openbao",
+  "S11": "langfuse",
+  "S12": "arize-phoenix",
+  "S13": "ragas",
+  "S14": "argo-cd"
+ },
+ "wiring": [
+  "surfaces (hermes-workspace + open-webui + onyx-ex-danswer(ACL) + dify) -> outils via MCP (mcpo / ibm-mcp-context-forge) -> connecteurs entreprise S8 : chaque surface parle OpenAI-compat",
+  "hermes-agent -> litellm via any-OpenAI-backend : Hermes pointe son backend sur le gateway (cerveau unifiant)",
+  "ragflow(spine RAG) <- ingest docling/mineru/unstructured -> chunk chonkie/late-chunking -> microsoft-presidio de-id -> embed bge-m3 (text-embeddings-inference-tei) -> qdrant(payload/tenant) + neo4j(KG)",
+  "query RAG : dspy rewrite -> hybride dense+BM25(meilisearch)+colbert -> RRF -> rerank bge-reranker-v2-m3 -> llmlingua-2 -> graphrag/lightrag",
+  "memoire : mem0-local/graphiti/zep/letta/cognee/langmem sur qdrant+neo4j (couches par type, complementaires)",
+  "nemo-guardrails INPUT (jailbreak/PII + llama-guard + rebuff + llm-guard) -> litellm(PIVOT) -> nemo-guardrails OUTPUT (guardrails-ai)",
+  "litellm PIVOT : cle virtuelle=team (budget/quota) + microsoft-presidio rail + cache redis + callback langfuse -> vllm /v1/chat/completions (dev: ollama)",
+  "tool-exec sandbox gvisor / e2b-code-interpreter ; secrets openbao -> external-secrets-operator ; mTLS spiffe-spire",
+  "audit/obs : langfuse(trace+cout/tenant) + otel(opentelemetry-collector)->prometheus/grafana/loki/tempo + openmeter + immudb ; gate CI ragas+deepeval+promptfoo+garak -> argo-cd"
+ ],
+ "config_critique": {
+  "LITELLM_HIERARCHY": "Organization->Team->User->Key ; budgets+rate-limits par niveau ; cles virtuelles=spend tracking ; callback Langfuse",
+  "LITELLM_GUARDRAIL_PRESIDIO": "pii_masking_v2 rail natif au gateway",
+  "QDRANT_MULTITENANCY": "collection partagee unique + partition par payload (cle tenant) + is_tenant=true ; Tiered Multitenancy (Qdrant 1.16) gros tenants en shards dedies",
+  "PRESIDIO_3_POINTS": "ingestion RAG de-id + rail LiteLLM gateway + rails NeMo input/output/retrieval",
+  "VLLM_OLLAMA_SWAP": "OpenAI-compat, swap prod<->dev = 2 variables d'env",
+  "ONYX_ACL_SYNC": "sync ACL Slack/GDrive/Confluence/SharePoint par connecteur (l'utilisateur ne voit que ses docs autorises)"
+ },
+ "surface": "hermes-workspace"
+}
\ No newline at end of file
diff --git a/src/forgeai/data/stacks/automatisation.json b/src/forgeai/data/stacks/automatisation.json
new file mode 100644
index 0000000..cae48ce
--- /dev/null
+++ b/src/forgeai/data/stacks/automatisation.json
@@ -0,0 +1,141 @@
+{
+ "id": "automatisation",
+ "name": "Automatisation / Workflows",
+ "description_fr": "Automatisation d'entreprise pilotee par n8n (hub) : orchestrateurs par couche (LangGraph raisonnement, Temporal durabilite, Windmill code, Dify LLM-app), connecteurs via MCP natif, RAG hybride vecteur+graphe, memoire 5 couches, bus evenementiel Kafka/NATS.",
+ "description_en": "n8n-hub-driven enterprise automation: orchestrators layered by role (LangGraph reasoning, Temporal durability, Windmill code, Dify LLM-app), connectors via native MCP, hybrid vector+graph RAG, 5-layer memory, Kafka/NATS event bus.",
+ "base_rag_durci": true,
+ "deploy_by_sphere": {
+  "S1": [
+   "k3s",
+   "nvidia-gpu-operator",
+   "longhorn",
+   "traefik"
+  ],
+  "S2": [
+   "vllm",
+   "ollama",
+   "text-embeddings-inference-tei",
+   "infinity"
+  ],
+  "S3": [
+   "bge-m3",
+   "bge-reranker-v2-m3"
+  ],
+  "S4": [
+   "litellm",
+   "redis"
+  ],
+  "S5": [
+   "n8n",
+   "langgraph",
+   "temporal",
+   "windmill",
+   "dify",
+   "langflow",
+   "flowise",
+   "hermes-agent",
+   "superpowers"
+  ],
+  "S6": [
+   "qdrant",
+   "valkey",
+   "mem0",
+   "zep",
+   "graphiti",
+   "langmem",
+   "letta",
+   "pgvector",
+   "cognee",
+   "memos",
+   "hipporag",
+   "neo4j"
+  ],
+  "S7": [
+   "ragflow",
+   "lightrag",
+   "graphrag",
+   "llamaindex",
+   "docling",
+   "mineru",
+   "firecrawl",
+   "unstructured",
+   "chonkie",
+   "late-chunking",
+   "llmlingua-2"
+  ],
+  "S8": [
+   "mcp-servers",
+   "composio",
+   "pipedream",
+   "arcade",
+   "langchain-mcp-adapters",
+   "metamcp",
+   "ibm-mcp-context-forge"
+  ],
+  "S9": [
+   "nemo-guardrails",
+   "microsoft-presidio"
+  ],
+  "S10": [
+   "openbao",
+   "external-secrets-operator"
+  ],
+  "S11": [
+   "opa-rego",
+   "kyverno",
+   "immudb",
+   "openmeter"
+  ],
+  "S12": [
+   "langfuse"
+  ],
+  "S13": [
+   "promptfoo",
+   "ragas",
+   "deepeval"
+  ],
+  "S14": [
+   "argo-cd",
+   "kserve",
+   "kafka",
+   "nats-jetstream",
+   "postgresql",
+   "minio"
+  ]
+ },
+ "default_by_sphere": {
+  "S1": "k3s",
+  "S2": "vllm",
+  "S3": "bge-m3",
+  "S4": "litellm",
+  "S5": "n8n",
+  "S6": "qdrant",
+  "S7": "ragflow",
+  "S8": "mcp-servers",
+  "S9": "nemo-guardrails",
+  "S10": "openbao",
+  "S11": "opa-rego",
+  "S12": "langfuse",
+  "S13": "promptfoo",
+  "S14": "argo-cd"
+ },
+ "wiring": [
+  "protocole unifiant = MCP + HTTP/API : trigger (webhook/cron/MCP/A2A) -> n8n -> {AI-Agent node | HTTP->langgraph | HTTP->dify | temporal (long)} -> litellm -> vllm/ollama",
+  "n8n(hub, 500+ integrations) <-> langgraph (agents longs/stateful via HTTP) : separation raisonnement (langgraph) / integration systeme (n8n)",
+  "temporal = durable execution des taches critiques/longues (Signals/Queries HITL) ; garde SEPARE de langgraph (imbriquer perd la replayability)",
+  "windmill = jobs code (Python/TS/Go/Bash) ; dify = LLM-app/RAG UI via API ; langflow/flowise = builders optionnels",
+  "connecteurs : composio/pipedream/arcade via nodes MCP natifs n8n (MCP Client Tool + MCP Server Trigger) ; langchain-mcp-adapters cote langgraph ; metamcp/ibm-mcp-context-forge = gateway MCP",
+  "RAG hybride : ingestion docling/mineru/firecrawl/unstructured -> chunk chonkie/late-chunking -> embed bge-m3 (text-embeddings-inference-tei) -> qdrant(dense)+BM25+KG(ragflow GraphRAG/lightrag) -> rerank bge-reranker-v2-m3 -> llmlingua-2 -> litellm",
+  "memoire 5 couches : valkey(court-terme) + mem0(extraction faits) + zep/graphiti(KG temporel) + langmem(long-terme LangGraph) + letta(runtime stateful) ; cognee/memos/hipporag en option",
+  "guardrails nemo-guardrails + microsoft-presidio (wrap I/O) ; secrets openbao->external-secrets-operator ; bus kafka/nats-jetstream (triggers/fan-out) + postgresql + minio (artefacts)",
+  "gouvernance/deploy : opa-rego/kyverno (gate T3) ; promptfoo+ragas+deepeval (CI) ; langfuse (callbacks litellm) ; argo-cd GitOps"
+ ],
+ "config_critique": {
+  "N8N_MCP_NATIVE": "MCP Client Tool (consommer serveurs MCP) + MCP Server Trigger (exposer les workflows n8n comme outils MCP)",
+  "N8N_TO_LANGGRAPH": "n8n HTTP Request node -> agent LangGraph deploye -> resultats routes vers les systemes metier",
+  "TEMPORAL_GRANULARITY": "Temporal = substrat de durabilite ; NE PAS wrapper un run LangGraph entier dans une seule activite (perd la replayability fine)",
+  "LITELLM_ROUTE": "LiteLLM :4000 route+fallback+budget+cache -> vLLM(prod)/Ollama(dev)",
+  "EVENT_BUS": "Kafka/NATS-JetStream pour triggers/fan-out et re-train event-driven"
+ },
+ "surface": "n8n"
+}
\ No newline at end of file
diff --git a/src/forgeai/data/stacks/mlops.json b/src/forgeai/data/stacks/mlops.json
new file mode 100644
index 0000000..e6c17dc
--- /dev/null
+++ b/src/forgeai/data/stacks/mlops.json
@@ -0,0 +1,177 @@
+{
+ "id": "mlops",
+ "name": "MLOps / Fine-tuning (usine a modeles)",
+ "description_fr": "Usine a modeles : pipeline dataset->fine-tune(LoRA/QLoRA/RL)->quantize->merge->eval->registry->serve(vLLM/LoRAX)->gateway, tracking MLflow+W&B en surcouche train->eval, gate CI deterministe (modelscan+trivy+garak+lm-eval) avant promotion, GitOps Argo CD.",
+ "description_en": "Model factory: dataset->fine-tune(LoRA/QLoRA/RL)->quantize->merge->eval->registry->serve(vLLM/LoRAX)->gateway pipeline, MLflow+W&B tracking over train->eval, deterministic CI gate (modelscan+trivy+garak+lm-eval) before promotion, Argo CD GitOps.",
+ "base_rag_durci": true,
+ "deploy_by_sphere": {
+  "S1": [
+   "k3s",
+   "volcano",
+   "kueue",
+   "ray",
+   "kuberay",
+   "nvidia-gpu-operator",
+   "skypilot"
+  ],
+  "S2": [
+   "vllm",
+   "lorax",
+   "sglang",
+   "lmdeploy",
+   "ollama",
+   "text-embeddings-inference-tei",
+   "infinity"
+  ],
+  "S3": [
+   "transformers",
+   "datasets",
+   "llama-factory",
+   "unsloth",
+   "axolotl",
+   "peft",
+   "trl",
+   "deepspeed",
+   "pytorch-fsdp",
+   "accelerate",
+   "liger-kernel",
+   "bitsandbytes",
+   "autoawq",
+   "llm-compressor",
+   "mergekit",
+   "sentence-transformers",
+   "bge-m3",
+   "bge-reranker-v2-m3"
+  ],
+  "S4": [
+   "litellm",
+   "llmlingua-2"
+  ],
+  "S5": [
+   "zenml",
+   "apache-airflow",
+   "dagster",
+   "hermes-agent",
+   "superpowers"
+  ],
+  "S6": [
+   "qdrant",
+   "milvus",
+   "faiss",
+   "mem0"
+  ],
+  "S7": [
+   "ragflow",
+   "data-juicer",
+   "distilabel",
+   "argilla",
+   "datatrove",
+   "nemo-curator",
+   "docling",
+   "unstructured",
+   "chonkie"
+  ],
+  "S8": [
+   "mcp-servers",
+   "composio",
+   "fastmcp-python",
+   "qdrant-mcp-officiel"
+  ],
+  "S9": [
+   "garak",
+   "modelscan",
+   "deepteam",
+   "guardrails-ai",
+   "nemo-guardrails",
+   "microsoft-presidio",
+   "pyrit"
+  ],
+  "S10": [
+   "openbao",
+   "external-secrets-operator",
+   "cert-manager",
+   "trivy",
+   "cosign-sigstore",
+   "e2b-code-interpreter"
+  ],
+  "S11": [
+   "mlflow",
+   "bentoml",
+   "openmetadata",
+   "immudb"
+  ],
+  "S12": [
+   "weights-biases",
+   "langfuse",
+   "arize-phoenix",
+   "prometheus",
+   "grafana",
+   "loki",
+   "tempo",
+   "nvidia-dcgm-exporter",
+   "evidently"
+  ],
+  "S13": [
+   "lm-evaluation-harness",
+   "deepeval",
+   "ragas",
+   "giskard",
+   "promptfoo",
+   "opencompass",
+   "mteb",
+   "guidellm",
+   "dspy",
+   "textgrad"
+  ],
+  "S14": [
+   "argo-cd",
+   "kserve",
+   "seldon-core",
+   "kustomize",
+   "terraform-opentofu",
+   "velero",
+   "minio",
+   "postgresql",
+   "cloudnativepg",
+   "redis",
+   "kafka",
+   "nats-jetstream"
+  ]
+ },
+ "default_by_sphere": {
+  "S1": "k3s",
+  "S2": "vllm",
+  "S3": "transformers",
+  "S4": "litellm",
+  "S5": "zenml",
+  "S6": "qdrant",
+  "S7": "data-juicer",
+  "S8": "mcp-servers",
+  "S9": "garak",
+  "S10": "openbao",
+  "S11": "mlflow",
+  "S12": "weights-biases",
+  "S13": "lm-evaluation-harness",
+  "S14": "argo-cd"
+ },
+ "wiring": [
+  "dataset : minio + postgresql/cloudnativepg (backend registry/tracking) -> curate data-juicer/distilabel/argilla/datatrove/nemo-curator ; ingestion docling/unstructured->chonkie",
+  "fine-tune : llama-factory/unsloth/axolotl -> peft + trl (SFT/DPO/GRPO) ; backend deepspeed/pytorch-fsdp + accelerate + liger-kernel ; pods GPU k3s + volcano/kueue/ray/kuberay ; autolog weights-biases + mlflow",
+  "quantize : bitsandbytes (train 4-bit) | autoawq/llm-compressor (W4A16 -> vLLM natif) -> merge mergekit (TIES/DARE/SLERP)",
+  "eval : lm-evaluation-harness + deepeval/ragas + mteb (embeddings) + guidellm (serving) ; garak/deepteam/pyrit red-team ; modelscan scanne .safetensors ; evidently baseline drift ; dspy/textgrad optimisent sur metriques ; code genere en sandbox e2b-code-interpreter",
+  "registry : mlflow Registry (None->Staging->Prod, artefacts->minio) | bentoml store ; promotion signee cosign-sigstore ; audit immudb ; lineage openmetadata",
+  "serve : vllm --enable-lora | lorax (multi-adaptateurs) | lmdeploy (AWQ) | GGUF->ollama ; K8s kserve/seldon-core",
+  "gateway : litellm (cle virtuelle/version, callback langfuse) ; llmlingua-2 compresse le contexte",
+  "obs/drift : mlflow -> tracking+registry (sert S12 tracking ET S11 registry) ; weights-biases + langfuse (traces) + evidently (drift) + nvidia-dcgm-exporter/prometheus/grafana/loki/tempo -> re-train",
+  "GitOps : argo-cd sync kserve/bentoml ; secrets openbao + external-secrets-operator ; gate CI deterministe modelscan+trivy+garak+lm-eval AVANT promo Staging->Prod (echec seuil => blocage)"
+ ],
+ "config_critique": {
+  "MLFLOW": "MLFLOW_TRACKING_URI + backend PostgreSQL/CloudNativePG + artifact-store MinIO (MLFLOW_S3_ENDPOINT_URL, creds OpenBao/ESO) ; sert registry (S11) ET tracking (S12)",
+  "LLAMA_FACTORY": "dataset_info.json + template ; report_to=[wandb,mlflow] ; export adaptateur merge",
+  "VLLM_LORA": "--enable-lora --max-lora-rank 64 (ou LoRAX pour des milliers d'adaptateurs/GPU) ; poids PVC RO",
+  "QUANT_SERVE_CHAIN": "llm-compressor -> W4A16 consomme nativement par vLLM (chaine quant->serve validee)",
+  "GPU_GANG_SCHED": "k3s + volcano/kueue gang-scheduling multi-GPU ; nvidia-gpu-operator AVANT vLLM",
+  "CI_PROMOTION_GATE": "modelscan (artefact) + trivy (image) + garak/deepteam (red-team) + lm-eval/deepeval (seuils) AVANT promo Staging->Prod ; echec seuil => blocage"
+ },
+ "surface": "mlflow"
+}
\ No newline at end of file
diff --git a/src/forgeai/data/stacks/support-conversationnel.json b/src/forgeai/data/stacks/support-conversationnel.json
new file mode 100644
index 0000000..d76c0d3
--- /dev/null
+++ b/src/forgeai/data/stacks/support-conversationnel.json
@@ -0,0 +1,130 @@
+{
+ "id": "support-conversationnel",
+ "name": "Support client / Conversationnel (chat + voix)",
+ "description_fr": "Support client omnicanal chat + voix temps reel (voix-a-voix < 800 ms) : pipeline Pipecat (VAD/turn/STT/TTS) sur transport LiveKit (WebRTC+SIP/PSTN), PII bidirectionnelle native au gateway LiteLLM+Presidio, RAG durci expose en MCP, memoire multi-couches a stores distincts.",
+ "description_en": "Omnichannel chat + real-time voice customer support (voice-to-voice < 800 ms): Pipecat pipeline (VAD/turn/STT/TTS) on LiveKit transport (WebRTC+SIP/PSTN), bidirectional PII native to the LiteLLM+Presidio gateway, hardened RAG exposed over MCP, multi-layer memory on distinct stores.",
+ "base_rag_durci": true,
+ "deploy_by_sphere": {
+  "S1": [
+   "k3s",
+   "nvidia-gpu-operator",
+   "longhorn",
+   "cloudnativepg"
+  ],
+  "S2": [
+   "vllm",
+   "sglang",
+   "lmcache",
+   "text-embeddings-inference-tei"
+  ],
+  "S3": [
+   "bge-m3",
+   "bge-reranker-v2-m3"
+  ],
+  "S4": [
+   "litellm",
+   "redis"
+  ],
+  "S5": [
+   "langgraph",
+   "pydanticai",
+   "hermes-agent",
+   "superpowers",
+   "open-webui",
+   "chatwoot"
+  ],
+  "S6": [
+   "zep",
+   "graphiti",
+   "mem0",
+   "qdrant",
+   "neo4j",
+   "infinity"
+  ],
+  "S7": [
+   "ragflow"
+  ],
+  "S8": [
+   "mcp-servers",
+   "composio",
+   "docker-mcp-gateway",
+   "fastmcp-python"
+  ],
+  "S9": [
+   "nemo-guardrails",
+   "microsoft-presidio",
+   "llm-guard",
+   "llama-guard"
+  ],
+  "S10": [
+   "openbao",
+   "external-secrets-operator",
+   "gvisor",
+   "firecracker"
+  ],
+  "S11": [
+   "immudb",
+   "opa-rego",
+   "openmeter"
+  ],
+  "S12": [
+   "langfuse",
+   "evidently",
+   "whisperx"
+  ],
+  "S13": [
+   "ragas",
+   "deepeval",
+   "promptfoo"
+  ],
+  "S14": [
+   "argo-cd",
+   "kserve",
+   "kustomize"
+  ],
+  "VOIX": [
+   "livekit",
+   "pipecat",
+   "silero-vad",
+   "smart-turn",
+   "faster-whisper",
+   "kokoro"
+  ]
+ },
+ "default_by_sphere": {
+  "S1": "k3s",
+  "S2": "vllm",
+  "S3": "bge-m3",
+  "S4": "litellm",
+  "S5": "langgraph",
+  "S6": "qdrant",
+  "S7": "ragflow",
+  "S8": "mcp-servers",
+  "S9": "nemo-guardrails",
+  "S10": "openbao",
+  "S11": "immudb",
+  "S12": "langfuse",
+  "S13": "ragas",
+  "S14": "argo-cd",
+  "VOIX": "pipecat"
+ },
+ "wiring": [
+  "transport livekit (WebRTC + SIP/PSTN natif) -> pipecat cree le bot et gere le pipeline VAD/LLM/TTS par-dessus",
+  "turn-taking : silero-vad detecte le silence PUIS smart-turn (~65 ms, semantique on-device) predit la fin d'enonce ; complementaires",
+  "STT faster-whisper int8 streaming (CTranslate2) -> langgraph/pydanticai (cerveau, + hermes-agent/superpowers) ; nemo-guardrails Colang pour dialogue deterministe auth/remboursement",
+  "gateway litellm (cles virtuelles/tenant, budget, cache redis, callback langfuse) -> vllm (+ sglang RadixAttention prefixe systeme+RAG en cache ; lmcache KV) -> TTS kokoro streaming (~28-200 ms 1er frame)",
+  "PII BIDIR : microsoft-presidio via guardrail litellm scope=both (pre_call input + post_call output + restore + logging_only) ; aussi FrameProcessor Pipecat sur le transcript avant tout log",
+  "ragflow (deep-doc, hybrid bge-m3 + bge-reranker-v2-m3, citations) sur moteur infinity, expose via RAGFlow MCP a pipecat/langgraph",
+  "memoire a 2 stores distincts : zep/graphiti (KG temporel, neo4j) + mem0 (faits, qdrant) ; write-back en fin d'appel ; qdrant sert mem0 (PAS ragflow, PAS zep)",
+  "outils CRM/commande/ticket/stripe : mcp-servers/composio via docker-mcp-gateway allow-list + sandbox gvisor/firecracker",
+  "surfaces open-webui + chatwoot (omnicanal, CSAT, handoff humain) ; obs langfuse (masking PII, scores containment/CSAT/sentiment) + evidently (drift) + whisperx (QA nocturne diarizee) ; ledger immudb (PII/consentement)"
+ ],
+ "config_critique": {
+  "VOICE_LATENCY_BUDGET": "< 800 ms voix-a-voix : silero+smart-turn ~65 ms -> faster-whisper int8 ~100-150 ms -> LLM TTFT sglang RadixAttention+lmcache ~200-300 ms -> kokoro 1er frame ~28-200 ms",
+  "PRESIDIO_SCOPE_BOTH": "presidio_filter_scope=both, pre_call+post_call, restore (retablit la valeur reelle pour l'appelant), logging_only (masque avant log)",
+  "RAGFLOW_BACKEND": "moteur retrieval = Infinity ou Elasticsearch (PAS Qdrant) ; expose serveur MCP + API HTTP",
+  "GRAPHITI_BACKEND": "KG temporel sur Neo4j/FalkorDB (PAS Qdrant) ; mem0 sur Qdrant : 2 couches, 2 stores, 0 conflit",
+  "SGLANG_PREFIX_CACHE": "RadixAttention met en cache le prefixe systeme+RAG ; lmcache reutilise le KV entre tours"
+ },
+ "surface": "chatwoot"
+}
\ No newline at end of file
diff --git a/src/forgeai/data/stacks/tout-en-un.json b/src/forgeai/data/stacks/tout-en-un.json
new file mode 100644
index 0000000..e893462
--- /dev/null
+++ b/src/forgeai/data/stacks/tout-en-un.json
@@ -0,0 +1,332 @@
+{
+ "id": "tout-en-un",
+ "name": "Tout-en-un (union des 5 surfaces)",
+ "description_fr": "Union dedupliquee des SET DEPLOYES des 5 profils (assistant, agentique, support+voix, automatisation, mlops). Super-ensemble couvrant toutes les surfaces S5 et la sphere VOIX.",
+ "description_en": "Deduplicated union of the 5 profiles' deployed sets (assistant, agentic, support+voice, automation, mlops). Superset covering all S5 surfaces and the VOIX sphere.",
+ "base_rag_durci": true,
+ "deploy_by_sphere": {
+  "S1": [
+   "k3s",
+   "nvidia-gpu-operator",
+   "kueue",
+   "longhorn",
+   "cloudnativepg",
+   "traefik",
+   "cilium-hubble",
+   "velero",
+   "volcano",
+   "ray",
+   "kuberay",
+   "skypilot"
+  ],
+  "S2": [
+   "vllm",
+   "ollama",
+   "text-embeddings-inference-tei",
+   "infinity",
+   "llama-cpp",
+   "sglang",
+   "lmcache",
+   "lorax",
+   "lmdeploy"
+  ],
+  "S3": [
+   "bge-m3",
+   "bge-reranker-v2-m3",
+   "qwen3-embedding",
+   "colbert",
+   "pylate",
+   "sentence-transformers",
+   "transformers",
+   "datasets",
+   "llama-factory",
+   "unsloth",
+   "axolotl",
+   "peft",
+   "trl",
+   "deepspeed",
+   "pytorch-fsdp",
+   "accelerate",
+   "liger-kernel",
+   "bitsandbytes",
+   "autoawq",
+   "llm-compressor",
+   "mergekit"
+  ],
+  "S4": [
+   "litellm",
+   "redis",
+   "routellm",
+   "vllm-semantic-router",
+   "llmlingua-2"
+  ],
+  "S5": [
+   "hermes-agent",
+   "hermes-workspace",
+   "hermes-orchestrator",
+   "superpowers",
+   "open-webui",
+   "onyx-ex-danswer",
+   "dify",
+   "langgraph",
+   "langchain",
+   "n8n",
+   "llamaindex",
+   "instructor",
+   "outlines",
+   "guidance",
+   "browser-use",
+   "playwright",
+   "openclaw",
+   "openhands",
+   "pydanticai",
+   "chatwoot",
+   "temporal",
+   "windmill",
+   "langflow",
+   "flowise",
+   "zenml",
+   "apache-airflow",
+   "dagster"
+  ],
+  "S6": [
+   "qdrant",
+   "neo4j",
+   "mem0-local",
+   "graphiti",
+   "zep",
+   "letta",
+   "cognee",
+   "langmem",
+   "mem0",
+   "valkey",
+   "pgvector",
+   "memos",
+   "hipporag",
+   "milvus",
+   "faiss"
+  ],
+  "S7": [
+   "ragflow",
+   "docling",
+   "mineru",
+   "unstructured",
+   "chonkie",
+   "late-chunking",
+   "dspy",
+   "graphrag",
+   "lightrag",
+   "meilisearch",
+   "firecrawl",
+   "crawl4ai",
+   "markitdown",
+   "data-juicer",
+   "distilabel",
+   "argilla",
+   "datatrove",
+   "nemo-curator"
+  ],
+  "S8": [
+   "mcp-servers",
+   "ibm-mcp-context-forge",
+   "filesystem-mcp",
+   "github-mcp-officiel",
+   "slack-mcp-korotovsky",
+   "postgres-mcp-pro",
+   "qdrant-mcp-officiel",
+   "fastmcp-python",
+   "mcp-scan-invariant-labs-snyk",
+   "langchain-mcp-adapters",
+   "composio",
+   "docker-mcp-gateway",
+   "pipedream",
+   "arcade",
+   "metamcp"
+  ],
+  "S9": [
+   "nemo-guardrails",
+   "microsoft-presidio",
+   "llama-guard",
+   "llm-guard",
+   "guardrails-ai",
+   "rebuff",
+   "garak",
+   "llamafirewall",
+   "promptguard",
+   "modelscan",
+   "deepteam",
+   "pyrit"
+  ],
+  "S10": [
+   "openbao",
+   "external-secrets-operator",
+   "spiffe-spire",
+   "keycloak",
+   "cert-manager",
+   "kyverno",
+   "opa-rego",
+   "gvisor",
+   "e2b-code-interpreter",
+   "firecracker",
+   "cosign-sigstore",
+   "trivy"
+  ],
+  "S11": [
+   "langfuse",
+   "mlflow",
+   "openmeter",
+   "immudb",
+   "openmetadata",
+   "bentoml"
+  ],
+  "S12": [
+   "arize-phoenix",
+   "opentelemetry-collector",
+   "prometheus",
+   "grafana",
+   "loki",
+   "tempo",
+   "evidently",
+   "whisperx",
+   "weights-biases",
+   "nvidia-dcgm-exporter"
+  ],
+  "S13": [
+   "ragas",
+   "deepeval",
+   "promptfoo",
+   "giskard",
+   "swe-bench",
+   "lm-evaluation-harness",
+   "opencompass",
+   "mteb",
+   "guidellm",
+   "textgrad"
+  ],
+  "S14": [
+   "argo-cd",
+   "kustomize",
+   "kserve",
+   "kubeai",
+   "kafka",
+   "nats-jetstream",
+   "postgresql",
+   "minio",
+   "seldon-core",
+   "terraform-opentofu"
+  ],
+  "VOIX": [
+   "livekit",
+   "pipecat",
+   "silero-vad",
+   "smart-turn",
+   "faster-whisper",
+   "kokoro"
+  ]
+ },
+ "default_by_sphere": {
+  "S1": "k3s",
+  "S2": "vllm",
+  "S3": "bge-m3",
+  "S4": "litellm",
+  "S5": "hermes-agent",
+  "S6": "qdrant",
+  "S7": "ragflow",
+  "S8": "mcp-servers",
+  "S9": "nemo-guardrails",
+  "S10": "openbao",
+  "S11": "langfuse",
+  "S12": "arize-phoenix",
+  "S13": "ragas",
+  "S14": "argo-cd",
+  "VOIX": "pipecat"
+ },
+ "surfaces": [
+  "hermes-workspace",
+  "hermes-agent",
+  "chatwoot",
+  "n8n",
+  "mlflow",
+  "open-webui",
+  "dify",
+  "onyx-ex-danswer"
+ ],
+ "surface": "hermes-workspace",
+ "wiring": [
+  "surfaces (hermes-workspace + open-webui + onyx-ex-danswer(ACL) + dify) -> outils via MCP (mcpo / ibm-mcp-context-forge) -> connecteurs entreprise S8 : chaque surface parle OpenAI-compat",
+  "hermes-agent -> litellm via any-OpenAI-backend : Hermes pointe son backend sur le gateway (cerveau unifiant)",
+  "ragflow(spine RAG) <- ingest docling/mineru/unstructured -> chunk chonkie/late-chunking -> microsoft-presidio de-id -> embed bge-m3 (text-embeddings-inference-tei) -> qdrant(payload/tenant) + neo4j(KG)",
+  "query RAG : dspy rewrite -> hybride dense+BM25(meilisearch)+colbert -> RRF -> rerank bge-reranker-v2-m3 -> llmlingua-2 -> graphrag/lightrag",
+  "memoire : mem0-local/graphiti/zep/letta/cognee/langmem sur qdrant+neo4j (couches par type, complementaires)",
+  "nemo-guardrails INPUT (jailbreak/PII + llama-guard + rebuff + llm-guard) -> litellm(PIVOT) -> nemo-guardrails OUTPUT (guardrails-ai)",
+  "litellm PIVOT : cle virtuelle=team (budget/quota) + microsoft-presidio rail + cache redis + callback langfuse -> vllm /v1/chat/completions (dev: ollama)",
+  "tool-exec sandbox gvisor / e2b-code-interpreter ; secrets openbao -> external-secrets-operator ; mTLS spiffe-spire",
+  "audit/obs : langfuse(trace+cout/tenant) + otel(opentelemetry-collector)->prometheus/grafana/loki/tempo + openmeter + immudb ; gate CI ragas+deepeval+promptfoo+garak -> argo-cd",
+  "boucle agent (openhands event-stream) : User->hermes-agent->litellm->Action->runtime sandbox->Observation->Agent ; patterns orchestrator-workers / evaluator-optimizer",
+  "harness : superpowers (methodo/skills IMPOSES) + openclaw + hermes-agent (runtime) ; couches distinctes qui composent",
+  "langgraph = sous-graphes stateful (checkpoint redis, HITL) ; n8n = triggers/integrations declenchant langgraph en HTTP",
+  "tout appel -> litellm (virtual-key/budget par agent) -> vllm/sglang (prod) + ollama (dev) ; routellm/vllm-semantic-router pour le cout",
+  "kueue/volcano ordonnancent le GPU entre vllm/sglang/ollama (time-share) ; poids sur PVC RO ; readiness /health",
+  "spine retrieval : bge-m3 (text-embeddings-inference-tei/infinity) + bge-reranker-v2-m3 + qdrant ; ragflow expose en tool MCP a l'agent ; lightrag/graphrag routes par type de requete",
+  "memoire agent (S6, 4 couches) mem0(perso)+graphiti/zep(KG temporel)+letta(runtime paging)+cognee(doc->KG) sur qdrant+neo4j : distincte du plan RAG (memoire = read-write stateful, RAG = read-only)",
+  "outils MCP untrusted derriere guardrails/allow-list (nemo-guardrails + llama-guard/llamafirewall/promptguard) en sandbox e2b-code-interpreter/gvisor/firecracker ; secrets external-secrets-operator/openbao",
+  "obs/eval/gouv : langfuse trace chaque step ; CI ragas/deepeval/swe-bench ; metering openmeter + ledger immudb ; images signees cosign-sigstore + scan trivy -> argo-cd GitOps",
+  "transport livekit (WebRTC + SIP/PSTN natif) -> pipecat cree le bot et gere le pipeline VAD/LLM/TTS par-dessus",
+  "turn-taking : silero-vad detecte le silence PUIS smart-turn (~65 ms, semantique on-device) predit la fin d'enonce ; complementaires",
+  "STT faster-whisper int8 streaming (CTranslate2) -> langgraph/pydanticai (cerveau, + hermes-agent/superpowers) ; nemo-guardrails Colang pour dialogue deterministe auth/remboursement",
+  "gateway litellm (cles virtuelles/tenant, budget, cache redis, callback langfuse) -> vllm (+ sglang RadixAttention prefixe systeme+RAG en cache ; lmcache KV) -> TTS kokoro streaming (~28-200 ms 1er frame)",
+  "PII BIDIR : microsoft-presidio via guardrail litellm scope=both (pre_call input + post_call output + restore + logging_only) ; aussi FrameProcessor Pipecat sur le transcript avant tout log",
+  "ragflow (deep-doc, hybrid bge-m3 + bge-reranker-v2-m3, citations) sur moteur infinity, expose via RAGFlow MCP a pipecat/langgraph",
+  "memoire a 2 stores distincts : zep/graphiti (KG temporel, neo4j) + mem0 (faits, qdrant) ; write-back en fin d'appel ; qdrant sert mem0 (PAS ragflow, PAS zep)",
+  "outils CRM/commande/ticket/stripe : mcp-servers/composio via docker-mcp-gateway allow-list + sandbox gvisor/firecracker",
+  "surfaces open-webui + chatwoot (omnicanal, CSAT, handoff humain) ; obs langfuse (masking PII, scores containment/CSAT/sentiment) + evidently (drift) + whisperx (QA nocturne diarizee) ; ledger immudb (PII/consentement)",
+  "protocole unifiant = MCP + HTTP/API : trigger (webhook/cron/MCP/A2A) -> n8n -> {AI-Agent node | HTTP->langgraph | HTTP->dify | temporal (long)} -> litellm -> vllm/ollama",
+  "n8n(hub, 500+ integrations) <-> langgraph (agents longs/stateful via HTTP) : separation raisonnement (langgraph) / integration systeme (n8n)",
+  "temporal = durable execution des taches critiques/longues (Signals/Queries HITL) ; garde SEPARE de langgraph (imbriquer perd la replayability)",
+  "windmill = jobs code (Python/TS/Go/Bash) ; dify = LLM-app/RAG UI via API ; langflow/flowise = builders optionnels",
+  "connecteurs : composio/pipedream/arcade via nodes MCP natifs n8n (MCP Client Tool + MCP Server Trigger) ; langchain-mcp-adapters cote langgraph ; metamcp/ibm-mcp-context-forge = gateway MCP",
+  "RAG hybride : ingestion docling/mineru/firecrawl/unstructured -> chunk chonkie/late-chunking -> embed bge-m3 (text-embeddings-inference-tei) -> qdrant(dense)+BM25+KG(ragflow GraphRAG/lightrag) -> rerank bge-reranker-v2-m3 -> llmlingua-2 -> litellm",
+  "memoire 5 couches : valkey(court-terme) + mem0(extraction faits) + zep/graphiti(KG temporel) + langmem(long-terme LangGraph) + letta(runtime stateful) ; cognee/memos/hipporag en option",
+  "guardrails nemo-guardrails + microsoft-presidio (wrap I/O) ; secrets openbao->external-secrets-operator ; bus kafka/nats-jetstream (triggers/fan-out) + postgresql + minio (artefacts)",
+  "gouvernance/deploy : opa-rego/kyverno (gate T3) ; promptfoo+ragas+deepeval (CI) ; langfuse (callbacks litellm) ; argo-cd GitOps",
+  "dataset : minio + postgresql/cloudnativepg (backend registry/tracking) -> curate data-juicer/distilabel/argilla/datatrove/nemo-curator ; ingestion docling/unstructured->chonkie",
+  "fine-tune : llama-factory/unsloth/axolotl -> peft + trl (SFT/DPO/GRPO) ; backend deepspeed/pytorch-fsdp + accelerate + liger-kernel ; pods GPU k3s + volcano/kueue/ray/kuberay ; autolog weights-biases + mlflow",
+  "quantize : bitsandbytes (train 4-bit) | autoawq/llm-compressor (W4A16 -> vLLM natif) -> merge mergekit (TIES/DARE/SLERP)",
+  "eval : lm-evaluation-harness + deepeval/ragas + mteb (embeddings) + guidellm (serving) ; garak/deepteam/pyrit red-team ; modelscan scanne .safetensors ; evidently baseline drift ; dspy/textgrad optimisent sur metriques ; code genere en sandbox e2b-code-interpreter",
+  "registry : mlflow Registry (None->Staging->Prod, artefacts->minio) | bentoml store ; promotion signee cosign-sigstore ; audit immudb ; lineage openmetadata",
+  "serve : vllm --enable-lora | lorax (multi-adaptateurs) | lmdeploy (AWQ) | GGUF->ollama ; K8s kserve/seldon-core",
+  "gateway : litellm (cle virtuelle/version, callback langfuse) ; llmlingua-2 compresse le contexte",
+  "obs/drift : mlflow -> tracking+registry (sert S12 tracking ET S11 registry) ; weights-biases + langfuse (traces) + evidently (drift) + nvidia-dcgm-exporter/prometheus/grafana/loki/tempo -> re-train",
+  "GitOps : argo-cd sync kserve/bentoml ; secrets openbao + external-secrets-operator ; gate CI deterministe modelscan+trivy+garak+lm-eval AVANT promo Staging->Prod (echec seuil => blocage)"
+ ],
+ "config_critique": {
+  "LITELLM_HIERARCHY": "Organization->Team->User->Key ; budgets+rate-limits par niveau ; cles virtuelles=spend tracking ; callback Langfuse",
+  "LITELLM_GUARDRAIL_PRESIDIO": "pii_masking_v2 rail natif au gateway",
+  "QDRANT_MULTITENANCY": "collection partagee unique + partition par payload (cle tenant) + is_tenant=true ; Tiered Multitenancy (Qdrant 1.16) gros tenants en shards dedies",
+  "PRESIDIO_3_POINTS": "ingestion RAG de-id + rail LiteLLM gateway + rails NeMo input/output/retrieval",
+  "VLLM_OLLAMA_SWAP": "OpenAI-compat, swap prod<->dev = 2 variables d'env",
+  "ONYX_ACL_SYNC": "sync ACL Slack/GDrive/Confluence/SharePoint par connecteur (l'utilisateur ne voit que ses docs autorises)",
+  "LITELLM_VIRTUAL_KEY": "1 cle virtuelle par agent : budget + quota + fallback + callback Langfuse",
+  "AGENT_TOOLS_UNTRUSTED": "tout tool MCP = untrusted -> allow-list nemo-guardrails + llamafirewall AVANT execution",
+  "SANDBOX_EXEC": "chaque Action code s'execute en sandbox e2b-code-interpreter / gvisor / firecracker (jamais sur l'hote)",
+  "GPU_TIMESHARE": "kueue/volcano gang-scheduling ; vllm(prod) et ollama(dev) partagent le GPU en time-share, pas en conflit",
+  "LANGGRAPH_CHECKPOINT": "checkpoint Redis + human-in-the-loop (HITL) sur les sous-graphes stateful",
+  "SUPPLY_CHAIN_GATE": "cosign-sigstore (signature image) + trivy (scan) AVANT argo-cd sync",
+  "VOICE_LATENCY_BUDGET": "< 800 ms voix-a-voix : silero+smart-turn ~65 ms -> faster-whisper int8 ~100-150 ms -> LLM TTFT sglang RadixAttention+lmcache ~200-300 ms -> kokoro 1er frame ~28-200 ms",
+  "PRESIDIO_SCOPE_BOTH": "presidio_filter_scope=both, pre_call+post_call, restore (retablit la valeur reelle pour l'appelant), logging_only (masque avant log)",
+  "RAGFLOW_BACKEND": "moteur retrieval = Infinity ou Elasticsearch (PAS Qdrant) ; expose serveur MCP + API HTTP",
+  "GRAPHITI_BACKEND": "KG temporel sur Neo4j/FalkorDB (PAS Qdrant) ; mem0 sur Qdrant : 2 couches, 2 stores, 0 conflit",
+  "SGLANG_PREFIX_CACHE": "RadixAttention met en cache le prefixe systeme+RAG ; lmcache reutilise le KV entre tours",
+  "N8N_MCP_NATIVE": "MCP Client Tool (consommer serveurs MCP) + MCP Server Trigger (exposer les workflows n8n comme outils MCP)",
+  "N8N_TO_LANGGRAPH": "n8n HTTP Request node -> agent LangGraph deploye -> resultats routes vers les systemes metier",
+  "TEMPORAL_GRANULARITY": "Temporal = substrat de durabilite ; NE PAS wrapper un run LangGraph entier dans une seule activite (perd la replayability fine)",
+  "LITELLM_ROUTE": "LiteLLM :4000 route+fallback+budget+cache -> vLLM(prod)/Ollama(dev)",
+  "EVENT_BUS": "Kafka/NATS-JetStream pour triggers/fan-out et re-train event-driven",
+  "MLFLOW": "MLFLOW_TRACKING_URI + backend PostgreSQL/CloudNativePG + artifact-store MinIO (MLFLOW_S3_ENDPOINT_URL, creds OpenBao/ESO) ; sert registry (S11) ET tracking (S12)",
+  "LLAMA_FACTORY": "dataset_info.json + template ; report_to=[wandb,mlflow] ; export adaptateur merge",
+  "VLLM_LORA": "--enable-lora --max-lora-rank 64 (ou LoRAX pour des milliers d'adaptateurs/GPU) ; poids PVC RO",
+  "QUANT_SERVE_CHAIN": "llm-compressor -> W4A16 consomme nativement par vLLM (chaine quant->serve validee)",
+  "GPU_GANG_SCHED": "k3s + volcano/kueue gang-scheduling multi-GPU ; nvidia-gpu-operator AVANT vLLM",
+  "CI_PROMOTION_GATE": "modelscan (artefact) + trivy (image) + garak/deepteam (red-team) + lm-eval/deepeval (seuils) AVANT promo Staging->Prod ; echec seuil => blocage"
+ }
+}
\ No newline at end of file
diff --git a/src/forgeai/stacks.py b/src/forgeai/stacks.py
new file mode 100644
index 0000000..43baf1d
--- /dev/null
+++ b/src/forgeai/stacks.py
@@ -0,0 +1,76 @@
+"""Profils de déploiement (stacks) ForgeAI — IMPL-3.
+
+Un profil (``data/stacks/<id>.json``) décrit le **SET DÉPLOYÉ synergique** d'un stack :
+
+- ``deploy_by_sphere`` : les ids catalogue effectivement déployés+câblés par défaut, par sphère ;
+- ``default_by_sphere`` : la brique primaire (1) de chaque sphère ;
+- ``wiring`` : le graphe de câblage (qui parle à qui) issu de la recherche de perfection ;
+- ``config_critique`` : les points de configuration qui rendent le stack « 100 % utilisable ».
+
+Le **catalogue** est l'univers des options (activables à la carte) ; le **profil** décrit ce qui
+démarre par défaut. Le champ catalogue ``default_eligible`` concerne le défaut ⭐ *de catégorie*
+(B-21) — il est ORTHOGONAL au déploiement par profil : une brique peut être « non-éligible au ⭐ »
+et pourtant déployée par un stack (ex. les briques voix du stack Support).
+"""
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+
+def stacks_dir() -> Path:
+    return Path(__file__).resolve().parent / "data" / "stacks"
+
+
+def list_stacks() -> list[str]:
+    """Ids des profils disponibles (nom de fichier sans extension), triés."""
+    return sorted(p.stem for p in stacks_dir().glob("*.json"))
+
+
+def load_stack(stack_id: str) -> dict:
+    path = stacks_dir() / f"{stack_id}.json"
+    if not path.exists():
+        raise FileNotFoundError(f"stack inconnu : {stack_id}")
+    return json.loads(path.read_text(encoding="utf-8"))
+
+
+def deploy_ids(stack: dict) -> list[str]:
+    """Ids déployés (toutes sphères), dédupliqués, dans l'ordre de première apparition."""
+    seen: dict[str, None] = {}
+    for ids in stack.get("deploy_by_sphere", {}).values():
+        for brick_id in ids:
+            seen.setdefault(brick_id, None)
+    return list(seen)
+
+
+def validate_stack(stack: dict, catalogue_ids: set[str]) -> list[str]:
+    """Retourne les violations du profil (liste vide = valide).
+
+    Invariants : deploy non vide et entièrement dans le catalogue ; RAG durci ; gateway unique
+    ``litellm`` ; ``hermes-agent`` déployé (imposé à tous) ; ``superpowers``+``openclaw`` pour
+    l'agentique ; câblage présent.
+    """
+    errors: list[str] = []
+    dep = deploy_ids(stack)
+    if not dep:
+        errors.append("deploy_by_sphere vide")
+    missing = sorted(i for i in dep if i not in catalogue_ids)
+    if missing:
+        errors.append(f"ids déployés absents du catalogue : {missing[:5]}")
+    s5 = set(stack.get("deploy_by_sphere", {}).get("S5", []))
+    if "hermes-agent" not in s5:
+        errors.append("S5 doit déployer hermes-agent (imposé à tous les stacks)")
+    if stack.get("id") == "agentique":
+        for req in ("superpowers", "openclaw"):
+            if req not in s5:
+                errors.append(f"S5 agentique doit déployer {req}")
+    defaults = stack.get("default_by_sphere", {})
+    if defaults.get("S4") != "litellm":
+        errors.append("défaut S4 (gateway unique) doit être 'litellm'")
+    if not defaults.get("S7"):
+        errors.append("défaut S7 (RAG) manquant")
+    if not stack.get("base_rag_durci"):
+        errors.append("base_rag_durci doit être true")
+    if not stack.get("wiring"):
+        errors.append("câblage (wiring) manquant")
+    return errors
diff --git a/tests/test_stacks.py b/tests/test_stacks.py
new file mode 100644
index 0000000..1c3e6b5
--- /dev/null
+++ b/tests/test_stacks.py
@@ -0,0 +1,73 @@
+"""IMPL-3 — preuve : les 6 profils de déploiement (data/stacks/*.json).
+
+Chaque profil est valide, ne déploie que des ids réels du catalogue, porte le RAG durci + le
+gateway unique litellm + hermes-agent, et l'agentique déploie superpowers + openclaw."""
+import json
+
+import pytest
+
+from forgeai.resources import catalogue_path
+from forgeai.stacks import deploy_ids, list_stacks, load_stack, validate_stack
+
+EXPECTED = {
+    "agentique",
+    "assistant-entreprise",
+    "support-conversationnel",
+    "automatisation",
+    "mlops",
+    "tout-en-un",
+}
+
+
+def _catalogue_ids():
+    d = json.loads(catalogue_path().read_text(encoding="utf-8"))
+    entries = d if isinstance(d, list) else d["entries"]
+    return {x["id"] for x in entries}
+
+
+def test_les_6_profils_presents():
+    assert set(list_stacks()) == EXPECTED
+
+
+def test_chaque_profil_valide():
+    cids = _catalogue_ids()
+    for sid in sorted(EXPECTED):
+        errs = validate_stack(load_stack(sid), cids)
+        assert errs == [], f"{sid} : {errs}"
+
+
+def test_tous_les_ids_deployes_sont_au_catalogue():
+    cids = _catalogue_ids()
+    for sid in sorted(EXPECTED):
+        dep = deploy_ids(load_stack(sid))
+        assert dep, f"{sid} : deploy vide"
+        hors = sorted(i for i in dep if i not in cids)
+        assert hors == [], f"{sid} déploie des ids hors catalogue : {hors}"
+
+
+def test_rag_durci_et_gateway_partout():
+    for sid in sorted(EXPECTED):
+        s = load_stack(sid)
+        assert s["base_rag_durci"] is True, sid
+        assert s["default_by_sphere"]["S4"] == "litellm", sid
+        assert s["default_by_sphere"].get("S7"), sid
+
+
+def test_hermes_partout_superpowers_openclaw_agentique():
+    for sid in sorted(EXPECTED):
+        s5 = set(load_stack(sid)["deploy_by_sphere"].get("S5", []))
+        assert "hermes-agent" in s5, f"{sid} : S5 sans hermes-agent"
+    ag_s5 = set(load_stack("agentique")["deploy_by_sphere"]["S5"])
+    assert {"superpowers", "openclaw"} <= ag_s5, "agentique doit déployer superpowers+openclaw"
+
+
+def test_cablage_et_config_non_vides():
+    for sid in sorted(EXPECTED):
+        s = load_stack(sid)
+        assert len(s.get("wiring", [])) >= 3, f"{sid} : câblage trop maigre"
+        assert s.get("config_critique"), f"{sid} : config_critique manquante"
+
+
+def test_load_stack_inconnu_leve():
+    with pytest.raises(FileNotFoundError):
+        load_stack("stack-inexistant-xyz")
```
