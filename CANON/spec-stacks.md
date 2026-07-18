# spec-stacks.md — Les 6 stacks ForgeAI × 14 sphères (design fondation)

- **Statut** : approuvé Nathan 2026-07-17. Étend `spec-web-ui.md` (surface) et le catalogue (948 briques, R-ALL).
- **Exigences** : ID-4 (stacks complets), CD-1/CD-2 (« système COMPLET, branché et fonctionnel »).
- **Méthode** : sourcé R-ALL (aucune brique sans id catalogue réel / URL gh-api). 18 agents de recherche + 4 assemblages (traces : `scratchpad/research/*`, `scratchpad/stacks/*`, `spec-stacks-FINAL.md`).

---

## §0 — MODÈLE DIRECTEUR (le plus important)

**« Châssis unique + tête interchangeable », profil de défauts sur catalogue par sphère.**

- Le **catalogue (948 briques)** est l'**univers**, organisé en **14 sphères**. Il EST la page *briques additionnelles* : tout est activable/désactivable par sphère.
- Un **stack = un PROFIL DE DÉFAUTS** : ce qui se **déploie** et se **câble** par défaut = **châssis commun (57) + défauts de domaine + tête S5** ≈ **60-150 briques réelles**. Le reste de chaque sphère reste **disponible en 1 clic**.
- Poussé au plafond, chaque stack **expose** ~toute sa catégorie pertinente (Agentique **858/948**, MLOps 479, Assistant 417, Automatisation 290, Support 277) — mais on ne **déploie jamais** 858 briques (conflits, ressources) : on déploie les **défauts optimaux** et on **expose** tout.
- Conséquence d'implémentation : **les rosters ne sont pas hardcodés** ; ils sont **dérivés du catalogue par sphère** (mapping catégorie→sphère). Un stack ne stocke que : ses **défauts** (1/sphère), son **châssis**, sa **tête S5**, et son **graphe de câblage**.

---

## §1 — Les 14 sphères
① Compute/K3s · ② Inference & serving · ③ Modèles (LLM + embeddings + rerankers) · ④ Gateway & routage (pivot) · ⑤ Orchestration & agents (la « tête ») · ⑥ Mémoire & vector DB · ⑦ Connaissance & RAG · ⑧ Outils & interop MCP · ⑨ Guardrails & sûreté/PII · ⑩ Sécurité & secrets · ⑪ Gouvernance/ledger/audit · ⑫ Observabilité & tracing · ⑬ Évaluation & test (harness) · ⑭ Déploiement & cycle de vie.

