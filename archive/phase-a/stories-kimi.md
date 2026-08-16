<!-- Livrable Phase A — §1 plan maître
membre: kimi (Kimi-2.7 via forge-model-bridge, provider_id=kimi)
date: 2026-07-14 | statut: DONE | claim: UNVERIFIED (revue aveugle à venir au plan-freeze)
note Fable: produit en 2 lots (la route kimi tronque les sorties longues au-delà de ~70 lignes).
-->
# Stories BMAD — Phase P1

## P1-S01 — Bare-metal Hardware Discovery
- Valeur : Auto-découvrir les ressources bare-metal afin de déclencher le profil Minimal adapté.
- In/Out : CPU, RAM, disque, GPU éventuel, OS, réseau / benchmarks, métriques énergie, inventaire multi-nœuds.
- Critères : CA1 exécute un script de détection offline; CA2 produit un JSON normalisé; CA3 signale « unsupported » si RAM<8 Go ou CPU sans AVX2.
- Preuve e2e : `python -m forgeai.hw detect` → JSON avec `cpu`, `ram_gb`, `disk_gb`, `gpu`, `profile_candidate="Minimal"` ou `"Unsupported"`.
- Dépend : aucune | Taille : S | Codeur : fable

## P1-S02 — Minimal Single-node Profile Derivation
- Valeur : Mapper le hardware détecté vers un profil de déploiement single-node déterministe.
- In/Out : JSON S01 + contraintes catalogue / profils multi-nœuds, auto-scaling, profils GPU dédiés.
- Critères : CA1 choisit Minimal si ≤ seuils catalogue; CA2 génère `minimal.yaml` avec limites et labels; CA3 rejette les profils impossibles.
- Preuve e2e : `python -m forgeai.profile derive --hw hw.json` → `.forgeai/profiles/minimal.yaml` contient `nodes=1`, `rag.embedding.device=cpu` et `resources.max_ram_gb`.
- Dépend : P1-S01 | Taille : S | Codeur : fable

## P1-S03 — Catalogue Load & Hash-chain Validation
- Valeur : Charger les 1021 briques et garantir leur intégrité via le registre chaîné par hachage.
- In/Out : manifestes YAML/JSON des 1021 briques + chaîne de hachage / téléchargements/builds runtime, résolution registry distante.
- Critères : CA1 parse tous les manifestes; CA2 vérifie la chaîne de hachage et détecte toute altération; CA3 retourne le sous-ensemble compatible avec le profil Minimal.
- Preuve e2e : `python -m forgeai.catalog validate --catalog bricks/` → exit 0, affiche `last_block_hash` et `compatible_bricks=1021`.
- Dépend : aucune | Taille : M | Codeur : grok

## P1-S04 — Assemble Minimal RAG Stack
- Valeur : Produire un Docker Compose et des manifests K3s opérationnels pour un RAG sur un seul nœud.
- In/Out : profil Minimal (S02) + catalogue validé (S03) / HA multi-nœuds, GPU embeddings, migrations de base vectorielle.
- Critères : CA1 sélectionne modèle CPU, vector store, ingestion API, LLM backend depuis le catalogue; CA2 génère compose.yaml et k3s/ respectant RAM/disque; CA3 ajoute healthchecks et politiques de redémarrage.
- Preuve e2e : `docker compose -f generated/compose.yaml config` → services `embedder`, `vectorstore`, `rag-api`, `llm`; `kubectl apply --dry-run=client -f generated/k3s/` → success.
- Dépend : P1-S02 | P1-S03 | Taille : L | Codeur : composer

## P1-S05 — Secure Local Bootstrap
- Valeur : Initialiser clés, tokens et mots de passe locaux sans fuite dans les manifests.
- In/Out : stack générée S04 / TLS, KMS externe, secret managers cloud, CI/CD.
- Critères : CA1 génère secrets aléatoires écrits dans `.env` et `secrets/` en 0600; CA2 injecte via références compose/k3s; CA3 vérifie aucun secret en clair dans les manifests.
- Preuve e2e : `python -m forgeai.sec bootstrap --out generated` → crée `.env` et `secrets/jwt_key` mode 0o600; `grep -R 'dummy-secret' generated/compose.yaml generated/k3s/` → vide.
- Dépend : P1-S04 | Taille : S | Codeur : fable

