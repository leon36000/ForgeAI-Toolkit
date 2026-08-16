# Story IMPL-2 — +33 briques [GAP] au catalogue (voix/secrets/lineage)

## Criteres d'acceptation
- 33 briques (17 R3 + 16 voix) sourcees gh-api (source_url github, verify_method gh-api, verified=true, flag PUBLIC-INSTALLABLE), 0 collision, 981 entrees, gate B-26 OK, sha256 regen+verifie, categorie reelle, classees en sphere.

## PREUVE D'EXECUTION LOCALE (sortie reelle : 12/12 tests, gates OK)
```
### pytest tests/test_gap_bricks.py tests/test_spheres.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /media/pc1/Storage/Repo/ForgeAI Toolkit
configfile: pyproject.toml
plugins: typeguard-4.4.3, langsmith-0.9.4, anyio-4.14.1, Faker-37.12.0, cov-7.1.0
collected 12 items

tests/test_gap_bricks.py .......                                         [ 58%]
tests/test_spheres.py .....                                              [100%]

============================== 12 passed in 0.06s ==============================

### no_stub_scan tests/test_gap_bricks.py
NO-STUB-SCAN : OK (1 fichiers scannés, zéro violation)

### scripts/catalogue_gate.py (B-26)
CATALOGUE-GATE : OK (981 entrées, zéro ambiguïté)

### verify_catalogue (sha256)
sha256 OK: 0a265f83eb0316d50fc641defa88348c4511209ef61c894400e680d4913e6cc4
```