Mapping catégorie catalogue → sphère : voir §6 (encodé à l'implémentation).

---

## §2 — CHÂSSIS COMMUN (57 briques, universelles 5/5 — socle non négociable)

- **S1 (3)** `k3s` · `nvidia-gpu-operator` · `kuberay`
- **S2 (5)** `vllm` · `sglang` · `ollama` · `lmdeploy` · `xinference`
- **S3 (9)** `bge-m3` · `bge-reranker-v2-m3` · `qwen3-embedding` · `qwen3-reranker` · `nomic-embed-text` · `gte-gte-multilingual-base` · `nv-embed-v2` · `modernbert` · `text-embeddings-inference-tei`
- **S4 (2)** `litellm` (pivot) · `portkey-gateway`
- **S6 vector (5)** `qdrant` · `weaviate` · `milvus` · `pgvector` · `chroma`
- **S6 mémoire (8)** `zep` · `letta` · `cognee` · `langmem` · `graphiti` · `memos` · `memobase` · `memoripy`
- **S8 (2)** `composio` · `fastmcp-python`
- **S9 (7)** `nemo-guardrails` · `microsoft-presidio` (PII) · `llama-guard` · `guardrails-ai` · `llm-guard` · `rebuff` · `garak`
- **S10 (4)** `openbao` · `external-secrets-operator` · `cert-manager` · `trivy`
- **S12 (5)** `langfuse` · `arize-phoenix` · `opik` · `prometheus` · `grafana`
- **S13 (5)** `ragas` · `deepeval` · `promptfoo` · `giskard` · `trulens`
- **S14 (2)** `argo-cd` · `terraform-opentofu`

**Spine RAG-DURCI (intégral au châssis)** : `bge-m3` → `text-embeddings-inference-tei` → `qdrant` (dense+sparse, RRF) → `bge-reranker-v2-m3` → `microsoft-presidio` (PII) → `nemo-guardrails` (rails I/O) → `litellm` → `vllm`.

**Bases imposées** : `hermes-agent` (tous) · `superpowers` (agentique, + disponible partout).

---

## §3 — Les 6 stacks (tête S5 + défauts clés + exposition)

| # | Stack | Tête S5 (défaut) | Défauts distinctifs | Exposé |
|---|---|---|---|---|
| 1 | **Copilote/Assistant d'entreprise** | `dify` | RAG `ragflow`, surface `open-webui`, gouvernance `langfuse`+`opa-rego` | 417 |
| 2 | **Agentique (dev+ops)** | `langgraph` (+`superpowers`/`hermes-agent`) | harness `openhands`/`aider`/`cline`, MCP profond, sandbox `gvisor` | 858 |
| 3 | **Support/Conversationnel** | `pipecat` | mémoire `zep`+`graphiti`, PII bidir `presidio`, **voix** STT/TTS/VAD | 277 |
| 4 | **Automatisation/workflows** | `n8n` | connecteurs `composio`, RAG `ragflow`, triggers webhook/cron | 290 |
| 5 | **MLOps/fine-tuning** | `zenml` | entraînement `unsloth`/`llama-factory`, registre `mlflow`, éval `lm-evaluation-harness`, red-team `garak` | 479 |
| 6 | **Tout-en-un** | union des 5 têtes | châssis + toutes surfaces (activables par profil) | union |

RAG-durci + mémoire multi-couches = **socle commun à tous** (§2). Le stack 6 = union des défauts des 5.

---

## §4 — Briques [GAP] à ajouter au catalogue (33, gh-api 2026-07-17)

**Voix/conversationnel (16)** : `faster-whisper` `whisperx` `silero-vad` `smart-turn` `kokoro` `piper1-gpl` `coqui-tts` `chatterbox` `moonshine` `sensevoice` `livekit-server` `speaches` `rasa` `vocode-core` `chatwoot` `chainlit`.
**Secrets/IaC/surfaces/lineage (17)** : `hashicorp-vault` `infisical` `sops` `hashicorp-terraform` `pulumi` `flux2` `nextchat` `lobe-chat` `librechat` `paddleocr` `private-gpt` `strix` `bitnet` `kubeflow` `openai-evals` `datahub` `openlineage`.
Dossiers R-ALL prêts (id/name/source_url/license/★/verified) : `scratchpad/research/R3-gap-dossiers.md` + table voix `stack3-support`.
**Open pur en primaire** : `openbao` [IN] > Vault (BUSL) ; `terraform-opentofu` [IN] > Terraform (BUSL) — les HashiCorp restent en alternate.

---

## §5 — Câblage (invariant, par stack)

Tout appel modèle → **gateway `litellm`** (clés virtuelles = budgets, cache, fallbacks, callback `langfuse`) → serving `vllm`/`ollama`. RAG-durci = §2 spine. Secrets → `openbao`+`external-secrets-operator` (zéro secret en clair). Observabilité `langfuse` sur chaque appel. Éval `ragas`/`promptfoo` en CI avant promotion `argo-cd`. Guardrails I/O `nemo-guardrails`+`presidio`. Détail par stack : `scratchpad/stacks/stackN-*.md`.

---

## §6 — Plan d'implémentation (lots, chacun via le pipeline PROOF)

1. **IMPL-1 — Couche 14 sphères** : mapping catégorie catalogue→sphère (`forgeai/catalogue/spheres.py` + champ/vue), + gate de complétude (chaque catégorie mappée à 1 sphère).
2. **IMPL-2 — +33 briques catalogue** : insertion des dossiers R3 + voix (R-ALL, verified_at, sha256 régénéré, désambiguïsation `helm`/`aphrodite-engine` corrigée).
3. **IMPL-3 — 6 profils-défauts** : `data/stacks/<stack>.json` = {tête S5, défauts/sphère, châssis, câblage} ; résolution = défauts déployés + sphère→catalogue pour l'exposition.
4. **IMPL-4 — Page briques additionnelles** (UI, cf. spec-web-ui) : catalogue par sphère, cases à cocher, défauts pré-cochés.
5. **IMPL-5 — Modèles & clés API** (UI) : tous modèles local+cloud + saisie clés.

---

## §7 — Invariants
Souveraineté/hors-ligne (open pur, air-gap) · secrets jamais en clair (openbao) · T3 = Nathan (paiements/publication/prod) · RAG-durci + mémoire exceptionnelle partout · pipeline PROOF (codeur→gates→revue scellée 3 vendors→merge) · docs = gate (ce fichier fait foi).
