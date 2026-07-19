# Story P0.3a — Installateur par etapes + registre modeles verifies + etape Modeles IA

## Criteres (exigences Nathan verbatim : installateur multi-etapes ; TOUS les modeles petits/moyens/gros dont GLM 5.2, Qwen 3.6 27B, Gemma 4 ; AUCUN filtrage par materiel local ; deployable vers tout noeud)
- Rail 6 etapes, verrouillage progressif (3/4/6 exigent un stack), nav clavier/clic.
- Registre 113 modeles : chaque hf_id verifie HF (preuve dans le champ verif) ; endpoint les sert TOUS ; gate pytest fige integrite + citations + non-filtrage.
- Etape Modeles : filtres/recherche/selection ; models[] transmis au POST /api/deploy.

## PREUVE
```
### SUITE COMPLETE (207 tests)
...............................................................          [100%]
### no_stub : OK 159 fichiers

### REGISTRE MODELES : 113 entrees, 10 familles (65 petits / 24 moyens / 24 gros), CHACUNE verifiee sur HF (champ verif = HTTP 200 + downloads). Citations utilisateur PROUVEES reelles : zai-org/GLM-5.2 (MIT, 536k dl), Qwen/Qwen3.6-27B (5,3M dl), google/gemma-4-* (5 variantes). Genere par workflow 20 agents (10 recherche + 10 verif HF), 0 erreur.

### PREUVE NAVIGATEUR REEL — installateur 6 etapes + etape Modeles
Rail 6 etapes ; etape 1 seule visible au boot ; etape 4 VERROUILLEE sans stack (hint "Choisissez d abord un stack") ; apres choix agentique : deverrouillee, 62 briques chargees ; etape 6 : selecteur de noeud = vrai cluster (local/auto/pc1-x870e-taichi/pc2-forge-b/pc3-grs-a/pc4-grs-b).
Etape 3 Modeles : 113 affiches (ZERO masquage par materiel — directive permanente) ; filtre Moyens -> 24 ; recherche "3.6" -> QwQ-32B, Qwen3.6-27B, Qwen3.6-35B-A3B ; selection Qwen/Qwen3.6-27B cochee ; le POST /api/deploy embarque models[] choisis.
Design : variables du theme reel appliquees (fond carte sur etape active, accent braise) ; verifie par getComputedStyle.
```

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/src/forgeai/data/modeles-locaux.json b/src/forgeai/data/modeles-locaux.json
new file mode 100644
index 0000000..85add60
--- /dev/null
+++ b/src/forgeai/data/modeles-locaux.json
@@ -0,0 +1,2299 @@
+{
+ "_doc": "Registre des modèles IA open-weight déployables localement — 113 entrées, chacune VERIFIEE sur Hugging Face (champ verif = preuve HTTP). Généré par recherche multi-agents 2026-07-19, revu en story P0.3. AUCUN filtrage par matériel local : tout modèle est déployable vers n'importe quel nœud (directive permanente).",
+ "modeles": [
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama",
+    "tgi"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
+   "license": "Llama 3.3 Community License",
+   "name": "Llama 3.3 70B Instruct",
+   "notes_fr": "Dense 70B très mature en prod, qualité proche du 405B de la 3.1. Gated Meta. Q4 ~42 GB → 2×5090 ou offload partiel CPU.",
+   "params_b": 70.6,
+   "release": "2024-12",
+   "source_url": "https://huggingface.co/api/models/meta-llama/Llama-3.3-70B-Instruct",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=711312, gated=manual",
+   "vram_fp16_gb": 141,
+   "vram_q4_gb": 42
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
+   "license": "MIT",
+   "name": "DeepSeek R1 Distill Llama 70B",
+   "notes_fr": "R1 distillé sur base Llama-3.3-70B : raisonnement fort sous licence MIT (plus permissive que Llama). Q4 ~42 GB → 2 GPU.",
+   "params_b": 70.6,
+   "release": "2025-01",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=974485",
+   "vram_fp16_gb": 141,
+   "vram_q4_gb": 42
+  },
+  {
+   "context_k": 1000,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-V4-Pro",
+   "license": "MIT",
+   "name": "DeepSeek V4 Pro",
+   "notes_fr": "MoE 1,6T total / 49B actifs, FP4+FP8 natif, contexte 1M, mode raisonnement max. Serveur multi-GPU obligatoire. DeepSeek-R2 n'existe pas sur HF : V4 est le successeur.",
+   "params_b": 49,
+   "release": "2026-06",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-V4-Pro",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=1487544, id canonique identique",
+   "vram_q4_gb": 900
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-V3.2-Exp",
+   "license": "MIT",
+   "name": "DeepSeek V3.2-Exp",
+   "notes_fr": "MoE 685B total / 37B actifs, sparse attention DSA (long contexte économe). Dépassé par V4 mais utile en recherche. GGUF unsloth/DeepSeek-V3.2-GGUF vérifié.",
+   "params_b": 37,
+   "release": "2025-09",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-V3.2-Exp",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=284174",
+   "vram_fp16_gb": 1370,
+   "vram_q4_gb": 390
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-R1-0528",
+   "license": "MIT",
+   "name": "DeepSeek R1-0528",
+   "notes_fr": "Référence raisonnement open-weight (MoE 685B total / 37B actifs). R2 jamais publié sur HF — la lignée continue avec V4. GGUF communautaires (unsloth).",
+   "params_b": 37,
+   "release": "2025-05",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-R1-0528",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=452842",
+   "vram_fp16_gb": 1370,
+   "vram_q4_gb": 390
+  },
+  {
+   "context_k": 1000,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
+   "license": "Llama 4 Community License",
+   "name": "Llama 4 Maverick",
+   "notes_fr": "MoE 402B total / 17B actifs (128 experts), multimodal, contexte 1M. Gated Meta (formulaire). ~225 GB en Q4 → serveur multi-GPU.",
+   "params_b": 17,
+   "release": "2025-04",
+   "source_url": "https://huggingface.co/api/models/meta-llama/Llama-4-Maverick-17B-128E-Instruct",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=69605, gated=manual",
+   "vram_fp16_gb": 804,
+   "vram_q4_gb": 225
+  },
+  {
+   "context_k": 10000,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
+   "license": "Llama 4 Community License",
+   "name": "Llama 4 Scout",
+   "notes_fr": "MoE 109B total / 17B actifs (16 experts), multimodal, contexte 10M annoncé. Gated Meta. Q4 ~62 GB → 2×5090 ou serveur.",
+   "params_b": 17,
+   "release": "2025-04",
+   "source_url": "https://huggingface.co/api/models/meta-llama/Llama-4-Scout-17B-16E-Instruct",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=460050, gated=manual",
+   "vram_fp16_gb": 218,
+   "vram_q4_gb": 62
+  },
+  {
+   "context_k": 1000,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-V4-Flash",
+   "license": "MIT",
+   "name": "DeepSeek V4 Flash",
+   "notes_fr": "MoE 284B total / 13B actifs, FP4+FP8, contexte 1M. GGUF unsloth dispo. Frontier « abordable » : ~170 GB en Q4 → multi-GPU ou serveur CPU-RAM, pas une seule 5090.",
+   "params_b": 13,
+   "release": "2026-06",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-V4-Flash",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=2955732, id canonique identique",
+   "vram_q4_gb": 170
+  },
+  {
+   "context_k": 1024,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "glm",
+   "gguf": true,
+   "hf_id": "zai-org/GLM-5.2",
+   "license": "MIT",
+   "name": "GLM-5.2",
+   "notes_fr": "Bien open-weight (MIT, HF 2026-06-16). MoE 753B total / ~40B actifs, ctx 1M (IndexShare), MTP. GGUF unsloth dispo. Multi-nœuds ou offload RAM (KTransformers) requis.",
+   "params_b": 40,
+   "release": "2026-06",
+   "source_url": "https://huggingface.co/zai-org/GLM-5.2",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=536177, likes=4153",
+   "vram_fp16_gb": 1510,
+   "vram_q4_gb": 400
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang"
+   ],
+   "famille": "glm",
+   "gguf": false,
+   "hf_id": "zai-org/GLM-5",
+   "license": "MIT",
+   "name": "GLM-5",
+   "notes_fr": "MoE 744B total / 40B actifs (fiche HF). Ctx éval 128K (non précisé). Aucun GGUF trouvé pour la base — préférer 5.2 (ou unsloth/GLM-5.1-GGUF). Multi-nœuds.",
+   "params_b": 40,
+   "release": "2026-02",
+   "source_url": "https://huggingface.co/zai-org/GLM-5",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=98082, likes=2116",
+   "vram_fp16_gb": 1490,
+   "vram_q4_gb": 400
+  },
+  {
+   "context_k": 200,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "glm",
+   "gguf": true,
+   "hf_id": "zai-org/GLM-4.7",
+   "license": "MIT",
+   "name": "GLM-4.7",
+   "notes_fr": "MoE 358B total / 32B actifs, ctx ~200K. GGUF unsloth/bartowski/ubergarm. Serveur multi-GPU ou offload RAM ; successeur direct de 4.6.",
+   "params_b": 32,
+   "release": "2025-12",
+   "source_url": "https://huggingface.co/zai-org/GLM-4.7",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=60503, likes=2046",
+   "vram_fp16_gb": 716,
+   "vram_q4_gb": 200
+  },
+  {
+   "context_k": 200,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "glm",
+   "gguf": true,
+   "hf_id": "zai-org/GLM-4.6",
+   "license": "MIT",
+   "name": "GLM-4.6",
+   "notes_fr": "MoE 357B total / 32B actifs, ctx 200K (fiche). Quantifs llama.cpp/Ollama/LM Studio citées par la fiche officielle. Référence agentique éprouvée.",
+   "params_b": 32,
+   "release": "2025-09",
+   "source_url": "https://huggingface.co/zai-org/GLM-4.6",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=12280, likes=1230",
+   "vram_fp16_gb": 714,
+   "vram_q4_gb": 200
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "glm",
+   "gguf": true,
+   "hf_id": "zai-org/GLM-4.5-Air",
+   "license": "MIT",
+   "name": "GLM-4.5-Air",
+   "notes_fr": "MoE 106B total / 12B actifs. Q4 ~62 GB : > 1 RTX 5090, mais tournable via llama.cpp MoE-offload CPU (64 GB RAM) grâce aux 12B actifs. GGUF unsloth/bartowski.",
+   "params_b": 12,
+   "release": "2025-07",
+   "source_url": "https://huggingface.co/zai-org/GLM-4.5-Air",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=482066, likes=618",
+   "vram_fp16_gb": 220,
+   "vram_q4_gb": 62
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "llama.cpp"
+   ],
+   "famille": "mistral-phi",
+   "hf_id": "mistralai/Devstral-2-123B-Instruct-2512",
+   "license": "MIT modifiée (restriction droits de tiers)",
+   "name": "Devstral 2 (123B)",
+   "notes_fr": "Agent de code frontière, dense 123B, 256k. Recommandé FP8 sur 8 GPU ; Q4 ~70 GB = multi-GPU obligatoire.",
+   "params_b": 123,
+   "release": "2025-12",
+   "source_url": "https://huggingface.co/mistralai/Devstral-2-123B-Instruct-2512",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=65403",
+   "vram_fp16_gb": 250,
+   "vram_q4_gb": 70
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang"
+   ],
+   "famille": "mistral-phi",
+   "hf_id": "mistralai/Mistral-Large-3-675B-Instruct-2512",
+   "license": "Apache-2.0",
+   "name": "Mistral Large 3 (675B MoE)",
+   "notes_fr": "MoE 675B totaux / 41B actifs, 256k, vision, Apache-2.0. Frontière open-weight de Mistral ; nœud 8×H200 en FP8 — tier serveur uniquement.",
+   "params_b": 41,
+   "release": "2025-12",
+   "source_url": "https://huggingface.co/mistralai/Mistral-Large-3-675B-Instruct-2512",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=809",
+   "vram_fp16_gb": 1350,
+   "vram_q4_gb": 380
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama",
+    "sglang",
+    "tgi"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "mistralai/Mixtral-8x7B-Instruct-v0.1",
+   "license": "Apache-2.0",
+   "name": "Mixtral 8x7B Instruct",
+   "notes_fr": "Legacy : MoE 46,7B totaux / 12,9B actifs. Q4 ~26,5 GB > seuil 24 GB du tiering (tient néanmoins en 32 GB). Dépassé par Mistral Small 3.2.",
+   "params_b": 12.9,
+   "release": "2023-12",
+   "source_url": "https://huggingface.co/api/models/mistralai/Mixtral-8x7B-Instruct-v0.1",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=765075",
+   "vram_fp16_gb": 93.4,
+   "vram_q4_gb": 26.5
+  },
+  {
+   "engines": [
+    "vllm",
+    "sglang"
+   ],
+   "famille": "qwen",
+   "gguf": false,
+   "hf_id": "Qwen/Qwen3.5-397B-A17B",
+   "license": "apache-2.0",
+   "name": "Qwen3.5-397B-A17B",
+   "notes_fr": "Flagship MoE 403B total / 17B actifs, multimodal vision. Serveur multi-GPU requis ; variantes FP8 et GPTQ-Int4 officielles. Aucun GGUF trouvé sur HF (recherche library=gguf).",
+   "params_b": 17,
+   "release": "2026-02",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3.5-397B-A17B",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=401166",
+   "vram_fp16_gb": 807,
+   "vram_q4_gb": 230
+  },
+  {
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "qwen",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3.5-122B-A10B",
+   "license": "apache-2.0",
+   "name": "Qwen3.5-122B-A10B",
+   "notes_fr": "MoE 125B total / 10B actifs, multimodal. Compromis flagship/local : Q4 ~72 Go donc 2-3 GPU ou serveur. FP8 et GPTQ-Int4 officiels ; GGUF unsloth (MTP).",
+   "params_b": 10,
+   "release": "2026-02",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3.5-122B-A10B",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=698796",
+   "vram_fp16_gb": 250,
+   "vram_q4_gb": 72
+  },
+  {
+   "context_k": 262,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "qwen",
+   "hf_id": "Qwen/Qwen3-Coder-Next",
+   "license": "apache-2.0",
+   "name": "Qwen3-Coder-Next",
+   "notes_fr": "MoE 80B total / 3B actifs (512 experts, 10+1). Codage agentique, tool-calling, ctx 262k. Meilleur codeur local récent ; Q4 > 32 Go donc multi-GPU ou KTransformers CPU+GPU.",
+   "params_b": 3,
+   "release": "2026-01",
+   "source_url": "https://huggingface.co/Qwen/Qwen3-Coder-Next",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=1029644",
+   "vram_fp16_gb": 160,
+   "vram_q4_gb": 46
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "sglang"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "NousResearch/Hermes-4-70B",
+   "license": "Llama 3.1 Community",
+   "name": "Hermes 4 70B",
+   "notes_fr": "Hermes-4 de Nous est bien open-weight (base Llama 3.1, licence llama3). Raisonnement hybride + tool use/JSON. Q4 ~42 Go : 2 GPU ou offload CPU, dépasse une 5090 seule.",
+   "params_b": 70.6,
+   "release": "2025-08",
+   "source_url": "https://huggingface.co/api/models/NousResearch/Hermes-4-70B",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=1792, gated=False",
+   "vram_fp16_gb": 141,
+   "vram_q4_gb": 42
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
+   "license": "Apache-2.0",
+   "name": "Qwen3-Coder 480B-A35B Instruct",
+   "notes_fr": "MoE 480,15 G total / 35 G actifs (API HF). Flagship code de Qwen, 256 K contexte natif. Multi-nœuds (Q4 ~272 Go, GGUF Unsloth).",
+   "params_b": 35,
+   "release": "2025-07",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-Coder-480B-A35B-Instruct",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=29765, gated=False",
+   "vram_fp16_gb": 960,
+   "vram_q4_gb": 272
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "moonshotai/Kimi-K2-Thinking",
+   "license": "MIT modifiée",
+   "name": "Kimi K2 Thinking",
+   "notes_fr": "MoE 1,06 T total / 32 G actifs, INT4 natif ~594 Go. Raisonnement agentique SOTA open-weight. Kimi K3 : aucun repo HF public (moonshotai/Kimi-K3 → 401 vérifié). Multi-nœuds.",
+   "params_b": 32,
+   "release": "2025-11",
+   "source_url": "https://huggingface.co/api/models/moonshotai/Kimi-K2-Thinking",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=92808, gated=False",
+   "vram_q4_gb": 594
+  },
+  {
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "MiniMaxAI/MiniMax-M2",
+   "license": "MIT modifiée",
+   "name": "MiniMax-M2",
+   "notes_fr": "MoE 228,7 G total / 10 G actifs (API HF), poids FP8 natifs. Très fort code + agentique pour son coût d'inférence. Serveur multi-GPU requis (Q4 ~130 Go).",
+   "params_b": 10,
+   "release": "2025-10",
+   "source_url": "https://huggingface.co/api/models/MiniMaxAI/MiniMax-M2",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=112102, gated=False",
+   "vram_q4_gb": 130
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "vision-multimodal",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-VL-235B-A22B-Instruct",
+   "license": "apache-2.0",
+   "name": "Qwen3-VL 235B-A22B Instruct",
+   "notes_fr": "MoE 235,7B total / 22B actifs. Flagship vision open-weight 2025. Multi-GPU obligatoire (serveur 80 Go+ ou cluster de 5090).",
+   "params_b": 22,
+   "release": "2025-09",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-VL-235B-A22B-Instruct",
+   "tier": "gros",
+   "verif": "HTTP 200 api/models, downloads=1674147",
+   "vram_fp16_gb": 480,
+   "vram_q4_gb": 135
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
+   "license": "MIT",
+   "name": "DeepSeek R1 Distill Qwen 32B",
+   "notes_fr": "Meilleur ratio raisonnement/VRAM de la famille : Q4 ~20 GB, tient sur UNE RTX 5090 32 GB avec marge KV. Cheval de bataille local.",
+   "params_b": 32.8,
+   "release": "2025-01",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=950393",
+   "vram_fp16_gb": 66,
+   "vram_q4_gb": 20
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/gemma-4-31B-it",
+   "license": "apache-2.0",
+   "name": "Gemma 4 31B Instruct",
+   "notes_fr": "Vaisseau amiral dense (256K ctx, texte+image). Licence Apache 2.0. QAT q4_0 GGUF officiel. NB: pas de « gemma-4-27b » — le gros dense de la gén. 4 est 31B.",
+   "params_b": 31.3,
+   "release": "2026-06",
+   "source_url": "https://huggingface.co/google/gemma-4-31B-it",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id echo exact, downloads=12337374, gated=False",
+   "vram_fp16_gb": 63,
+   "vram_q4_gb": 19
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama",
+    "sglang",
+    "tgi"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/gemma-3-27b-it",
+   "license": "gemma",
+   "name": "Gemma 3 27B Instruct",
+   "notes_fr": "Génération précédente, supplanté par Gemma 4 31B/26B-A4B mais écosystème très mûr (QAT GGUF officiel). Licence Gemma (pas Apache) — vérifier l'usage.",
+   "params_b": 27.4,
+   "release": "2025-03",
+   "source_url": "https://huggingface.co/google/gemma-3-27b-it",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=786115, gated=manual (licence à accepter)",
+   "vram_fp16_gb": 55,
+   "vram_q4_gb": 18
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/gemma-4-12B-it",
+   "license": "apache-2.0",
+   "name": "Gemma 4 12B Instruct (unifié)",
+   "notes_fr": "Architecture unifiée any-to-any : texte+image+audio+vidéo en entrée, 256K ctx. GGUF QAT officiel de 6,98 Go — tourne aussi sur GPU 12 Go.",
+   "params_b": 12,
+   "release": "2026-06",
+   "source_url": "https://huggingface.co/google/gemma-4-12B-it",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id echo exact, downloads=2828880, gated=False",
+   "vram_fp16_gb": 24,
+   "vram_q4_gb": 9
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/gemma-4-26B-A4B-it",
+   "license": "apache-2.0",
+   "name": "Gemma 4 26B-A4B Instruct (MoE)",
+   "notes_fr": "MoE ~26B total / 3,8B actifs : débit d'un 4B, qualité proche 27B. 256K ctx, texte+image, QAT GGUF officiel. Meilleur ratio débit/qualité sur une RTX 5090.",
+   "params_b": 3.8,
+   "release": "2026-06",
+   "source_url": "https://huggingface.co/google/gemma-4-26B-A4B-it",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id echo exact, downloads=13639249, gated=False",
+   "vram_fp16_gb": 52,
+   "vram_q4_gb": 16
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "llama.cpp"
+   ],
+   "famille": "glm",
+   "gguf": true,
+   "hf_id": "zai-org/GLM-4-32B-0414",
+   "license": "MIT",
+   "name": "GLM-4-32B-0414",
+   "notes_fr": "Dense 32,6B, ctx 32K natif. Tient en Q4 sur une 5090. GGUF bartowski/lmstudio-community. Solide en code, mais dépassé par GLM-4.7-Flash (plus récent, ctx 200K).",
+   "params_b": 32.6,
+   "release": "2025-04",
+   "source_url": "https://huggingface.co/zai-org/GLM-4-32B-0414",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=12099, likes=487",
+   "vram_fp16_gb": 65,
+   "vram_q4_gb": 19
+  },
+  {
+   "context_k": 200,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "glm",
+   "gguf": true,
+   "hf_id": "zai-org/GLM-4.7-Flash",
+   "license": "MIT",
+   "name": "GLM-4.7-Flash",
+   "notes_fr": "MoE 30B total / 3B actifs, ctx 202752 (config vérifiée). Sweet spot RTX 5090 32 GB en Q4. GGUF unsloth/bartowski. 2,4M téléchargements.",
+   "params_b": 3,
+   "release": "2026-01",
+   "source_url": "https://huggingface.co/zai-org/GLM-4.7-Flash",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=2399093, likes=1785",
+   "vram_fp16_gb": 62,
+   "vram_q4_gb": 18
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama",
+    "sglang"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
+   "license": "Apache-2.0",
+   "name": "Mistral Small 3.2 (24B)",
+   "notes_fr": "Workhorse 24B dense avec vision, arch Mistral3. Q4 ~14,5 GB : très à l'aise sur une RTX 5090 32 GB avec long contexte. Base des Magistral/Devstral Small.",
+   "params_b": 24,
+   "release": "2025-06",
+   "source_url": "https://huggingface.co/api/models/mistralai/Mistral-Small-3.2-24B-Instruct-2506",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=367879",
+   "vram_fp16_gb": 48,
+   "vram_q4_gb": 14.5
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "mistralai/Devstral-Small-2-24B-Instruct-2512",
+   "license": "Apache-2.0",
+   "name": "Devstral Small 2 (24B)",
+   "notes_fr": "Agent de code (moteur par défaut du CLI Mistral Vibe), dense 24B, 256k. Le meilleur codeur open-weight tenant sur UNE 5090.",
+   "params_b": 24,
+   "release": "2025-12",
+   "source_url": "https://huggingface.co/api/models/mistralai/Devstral-Small-2-24B-Instruct-2512",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=259918",
+   "vram_fp16_gb": 48,
+   "vram_q4_gb": 14.5
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "mistralai/Magistral-Small-2509",
+   "license": "Apache-2.0",
+   "name": "Magistral Small 1.2 (24B, raisonnement)",
+   "notes_fr": "Raisonnement à traces (think), fine-tune de Mistral Small 3.2, vision incluse. Complément raisonnement du tier moyen.",
+   "params_b": 24,
+   "release": "2025-09",
+   "source_url": "https://huggingface.co/api/models/mistralai/Magistral-Small-2509",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=37355",
+   "vram_fp16_gb": 48,
+   "vram_q4_gb": 14.5
+  },
+  {
+   "engines": [
+    "vllm"
+   ],
+   "famille": "mistral-phi",
+   "hf_id": "microsoft/Phi-4-reasoning-vision-15B",
+   "license": "MIT",
+   "name": "Phi-4-reasoning-vision (15B)",
+   "notes_fr": "Très récent (janv. 2026) : vision+raisonnement, OCR, grounding GUI/computer-use (ScreenSpot-V2 88,2 %). Support GGUF/llama.cpp non établi.",
+   "params_b": 15.1,
+   "release": "2026-01",
+   "source_url": "https://huggingface.co/api/models/microsoft/Phi-4-reasoning-vision-15B",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=4830",
+   "vram_fp16_gb": 30.2,
+   "vram_q4_gb": 9.5
+  },
+  {
+   "context_k": 16,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama",
+    "sglang",
+    "tgi"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "microsoft/phi-4",
+   "license": "MIT",
+   "name": "Phi-4 (14B)",
+   "notes_fr": "Dense 14,7B MIT, GGUF officiel (microsoft/phi-4-gguf). Phi-5 n'existe pas en open-weight (vérifié 2026-07 : microsoft/phi-5 absent de HF).",
+   "params_b": 14.7,
+   "release": "2024-12",
+   "source_url": "https://huggingface.co/api/models/microsoft/phi-4",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=786751",
+   "vram_fp16_gb": 29.3,
+   "vram_q4_gb": 9.1
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "microsoft/Phi-4-reasoning-plus",
+   "license": "MIT",
+   "name": "Phi-4-reasoning-plus (14B)",
+   "notes_fr": "phi-4 affiné (SFT+RL) pour raisonnement long à traces think. Sorties verbeuses : prévoir du budget tokens.",
+   "params_b": 14.7,
+   "release": "2025-04",
+   "source_url": "https://huggingface.co/api/models/microsoft/Phi-4-reasoning-plus",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=13830",
+   "vram_fp16_gb": 29.3,
+   "vram_q4_gb": 9.1
+  },
+  {
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "qwen",
+   "hf_id": "Qwen/QwQ-32B",
+   "license": "apache-2.0",
+   "name": "QwQ-32B",
+   "notes_fr": "Dense 32,8B raisonnement (mars 2025, arch Qwen2). Historique : dépassé par le thinking natif de Qwen3.5/3.6 — préférer Qwen3.6-27B à VRAM égale.",
+   "params_b": 32.8,
+   "release": "2025-03",
+   "source_url": "https://huggingface.co/api/models/Qwen/QwQ-32B",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=378371",
+   "vram_fp16_gb": 66,
+   "vram_q4_gb": 20
+  },
+  {
+   "context_k": 262,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "qwen",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3.6-27B",
+   "license": "apache-2.0",
+   "name": "Qwen3.6-27B",
+   "notes_fr": "Le « Qwen 3.6 27B » cité existe bien. Dense hybride (Gated DeltaNet), vision native image+vidéo, thinking hybride, MTP, ctx ext. 1M. GGUF unsloth/Qwen3.6-27B-GGUF. Q4 tient sur une 5090.",
+   "params_b": 27.8,
+   "release": "2026-04",
+   "source_url": "https://huggingface.co/Qwen/Qwen3.6-27B",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=5314191",
+   "vram_fp16_gb": 56,
+   "vram_q4_gb": 17
+  },
+  {
+   "context_k": 262,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "qwen",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
+   "license": "apache-2.0",
+   "name": "Qwen3-Coder-30B-A3B-Instruct",
+   "notes_fr": "MoE 30,5B total / 3,3B actifs (128 experts, 8), ctx 262k (1M via Yarn). Codeur agentique qui tient sur UNE 5090 en Q4 ; plus léger que Coder-Next.",
+   "params_b": 3.3,
+   "release": "2025-07",
+   "source_url": "https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=1746771",
+   "vram_fp16_gb": 61,
+   "vram_q4_gb": 18
+  },
+  {
+   "context_k": 262,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "qwen",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3.6-35B-A3B",
+   "license": "apache-2.0",
+   "name": "Qwen3.6-35B-A3B",
+   "notes_fr": "MoE 36B total / 3B actifs (256 experts, 8+1). Vision native, MTP, ctx 262k ext. 1M. Très rapide en local ; Q4 tient sur UNE RTX 5090. GGUF unsloth/Qwen3.6-35B-A3B-GGUF.",
+   "params_b": 3,
+   "release": "2026-04",
+   "source_url": "https://huggingface.co/Qwen/Qwen3.6-35B-A3B",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=6172810",
+   "vram_fp16_gb": 72,
+   "vram_q4_gb": 21
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "mistralai/Devstral-Small-2507",
+   "license": "Apache-2.0",
+   "name": "Devstral Small 2507",
+   "notes_fr": "23,57 G dense (API HF), spécialiste agents logiciels (SWE-bench). Q4 ~14 Go sur la 5090. Remplace Codestral pour l'usage production.",
+   "params_b": 23.6,
+   "release": "2025-07",
+   "source_url": "https://huggingface.co/api/models/mistralai/Devstral-Small-2507",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=35539, gated=False",
+   "vram_fp16_gb": 47,
+   "vram_q4_gb": 14
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "mistralai/Codestral-22B-v0.1",
+   "license": "MNPL-0.1 (non-production)",
+   "name": "Codestral-22B v0.1",
+   "notes_fr": "Seul Codestral open-weight (API HF : 22,25 G). Licence MNPL = recherche/test SEULEMENT, pas de production. Les Codestral 25xx ne sont pas open-weight : prendre Devstral.",
+   "params_b": 22.2,
+   "release": "2024-05",
+   "source_url": "https://huggingface.co/api/models/mistralai/Codestral-22B-v0.1",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=15259, gated=False",
+   "vram_fp16_gb": 44,
+   "vram_q4_gb": 14
+  },
+  {
+   "context_k": 16,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama",
+    "tgi"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "bigcode/starcoder2-15b",
+   "license": "BigCode OpenRAIL-M",
+   "name": "StarCoder2-15B",
+   "notes_fr": "Modèle de BASE FIM 15,96 G (API HF, poids F32), pas instruct. 16 K contexte. Utile en complétion locale transparente (données tracées), sinon dépassé en 2026.",
+   "params_b": 16,
+   "release": "2024-02",
+   "source_url": "https://huggingface.co/api/models/bigcode/starcoder2-15b",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=7920, gated=False",
+   "vram_fp16_gb": 32,
+   "vram_q4_gb": 10
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
+   "license": "DeepSeek Model License",
+   "name": "DeepSeek-Coder-V2-Lite Instruct",
+   "notes_fr": "MoE 15,7 G total / 2,4 G actifs (API HF). 2024 : dépassé par Qwen3-Coder en agentique mais reste efficace en complétion/FIM. Licence DeepSeek avec restrictions d'usage.",
+   "params_b": 2.4,
+   "release": "2024-06",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=611501, gated=False",
+   "vram_fp16_gb": 31,
+   "vram_q4_gb": 10
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "sglang"
+   ],
+   "famille": "vision-multimodal",
+   "hf_id": "OpenGVLab/InternVL3_5-38B",
+   "license": "apache-2.0",
+   "name": "InternVL3.5 38B",
+   "notes_fr": "InternViT + Qwen3-32B. Très fort en OCR/docs et tâches agents. Q4 ≈ 24 Go : à la limite d'une 5090, contexte court. Gamme 1B → 241B-A28B.",
+   "params_b": 38.4,
+   "release": "2025-08",
+   "source_url": "https://huggingface.co/api/models/OpenGVLab/InternVL3_5-38B",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=34660",
+   "vram_fp16_gb": 77,
+   "vram_q4_gb": 24
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "vision-multimodal",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-VL-32B-Instruct",
+   "license": "apache-2.0",
+   "name": "Qwen3-VL 32B Instruct",
+   "notes_fr": "Dense 33,4B : qualité max mono-5090 en Q4 (~22 Go, contexte à limiter). Remplace Qwen2.5-VL-32B/72B pour la plupart des usages vision.",
+   "params_b": 33.4,
+   "release": "2025-10",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-VL-32B-Instruct",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=2906514",
+   "vram_fp16_gb": 67,
+   "vram_q4_gb": 22
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "vision-multimodal",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-VL-30B-A3B-Instruct",
+   "license": "apache-2.0",
+   "name": "Qwen3-VL 30B-A3B Instruct",
+   "notes_fr": "MoE 31B total / 3B actifs — débit élevé sur une seule 5090. Famille phare 2025-2026 pour agents GUI et OCR (32 langues). Contexte 256K natif.",
+   "params_b": 3,
+   "release": "2025-09",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-VL-30B-A3B-Instruct",
+   "tier": "moyen",
+   "verif": "HTTP 200 api/models, downloads=992099",
+   "vram_fp16_gb": 62,
+   "vram_q4_gb": 21
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama",
+    "tgi"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "meta-llama/Llama-3.1-8B-Instruct",
+   "license": "Llama 3.1 Community License",
+   "name": "Llama 3.1 8B Instruct",
+   "notes_fr": "Dense 8B de référence, écosystème géant (fine-tunes, outillage). Gated Meta. Q4 ~5,5 GB, tourne aussi en CPU edge.",
+   "params_b": 8,
+   "release": "2024-07",
+   "source_url": "https://huggingface.co/api/models/meta-llama/Llama-3.1-8B-Instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=8164214, gated=manual",
+   "vram_fp16_gb": 16,
+   "vram_q4_gb": 5.5
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
+   "license": "MIT",
+   "name": "DeepSeek R1 Distill Qwen 7B",
+   "notes_fr": "Raisonnement compact sous MIT : Q4 ~5 GB — GPU 8 GB ou CPU. Idéal edge avec chaîne de pensée.",
+   "params_b": 7.6,
+   "release": "2025-01",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=295628",
+   "vram_fp16_gb": 15.2,
+   "vram_q4_gb": 5
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "deepseek-llama",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
+   "license": "MIT",
+   "name": "DeepSeek R1 Distill Qwen 1.5B",
+   "notes_fr": "1,78B réels (safetensors). Ultra-léger : Q4 ~1,5 GB, CPU edge / embarqué, utile aussi en speculative decoding.",
+   "params_b": 1.78,
+   "release": "2025-01",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=660077",
+   "vram_fp16_gb": 3.6,
+   "vram_q4_gb": 1.5
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "Qwen/Qwen3-Embedding-8B",
+   "license": "apache-2.0",
+   "name": "Qwen3-Embedding 8B",
+   "notes_fr": "N°1 MTEB multilingue à sa sortie. 7,57 Md params vérifiés ; Q4 ~5 GB donc tier petit, mais FP16 (16 GB) vise plutôt la 5090. Pour RAG haut de gamme.",
+   "params_b": 7.57,
+   "release": "2025-06",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-Embedding-8B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=2892647, likes=751",
+   "vram_fp16_gb": 16,
+   "vram_q4_gb": 5
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "jinaai/jina-embeddings-v4",
+   "license": "qwen-research (non commercial)",
+   "name": "Jina Embeddings v4",
+   "notes_fr": "Multimodal texte+images+documents visuels (base Qwen2.5-VL-3B), dense 2048d ou multi-vecteur 128d. Licence Qwen Research = NON commercial ; offre commerciale via Jina.",
+   "params_b": 3.75,
+   "release": "2025-06",
+   "source_url": "https://huggingface.co/jinaai/jina-embeddings-v4",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=639593, likes=529",
+   "vram_fp16_gb": 7.5,
+   "vram_q4_gb": 2.5
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "mixedbread-ai/mxbai-rerank-large-v2",
+   "license": "apache-2.0",
+   "name": "MxBAI Rerank Large v2",
+   "notes_fr": "Reranker génératif base Qwen2.5-1.5B (1,54 Md params vérifiés), 100+ langues, entraîné par RL. SOTA open-weight sur BEIR à sa sortie. Apache-2.0.",
+   "params_b": 1.54,
+   "release": "2025-03",
+   "source_url": "https://huggingface.co/api/models/mixedbread-ai/mxbai-rerank-large-v2",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=60630, likes=142",
+   "vram_fp16_gb": 3.1,
+   "vram_q4_gb": 1
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "embeddings-rerank",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-Embedding-0.6B",
+   "license": "apache-2.0",
+   "name": "Qwen3-Embedding 0.6B",
+   "notes_fr": "Meilleur rapport qualité/taille 2025-2026 (MTEB multilingue). Instructions par tâche, Matryoshka. GGUF officiel Qwen (Q4_K_M/Q8_0) vérifié. Idéal RTX 5090 et CPU edge.",
+   "params_b": 0.6,
+   "release": "2025-06",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-Embedding-0.6B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=10298736, likes=1115",
+   "vram_fp16_gb": 1.2,
+   "vram_q4_gb": 0.5
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "sglang"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "Qwen/Qwen3-Reranker-0.6B",
+   "license": "apache-2.0",
+   "name": "Qwen3-Reranker 0.6B",
+   "notes_fr": "Reranker appairé aux Qwen3-Embedding (base Qwen3-0.6B-Base vérifiée). Contexte 32k rare pour un reranker. Variantes 4B/8B dispo sur HF si besoin de plus de qualité.",
+   "params_b": 0.6,
+   "release": "2025-06",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-Reranker-0.6B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=2678032, likes=374",
+   "vram_fp16_gb": 1.2,
+   "vram_q4_gb": 0.5
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "embeddings-rerank",
+   "gguf": true,
+   "hf_id": "BAAI/bge-m3",
+   "license": "mit",
+   "name": "BGE-M3",
+   "notes_fr": "Référence RAG multilingue : dense + sparse (lexical) + ColBERT multi-vecteur dans un seul modèle, 8k tokens. 34 M téléchargements. GGUF communautaire gpustack vérifié.",
+   "params_b": 0.57,
+   "release": "2024-01",
+   "source_url": "https://huggingface.co/api/models/BAAI/bge-m3",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=34670275, likes=3240",
+   "vram_fp16_gb": 1.2,
+   "vram_q4_gb": 0.4
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm",
+    "llama.cpp"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "BAAI/bge-reranker-v2-m3",
+   "license": "apache-2.0",
+   "name": "BGE Reranker v2-M3",
+   "notes_fr": "Standard de facto du reranking multilingue (17,5 M téléchargements), 568 M params vérifiés. Cross-encoder appairé naturel de BGE-M3 dans un pipeline RAG.",
+   "params_b": 0.57,
+   "release": "2024-03",
+   "source_url": "https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=17535094, likes=1092",
+   "vram_fp16_gb": 1.2,
+   "vram_q4_gb": 0.4
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "Snowflake/snowflake-arctic-embed-l-v2.0",
+   "license": "apache-2.0",
+   "name": "Snowflake Arctic Embed L v2.0",
+   "notes_fr": "Retrieval multilingue solide (90+ langues, base XLM-R large), optimisé recherche sémantique en prod. Apache-2.0 vérifié. Dispo dans la bibliothèque Ollama (arctic-embed2).",
+   "params_b": 0.57,
+   "release": "2024-12",
+   "source_url": "https://huggingface.co/api/models/Snowflake/snowflake-arctic-embed-l-v2.0",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=1561565, likes=248",
+   "vram_fp16_gb": 1.2,
+   "vram_q4_gb": 0.4
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "jinaai/jina-embeddings-v3",
+   "license": "cc-by-nc-4.0",
+   "name": "Jina Embeddings v3",
+   "notes_fr": "XLM-R + adaptateurs LoRA par tâche, Matryoshka, 8k tokens, 100+ langues. Attention : CC-BY-NC-4.0 vérifiée = usage NON commercial (API Jina pour le commercial).",
+   "params_b": 0.57,
+   "release": "2024-09",
+   "source_url": "https://huggingface.co/api/models/jinaai/jina-embeddings-v3",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=3074941, likes=1149",
+   "vram_fp16_gb": 1.2,
+   "vram_q4_gb": 0.4
+  },
+  {
+   "context_k": 0.5,
+   "engines": [
+    "vllm",
+    "llama.cpp"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "intfloat/multilingual-e5-large-instruct",
+   "license": "mit",
+   "name": "Multilingual E5 Large Instruct",
+   "notes_fr": "Baseline robuste et très citée (Microsoft), 100 langues, instructions par tâche, MIT. Contexte 512 tokens : pour chunks courts uniquement.",
+   "params_b": 0.56,
+   "release": "2024-02",
+   "source_url": "https://huggingface.co/api/models/intfloat/multilingual-e5-large-instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=2059193, likes=631",
+   "vram_fp16_gb": 1.1,
+   "vram_q4_gb": 0.4
+  },
+  {
+   "context_k": 0.5,
+   "engines": [
+    "llama.cpp"
+   ],
+   "famille": "embeddings-rerank",
+   "gguf": true,
+   "hf_id": "nomic-ai/nomic-embed-text-v2-moe",
+   "license": "apache-2.0",
+   "name": "Nomic Embed Text v2 MoE",
+   "notes_fr": "Premier embedding MoE ouvert : 475 M totaux / ~305 M actifs (8 experts), 100+ langues. GGUF officiel nomic-ai vérifié. Limite : contexte 512 tokens seulement.",
+   "params_b": 0.31,
+   "release": "2025-02",
+   "source_url": "https://huggingface.co/api/models/nomic-ai/nomic-embed-text-v2-moe",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=1579965, likes=489",
+   "vram_fp16_gb": 1,
+   "vram_q4_gb": 0.3
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "Alibaba-NLP/gte-multilingual-base",
+   "license": "apache-2.0",
+   "name": "GTE Multilingual Base",
+   "notes_fr": "Encoder-only rapide (~10x vs modèles décodeur), 70+ langues, 8k tokens, embeddings élastiques. Très bon compromis débit/qualité pour l'indexation massive.",
+   "params_b": 0.31,
+   "release": "2024-07",
+   "source_url": "https://huggingface.co/api/models/Alibaba-NLP/gte-multilingual-base",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=1249749, likes=367",
+   "vram_fp16_gb": 0.7,
+   "vram_q4_gb": 0.2
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm"
+   ],
+   "famille": "embeddings-rerank",
+   "hf_id": "Alibaba-NLP/gte-multilingual-reranker-base",
+   "license": "apache-2.0",
+   "name": "GTE Multilingual Reranker Base",
+   "notes_fr": "Reranker appairé de gte-multilingual-base : 306 M params vérifiés, 70+ langues, 8k tokens. Léger et rapide, bon choix CPU/edge quand bge-reranker-v2-m3 est trop lourd.",
+   "params_b": 0.31,
+   "release": "2024-07",
+   "source_url": "https://huggingface.co/api/models/Alibaba-NLP/gte-multilingual-reranker-base",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=137999, likes=183",
+   "vram_fp16_gb": 0.7,
+   "vram_q4_gb": 0.2
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama",
+    "tgi"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/codegemma-7b-it",
+   "license": "gemma",
+   "name": "CodeGemma 7B Instruct",
+   "notes_fr": "Héritage 2024 (GGUF officiel google/codegemma-7b-it-GGUF). Aucun CodeGemma 2/3/4 sur HF : pour le code, préférer Gemma 4 12B ou 26B-A4B.",
+   "params_b": 8.5,
+   "release": "2024-04",
+   "source_url": "https://huggingface.co/google/codegemma-7b-it",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=1498, gated=manual",
+   "vram_fp16_gb": 17,
+   "vram_q4_gb": 5.5
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/gemma-4-E4B-it",
+   "license": "apache-2.0",
+   "name": "Gemma 4 E4B Instruct (edge)",
+   "notes_fr": "8B total / 4,5B effectifs (Per-Layer Embeddings). Texte+image+audio (30 s), vidéo par trames. Cible edge/laptop, QAT GGUF officiel. Remplace Gemma 3n E4B.",
+   "params_b": 8,
+   "release": "2026-06",
+   "source_url": "https://huggingface.co/google/gemma-4-E4B-it",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id echo exact, downloads=5493945, gated=False",
+   "vram_fp16_gb": 16,
+   "vram_q4_gb": 5
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "llama.cpp",
+    "ollama",
+    "vllm"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/gemma-4-E2B-it",
+   "license": "apache-2.0",
+   "name": "Gemma 4 E2B Instruct (edge)",
+   "notes_fr": "5,1B total / 2,3B effectifs. Texte+image+audio, 128K ctx, fenêtre glissante 512. Pour mobile/CPU edge ; QAT q4_0 GGUF officiel vérifié.",
+   "params_b": 5.1,
+   "release": "2026-06",
+   "source_url": "https://huggingface.co/google/gemma-4-E2B-it",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id echo exact, downloads=3007038, gated=False",
+   "vram_fp16_gb": 10.5,
+   "vram_q4_gb": 3.2
+  },
+  {
+   "context_k": 2,
+   "engines": [
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/embeddinggemma-300m",
+   "license": "gemma",
+   "name": "EmbeddingGemma 300M",
+   "notes_fr": "Embeddings 768d (Matryoshka) pour le RAG local, base Gemma 3. GGUF QAT ggml-org vérifié. Pas de successeur embeddings Gemma 4 repéré sur HF au 2026-07.",
+   "params_b": 0.3,
+   "release": "2025-09",
+   "source_url": "https://huggingface.co/google/embeddinggemma-300m",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=1580679, gated=manual",
+   "vram_fp16_gb": 0.6,
+   "vram_q4_gb": 0.35
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "llama.cpp",
+    "ollama",
+    "vllm"
+   ],
+   "famille": "gemma",
+   "gguf": true,
+   "hf_id": "google/gemma-3-270m-it",
+   "license": "gemma",
+   "name": "Gemma 3 270M Instruct",
+   "notes_fr": "Micro-modèle (268M) pour classification, routage et fine-tuning ultra-économe ; tourne sur CPU pur. GGUF QAT communautaires (unsloth, lmstudio) vérifiés.",
+   "params_b": 0.27,
+   "release": "2025-08",
+   "source_url": "https://huggingface.co/google/gemma-3-270m-it",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=1310293, gated=manual",
+   "vram_fp16_gb": 0.6,
+   "vram_q4_gb": 0.3
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "glm",
+   "gguf": true,
+   "hf_id": "zai-org/GLM-4.6V-Flash",
+   "license": "MIT",
+   "name": "GLM-4.6V-Flash (vision)",
+   "notes_fr": "VLM dense 9B (10,3B safetensors avec encodeur vision), ctx 128K, optimisé local/basse latence. GGUF unsloth. Meilleur choix vision edge de la famille.",
+   "params_b": 9.4,
+   "release": "2025-12",
+   "source_url": "https://huggingface.co/zai-org/GLM-4.6V-Flash",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=436090, likes=619",
+   "vram_fp16_gb": 21,
+   "vram_q4_gb": 7
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "llama.cpp"
+   ],
+   "famille": "glm",
+   "gguf": true,
+   "hf_id": "zai-org/GLM-4-9B-0414",
+   "license": "MIT",
+   "name": "GLM-4-9B-0414",
+   "notes_fr": "Dense 9,4B, ctx 32K. Q4 ~6 GB : GPU modeste ou CPU edge. GGUF unsloth/bartowski. Petit texte pur ; pour la vision préférer GLM-4.6V-Flash.",
+   "params_b": 9.4,
+   "release": "2025-04",
+   "source_url": "https://huggingface.co/zai-org/GLM-4-9B-0414",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=31691, likes=107",
+   "vram_fp16_gb": 19,
+   "vram_q4_gb": 6
+  },
+  {
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "mistralai/Ministral-3-8B-Instruct-2512",
+   "license": "Apache-2.0",
+   "name": "Ministral 3 8B",
+   "notes_fr": "Famille Mistral 3 (déc. 2025), 8,9B avec vision, Apache-2.0. Bon défaut edge-GPU / tâches routinières du toolkit.",
+   "params_b": 8.9,
+   "release": "2025-12",
+   "source_url": "https://huggingface.co/api/models/mistralai/Ministral-3-8B-Instruct-2512",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=122413",
+   "vram_fp16_gb": 17.8,
+   "vram_q4_gb": 5.6
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm"
+   ],
+   "famille": "mistral-phi",
+   "gguf": false,
+   "hf_id": "microsoft/Phi-4-multimodal-instruct",
+   "license": "MIT",
+   "name": "Phi-4-multimodal (5.6B)",
+   "notes_fr": "Texte+vision+audio (ASR/traduction) en 5,6B MIT — seul multimodal audio du registre. Arch Phi4MM : vLLM/transformers, pas de GGUF.",
+   "params_b": 5.6,
+   "release": "2025-02",
+   "source_url": "https://huggingface.co/api/models/microsoft/Phi-4-multimodal-instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=520709",
+   "vram_fp16_gb": 11.1,
+   "vram_q4_gb": 4.5
+  },
+  {
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "mistralai/Ministral-3-3B-Instruct-2512",
+   "license": "Apache-2.0",
+   "name": "Ministral 3 3B",
+   "notes_fr": "Enfin open-weight : l'ancien Ministral 3B (2410) était API-only, celui-ci est Apache-2.0 avec vision. Idéal CPU/edge.",
+   "params_b": 3.85,
+   "release": "2025-12",
+   "source_url": "https://huggingface.co/api/models/mistralai/Ministral-3-3B-Instruct-2512",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=932716",
+   "vram_fp16_gb": 7.7,
+   "vram_q4_gb": 2.5
+  },
+  {
+   "engines": [
+    "vllm"
+   ],
+   "famille": "mistral-phi",
+   "gguf": false,
+   "hf_id": "microsoft/Phi-4-mini-flash-reasoning",
+   "license": "MIT",
+   "name": "Phi-4-mini-flash-reasoning (3.8B)",
+   "notes_fr": "Raisonnement math compact, décodeur hybride SambaY à débit élevé. Arch Phi4Flash non supportée llama.cpp : vLLM/transformers seulement.",
+   "params_b": 3.85,
+   "release": "2025-06",
+   "source_url": "https://huggingface.co/api/models/microsoft/Phi-4-mini-flash-reasoning",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=801",
+   "vram_fp16_gb": 7.7,
+   "vram_q4_gb": 2.5
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "mistral-phi",
+   "gguf": true,
+   "hf_id": "microsoft/Phi-4-mini-instruct",
+   "license": "MIT",
+   "name": "Phi-4-mini (3.8B)",
+   "notes_fr": "3,8B MIT, 128k, multilingue, function calling. Excellent ratio qualité/VRAM pour CPU/edge.",
+   "params_b": 3.84,
+   "release": "2025-02",
+   "source_url": "https://huggingface.co/api/models/microsoft/Phi-4-mini-instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=432775",
+   "vram_fp16_gb": 7.7,
+   "vram_q4_gb": 2.5
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-4B-Instruct-2507",
+   "license": "apache-2.0",
+   "name": "Qwen3 4B Instruct 2507",
+   "notes_fr": "4,02 Md params vérifiés. Meilleur rapport qualité/taille ≤4 GB VRAM en 2026, contexte 256k natif. Haut de gamme du tier edge, tourne aussi en CPU via GGUF.",
+   "params_b": 4,
+   "release": "2025-08",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-4B-Instruct-2507",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=3416610, gated=False",
+   "vram_fp16_gb": 8.5,
+   "vram_q4_gb": 3
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "ibm-granite/granite-4.0-micro",
+   "license": "apache-2.0",
+   "name": "Granite 4.0 Micro (IBM)",
+   "notes_fr": "3,4 Md params vérifiés, Apache 2.0, orienté entreprise (RAG, function calling). Variantes hybrides Mamba-2 h-micro/h-tiny dans la même famille. GGUF officiels IBM.",
+   "params_b": 3.4,
+   "release": "2025-10",
+   "source_url": "https://huggingface.co/api/models/ibm-granite/granite-4.0-micro",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=72315, gated=False",
+   "vram_fp16_gb": 7,
+   "vram_q4_gb": 2.6
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama",
+    "tgi"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "meta-llama/Llama-3.2-3B-Instruct",
+   "license": "llama3.2 (Llama 3.2 Community License)",
+   "name": "Llama 3.2 3B Instruct",
+   "notes_fr": "3,21 Md params vérifiés. Écosystème le plus mature (finetunes, adaptateurs), contexte 128k. Repo gated : accepter la licence Meta sur HF avant téléchargement.",
+   "params_b": 3.2,
+   "release": "2024-09",
+   "source_url": "https://huggingface.co/api/models/meta-llama/Llama-3.2-3B-Instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=2036549, gated=manual (gated mais existe)",
+   "vram_fp16_gb": 6.8,
+   "vram_q4_gb": 2.4
+  },
+  {
+   "context_k": 64,
+   "engines": [
+    "vllm",
+    "llama.cpp"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "HuggingFaceTB/SmolLM3-3B",
+   "license": "apache-2.0",
+   "name": "SmolLM3 3B",
+   "notes_fr": "3,08 Md params vérifiés. Petit modèle ouvert de référence (recette d'entraînement publiée), mode raisonnement hybride, multilingue dont français. Contexte 64k (128k via YaRN).",
+   "params_b": 3.1,
+   "release": "2025-07",
+   "source_url": "https://huggingface.co/api/models/HuggingFaceTB/SmolLM3-3B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=672686, gated=False",
+   "vram_fp16_gb": 6.5,
+   "vram_q4_gb": 2.4
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-1.7B",
+   "license": "apache-2.0",
+   "name": "Qwen3 1.7B",
+   "notes_fr": "2,03 Md params vérifiés (nominal 1.7B). Mode think/no-think commutable, très bon en CPU quantifié Q4. Référence du tier ~2B.",
+   "params_b": 2,
+   "release": "2025-04",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-1.7B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=5848353, gated=False",
+   "vram_fp16_gb": 4.5,
+   "vram_q4_gb": 1.6
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
+   "license": "apache-2.0",
+   "name": "SmolLM2 1.7B Instruct",
+   "notes_fr": "1,71 Md params vérifiés. Prédécesseur de SmolLM3, encore pertinent en CPU pur (variantes ONNX quantifiées officielles). Préférer SmolLM3-3B si 2,5 GB dispo.",
+   "params_b": 1.7,
+   "release": "2024-10",
+   "source_url": "https://huggingface.co/api/models/HuggingFaceTB/SmolLM2-1.7B-Instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=157095, gated=False",
+   "vram_fp16_gb": 3.7,
+   "vram_q4_gb": 1.5
+  },
+  {
+   "context_k": 8,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "tiiuae/Falcon3-1B-Instruct",
+   "license": "falcon-llm-license",
+   "name": "Falcon 3 1B Instruct (TII)",
+   "notes_fr": "1,67 Md params vérifiés. Correct en maths/code pour sa taille ; licence TII propre (pas Apache), contexte 8k. Falcon3-3B vérifié aussi mais redondant ici.",
+   "params_b": 1.7,
+   "release": "2024-12",
+   "source_url": "https://huggingface.co/api/models/tiiuae/Falcon3-1B-Instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=21791, gated=False",
+   "vram_fp16_gb": 3.6,
+   "vram_q4_gb": 1.5
+  },
+  {
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "ibm-granite/granite-4.0-1b",
+   "license": "apache-2.0",
+   "name": "Granite 4.0 Nano 1B (IBM)",
+   "notes_fr": "1,63 Md params vérifiés (famille Nano, dense). Très récent, Apache 2.0, pensé pour edge/CPU et IoT. Existe aussi en variante hybride h-1b et en 350M.",
+   "params_b": 1.6,
+   "release": "2025-10",
+   "source_url": "https://huggingface.co/api/models/ibm-granite/granite-4.0-1b",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=9566, gated=False",
+   "vram_fp16_gb": 3.5,
+   "vram_q4_gb": 1.4
+  },
+  {
+   "context_k": 4,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "allenai/OLMo-2-0425-1B-Instruct",
+   "license": "apache-2.0",
+   "name": "OLMo 2 1B Instruct (AI2)",
+   "notes_fr": "1,48 Md params vérifiés. Seul du lot 100 % ouvert (poids + données + code d'entraînement) : idéal souveraineté/auditabilité. Limite : contexte court 4k.",
+   "params_b": 1.5,
+   "release": "2025-04",
+   "source_url": "https://huggingface.co/api/models/allenai/OLMo-2-0425-1B-Instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=56131, gated=False",
+   "vram_fp16_gb": 3.2,
+   "vram_q4_gb": 1.3
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "llama.cpp",
+    "ollama",
+    "vllm"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "LiquidAI/LFM2-1.2B",
+   "license": "lfm1.0 (LFM Open License v1.0)",
+   "name": "LFM2 1.2B (Liquid AI)",
+   "notes_fr": "1,17 Md params vérifiés. LFM EST open-weight via LFM2 (licence lfm1.0 : libre sous ~10 M$ de revenus). Architecture hybride conçue pour l'inférence CPU/edge rapide.",
+   "params_b": 1.2,
+   "release": "2025-07",
+   "source_url": "https://huggingface.co/api/models/LiquidAI/LFM2-1.2B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=143740, gated=False",
+   "vram_fp16_gb": 2.6,
+   "vram_q4_gb": 1.1
+  },
+  {
+   "context_k": 128,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama",
+    "tgi"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "meta-llama/Llama-3.2-1B-Instruct",
+   "license": "llama3.2 (Llama 3.2 Community License)",
+   "name": "Llama 3.2 1B Instruct",
+   "notes_fr": "1,24 Md params vérifiés. Ultra-léger avec contexte 128k, bon pour résumé/extraction on-device. Gated (acceptation licence Meta requise).",
+   "params_b": 1.2,
+   "release": "2024-09",
+   "source_url": "https://huggingface.co/api/models/meta-llama/Llama-3.2-1B-Instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=9991558, gated=manual (gated mais existe)",
+   "vram_fp16_gb": 2.8,
+   "vram_q4_gb": 1.2
+  },
+  {
+   "context_k": 2,
+   "engines": [
+    "llama.cpp",
+    "ollama",
+    "vllm"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
+   "license": "apache-2.0",
+   "name": "TinyLlama 1.1B Chat",
+   "notes_fr": "1,10 Md params vérifiés. Historique (2023) : dépassé par Qwen3-0.6B/Gemma3-1B/Granite Nano sur tout. À garder uniquement comme baseline ultra-compatible.",
+   "params_b": 1.1,
+   "release": "2023-12",
+   "source_url": "https://huggingface.co/api/models/TinyLlama/TinyLlama-1.1B-Chat-v1.0",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=2402395, gated=False",
+   "vram_fp16_gb": 2.4,
+   "vram_q4_gb": 1
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "google/gemma-3-1b-it",
+   "license": "gemma (Gemma Terms of Use)",
+   "name": "Gemma 3 1B IT",
+   "notes_fr": "1,0 Md params vérifiés. QAT officiel Google en GGUF Q4 (qualité quasi-bf16 à ~0,7 GB). Licence Gemma = usage permis mais conditions Google, pas Apache.",
+   "params_b": 1,
+   "release": "2025-03",
+   "source_url": "https://huggingface.co/api/models/google/gemma-3-1b-it",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=3974832, gated=manual (gated mais existe)",
+   "vram_fp16_gb": 2.2,
+   "vram_q4_gb": 1
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "petits-edge",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-0.6B",
+   "license": "apache-2.0",
+   "name": "Qwen3 0.6B",
+   "notes_fr": "752 M params vérifiés. Le plus petit Qwen3 utile : routage, classification, drafts (speculative decoding) sur nœuds sans GPU. Tourne sur Raspberry Pi.",
+   "params_b": 0.75,
+   "release": "2025-04",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-0.6B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=26124974, gated=False",
+   "vram_fp16_gb": 1.6,
+   "vram_q4_gb": 0.8
+  },
+  {
+   "context_k": 262,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "qwen",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3.5-9B",
+   "license": "apache-2.0",
+   "name": "Qwen3.5-9B",
+   "notes_fr": "Dense hybride 9,65B, vision native, 201 langues, thinking par défaut, ctx 262k ext. 1M. Excellent défaut « petit » ; Q4 ~6,5 Go. GGUF unsloth/Qwen3.5-9B-GGUF.",
+   "params_b": 9.65,
+   "release": "2026-02",
+   "source_url": "https://huggingface.co/Qwen/Qwen3.5-9B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=9228130",
+   "vram_fp16_gb": 19,
+   "vram_q4_gb": 6.5
+  },
+  {
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "qwen",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3.5-4B",
+   "license": "apache-2.0",
+   "name": "Qwen3.5-4B",
+   "notes_fr": "Dense 4,66B multimodal (vision native). Petit agent/edge GPU 4-6 Go de VRAM. GGUF unsloth/Qwen3.5-4B-MTP-GGUF.",
+   "params_b": 4.66,
+   "release": "2026-02",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3.5-4B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=6591518",
+   "vram_fp16_gb": 9.3,
+   "vram_q4_gb": 3.2
+  },
+  {
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp"
+   ],
+   "famille": "qwen",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3.5-2B",
+   "license": "apache-2.0",
+   "name": "Qwen3.5-2B",
+   "notes_fr": "Dense 2,27B multimodal, cible CPU/edge (tourne sans GPU en Q4). GGUF unsloth/Qwen3.5-2B-GGUF.",
+   "params_b": 2.27,
+   "release": "2026-02",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3.5-2B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id canonique identique, downloads=2175835",
+   "vram_fp16_gb": 4.5,
+   "vram_q4_gb": 1.8
+  },
+  {
+   "context_k": 32,
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama",
+    "sglang"
+   ],
+   "famille": "raisonnement-code",
+   "gguf": true,
+   "hf_id": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
+   "license": "MIT",
+   "name": "DeepSeek-R1-0528 Distill Qwen3-8B",
+   "notes_fr": "Distillation R1-0528 sur Qwen3-8B (API HF : 8,19 G BF16). Q4 ~6 Go : GPU 8 Go ou CPU edge. Meilleur petit raisonneur MIT.",
+   "params_b": 8.2,
+   "release": "2025-05",
+   "source_url": "https://huggingface.co/api/models/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=2264686, gated=False",
+   "vram_fp16_gb": 16,
+   "vram_q4_gb": 6
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "vision-multimodal",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-VL-8B-Instruct",
+   "license": "apache-2.0",
+   "name": "Qwen3-VL 8B Instruct",
+   "notes_fr": "Dense 8,8B. Meilleur rapport qualité/VRAM du tier petit. Existe aussi en 2B/Thinking/FP8. Successeur direct de Qwen2.5-VL-7B.",
+   "params_b": 8.8,
+   "release": "2025-10",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-VL-8B-Instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=4902186",
+   "vram_fp16_gb": 18,
+   "vram_q4_gb": 7
+  },
+  {
+   "engines": [
+    "vllm",
+    "llama.cpp",
+    "ollama",
+    "sglang"
+   ],
+   "famille": "vision-multimodal",
+   "gguf": true,
+   "hf_id": "openbmb/MiniCPM-V-4_5",
+   "license": "apache-2.0",
+   "name": "MiniCPM-V 4.5",
+   "notes_fr": "8,7B (base Qwen3-8B). Vision haute résolution + vidéo, GGUF/int4 officiels, tourne jusque sur iPad. Excellent OCR pour sa taille.",
+   "params_b": 8.7,
+   "release": "2025-08",
+   "source_url": "https://huggingface.co/api/models/openbmb/MiniCPM-V-4_5",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=337253",
+   "vram_fp16_gb": 18,
+   "vram_q4_gb": 6
+  },
+  {
+   "engines": [
+    "vllm",
+    "sglang"
+   ],
+   "famille": "vision-multimodal",
+   "hf_id": "allenai/olmOCR-2-7B-1025",
+   "license": "apache-2.0",
+   "name": "olmOCR 2 7B",
+   "notes_fr": "OCR de documents → Markdown/HTML (équations, tableaux). Base Qwen2.5-VL-7B + RLVR, pipeline olmocr (vLLM). Recette 100% ouverte (AllenAI).",
+   "params_b": 8.3,
+   "release": "2025-10",
+   "source_url": "https://huggingface.co/api/models/allenai/olmOCR-2-7B-1025",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=44526",
+   "vram_fp16_gb": 17,
+   "vram_q4_gb": 6
+  },
+  {
+   "context_k": 256,
+   "engines": [
+    "vllm",
+    "sglang",
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "vision-multimodal",
+   "gguf": true,
+   "hf_id": "Qwen/Qwen3-VL-4B-Instruct",
+   "license": "apache-2.0",
+   "name": "Qwen3-VL 4B Instruct",
+   "notes_fr": "Dense 4,4B pour edge GPU/CPU. OCR et lecture d'écran solides pour la taille. Variante FP8 officielle disponible.",
+   "params_b": 4.4,
+   "release": "2025-10",
+   "source_url": "https://huggingface.co/api/models/Qwen/Qwen3-VL-4B-Instruct",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=3759410",
+   "vram_fp16_gb": 9,
+   "vram_q4_gb": 3.5
+  },
+  {
+   "engines": [
+    "vllm"
+   ],
+   "famille": "vision-multimodal",
+   "hf_id": "nanonets/Nanonets-OCR2-3B",
+   "license": "non précisée sur HF (base Qwen2.5-VL-3B)",
+   "name": "Nanonets-OCR2 3B",
+   "notes_fr": "OCR structuré : LaTeX, tableaux MD/HTML, cases à cocher, signatures, flowcharts→mermaid, manuscrit. Aucun tag licence sur HF — vérifier avant prod.",
+   "params_b": 3.8,
+   "release": "2025-10",
+   "source_url": "https://huggingface.co/api/models/nanonets/Nanonets-OCR2-3B",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=778227",
+   "vram_fp16_gb": 8,
+   "vram_q4_gb": 3
+  },
+  {
+   "context_k": 2,
+   "engines": [
+    "llama.cpp",
+    "ollama"
+   ],
+   "famille": "vision-multimodal",
+   "gguf": true,
+   "hf_id": "vikhyatk/moondream2",
+   "license": "apache-2.0",
+   "name": "Moondream 2",
+   "notes_fr": "1,9B, référence VLM CPU/edge (Apache, révisé jusque 2025-09). Détection/pointage inclus. moondream3-preview (MoE 9B/2B actifs, licence 'other') vérifié aussi.",
+   "params_b": 1.9,
+   "release": "2024-03",
+   "source_url": "https://huggingface.co/api/models/vikhyatk/moondream2",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, downloads=2123330",
+   "vram_fp16_gb": 4,
+   "vram_q4_gb": 1.5
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "kyutai/moshiko-pytorch-bf16",
+   "license": "CC-BY-4.0",
+   "name": "Moshi (Moshiko) — voix-à-voix Kyutai",
+   "notes_fr": "Speech-to-speech full-duplex temps réel (~200 ms), codec Mimi. bf16 ≈ 16 Go ; variante quantifiée officielle vérifiée (kyutai/moshiko-candle-q8). Runtimes PyTorch/Rust-candle/MLX, anglais.",
+   "params_b": 7.69,
+   "release": "2024-09",
+   "source_url": "https://huggingface.co/kyutai/moshiko-pytorch-bf16",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=187043",
+   "vram_fp16_gb": 15.4,
+   "vram_q4_gb": 6
+  },
+  {
+   "engines": [
+    "vllm",
+    "llama.cpp"
+   ],
+   "famille": "voix",
+   "gguf": true,
+   "hf_id": "canopylabs/orpheus-3b-0.1-ft",
+   "license": "Apache-2.0",
+   "name": "Orpheus 3B (TTS)",
+   "notes_fr": "TTS expressif backbone Llama-3.2-3B : émotions par tags, clonage zero-shot, streaming temps réel via vLLM. GGUF communautaire vérifié (isaiahbjork/...-Q4_K_M-GGUF).",
+   "params_b": 3.78,
+   "release": "2025-03",
+   "source_url": "https://huggingface.co/canopylabs/orpheus-3b-0.1-ft",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, gated=auto, downloads=23897",
+   "vram_fp16_gb": 7.6,
+   "vram_q4_gb": 3
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "nvidia/canary-qwen-2.5b",
+   "license": "CC-BY-4.0",
+   "name": "NVIDIA Canary-Qwen-2.5B (STT)",
+   "notes_fr": "STT anglais SOTA (WER record OpenASR) + mode LLM (résumé/QA sur la transcription, backbone Qwen3). Runtime NeMo (SALM). Anglais seulement.",
+   "params_b": 2.56,
+   "release": "2025-06",
+   "source_url": "https://huggingface.co/nvidia/canary-qwen-2.5b",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=49797",
+   "vram_fp16_gb": 5.1,
+   "vram_q4_gb": 3
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "sesame/csm-1b",
+   "license": "Apache-2.0",
+   "name": "CSM-1B Sesame (TTS conversationnel)",
+   "notes_fr": "CSM de Sesame EST open-weight (Apache 2.0). TTS conversationnel avec contexte audio (backbone Llama + décodeur Mimi). Runtime PyTorch/transformers dédié, anglais.",
+   "params_b": 1.55,
+   "release": "2025-03",
+   "source_url": "https://huggingface.co/sesame/csm-1b",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, gated=auto, downloads=255097",
+   "vram_fp16_gb": 3.1,
+   "vram_q4_gb": 2
+  },
+  {
+   "engines": [
+    "vllm"
+   ],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "openai/whisper-large-v3",
+   "license": "Apache-2.0",
+   "name": "Whisper large-v3 (STT)",
+   "notes_fr": "Référence STT multilingue (99 langues), meilleure précision que turbo. faster-whisper/whisper.cpp (GGML) pour l'edge, vLLM pour le serveur.",
+   "params_b": 1.54,
+   "release": "2023-11",
+   "source_url": "https://huggingface.co/openai/whisper-large-v3",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=5846236",
+   "vram_fp16_gb": 3.1,
+   "vram_q4_gb": 1.5
+  },
+  {
+   "engines": [
+    "vllm"
+   ],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "openai/whisper-large-v3-turbo",
+   "license": "MIT",
+   "name": "Whisper large-v3-turbo (STT)",
+   "notes_fr": "STT multilingue rapide (decoder réduit, ~8x plus vite que large-v3). Runtimes usuels : faster-whisper/CTranslate2, whisper.cpp (GGML), vLLM. Idéal RTX 5090 et edge.",
+   "params_b": 0.809,
+   "release": "2024-10",
+   "source_url": "https://huggingface.co/openai/whisper-large-v3-turbo",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=8055662",
+   "vram_fp16_gb": 1.7,
+   "vram_q4_gb": 1
+  },
+  {
+   "engines": [
+    "vllm"
+   ],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "distil-whisper/distil-large-v3.5",
+   "license": "MIT",
+   "name": "Distil-Whisper large-v3.5 (STT)",
+   "notes_fr": "Distillation de large-v3, ~1.5x plus rapide, anglais seulement. Compatible faster-whisper et spéculatif avec large-v3. Pour edge CPU/petit GPU anglophone.",
+   "params_b": 0.756,
+   "release": "2024-12",
+   "source_url": "https://huggingface.co/distil-whisper/distil-large-v3.5",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=3818",
+   "vram_fp16_gb": 1.5,
+   "vram_q4_gb": 1
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "coqui/XTTS-v2",
+   "license": "Coqui Public Model License (other)",
+   "name": "XTTS-v2 (TTS clonage multilingue)",
+   "notes_fr": "Clonage voix 6 s, 17 langues dont fr. Taille non publiée sur la fiche (~0,75B communément cité). Licence Coqui = usage NON commercial. Runtime Coqui TTS.",
+   "params_b": 0.75,
+   "release": "2023-10",
+   "source_url": "https://huggingface.co/coqui/XTTS-v2",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=9574240",
+   "vram_fp16_gb": 2,
+   "vram_q4_gb": 2.5
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "nvidia/parakeet-tdt-0.6b-v3",
+   "license": "CC-BY-4.0",
+   "name": "NVIDIA Parakeet TDT 0.6B v3 (STT)",
+   "notes_fr": "STT ultra-rapide 25 langues européennes (fr inclus), top débit du leaderboard OpenASR. Runtime NeMo/ONNX (pas vLLM/llama.cpp). Poids publiés en F32.",
+   "params_b": 0.627,
+   "release": "2025-08",
+   "source_url": "https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=118746",
+   "vram_fp16_gb": 1.3,
+   "vram_q4_gb": 1.5
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "2Noise/ChatTTS",
+   "license": "CC-BY-NC-4.0",
+   "name": "ChatTTS (TTS dialogue)",
+   "notes_fr": "TTS optimisé dialogue (rires, pauses contrôlables), en/zh seulement. Taille non publiée sur la fiche (~0,5B communément cité). Licence NON commerciale.",
+   "params_b": 0.5,
+   "release": "2024-05",
+   "source_url": "https://huggingface.co/2Noise/ChatTTS",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=2319",
+   "vram_fp16_gb": 1,
+   "vram_q4_gb": 1
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "gpt-omni/mini-omni",
+   "license": "MIT",
+   "name": "Mini-Omni — voix-à-voix",
+   "notes_fr": "Voix-à-voix léger (base Qwen2-0.5B, taille non publiée sur la fiche) : écoute et répond en audio en streaming. Qualité inférieure à Moshi mais tient sur edge. Runtime dédié.",
+   "params_b": 0.5,
+   "release": "2024-08",
+   "source_url": "https://huggingface.co/gpt-omni/mini-omni",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=1",
+   "vram_fp16_gb": 1.5,
+   "vram_q4_gb": 1
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "SWivid/F5-TTS",
+   "license": "CC-BY-NC-4.0",
+   "name": "F5-TTS (TTS clonage)",
+   "notes_fr": "Clonage vocal zero-shot excellent (flow matching, base 336M non publiée sur la fiche, taille tirée des poids F5TTS_Base). ATTENTION licence NON COMMERCIALE.",
+   "params_b": 0.336,
+   "release": "2024-10",
+   "source_url": "https://huggingface.co/SWivid/F5-TTS",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=789334",
+   "vram_fp16_gb": 0.7,
+   "vram_q4_gb": 1
+  },
+  {
+   "engines": [],
+   "famille": "voix",
+   "gguf": false,
+   "hf_id": "hexgrad/Kokoro-82M",
+   "license": "Apache-2.0",
+   "name": "Kokoro-82M (TTS)",
+   "notes_fr": "TTS 82M au rapport qualité/taille imbattable, multi-voix (fr incluse), temps réel sur CPU (ONNX). Runtime kokoro/ONNX. Le choix par défaut edge et serveur.",
+   "params_b": 0.082,
+   "release": "2024-12",
+   "source_url": "https://huggingface.co/hexgrad/Kokoro-82M",
+   "tier": "petit",
+   "verif": "HTTP 200 api/models, id exact, downloads=9918250",
+   "vram_fp16_gb": 0.4,
+   "vram_q4_gb": 0.5
+  }
+ ],
+ "total": 113,
+ "version": "2026-07-19"
+}
\ No newline at end of file
diff --git a/src/forgeai/web/assets/app.css b/src/forgeai/web/assets/app.css
index dbfe179..09c3317 100644
--- a/src/forgeai/web/assets/app.css
+++ b/src/forgeai/web/assets/app.css
@@ -264,34 +264,34 @@ code {
 .sphere-step {
   display: inline-flex; align-items: center; gap: 6px;
   padding: 5px 10px; border-radius: 8px; cursor: pointer;
-  border: 1px solid var(--line, #38434F); background: var(--panel-2, #212934);
+  border: 1px solid var(--border); background: var(--card-bg);
   color: inherit; font-size: 12px;
 }
 .sphere-step .sphere-num {
-  font-weight: 700; color: var(--accent, #EA6A2E);
+  font-weight: 700; color: var(--accent);
 }
 .sphere-step .sphere-count { opacity: .6; font-size: 11px; }
 .sphere-step.active {
-  border-color: var(--accent, #EA6A2E);
-  box-shadow: 0 0 0 1px var(--accent, #EA6A2E);
+  border-color: var(--accent);
+  box-shadow: 0 0 0 1px var(--accent);
 }
 .bricks-toolbar {
   display: flex; align-items: center; gap: 12px; margin: 10px 0; flex-wrap: wrap;
 }
 .bricks-toolbar input[type="search"] {
   flex: 1; min-width: 220px; padding: 8px 12px; border-radius: 8px;
-  border: 1px solid var(--line, #38434F); background: var(--panel, #1A2027); color: inherit;
+  border: 1px solid var(--border); background: var(--card-bg); color: inherit;
 }
 .bricks-counts { font-size: 12.5px; opacity: .8; }
 .bricks-list { display: flex; flex-direction: column; gap: 6px; }
 .brick-row {
   display: flex; align-items: flex-start; gap: 10px;
   padding: 9px 12px; border-radius: 10px;
-  border: 1px solid var(--line, #38434F); background: var(--panel, #1A2027);
+  border: 1px solid var(--border); background: var(--card-bg);
   cursor: pointer;
 }
-.brick-row input[type="checkbox"] { margin-top: 3px; accent-color: var(--accent, #EA6A2E); }
-.brick-row.installed { border-color: color-mix(in srgb, var(--accent, #EA6A2E) 45%, transparent); }
+.brick-row input[type="checkbox"] { margin-top: 3px; accent-color: var(--accent); }
+.brick-row.installed { border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
 .brick-row.locked { opacity: .92; }
 .brick-main { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
 .brick-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
@@ -302,8 +302,8 @@ code {
   font-size: 10px; letter-spacing: .04em; text-transform: uppercase;
   padding: 2px 7px; border-radius: 999px; white-space: nowrap;
 }
-.badge-installed { background: color-mix(in srgb, var(--accent, #EA6A2E) 18%, transparent); color: var(--accent, #EA6A2E); }
-.badge-locked { border: 1px solid var(--line, #38434F); opacity: .85; }
+.badge-installed { background: color-mix(in srgb, var(--accent) 18%, transparent); color: var(--accent); }
+.badge-locked { border: 1px solid var(--border); opacity: .85; }
 .badge-default { background: color-mix(in srgb, #2E9E5B 18%, transparent); color: #2E9E5B; }
 
 /* ---------- Modèles & clés API (B-02c) ---------- */
@@ -311,7 +311,7 @@ code {
 .model-row {
   display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
   padding: 8px 12px; border-radius: 10px;
-  border: 1px solid var(--line, #38434F); background: var(--panel, #1A2027);
+  border: 1px solid var(--border); background: var(--card-bg);
 }
 .model-form { margin-top: 12px; }
 .form-grid {
@@ -320,7 +320,7 @@ code {
 .form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }
 .form-grid input, .form-grid select {
   padding: 8px 10px; border-radius: 8px;
-  border: 1px solid var(--line, #38434F); background: var(--panel, #1A2027); color: inherit;
+  border: 1px solid var(--border); background: var(--card-bg); color: inherit;
 }
 .form-note { font-size: 12px; opacity: .7; margin: 10px 0 6px; }
 .form-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
@@ -330,7 +330,7 @@ code {
 /* ---------- Résumé & Déploiement (B-02e) ---------- */
 .deploy-log {
   margin-top: 12px; padding: 12px 14px; border-radius: 10px;
-  border: 1px solid var(--line, #38434F); background: #10151B; color: #C9D4DE;
+  border: 1px solid var(--border); background: #10151B; color: #C9D4DE;
   font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px;
   line-height: 1.55; max-height: 320px; overflow-y: auto; white-space: pre-wrap;
 }
@@ -338,7 +338,74 @@ code {
 
 /* ---------- A11y (B-02f) ---------- */
 :focus-visible {
-  outline: 2px solid var(--accent, #EA6A2E);
+  outline: 2px solid var(--accent);
   outline-offset: 2px;
   border-radius: 4px;
 }
+
+/* ---------- Installateur (P0.3) — Forge Console ---------- */
+.brand { display: flex; align-items: center; gap: 12px; }
+.brand-mark {
+  font-size: 26px; color: var(--accent);
+  filter: drop-shadow(0 0 6px color-mix(in srgb, var(--accent) 55%, transparent));
+}
+.brand-text h1 { margin: 0; font-size: 19px; letter-spacing: .02em; }
+.brand-tagline { margin: 2px 0 0; font-size: 12px; opacity: .65; }
+
+.installer {
+  display: grid; grid-template-columns: 210px 1fr; gap: 26px;
+  max-width: 1180px; margin: 0 auto; padding: 22px 18px 60px;
+}
+@media (max-width: 860px) { .installer { grid-template-columns: 1fr; } }
+
+.step-rail { display: flex; flex-direction: column; gap: 4px; position: sticky; top: 18px; align-self: start; }
+@media (max-width: 860px) { .step-rail { flex-direction: row; flex-wrap: wrap; position: static; } }
+.step-item {
+  display: flex; align-items: center; gap: 11px; text-align: left;
+  padding: 10px 12px; border-radius: 10px; cursor: pointer;
+  border: 1px solid transparent; background: transparent; color: inherit;
+  font-size: 13.5px; transition: background .15s, border-color .15s;
+}
+.step-item:hover { background: var(--card-bg); }
+.step-item .step-num {
+  display: inline-flex; align-items: center; justify-content: center;
+  width: 26px; height: 26px; border-radius: 50%; font-size: 12px; font-weight: 700;
+  border: 1.5px solid var(--border); flex: none;
+}
+.step-item.active {
+  background: var(--card-bg);
+  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
+}
+.step-item.active .step-num { border-color: var(--accent); color: var(--accent); }
+.step-item.done .step-num {
+  background: color-mix(in srgb, var(--accent) 22%, transparent);
+  border-color: var(--accent);
+}
+.step-item.locked { opacity: .45; cursor: not-allowed; }
+
+.step-panel > h2 { margin: 4px 0 6px; font-size: 21px; }
+.step-lede { margin: 0 0 18px; font-size: 13.5px; opacity: .75; max-width: 70ch; line-height: 1.5; }
+
+.step-nav {
+  display: flex; align-items: center; justify-content: space-between; gap: 14px;
+  margin-top: 30px; padding-top: 18px; border-top: 1px solid var(--border);
+}
+.btn-primary {
+  background: var(--accent); color: #fff; border-color: var(--accent);
+  font-weight: 600;
+}
+.btn-primary:hover { filter: brightness(1.08); }
+.btn:disabled { opacity: .4; cursor: not-allowed; }
+
+.models-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 10px 0 14px; }
+.models-toolbar input[type="search"] {
+  flex: 1; min-width: 200px; padding: 8px 12px; border-radius: 8px;
+  border: 1px solid var(--border); background: var(--card-bg); color: inherit;
+}
+.models-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
+
+.cloud-block {
+  margin-top: 26px; border: 1px solid var(--border); border-radius: 12px;
+  padding: 4px 16px 14px; background: var(--card-bg);
+}
+.cloud-block summary { cursor: pointer; padding: 10px 0; font-weight: 600; font-size: 14px; }
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index a297084..5f20426 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -10,6 +10,11 @@
     recommendedId: null,
     selectedId: null,
     sphereId: 'S1',
+    step: 1,
+    localModels: null,
+    modelTier: 'tous',
+    modelSearch: '',
+    modelsChosen: {},
     bricks: null,
     overrides: {},
     search: ''
@@ -89,7 +94,28 @@
       s_none: 'aucun',
       f_node_target: 'Nœud cible',
       node_local: 'Local (cette machine)',
-      node_auto: 'Auto — scheduler du cluster'
+      node_auto: 'Auto — scheduler du cluster',
+      tagline: 'Installateur d\'infrastructure IA souveraine',
+      step_hardware: 'Matériel',
+      step_stack: 'Stack',
+      step_models: 'Modèles IA',
+      step_bricks: 'Briques',
+      step_nodes: 'Nœuds',
+      step_deploy: 'Déploiement',
+      hardware_lede: 'Votre machine est analysée automatiquement — le reste de l\'installation s\'adapte à ce qu\'elle peut faire tourner.',
+      models_step_title: 'Modèles IA',
+      models_step_lede: 'Tous les modèles open-weight — petits, moyens, gros — déployables sur n\'importe quel nœud du réseau. Aucun n\'est masqué : choisissez librement, chaque nœud cible affiche s\'il peut le servir.',
+      tier_all: 'Tous',
+      tier_small: 'Petits',
+      tier_medium: 'Moyens',
+      tier_large: 'Gros',
+      model_search_placeholder: 'Filtrer les modèles…',
+      aria_tier: 'Taille',
+      aria_filter_models: 'Filtrer',
+      aria_steps: 'Étapes d\'installation',
+      nav_prev: '← Précédent',
+      nav_next: 'Suivant →',
+      need_stack_first: 'Choisissez d\'abord un stack à l\'étape 2.'
     },
     en: {
       title: 'ForgeAI Toolkit',
@@ -164,7 +190,28 @@
       s_none: 'none',
       f_node_target: 'Target node',
       node_local: 'Local (this machine)',
-      node_auto: 'Auto — cluster scheduler'
+      node_auto: 'Auto — cluster scheduler',
+      tagline: 'Sovereign AI infrastructure installer',
+      step_hardware: 'Hardware',
+      step_stack: 'Stack',
+      step_models: 'AI Models',
+      step_bricks: 'Bricks',
+      step_nodes: 'Nodes',
+      step_deploy: 'Deployment',
+      hardware_lede: 'Your machine is analyzed automatically — the rest of the install adapts to what it can run.',
+      models_step_title: 'AI Models',
+      models_step_lede: 'All open-weight models — small, medium, large — deployable to any node on the network. None is hidden: choose freely, each target node shows whether it can serve it.',
+      tier_all: 'All',
+      tier_small: 'Small',
+      tier_medium: 'Medium',
+      tier_large: 'Large',
+      model_search_placeholder: 'Filter models…',
+      aria_tier: 'Size',
+      aria_filter_models: 'Filter',
+      aria_steps: 'Install steps',
+      nav_prev: '← Previous',
+      nav_next: 'Next →',
+      need_stack_first: 'Choose a stack first at step 2.'
     }
   };
 
@@ -322,8 +369,9 @@
       const full = await fetchJson(`/api/stacks/${encodeURIComponent(stackId)}`);
       state.stackDetail = full;
       renderDetail(summary, full);
-      showBricksSection();
-      showDeploySection();
+      state.bricks = null;
+      state.summary = null;
+      goToStep(state.step); // rafraîchit rail + verrous (stack désormais choisi)
     } catch (e) {
       const detail = document.getElementById('stack-detail');
       detail.classList.remove('hidden');
@@ -341,8 +389,7 @@
     const detail = document.getElementById('stack-detail');
     detail.classList.add('hidden');
     detail.innerHTML = '';
-    hideBricksSection();
-    hideDeploySection();
+    goToStep(2);
   }
 
   function renderDetail(summary, full) {
@@ -639,6 +686,7 @@
             stack: state.selectedId,
             backend: form.elements.backend.value,
             node: form.elements.node ? form.elements.node.value : 'local',
+            models: Object.keys(state.modelsChosen),
             confirm: confirm
           })
         });
@@ -653,6 +701,73 @@
     });
   }
 
+
+  /* ---------- Étape Modèles IA (P0.3) — 113 modèles vérifiés HF, zéro masquage ---------- */
+
+  async function loadLocalModels() {
+    if (state.localModels) { renderLocalModels(); return; }
+    const box = document.getElementById('local-models-list');
+    box.innerHTML = `<p>${escapeHtml(t('loading'))}</p>`;
+    try {
+      state.localModels = await fetchJson('/api/models/local');
+    } catch (e) {
+      box.innerHTML = `<p class="error">${escapeHtml(t('error_load'))}</p>`;
+      return;
+    }
+    renderLocalModels();
+  }
+
+  function renderLocalModels() {
+    const box = document.getElementById('local-models-list');
+    if (!state.localModels) return;
+    const q = state.modelSearch.trim().toLowerCase();
+    const visibles = state.localModels.modeles.filter((m) => {
+      if (state.modelTier !== 'tous' && m.tier !== state.modelTier) return false;
+      if (!q) return true;
+      return (m.hf_id + ' ' + m.name + ' ' + m.famille + ' ' + (m.notes_fr || '')).toLowerCase().includes(q);
+    });
+    const counts = document.getElementById('models-counts');
+    if (counts) counts.textContent = `${visibles.length}/${state.localModels.total}`;
+    box.innerHTML = visibles.map((m) => {
+      const chosen = !!state.modelsChosen[m.hf_id];
+      return `
+        <label class="brick-row${chosen ? ' installed' : ''}">
+          <input type="checkbox" data-model-id="${escapeHtml(m.hf_id)}" ${chosen ? 'checked' : ''}
+                 aria-label="${escapeHtml(m.name)}">
+          <span class="brick-main">
+            <span class="brick-head">
+              <span class="brick-name">${escapeHtml(m.name)}</span>
+              <span class="def-pill">${escapeHtml(m.tier)}</span>
+              <span class="def-pill">${escapeHtml(String(m.params_b))}B</span>
+              ${m.vram_q4_gb ? `<span class="brick-stars">Q4 ~${escapeHtml(String(m.vram_q4_gb))} GB</span>` : ''}
+              ${m.gguf ? '<span class="badge-default">GGUF</span>' : ''}
+            </span>
+            <span class="brick-desc">${escapeHtml(m.notes_fr || '')}</span>
+            <span class="brick-stars">${escapeHtml(m.famille)} · ${escapeHtml(m.license)} · ${escapeHtml(m.hf_id)}</span>
+          </span>
+        </label>`;
+    }).join('');
+    box.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
+      cb.addEventListener('change', () => {
+        if (cb.checked) state.modelsChosen[cb.dataset.modelId] = true;
+        else delete state.modelsChosen[cb.dataset.modelId];
+      });
+    });
+  }
+
+  function initModelStep() {
+    document.querySelectorAll('#tier-filter button[data-tier]').forEach((b) => {
+      b.addEventListener('click', () => {
+        state.modelTier = b.dataset.tier;
+        document.querySelectorAll('#tier-filter button[data-tier]').forEach((x) =>
+          x.setAttribute('aria-pressed', String(x === b)));
+        renderLocalModels();
+      });
+    });
+    const search = document.getElementById('model-search');
+    if (search) search.addEventListener('input', () => { state.modelSearch = search.value; renderLocalModels(); });
+  }
+
   /* ---------- Nœuds (B-02d) ---------- */
 
   async function loadNodes() {
@@ -769,6 +884,58 @@
     });
   }
 
+
+  /* ---------- Installateur par étapes (P0.3) ---------- */
+
+  const TOTAL_STEPS = 6;
+  const NEEDS_STACK = new Set([3, 4, 6]);
+
+  function stepAllowed(n) {
+    if (NEEDS_STACK.has(n) && !state.selectedId) return false;
+    return n >= 1 && n <= TOTAL_STEPS;
+  }
+
+  function goToStep(n) {
+    if (!stepAllowed(n)) {
+      const hint = document.getElementById('step-hint');
+      if (hint) { hint.textContent = t('need_stack_first'); hint.classList.add('error'); }
+      return;
+    }
+    state.step = n;
+    document.querySelectorAll('[data-step-panel]').forEach((p) => {
+      p.classList.toggle('hidden', Number(p.dataset.stepPanel) !== n);
+    });
+    document.querySelectorAll('.step-item').forEach((b) => {
+      const sn = Number(b.dataset.step);
+      b.classList.toggle('active', sn === n);
+      b.classList.toggle('done', sn < n);
+      b.classList.toggle('locked', !stepAllowed(sn));
+      b.setAttribute('aria-pressed', String(sn === n));
+    });
+    const hint = document.getElementById('step-hint');
+    if (hint) { hint.textContent = ''; hint.classList.remove('error'); }
+    const prev = document.getElementById('btn-prev');
+    const next = document.getElementById('btn-next');
+    if (prev) prev.disabled = n === 1;
+    if (next) next.disabled = n === TOTAL_STEPS;
+    window.scrollTo({ top: 0, behavior: 'instant' });
+    if (n === 3) loadLocalModels();
+    if (n === 4 && state.selectedId && !state.bricks) loadBricks();
+    if (n === 6 && state.selectedId && !state.summary) { loadSummary(); populateNodeChoices(); }
+    if (n === 5) loadNodes();
+  }
+
+  function initStepper() {
+    document.querySelectorAll('.step-item').forEach((b) => {
+      b.addEventListener('click', () => goToStep(Number(b.dataset.step)));
+    });
+    const prev = document.getElementById('btn-prev');
+    const next = document.getElementById('btn-next');
+    if (prev) prev.addEventListener('click', () => goToStep(state.step - 1));
+    if (next) next.addEventListener('click', () => goToStep(state.step + 1));
+    goToStep(1);
+  }
+
   function initControls() {
     document.querySelectorAll('#theme-toggle button[data-theme]').forEach((btn) => {
       btn.addEventListener('click', () => setTheme(btn.dataset.theme));
@@ -784,6 +951,7 @@
       });
     }
     initModelForm();
+    initModelStep();
     initNodeForm();
     initDeployForm();
     setTheme(state.theme);
@@ -792,6 +960,7 @@
 
   async function boot() {
     initControls();
+    initStepper();
     loadModels();
     loadNodes();
     try {
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index 4da2525..529722f 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -8,7 +8,13 @@
 </head>
 <body>
   <header class="app-header">
-    <h1 data-i18n="title">ForgeAI Toolkit</h1>
+    <div class="brand">
+      <span class="brand-mark" aria-hidden="true">⬢</span>
+      <div class="brand-text">
+        <h1 data-i18n="title">ForgeAI Toolkit</h1>
+        <p class="brand-tagline" data-i18n="tagline">Installateur d'infrastructure IA souveraine</p>
+      </div>
+    </div>
     <div class="controls">
       <div id="lang-toggle" class="toggle-group" role="group" aria-label="Langue" data-i18n-aria="aria_lang">
         <button class="btn toggle" data-lang="fr" aria-pressed="false">FR</button>
@@ -21,111 +27,151 @@
     </div>
   </header>
 
-  <main id="app">
-    <section id="hardware" class="card">
-      <h2 data-i18n="hardware_title">Matériel détecté</h2>
-      <div id="hardware-content"><p data-i18n="loading">Chargement…</p></div>
-    </section>
+  <div class="installer">
+    <nav id="step-rail" class="step-rail" aria-label="Étapes d'installation" data-i18n-aria="aria_steps">
+      <button class="step-item" data-step="1"><span class="step-num">1</span><span class="step-name" data-i18n="step_hardware">Matériel</span></button>
+      <button class="step-item" data-step="2"><span class="step-num">2</span><span class="step-name" data-i18n="step_stack">Stack</span></button>
+      <button class="step-item" data-step="3"><span class="step-num">3</span><span class="step-name" data-i18n="step_models">Modèles IA</span></button>
+      <button class="step-item" data-step="4"><span class="step-num">4</span><span class="step-name" data-i18n="step_bricks">Briques</span></button>
+      <button class="step-item" data-step="5"><span class="step-num">5</span><span class="step-name" data-i18n="step_nodes">Nœuds</span></button>
+      <button class="step-item" data-step="6"><span class="step-num">6</span><span class="step-name" data-i18n="step_deploy">Déploiement</span></button>
+    </nav>
 
-    <section id="stacks">
-      <h2 data-i18n="stacks_title">Profils de déploiement</h2>
-      <p data-i18n="stacks_subtitle">Choisissez le stack synergique à déployer.</p>
-      <div id="stacks-grid" class="stacks-grid"></div>
-      <div id="stack-detail" class="stack-detail hidden" aria-live="polite"></div>
-    </section>
+    <main id="app">
+      <!-- Étape 1 : Matériel -->
+      <section id="hardware" class="step-panel" data-step-panel="1">
+        <h2 data-i18n="hardware_title">Matériel détecté</h2>
+        <p class="step-lede" data-i18n="hardware_lede">Votre machine est analysée automatiquement — le reste de l'installation s'adapte à ce qu'elle peut faire tourner.</p>
+        <div id="hardware-content" class="card"><p data-i18n="loading">Chargement…</p></div>
+      </section>
 
-    <section id="bricks" class="hidden">
-      <h2 data-i18n="bricks_title">Briques additionnelles</h2>
-      <p data-i18n="bricks_subtitle">Catalogue complet, classé par sphère. Les briques du stack sont pré-cochées ; le châssis commun est verrouillé.</p>
-      <nav id="sphere-steps" class="sphere-steps" aria-label="Sous-étapes par sphère" data-i18n-aria="aria_spheres"></nav>
-      <div class="bricks-toolbar">
-        <input id="brick-search" type="search" placeholder="Filtrer les briques…" data-i18n-placeholder="search_placeholder" aria-label="Filtrer" data-i18n-aria="aria_filter">
-        <span id="bricks-counts" class="bricks-counts" aria-live="polite"></span>
-      </div>
-      <div id="bricks-list" class="bricks-list" aria-live="polite"></div>
-    </section>
+      <!-- Étape 2 : Stack -->
+      <section id="stacks" class="step-panel hidden" data-step-panel="2">
+        <h2 data-i18n="stacks_title">Profils de déploiement</h2>
+        <p class="step-lede" data-i18n="stacks_subtitle">Choisissez le stack synergique à déployer.</p>
+        <div id="stacks-grid" class="stacks-grid"></div>
+        <div id="stack-detail" class="stack-detail hidden" aria-live="polite"></div>
+      </section>
 
-    <section id="deploy" class="card hidden">
-      <h2 data-i18n="deploy_title">Résumé &amp; Déploiement</h2>
-      <p data-i18n="deploy_subtitle">Vérifiez le résumé, puis tapez FORCER pour lancer le déploiement réel — chaque étape est prouvée en direct.</p>
-      <div id="deploy-summary" class="models-list" aria-live="polite"></div>
-      <form id="deploy-form" class="model-form" autocomplete="off">
-        <div class="form-grid">
-          <label><span data-i18n="f_backend">Backend</span>
-            <select name="backend">
-              <option value="compose">Docker Compose</option>
-              <option value="k3s">K3s</option>
-            </select></label>
-          <label><span data-i18n="f_node_target">Nœud cible</span>
-            <select name="node" id="deploy-node-select">
-              <option value="local" data-i18n="node_local">Local (cette machine)</option>
-              <option value="auto" data-i18n="node_auto">Auto — scheduler du cluster</option>
-            </select></label>
-          <label><span data-i18n="f_confirm">Confirmation (tapez FORCER)</span>
-            <input name="confirm" required placeholder="FORCER" autocomplete="off" spellcheck="false"></label>
+      <!-- Étape 3 : Modèles IA (locaux à déployer + routes cloud optionnelles) -->
+      <section id="models-step" class="step-panel hidden" data-step-panel="3">
+        <h2 data-i18n="models_step_title">Modèles IA</h2>
+        <p class="step-lede" data-i18n="models_step_lede">Tous les modèles open-weight — petits, moyens, gros — déployables sur n'importe quel nœud du réseau. Aucun n'est masqué : choisissez librement, chaque nœud cible affiche s'il peut le servir.</p>
+        <div class="models-toolbar">
+          <div id="tier-filter" class="toggle-group" role="group" aria-label="Taille" data-i18n-aria="aria_tier">
+            <button class="btn toggle" data-tier="tous" aria-pressed="true" data-i18n="tier_all">Tous</button>
+            <button class="btn toggle" data-tier="petit" aria-pressed="false" data-i18n="tier_small">Petits</button>
+            <button class="btn toggle" data-tier="moyen" aria-pressed="false" data-i18n="tier_medium">Moyens</button>
+            <button class="btn toggle" data-tier="gros" aria-pressed="false" data-i18n="tier_large">Gros</button>
+          </div>
+          <input id="model-search" type="search" placeholder="Filtrer les modèles…" data-i18n-placeholder="model_search_placeholder" aria-label="Filtrer" data-i18n-aria="aria_filter_models">
+          <span id="models-counts" class="bricks-counts" aria-live="polite"></span>
         </div>
-        <div class="form-actions">
-          <button type="submit" class="btn" data-i18n="launch_deploy">Déployer le stack</button>
-          <span id="deploy-form-status" class="form-status" aria-live="polite"></span>
-        </div>
-      </form>
-      <pre id="deploy-log" class="deploy-log hidden" role="log" aria-live="polite"></pre>
-    </section>
+        <div id="local-models-list" class="models-grid" aria-live="polite"></div>
 
-    <section id="nodes" class="card">
-      <h2 data-i18n="nodes_title">Nœuds — cluster multi-machines</h2>
-      <p data-i18n="nodes_subtitle">Ajoutez un nœud avec son IP, utilisateur et mot de passe — utilisé une seule fois au bootstrap, puis bascule sur clé ed25519. Jamais écrit sur disque.</p>
-      <div id="nodes-list" class="models-list" aria-live="polite"></div>
-      <form id="node-form" class="model-form" autocomplete="off">
-        <div class="form-grid">
-          <label><span data-i18n="f_node_ip">Adresse IP</span>
-            <input name="ip" required placeholder="192.168.1.31" spellcheck="false"></label>
-          <label><span data-i18n="f_node_user">Utilisateur</span>
-            <input name="user" required placeholder="forge" spellcheck="false"></label>
-          <label><span data-i18n="f_node_password">Mot de passe (éphémère)</span>
-            <input name="password" type="password" required autocomplete="new-password"></label>
-        </div>
-        <p class="form-note" data-i18n="node_key_note">🔑 Le mot de passe sert une seule fois : installation de la clé publique, bascule immédiate sur ed25519, puis seule l'empreinte est journalisée au registre.</p>
-        <div class="form-actions">
-          <button type="submit" class="btn" data-i18n="add_node">Ajouter le nœud</button>
-          <span id="node-form-status" class="form-status" aria-live="polite"></span>
-        </div>
-      </form>
-    </section>
+        <details class="cloud-block">
+          <summary data-i18n="models_title">Modèles cloud &amp; clés API (optionnel)</summary>
+          <p class="form-note" data-i18n="models_subtitle">Routes modèle cloud — test de connexion réel obligatoire ; la clé est scellée au coffre, seule l'empreinte est conservée.</p>
+          <div id="models-list" class="models-list" aria-live="polite"></div>
+          <form id="model-form" class="model-form" autocomplete="off">
+            <div class="form-grid">
+              <label><span data-i18n="f_name">Nom de la route</span>
+                <input name="name" required placeholder="openrouter-glm"></label>
+              <label><span data-i18n="f_provenance">Provenance</span>
+                <select name="provenance">
+                  <option value="openrouter">OpenRouter</option>
+                  <option value="deepinfra">DeepInfra</option>
+                  <option value="nim">NVIDIA NIM</option>
+                  <option value="direct" data-i18n="prov_direct">Direct fournisseur</option>
+                  <option value="autre" data-i18n="prov_autre">Autre (URL)</option>
+                </select></label>
+              <label><span data-i18n="f_model_id">Identifiant du modèle</span>
+                <input name="model_id" required placeholder="z-ai/glm-4.6"></label>
+              <label id="base-url-field" class="hidden"><span data-i18n="f_base_url">Base URL (OpenAI-compatible)</span>
+                <input name="base_url" placeholder="api.exemple.com/v1"></label>
+              <label><span data-i18n="f_api_key">Clé API</span>
+                <input name="api_key" type="password" required autocomplete="new-password"></label>
+              <label><span data-i18n="f_passphrase">Passphrase du coffre</span>
+                <input name="passphrase" type="password" required autocomplete="new-password"></label>
+            </div>
+            <p class="form-note" data-i18n="key_note">La clé transite en mémoire vers le serveur local (127.0.0.1) puis est scellée au coffre chiffré — jamais écrite en clair, jamais réaffichée.</p>
+            <div class="form-actions">
+              <button type="submit" class="btn" data-i18n="add_route">Ajouter la route (test réel)</button>
+              <span id="model-form-status" class="form-status" aria-live="polite"></span>
+            </div>
+          </form>
+        </details>
+      </section>
 
-    <section id="models" class="card">
-      <h2 data-i18n="models_title">Modèles &amp; clés API</h2>
-      <p data-i18n="models_subtitle">Routes modèle cloud — test de connexion réel obligatoire ; la clé est scellée au coffre, seule l'empreinte est conservée.</p>
-      <div id="models-list" class="models-list" aria-live="polite"></div>
-      <form id="model-form" class="model-form" autocomplete="off">
-        <div class="form-grid">
-          <label><span data-i18n="f_name">Nom de la route</span>
-            <input name="name" required placeholder="openrouter-glm"></label>
-          <label><span data-i18n="f_provenance">Provenance</span>
-            <select name="provenance">
-              <option value="openrouter">OpenRouter</option>
-              <option value="deepinfra">DeepInfra</option>
-              <option value="nim">NVIDIA NIM</option>
-              <option value="direct" data-i18n="prov_direct">Direct fournisseur</option>
-              <option value="autre" data-i18n="prov_autre">Autre (URL)</option>
-            </select></label>
-          <label><span data-i18n="f_model_id">Identifiant du modèle</span>
-            <input name="model_id" required placeholder="z-ai/glm-4.6"></label>
-          <label id="base-url-field" class="hidden"><span data-i18n="f_base_url">Base URL (OpenAI-compatible)</span>
-            <input name="base_url" placeholder="api.exemple.com/v1"></label>
-          <label><span data-i18n="f_api_key">Clé API</span>
-            <input name="api_key" type="password" required autocomplete="new-password"></label>
-          <label><span data-i18n="f_passphrase">Passphrase du coffre</span>
-            <input name="passphrase" type="password" required autocomplete="new-password"></label>
+      <!-- Étape 4 : Briques -->
+      <section id="bricks" class="step-panel hidden" data-step-panel="4">
+        <h2 data-i18n="bricks_title">Briques additionnelles</h2>
+        <p class="step-lede" data-i18n="bricks_subtitle">Catalogue complet, classé par sphère. Les briques du stack sont pré-cochées ; le châssis commun est verrouillé.</p>
+        <nav id="sphere-steps" class="sphere-steps" aria-label="Sous-étapes par sphère" data-i18n-aria="aria_spheres"></nav>
+        <div class="bricks-toolbar">
+          <input id="brick-search" type="search" placeholder="Filtrer les briques…" data-i18n-placeholder="search_placeholder" aria-label="Filtrer" data-i18n-aria="aria_filter">
+          <span id="bricks-counts" class="bricks-counts" aria-live="polite"></span>
         </div>
-        <p class="form-note" data-i18n="key_note">La clé transite en mémoire vers le serveur local (127.0.0.1) puis est scellée au coffre chiffré — jamais écrite en clair, jamais réaffichée.</p>
-        <div class="form-actions">
-          <button type="submit" class="btn" data-i18n="add_route">Ajouter la route (test réel)</button>
-          <span id="model-form-status" class="form-status" aria-live="polite"></span>
-        </div>
-      </form>
-    </section>
-  </main>
+        <div id="bricks-list" class="bricks-list" aria-live="polite"></div>
+      </section>
+
+      <!-- Étape 5 : Nœuds -->
+      <section id="nodes" class="step-panel hidden" data-step-panel="5">
+        <h2 data-i18n="nodes_title">Nœuds — cluster multi-machines</h2>
+        <p class="step-lede" data-i18n="nodes_subtitle">Ajoutez un nœud avec son IP, utilisateur et mot de passe — utilisé une seule fois au bootstrap, puis bascule sur clé ed25519. Jamais écrit sur disque.</p>
+        <div id="nodes-list" class="models-list" aria-live="polite"></div>
+        <form id="node-form" class="model-form card" autocomplete="off">
+          <div class="form-grid">
+            <label><span data-i18n="f_node_ip">Adresse IP</span>
+              <input name="ip" required placeholder="192.168.1.31" spellcheck="false"></label>
+            <label><span data-i18n="f_node_user">Utilisateur</span>
+              <input name="user" required placeholder="forge" spellcheck="false"></label>
+            <label><span data-i18n="f_node_password">Mot de passe (éphémère)</span>
+              <input name="password" type="password" required autocomplete="new-password"></label>
+          </div>
+          <p class="form-note" data-i18n="node_key_note">🔑 Le mot de passe sert une seule fois : installation de la clé publique, bascule immédiate sur ed25519, puis seule l'empreinte est journalisée au registre.</p>
+          <div class="form-actions">
+            <button type="submit" class="btn" data-i18n="add_node">Ajouter le nœud</button>
+            <span id="node-form-status" class="form-status" aria-live="polite"></span>
+          </div>
+        </form>
+      </section>
+
+      <!-- Étape 6 : Déploiement -->
+      <section id="deploy" class="step-panel hidden" data-step-panel="6">
+        <h2 data-i18n="deploy_title">Résumé &amp; Déploiement</h2>
+        <p class="step-lede" data-i18n="deploy_subtitle">Vérifiez le résumé, puis tapez FORCER pour lancer le déploiement réel — chaque étape est prouvée en direct.</p>
+        <div id="deploy-summary" class="models-list" aria-live="polite"></div>
+        <form id="deploy-form" class="model-form card" autocomplete="off">
+          <div class="form-grid">
+            <label><span data-i18n="f_backend">Backend</span>
+              <select name="backend">
+                <option value="compose">Docker Compose</option>
+                <option value="k3s">K3s</option>
+              </select></label>
+            <label><span data-i18n="f_node_target">Nœud cible</span>
+              <select name="node" id="deploy-node-select">
+                <option value="local" data-i18n="node_local">Local (cette machine)</option>
+                <option value="auto" data-i18n="node_auto">Auto — scheduler du cluster</option>
+              </select></label>
+            <label><span data-i18n="f_confirm">Confirmation (tapez FORCER)</span>
+              <input name="confirm" required placeholder="FORCER" autocomplete="off" spellcheck="false"></label>
+          </div>
+          <div class="form-actions">
+            <button type="submit" class="btn btn-primary" data-i18n="launch_deploy">Déployer le stack</button>
+            <span id="deploy-form-status" class="form-status" aria-live="polite"></span>
+          </div>
+        </form>
+        <pre id="deploy-log" class="deploy-log hidden" role="log" aria-live="polite"></pre>
+      </section>
+
+      <div class="step-nav">
+        <button id="btn-prev" class="btn" data-i18n="nav_prev">← Précédent</button>
+        <span id="step-hint" class="form-status" aria-live="polite"></span>
+        <button id="btn-next" class="btn btn-primary" data-i18n="nav_next">Suivant →</button>
+      </div>
+    </main>
+  </div>
 
   <script src="app.js"></script>
 </body>
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 9fd9819..13fa9fd 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -146,6 +146,12 @@ def bricks_payload(sphere_id: str, stack_id: str | None) -> dict | None:
     }
 
 
+
+def _read_data_text(name: str) -> str:
+    from importlib import resources
+    return (resources.files("forgeai.data") / name).read_text(encoding="utf-8")
+
+
 def forgeai_home() -> Path:
     """Répertoire utilisateur ForgeAI (FORGEAI_HOME ou ~/.forgeai)."""
     return Path(os.environ.get("FORGEAI_HOME", Path.home() / ".forgeai"))
@@ -295,6 +301,13 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
             )
             return
 
+        if path == "/api/models/local":
+            # Registre des modeles open-weight verifies HF — expose TEL QUEL :
+            # aucun filtrage par materiel local (directive permanente), l'UI informe seulement.
+            data = json.loads(_read_data_text("modeles-locaux.json"))
+            self._send_json(200, data)
+            return
+
         if path == "/api/models":
             store = RouteStore(_models_home())
             self._send_json(200, [r.public_dict() for r in store.list()])
diff --git a/tests/test_web_i18n.py b/tests/test_web_i18n.py
index 4b05b5d..0299e7c 100644
--- a/tests/test_web_i18n.py
+++ b/tests/test_web_i18n.py
@@ -28,8 +28,8 @@ def _used_keys() -> set[str]:
 
 def _dict_keys() -> tuple[set[str], set[str]]:
     js = _js()
-    fr_block = js.split("fr: {")[1].split("\n    },")[0]
-    en_block = js.split("en: {")[1].split("\n    }\n  };")[0]
+    fr_block = js.split("\n    fr: {")[1].split("\n    },")[0]
+    en_block = js.split("\n    en: {")[1].split("\n    }\n  };")[0]
     fr = set(re.findall(r"^\s+([a-z_]+):", fr_block, re.M))
     en = set(re.findall(r"^\s+([a-z_]+):", en_block, re.M))
     return fr, en
diff --git a/tests/test_web_models_local.py b/tests/test_web_models_local.py
new file mode 100644
index 0000000..db24077
--- /dev/null
+++ b/tests/test_web_models_local.py
@@ -0,0 +1,52 @@
+"""P0.3 — registre des modèles locaux : 113 entrées vérifiées HF, servies SANS filtrage matériel.
+
+Directive permanente : la config locale ne restreint JAMAIS le choix — tout modèle est
+déployable vers n'importe quel nœud du réseau."""
+import json
+import threading
+import urllib.request
+
+import pytest
+
+from forgeai.web.server import build_server
+
+
+@pytest.fixture()
+def base_url():
+    srv = build_server("127.0.0.1", 0)
+    threading.Thread(target=srv.serve_forever, daemon=True).start()
+    yield f"http://127.0.0.1:{srv.server_address[1]}"
+    srv.shutdown()
+    srv.server_close()
+
+
+def _get(base, path):
+    with urllib.request.urlopen(base + path, timeout=10) as r:
+        return r.status, json.loads(r.read().decode("utf-8"))
+
+
+def test_registre_complet_et_integre(base_url):
+    status, d = _get(base_url, "/api/models/local")
+    assert status == 200
+    assert d["total"] == len(d["modeles"]) == 113
+    for m in d["modeles"]:
+        assert m["hf_id"] and m["source_url"].startswith("https://huggingface.co")
+        assert m["tier"] in ("petit", "moyen", "gros")
+        assert m["famille"] and m["verif"], m["hf_id"]
+
+
+def test_citations_utilisateur_presentes(base_url):
+    """GLM 5.2, Qwen 3.6 27B et Gemma 4 (cites par l'utilisateur) sont VERIFIES reels."""
+    _, d = _get(base_url, "/api/models/local")
+    ids = {m["hf_id"] for m in d["modeles"]}
+    assert "zai-org/GLM-5.2" in ids
+    assert "Qwen/Qwen3.6-27B" in ids
+    assert any(i.startswith("google/gemma-4") for i in ids)
+
+
+def test_aucun_filtrage_materiel(base_url):
+    """Les 3 tiers sont TOUS servis quel que soit le materiel local (gros inclus)."""
+    _, d = _get(base_url, "/api/models/local")
+    tiers = {m["tier"] for m in d["modeles"]}
+    assert tiers == {"petit", "moyen", "gros"}
+    assert sum(1 for m in d["modeles"] if m["tier"] == "gros") >= 20
```