## DIFF COMPLET (main...impl/catalogue-gap-bricks) — inclut les 33 entrees appendues a src/forgeai/data/catalogue.json
```diff
diff --git a/src/forgeai/data/catalogue.json b/src/forgeai/data/catalogue.json
index d48f180..6535291 100644
--- a/src/forgeai/data/catalogue.json
+++ b/src/forgeai/data/catalogue.json
@@ -17981,6 +17981,633 @@
    "verified": true,
    "verified_at": "2026-07-14",
    "verify_method": "gh-api repos/... (source objective)"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Évaluation, observabilité, guardrails et sécurité",
+   "default": null,
+   "description_en": "A tool for secrets management, encryption as a service, and privileged access management.",
+   "description_fr": "Outil de gestion de secrets, de chiffrement-as-a-service et de gestion des accès privilégiés.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "hashicorp-vault",
+   "license": "BUSL-1.1",
+   "maintenance": "active",
+   "name": "hashicorp/vault",
+   "popularity": "★35933 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/hashicorp/vault",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/hashicorp/vault"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Évaluation, observabilité, guardrails et sécurité",
+   "default": null,
+   "description_en": "Open-source platform for secrets, certificates, and privileged access management.",
+   "description_fr": "Plateforme open-source de gestion de secrets, de certificats et des accès privilégiés.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "infisical",
+   "license": "MIT Expat",
+   "maintenance": "active",
+   "name": "Infisical/infisical",
+   "popularity": "★28137 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/Infisical/infisical",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/Infisical/infisical"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Évaluation, observabilité, guardrails et sécurité",
+   "default": null,
+   "description_en": "Simple and flexible tool for managing secrets.",
+   "description_fr": "Outil simple et flexible de gestion de secrets (chiffrement de fichiers de configuration).",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "sops",
+   "license": "MPL-2.0",
+   "maintenance": "active",
+   "name": "getsops/sops",
+   "popularity": "★22526 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/getsops/sops",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/getsops/sops"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Infrastructure, Kubernetes, IaC et livraison",
+   "default": null,
+   "description_en": "Terraform enables you to safely and predictably create, change, and improve infrastructure; a source-available tool that codifies APIs into declarative, versionable configuration files.",
+   "description_fr": "Terraform permet de creer, modifier et ameliorer une infrastructure de facon sure et previsible ; outil source-available codifiant les API en fichiers de configuration declaratifs et versionnables.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "hashicorp-terraform",
+   "license": "BUSL-1.1",
+   "maintenance": "active",
+   "name": "hashicorp/terraform",
+   "popularity": "★49215 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/hashicorp/terraform",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/hashicorp/terraform"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Infrastructure, Kubernetes, IaC et livraison",
+   "default": null,
+   "description_en": "Infrastructure as Code in any programming language.",
+   "description_fr": "Infrastructure-as-Code dans n'importe quel langage de programmation.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "pulumi",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "pulumi/pulumi",
+   "popularity": "★25451 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/pulumi/pulumi",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/pulumi/pulumi"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Infrastructure, Kubernetes, IaC et livraison",
+   "default": null,
+   "description_en": "Open and extensible continuous delivery solution for Kubernetes, powered by the GitOps Toolkit.",
+   "description_fr": "Solution de livraison continue ouverte et extensible pour Kubernetes, propulsee par le GitOps Toolkit.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "flux2",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "fluxcd/flux2",
+   "popularity": "★8281 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/fluxcd/flux2",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/fluxcd/flux2"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Orchestration, agents et interfaces",
+   "default": null,
+   "description_en": "Light and fast self-hosted AI assistant with Web, iOS, macOS, Android, Linux and Windows clients.",
+   "description_fr": "Assistant IA auto-heberge leger et rapide, avec clients Web, iOS, macOS, Android, Linux et Windows.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "nextchat",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "ChatGPTNextWeb/NextChat",
+   "popularity": "★88493 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/ChatGPTNextWeb/NextChat",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/ChatGPTNextWeb/NextChat"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Orchestration, agents et interfaces",
+   "default": null,
+   "description_en": "LobeHub (formerly LobeChat): open-source platform that organizes AI agents into 24/7 operations - hiring, scheduling, and reporting on your AI team.",
+   "description_fr": "LobeHub (ex-LobeChat) : plateforme open-source qui orchestre des agents IA en operations continues (recrutement, planification, reporting de l'equipe IA).",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "lobe-chat",
+   "license": "LobeHub Community License",
+   "maintenance": "active",
+   "name": "lobehub/lobe-chat",
+   "popularity": "★80413 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/lobehub/lobe-chat",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/lobehub/lobe-chat"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Orchestration, agents et interfaces",
+   "default": null,
+   "description_en": "Enhanced self-hosted ChatGPT clone: agents, MCP, skills, multi-provider model switching (Anthropic, OpenAI, DeepSeek, Gemini, Mistral, OpenRouter), code interpreter and secure multi-user auth.",
+   "description_fr": "Clone ChatGPT auto-heberge enrichi : agents, MCP, skills, bascule multi-fournisseurs (Anthropic, OpenAI, DeepSeek, Gemini, Mistral, OpenRouter), interpreteur de code et authentification multi-utilisateurs securisee.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "librechat",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "danny-avila/LibreChat",
+   "popularity": "★40858 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/danny-avila/LibreChat",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/danny-avila/LibreChat"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "RAG, vecteurs, ingestion et mémoire agentique",
+   "default": null,
+   "description_en": "Lightweight OCR toolkit that turns any PDF or image document into structured data for LLMs; supports 100+ languages.",
+   "description_fr": "Boite a outils OCR legere transformant tout PDF ou image en donnees structurees pour LLM ; prend en charge plus de 100 langues.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "paddleocr",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "PaddlePaddle/PaddleOCR",
+   "popularity": "★85709 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/PaddlePaddle/PaddleOCR",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/PaddlePaddle/PaddleOCR"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "RAG, vecteurs, ingestion et mémoire agentique",
+   "default": null,
+   "description_en": "Complete API layer for private AI applications on local models: RAG, tools, MCP, text-to-SQL; works with any OpenAI-compatible inference server.",
+   "description_fr": "Couche d'API complete pour applications d'IA privees sur modeles locaux : RAG, outils, MCP, text-to-SQL ; compatible avec tout serveur d'inference OpenAI-compatible.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "private-gpt",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "zylon-ai/private-gpt",
+   "popularity": "★57339 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/zylon-ai/private-gpt",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/zylon-ai/private-gpt"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Évaluation, observabilité, guardrails et sécurité",
+   "default": null,
+   "description_en": "Open-source AI penetration-testing (autonomous red-teaming) tool to find and fix application vulnerabilities.",
+   "description_fr": "Outil open-source de test d'intrusion par IA (red-teaming autonome) pour detecter et corriger les vulnerabilites applicatives.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "strix",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "usestrix/strix",
+   "popularity": "★42191 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/usestrix/strix",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/usestrix/strix"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "Official inference framework for 1-bit LLMs.",
+   "description_fr": "Framework d'inference officiel pour LLM 1-bit.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "bitnet",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "microsoft/BitNet",
+   "popularity": "★39744 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/microsoft/BitNet",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/microsoft/BitNet"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Infrastructure, Kubernetes, IaC et livraison",
+   "default": null,
+   "description_en": "Machine Learning toolkit for Kubernetes.",
+   "description_fr": "Boite a outils de Machine Learning pour Kubernetes.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "kubeflow",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "kubeflow/kubeflow",
+   "popularity": "★15779 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/kubeflow/kubeflow",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/kubeflow/kubeflow"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Évaluation, observabilité, guardrails et sécurité",
+   "default": null,
+   "description_en": "Framework for evaluating LLMs and LLM systems, plus an open-source registry of benchmarks.",
+   "description_fr": "Framework d'evaluation des LLM et des systemes a base de LLM, avec un registre open-source de benchmarks.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "openai-evals",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "openai/evals",
+   "popularity": "★18938 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/openai/evals",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/openai/evals"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "RAG, vecteurs, ingestion et mémoire agentique",
+   "default": null,
+   "description_en": "Open-source context/metadata platform for the data and AI stack (data discovery, lineage and governance).",
+   "description_fr": "Plateforme open-source de metadonnees/contexte pour la stack data et IA (decouverte, lineage et gouvernance des donnees).",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "datahub",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "datahub-project/datahub",
+   "popularity": "★12285 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/datahub-project/datahub",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/datahub-project/datahub"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "RAG, vecteurs, ingestion et mémoire agentique",
+   "default": null,
+   "description_en": "An open standard for lineage metadata collection.",
+   "description_fr": "Un standard ouvert pour la collecte de metadonnees de lineage (tracabilite des donnees).",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "openlineage",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "OpenLineage/OpenLineage",
+   "popularity": "★2545 (gh-api 2026-07-17)",
+   "source_url": "https://github.com/OpenLineage/OpenLineage",
+   "verified": true,
+   "verified_at": "2026-07-17",
+   "verify_method": "gh-api repos/OpenLineage/OpenLineage"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "Faster Whisper transcription with CTranslate2.",
+   "description_fr": "Transcription Whisper accélérée avec CTranslate2.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "faster-whisper",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "SYSTRAN/faster-whisper",
+   "popularity": "★24351 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/SYSTRAN/faster-whisper",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/SYSTRAN/faster-whisper"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "WhisperX: automatic speech recognition with word-level timestamps and speaker diarization.",
+   "description_fr": "WhisperX : reconnaissance automatique de la parole avec horodatage au niveau du mot et diarisation des locuteurs.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "whisperx",
+   "license": "BSD-2-Clause",
+   "maintenance": "active",
+   "name": "m-bain/whisperX",
+   "popularity": "★23125 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/m-bain/whisperX",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/m-bain/whisperX"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "Silero VAD: pre-trained enterprise-grade Voice Activity Detector.",
+   "description_fr": "Silero VAD : détecteur d'activité vocale (VAD) pré-entraîné de qualité entreprise.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "silero-vad",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "snakers4/silero-vad",
+   "popularity": "★9609 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/snakers4/silero-vad",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/snakers4/silero-vad"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "Open-source, community-driven native audio turn-detection model for conversational voice AI.",
+   "description_fr": "Modèle open-source et communautaire de détection de tour de parole en audio natif pour l'IA vocale conversationnelle.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "smart-turn",
+   "license": "BSD-2-Clause",
+   "maintenance": "active",
+   "name": "pipecat-ai/smart-turn",
+   "popularity": "★1473 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/pipecat-ai/smart-turn",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/pipecat-ai/smart-turn"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "Inference library for the Kokoro-82M open-weight text-to-speech model (82M parameters, Apache-licensed weights).",
+   "description_fr": "Bibliothèque d'inférence pour le modèle de synthèse vocale open-weight Kokoro-82M (82 M de paramètres, poids sous licence Apache).",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "kokoro",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "hexgrad/kokoro",
+   "popularity": "★8024 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/hexgrad/kokoro",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/hexgrad/kokoro"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "Fast and local neural text-to-speech engine.",
+   "description_fr": "Moteur de synthèse vocale neuronale rapide et local.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "piper1-gpl",
+   "license": "GPL-3.0",
+   "maintenance": "active",
+   "name": "OHF-Voice/piper1-gpl",
+   "popularity": "★4819 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/OHF-Voice/piper1-gpl",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/OHF-Voice/piper1-gpl"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "A deep learning toolkit for Text-to-Speech, battle-tested in research and production.",
+   "description_fr": "Boîte à outils d'apprentissage profond pour la synthèse vocale, éprouvée en recherche et en production.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "coqui-ai-tts",
+   "license": "MPL-2.0",
+   "maintenance": "active",
+   "name": "idiap/coqui-ai-TTS",
+   "popularity": "★2292 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/idiap/coqui-ai-TTS",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/idiap/coqui-ai-TTS"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "State-of-the-art open-source text-to-speech (TTS).",
+   "description_fr": "Synthèse vocale (TTS) open-source à l'état de l'art.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "chatterbox",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "resemble-ai/chatterbox",
+   "popularity": "★25559 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/resemble-ai/chatterbox",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/resemble-ai/chatterbox"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "Very low latency speech-to-text, intent recognition, and text-to-speech for building voice agents and interfaces.",
+   "description_fr": "Reconnaissance vocale, reconnaissance d'intention et synthèse vocale à très faible latence pour construire des agents et interfaces vocaux.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "moonshine",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "usefulsensors/moonshine",
+   "popularity": "★8729 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/usefulsensors/moonshine",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/usefulsensors/moonshine"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "Open-source SenseVoiceSmall model for Mandarin, Cantonese, English, Japanese and Korean ASR, language identification, emotion recognition and audio event detection.",
+   "description_fr": "Modèle open-source SenseVoiceSmall pour l'ASR en mandarin, cantonais, anglais, japonais et coréen, l'identification de la langue, la reconnaissance des émotions et la détection d'événements audio.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "sensevoice",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "FunAudioLLM/SenseVoice",
+   "popularity": "★8880 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/FunAudioLLM/SenseVoice",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/FunAudioLLM/SenseVoice"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "End-to-end realtime stack for connecting humans and AI.",
+   "description_fr": "Stack temps réel de bout en bout pour connecter les humains et l'IA.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "livekit",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "livekit/livekit",
+   "popularity": "★19827 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/livekit/livekit",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/livekit/livekit"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Inférence, serving et gateway modèles",
+   "default": null,
+   "description_en": "OpenAI API-compatible server for streaming speech-to-text, translation and text-to-speech (STT via faster-whisper; TTS via Piper and Kokoro).",
+   "description_fr": "Serveur compatible avec l'API OpenAI pour la transcription en flux, la traduction et la synthèse vocale (STT via faster-whisper ; TTS via Piper et Kokoro).",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "speaches",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "speaches-ai/speaches",
+   "popularity": "★3520 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/speaches-ai/speaches",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/speaches-ai/speaches"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Orchestration, agents et interfaces",
+   "default": null,
+   "description_en": "Open source machine learning framework to automate text- and voice-based conversations: NLU, dialogue management and connectors (Slack, Facebook, etc.) to create chatbots and voice assistants.",
+   "description_fr": "Framework de machine learning open-source pour automatiser les conversations textuelles et vocales : NLU, gestion du dialogue et connecteurs (Slack, Facebook, etc.) pour créer des chatbots et des assistants vocaux.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "rasa",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "RasaHQ/rasa",
+   "popularity": "★21245 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/RasaHQ/rasa",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/RasaHQ/rasa"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Orchestration, agents et interfaces",
+   "default": null,
+   "description_en": "Build voice-based LLM agents. Modular and open source.",
+   "description_fr": "Construire des agents LLM vocaux. Modulaire et open-source.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "vocode-core",
+   "license": "MIT",
+   "maintenance": "active",
+   "name": "vocodedev/vocode-core",
+   "popularity": "★3776 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/vocodedev/vocode-core",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/vocodedev/vocode-core"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Orchestration, agents et interfaces",
+   "default": null,
+   "description_en": "Open-source live-chat, email support and omni-channel help desk; an alternative to Intercom, Zendesk and Salesforce Service Cloud.",
+   "description_fr": "Live-chat, support par e-mail et service client omnicanal open-source ; une alternative à Intercom, Zendesk et Salesforce Service Cloud.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "chatwoot",
+   "license": "MIT Expat",
+   "maintenance": "active",
+   "name": "chatwoot/chatwoot",
+   "popularity": "★34519 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/chatwoot/chatwoot",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/chatwoot/chatwoot"
+  },
+  {
+   "atlas_only": false,
+   "atlas_status": "",
+   "category": "Orchestration, agents et interfaces",
+   "default": null,
+   "description_en": "Build Conversational AI in minutes.",
+   "description_fr": "Construire de l'IA conversationnelle en quelques minutes.",
+   "en_pending": false,
+   "flag": "PUBLIC-INSTALLABLE",
+   "id": "chainlit",
+   "license": "Apache-2.0",
+   "maintenance": "active",
+   "name": "Chainlit/chainlit",
+   "popularity": "★12317 (gh-api 2026-07-18)",
+   "source_url": "https://github.com/Chainlit/chainlit",
+   "verified": true,
+   "verified_at": "2026-07-18",
+   "verify_method": "gh-api repos/Chainlit/chainlit"
   }
  ],
  "version": "2026-07-13"
diff --git a/src/forgeai/data/catalogue.sha256 b/src/forgeai/data/catalogue.sha256
index fe1e69a..47f9014 100644
--- a/src/forgeai/data/catalogue.sha256
+++ b/src/forgeai/data/catalogue.sha256
@@ -1 +1 @@
-a23e8398774506266cf24f8c84161a5318ec4b878609b1f98289918d04c7b724
+0a265f83eb0316d50fc641defa88348c4511209ef61c894400e680d4913e6cc4
diff --git a/tests/test_gap_bricks.py b/tests/test_gap_bricks.py
new file mode 100644
index 0000000..be8d0a9
--- /dev/null
+++ b/tests/test_gap_bricks.py
@@ -0,0 +1,73 @@
+"""IMPL-2 — preuve : les 33 briques [GAP] (voix/secrets/lineage) ajoutées au catalogue,
+sourcées gh-api, valides au schéma, et classées dans une des 14 sphères."""
+import json
+
+from forgeai.catalogue.loader import verify_catalogue
+from forgeai.catalogue.spheres import SPHERE_IDS, classify_sphere
+from forgeai.resources import catalogue_path
+
+GAP_IDS = [
+    # 17 R3 — secrets / IaC / surfaces / lineage
+    "hashicorp-vault", "infisical", "sops", "hashicorp-terraform", "pulumi", "flux2",
+    "nextchat", "lobe-chat", "librechat", "paddleocr", "private-gpt", "strix",
+    "bitnet", "kubeflow", "openai-evals", "datahub", "openlineage",
+    # 16 voix / conversationnel
+    "faster-whisper", "whisperx", "silero-vad", "smart-turn", "kokoro", "piper1-gpl",
+    "coqui-ai-tts", "chatterbox", "moonshine", "sensevoice", "livekit", "speaches",
+    "rasa", "vocode-core", "chatwoot", "chainlit",
+]
+
+
+def _entries():
+    d = json.loads(catalogue_path().read_text(encoding="utf-8"))
+    return d if isinstance(d, list) else d["entries"]
+
+
+def test_33_gap_bricks_presentes():
+    ids = {e["id"] for e in _entries()}
+    manquantes = [g for g in GAP_IDS if g not in ids]
+    assert manquantes == [], f"briques GAP manquantes : {manquantes}"
+
+
+def test_gap_bricks_schema_et_source_reelle():
+    by = {e["id"]: e for e in _entries()}
+    for g in GAP_IDS:
+        e = by[g]
+        assert e["verified"] is True, g
+        assert e["source_url"].startswith("https://github.com/"), g
+        assert e["license"], g
+        assert e["verify_method"].startswith("gh-api"), g
+        assert e["flag"] == "PUBLIC-INSTALLABLE", g
+        assert e["category"], g
+
+
+def test_gap_bricks_classent_en_sphere():
+    by = {e["id"]: e for e in _entries()}
+    for g in GAP_IDS:
+        assert classify_sphere(by[g]) in SPHERE_IDS, g
+
+
+def test_catalogue_integrite_sha256():
+    # lève si le catalogue a été altéré sans régénérer l'empreinte
+    verify_catalogue(catalogue_path())
+
+
+def test_catalogue_ids_uniques():
+    ids = [e["id"] for e in _entries()]
+    assert len(ids) == len(set(ids)), "id dupliqué dans le catalogue"
+
+
+def test_gap_categories_sont_reelles():
+    """Les 33 briques n'introduisent AUCUNE nouvelle catégorie : chacune réutilise
+    une catégorie déjà présente parmi les autres entrées du catalogue."""
+    ents = _entries()
+    gap = set(GAP_IDS)
+    cats_gap = {e["category"] for e in ents if e["id"] in gap}
+    cats_autres = {e["category"] for e in ents if e["id"] not in gap}
+    nouvelles = cats_gap - cats_autres
+    assert nouvelles == set(), f"catégories inexistantes introduites : {nouvelles}"
+
+
+def test_catalogue_compte_981():
+    """948 (base) + 33 (GAP) = 981 entrées après IMPL-2."""
+    assert len(_entries()) == 981
```