## P1-S06 — Docker Compose single-node deployer
- Valeur : Porter la stack RAG minimal opérationnelle sur un nœud bare-metal en minutes.
- In/Out : `docker compose up`, healthchecks des services RAG / TLS, HA et multi-nœuds hors P1
- Critères : CA1 applique `compose.minimal.yml`; CA2 attend healthchecks `ollama`, `vector-store`, `rag-api`; CA3 retourne un rapport JSON healthy/erreur exploitable
- Preuve e2e : `python -m forgeai deploy compose --profile minimal --wait` → `{"status":"healthy","services":{"ollama":"healthy","vector-store":"healthy","rag-api":"healthy"}}`
- Dépend : P1-S04,P1-S05 | Taille : M | Codeur : composer

## P1-S07 — K3s single-node deployer
- Valeur : Exécuter le même RAG minimal sur Kubernetes embarqué local.
- In/Out : kubeconfig + manifests/apply, pods ready / ingress TLS, external LB, HA hors P1
- Critères : CA1 installe ou réutilise k3s single-node; CA2 applique manifests du namespace `minimal-rag`; CA3 `readinessProbe` OK sur tous les pods
- Preuve e2e : `python -m forgeai deploy k3s --profile minimal --wait` → `{"cluster":"k3s","namespace":"minimal-rag","pods":{"ollama":"ready","vector-store":"ready","rag-api":"ready"}}`
- Dépend : P1-S04,P1-S05 | Taille : M | Codeur : grok

## P1-S08 — RAG document ingestion
- Valeur : Introduire des connaissances documents et les rendre récupérables par le RAG.
- In/Out : ingest texte/Markdown/PDF simple en CLI/API / scrapers web, parseurs complexes hors P1
- Critères : CA1 accepte fichier ou stdin; CA2 découpe, embedde et indexe via le service local; CA3 stocke métadonnées source et retourne compteurs
- Preuve e2e : `python -m forgeai rag ingest --collection p1 tests/fixtures/faits_forgeai.txt` → `{"collection":"p1","file":"faits_forgeai.txt","chunks":4,"status":"ok"}`
- Dépend : P1-S06 | Taille : M | Codeur : kimi

## P1-S09 — E2E RAG answer proof
- Valeur : Démontrer que le RAG répond en citant un fait issu du document ingéré.
- In/Out : question → réponse avec citation / benchmark, jugement subjectif, fine-tuning hors P1
- Critères : CA1 pose une question en CLI; CA2 expose les chunks top-k utilisés; CA3 réponse contient un fait présent dans le doc et cite sa source
- Preuve e2e : `python -m forgeai rag ask "Quelle exigence Python est imposée au toolkit ?" --collection p1` → réponse contenant `Python ≥3.10`
- Dépend : P1-S03,P1-S08 | Taille : M | Codeur : kimi

## P1-S10 — Wizard TUI with CI mode
- Valeur : Enchaîner S01→S09 sans intervention et sceller la preuve dans un registre hash-chaîné.
- In/Out : mode `--ci` + preuve chainhash / mode interactif TUI graphique et UI web hors P1
- Critères : CA1 CLI `wizard --ci` enchaîne hardware→profil→catalogue→deploy→ingest→ask; CA2 s'arrête à la première erreur avec code non nul; CA3 écrit `~/.forgeai/registry/proof_<sha256>.json` liant S01…S09
- Preuve e2e : `python -m forgeai wizard --ci --profile minimal --witness ~/.forgeai/registry` → sortie se termine par `CI_WITNESS=<sha256>` et `RAG_OK=true`
- Dépend : P1-S01…P1-S09 | Taille : L | Codeur : fable

## Graphe de dépendances
Arêtes : S01→S02, S02→S03, S03→S04, S04→S05, S04→S06, S05→S06, S04→S07, S05→S07, S06→S08, S07→S08, S03→S09, S08→S09, S01→S10, S02→S10, S03→S10, S04→S10, S05→S10, S06→S10, S07→S10, S08→S10, S09→S10

Chemin critique : S01 → S02 → S04 → S05 → S06 → S08 → S09 → S10
