# AGENTS — ForgeAI Toolkit

## Mission
Construire le ForgeAI Toolkit selon le plan maître BMAD
([CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md](CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md)).
Fable (session lead Claude Code) orchestre; les membres de l'équipe sont routés via
`forge-model-bridge` (LiteLLM, 127.0.0.1:4000) — voir `manifests/roles.yaml` et `manifests/routes.yaml`.

## Règles non négociables
1. **§8bis — zéro stub, zéro faux** : une story sort en DONE-avec-preuve ou BLOCKED-avec-raison.
   Interdits dans tout code mergé : corps vides, `NotImplementedError`, marqueurs de travail
   inachevé, tests sans assertion, données inventées présentées comme réelles.
   Gate : `python3 scripts/no_stub_scan.py --all` (bloquant, aucune exception).
2. **Preuve au registre** : chaque livrable ⇒ une entrée dans `Registres/*.jsonl` via
   `scripts/registre.py append`. Un livrable sans preuve n'existe pas.
3. **Revue aveugle scellée (§3)** : verdicts déposés dans `reviews/<étape>/<modèle>.verdict.json`
   sans accès aux verdicts des autres. Jamais de verdict attendu, de compte d'approbations
   ni d'identité de reviewers dans un prompt de revue.
4. **Sorties de modèles = CLAIMS non vérifiées** : toute réponse du bridge est marquée
   `_claim_status=UNVERIFIED` — vérifier avant de relayer ou merger.
5. **T3 = Nathan** : paiements, secrets de production, suppressions définitives,
   engagements externes. Le consensus recommande; l'humain lève.

## Commandes
```bash
python3 scripts/registre.py append Registres/mission.jsonl --type <type> --actor <actor> --payload-json '<json>'
python3 scripts/registre.py verify Registres/mission.jsonl
python3 scripts/no_stub_scan.py --all
pytest
```

## Architecture (`src/forgeai/`)
- `hardware/`, `planner/`, `preflight` — détection matérielle → profil → plan Minimal.
- `catalogue/` + `data/catalogue.json` — 1577 briques R-ALL (vérifiées + bilingues), chargées
  par `importlib.resources` (portable après `pip install`, `dependencies=[]` stdlib pur).
- `deploy/`, `renderers/` — Compose + K3s ; `network/` — multi-nœuds (clés ed25519, bootstrap).
- `rag/` — client RAG e2e (preuve P1). `core/` — models, registre hash-chaîné, runner injectable.
- **`models/`** — cœur modèles/gateway (DM-5/DM-6) : `vault` (coffre chiffré stdlib), `probe`
  (test connexion réel, transport injectable), `routes` (routes cloud + cache par route, clés au
  coffre jamais en clair), `gateway` (invariant « aucune brique ne pointe un modèle »), `local`
  (download hash-vérifié + déploiement + test), `strategy` (Cerveau/Équipe/Hybride → slots).
- `cli.py` — `forgeai` : hardware, doctor, node, wizard, **model add-cloud/add-local/list/test**,
  **gateway set-url/wire/verify**, **strategy set/show**, **route configure**.

## Pipeline de développement (Étape 5 — opérationnel, prouvé BC-models/B-12/D9)
1. Story BMAD (`stories/<ID>.md`, critères testables) + revue d'archi si la structure est touchée
   (`crew_dispatch.py --model crew-architect`).
2. **Codeur de la table par appel-direct** — `~/proof-method/scripts/crew_dispatch.py --model
   crew-coder-long|bulk --spec … --context …` (le subagent natif `codeur-*` échoue : passthrough
   non câblé). **Le crew génère, l'Orchestrateur applique + teste + itère. L'Orchestrateur ne
   code jamais les stories.** TDD strict : test ROUGE sur l'ancien code AVANT le correctif.
