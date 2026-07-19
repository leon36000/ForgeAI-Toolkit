# spec-stacks.md — Les 6 stacks ForgeAI × 15 sphères (design fondation)

- **Statut** : Approuvé Nathan 2026-07-19. Étend l'installateur UI et le catalogue (1577 briques).
- **Exigences** : ID-4 (stacks complets), CD-1/CD-2 (système complet, branché et fonctionnel).
- **Méthode** : Sourcé R-ALL. 54 dossiers BINDING scellés et validés par la gate D9 (minimum 3 vendors distincts).

---

## §0 — MODÈLE DIRECTEUR

**« Châssis unique + tête interchangeable », profil de défauts sur catalogue par sphère.**

- Le **catalogue (1577 briques)** est l'**univers**, organisé en **15 sphères** (incluant la sphère réelle `VOIX`). Tout est activable/désactivable par sphère.
- Un **stack = un PROFIL DE DÉFAUTS** : ce qui se déploie et se câble par défaut. Il est composé du **châssis commun (24 briques calculées)** + les défauts de domaine + la tête S5. Le reste de chaque sphère reste disponible en exploration.
- **Doctrine des défauts (hiérarchie gravée par gates)** :
  1. `default_by_sphere` : Autorité absolue de déploiement par défaut.
  2. Étoiles du catalogue (`forgeai_home/parse_stars`) : Exploration et mise en avant seule.
  3. Overlay : Repli de type `Minimal` en cas d'absence de spécification.
- **Templates fusionnés** : Les anciens templates sont fusionnés sous forme d'alias hérités rétro-compatibles :
  - `dev-agentic` → `agentique`
  - `rag-souverain` → `assistant-entreprise`
  - `lab-fine-tuning` → `mlops`
  - `production-souveraine` → `tout-en-un`

---

## §1 — Les 15 sphères
① Compute/K3s · ② Inference & serving · ③ Modèles (LLM + embeddings + rerankers) · ④ Gateway & routage (pivot) · ⑤ Orchestration & agents (la « tête ») · ⑥ Mémoire & vector DB · ⑦ Connaissance & RAG · ⑧ Outils & interop MCP · ⑨ Guardrails & sûreté/PII · ⑩ Sécurité & secrets · ⑪ Gouvernance/ledger/audit · ⑫ Observabilité & tracing · ⑬ Évaluation & test (harness) · ⑭ Déploiement & cycle de vie · ⑮ VOIX (STT/TTS/VAD).

---

## §2 — CHÂSSIS COMMUN (24 briques calculées)

Le châssis commun est calculé dynamiquement comme l'intersection stricte des 5 stacks de spécialité. Il contient les 24 briques fondamentales et non négociables assurant le fonctionnement du socle souverain, du routage, de la sécurité et de l'observabilité de base.

**Spine RAG-DURCI (intégré au châssis)** : `bge-m3` → `text-embeddings-inference-tei` → `qdrant` (dense+sparse, RRF) → `bge-reranker-v2-m3` → `microsoft-presidio` (PII) → `nemo-guardrails` (rails I/O) → `litellm` → `vllm`.

---

## §3 — Les 6 stacks (tête S5 + défauts clés + exposition)

| # | Stack | Tête S5 (défaut) | Briques déployées | Rôle & Spécificité |
|---|---|---|---|---|
| 1 | **Copilote/Assistant d'entreprise** | `dify` | 102 | RAG d'entreprise, assistant souverain, interfaces de collaboration. |
| 2 | **Agentique (dev+ops)** | `langgraph` | 72 | Systèmes multi-agents autonomes, intégration MCP profonde, codage. |
| 3 | **Support/Conversationnel** | `pipecat` | 55 | Interaction temps réel, intégration de la sphère **VOIX** (STT/TTS/VAD). |
| 4 | **Automatisation/workflows** | `n8n` | 69 | Orchestration de tâches, connecteurs tiers et pipelines événementiels. |
| 5 | **MLOps/fine-tuning** | `zenml` | 104 | Entraînement, évaluation, gestion de modèles et pipelines de données. |
| 6 | **Tout-en-un** | Union des têtes | 188 | Profil global regroupant l'ensemble des capacités des 5 stacks. |

---

## §4 — Câblage (invariant, par stack)

Tout appel modèle → **gateway `litellm`** (clés virtuelles = budgets, cache, fallbacks, callback `langfuse`) → serving `vllm`/`ollama`. RAG-durci = spine du châssis commun. Les secrets sont gérés via le coffre fort chiffré local. L'observabilité est assurée par `langfuse` sur chaque appel.

---

## §5 — Doctrine de validation (Gate D9)

Chaque modification apportée aux définitions de stacks, au catalogue ou aux configurations de déploiement doit passer la gate de validation du dépôt :
- **Validation multi-vendor** : Tout dossier listé dans `reviews/BINDING.txt` (54 dossiers scellés) doit obligatoirement comporter une approbation signée d'au moins **3 vendors distincts**.
- **CI unique** : Validation automatisée via `gates.yml` (vérification de l'absence de stubs, intégrité du registre hash-chaîné, et couverture de tests).