3. Gates : `pytest`, `no_stub_scan.py --all` (après `git add`).
4. **Revue aveugle scellée 3/3** — `~/proof-method/scripts/civ_review.py --story reviews/<ID>
   --pack <pack>` (prompt byte-identique aux `CIV_MODELS`, 16k tokens, scelle `prompt_sha256`) →
   `scripts/revue.py tally reviews/<ID>` (dépouillement déterministe : 3 vendors distincts ≠
   vendor du codeur, même sha, APPROVE-ssi-tous). **Artefact de revue = diff git**, jamais des
   snippets recollés. Pack via `pack_build.sh story diff out` (PROOF_COMPRESS=0).
5. Signature Orchestrateur par-dessus (gates verts + revue APPROVE) → PR → merge (CODEOWNERS = Nathan).
6. Gate CI **`reviews-sealed`** (`scripts/reviews_gate.py` + `reviews/BINDING.txt`) : bloque tout
   merge où une revue liante n'est pas APPROVE 3/3.

Env bridge/revue : base LiteLLM sur `http://localhost:4000` ; la clé d'API LiteLLM est lue
du conteneur `serveur-litellm` via `docker inspect` (jamais en clair au dépôt — voir CLAUDE.md).

## Périmètre
Confinement au repo (directive `CANON/directives-perimetre.md`) : aucune source produit hors du
dépôt ; le produit ne dépend d'aucun fichier de la machine (portabilité). L'outillage de
gouvernance (`~/proof-method`, `forge-model-bridge`/LiteLLM) est autorisé pour CONSTRUIRE le
toolkit, jamais embarqué dans le produit livré.

## Plan de contrôle multi-IDE (ORCH-001 — actif depuis M0)

Plusieurs IDE/agents corrigent ForgeAI en parallèle selon un contrat commun. Le cockpit est
**GitHub Copilot / VS Code**; il détient `ORCH-001` et gère les claims, labels, milestones et
issues. Les autres IDE sont Codex (sécurité/backend), Claude Code (K3s/RAG/hardware) et
Cursor (UI/accessibilité/docs).

### Source de vérité opérationnelle

```text
coordination/work-packages.json  — 64 packages, lanes, deps, périmètres
coordination/active-claims.json  — claims actifs (un par lane exclusive)
coordination/completed.json      — SHA de merge prouvés
```

### Invariants non négociables

1. Une issue = une branche = un worktree = un IDE = une PR.
2. Un claim actif détient un lease sur sa lane et ses chemins (`allowed_paths`).
3. Toute branche part du dernier `origin/main` **après** fusion de toutes les dépendances.
4. Pas de stacked PR implicite; merge queue uniquement.
5. Aucun agent ne modifie `build/**`, `dist/**` ou le catalogue maître sans issue explicite.

### Flux de claim

```text
ELIGIBLE → CLAIMED → WORKTREE_CREATED → BASELINE_VERIFIED → RED_TEST
→ IMPLEMENTATION → FOCUSED_TESTS → FULL_GATES → SECURITY_SCANS
→ REVIEW_PACK → 3 BLIND VERDICTS → FINAL TALLY → PR → MERGE_QUEUE → MERGED
→ COMPLETED (inscrire dans completed.json) → CLAIM_RELEASED
```

### Scripts de coordination

```bash
python3 scripts/coordination/validate_coordination.py   # valide claims + lanes + deps
python3 scripts/coordination/simulate_orchestration.py  # 10 simulations anti-collision
```

### Sécurité IDE

- ggshield AI hooks actifs pour les quatre IDE (`.gitguardian.yaml` présent).
- Aucun secret dans `coordination/**`, prompts, logs ou commits.
- `.cursor/rules/forgeai-orchestration.mdc` — règles path-scoped Cursor.
- `CLAUDE.md` — contrat Claude Code (adoption PROOF canonique).

### Concurrence maximale

| IDE | Claims max |
|---|---|
| COPILOT (cockpit) | 1 |
| VS_CODE | 1 |
| CURSOR | 1 |
| CODEX | 2 |
| CLAUDE_CODE | 2 |
| **Total** | **6** |
