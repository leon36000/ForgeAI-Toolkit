# ÉTAT-SYSTÈME — ForgeAI Toolkit (canon vivant)

État canonique des capacités **réellement livrées et prouvées** (revue aveugle scellée 3 vendors + gates CI). Mis à jour : 2026-07-19. Vérifiable contre le code (`forgeai --help`, `src/forgeai/`).

## Surface CLI (`python3 -m forgeai …`)
Option globale : `--lang {fr,en}` (i18n, B-03, défaut: fr ou `$FORGEAI_LANG`).

| Commande | Sous-commandes / Arguments | Rôle |
|---|---|---|
| `hardware` | — | détection hardware (S01) |
| `doctor` | — | préflight : ce que votre machine peut faire |
| `gpu` | — | cycle de vie des drivers GPU NVIDIA/AMD/Intel (B-04) |
| `node` | status, add, tailscale, probe | multi-nœuds (P2 / P2.5 B-05/B-06/B-07) |
| `wizard` | — | wizard bout-en-bout |
| `model` | add-cloud, add-local, list, test | routes modèle cloud/local, clé au coffre chiffré (DM-5 / B-08/B-09) |
| `gateway` | set-url, wire, verify | branchement brique→gateway unique (DM-6 / B-11) |
| `strategy` | set, show | stratégie modèle Cerveau/Équipe/Hybride (DM-5b / B-10) |
| `route` | configure | configure les routes et cache au gateway (B-12) |
| `budget` | set, status | gestion des budgets agents : quota/alerte/coupure (B-20) |
| `export` | — | exporte le setup portable, sans secrets (B-16) |
| `import` | — | importe un bundle de setup (re-demande les secrets) (B-16) |
| `ide` | list, configure, mcp, governance | branche un IDE/CLI sur le gateway local + MCP + skills/hooks (B-17/B-18) |
| `catalogue` | `--defaults` | explore le catalogue de briques (1577 briques), brique ⭐ par catégorie (B-01) |
| `loop` | run | boucle d'agent gouvernée : budget+complétion+journal (B-19) |
| `template` | — | templates de déploiement — systèmes complets curés (B-13/B-14) |
| `web` | — | interface web locale (stdlib, hors-ligne) — B-02a..f |

## Sous-systèmes (`src/forgeai/`)
- **hardware/** détection ; **planner/** (profile, assemble) ; **preflight** matrice backend ; **gpu/** (drivers GPU B-04).
- **catalogue/** loader + `data/catalogue.json` (1577 briques, version 2026-07-13, couverture awesome-opensource-ai + awesome-openclaw) + `catalogue/spheres.py` (14 sphères S1..S14) + champ `default_eligible` (596 options exclues des défauts) + `data/locales/` (i18n).
- **stacks/** (`stacks.py` + `data/stacks/*.json`) : 6 profils de déploiement.
  - *agentique* : 72 déployées (superpowers + openclaw, hermes-agent imposé en S5, base_rag_durci)
  - *assistant-entreprise* : 102 déployées (hermes-agent en S5, base_rag_durci)
  - *automatisation* : 69 déployées (hermes-agent en S5, base_rag_durci)
  - *mlops* : 104 déployées (hermes-agent en S5, base_rag_durci)
  - *support-conversationnel* : 55 déployées (+VOIX, hermes-agent en S5, base_rag_durci)
  - *tout-en-un* : 188 déployées (union, hermes-agent en S5, base_rag_durci)
  - *châssis commun* : 24 briques communes calculées et verrouillées.
- **models/** routes, gateway, strategy, budget, vault (scrypt+HMAC), probe, local.
- **deploy/** + **renderers/** (compose, k3s) ; **rag/** client.
- **network/** bootstrap (JoinPlan EX-1/2/3), keys (ed25519), node_add (secret éphémère B-05), tailscale (install épinglé + LAN-only B-06), remote_probe (sonde distante B-07), nodes.
- **ide/** (branchement + bootstrap MCP/gouvernance) ; **portability** (export/import) ; **loop** (Ralph).
- **templates/** (B-13/B-14).
- **web/** (B-02a..f, ThreadingHTTPServer stdlib pure hors-ligne, i18n FR/EN in-place, a11y). Routes API réelles :
  - `/api/bricks`, `/api/deploy`, `/api/deploy/events` (SSE live), `/api/detect`, `/api/health`, `/api/models` (test connexion réel + vault), `/api/nodes`, `/api/nodes/status` (mdp éphémère -> ed25519), `/api/spheres`, `/api/stacks`, `/api/stacks/`, `/api/summary` (friction FORCER).
- **core/** models, registre (JSONL hash-chaîné), runner.

## Gouvernance (auto-appliquée)
- **Gates CI** (`.github/workflows/gates.yml`, `quality-gates-python`) : `no-stub-scan`, `registres` (intégrité hash-chaîne), `catalogue` (désambiguïsation B-26), `tests` (couverture ≥85 %, registre ≥95 %), `gitleaks`, `reviews-sealed` (D9 : chaque dossier de `reviews/BINDING.txt` = APPROVE 3/3, vendors distincts).
- **Hooks locaux** (globaux) : pre-commit (no-stub + secrets + docs-drift), post-merge.
- **Sentinelle** : balayage continu multi-vendor hors session (findings au registre).
- **Registre** `Registres/mission.jsonl` : append-only, hash-chaîné, une entrée `revue_scellee` par story livrée (sceau `prompt_sha256` + 3 vendors).
- **Revues scellées liantes (BINDING.txt)** :
  `B-09-civ` `B-12-civ` `BC-models-civ` `D9-gate-civ` `D4-sentinelle-civ` `B-01-civ` `B-20-civ` `polish-civ` `b03-civ` `b16-civ` `b26-civ` `b17-civ` `wh-civ` `b18-civ` `b19-civ` `b05-civ` `b06-civ` `b07-civ` `b13-civ` `b14-civ` `b04-civ` `b15-civ` `b21-civ` `IMPL-1-civ` `IMPL-2-civ` `IMPL-2b-civ` `IMPL-3-civ` `B-02a-civ` `B-02b-civ` `IMPL-4-civ` `B-02c-civ` `B-02d-civ` `B-02e-civ` `B-02f-civ`

## État des phases
- **P1** COUVERTE (machine nue → RAG prouvé e2e, S01–S10).
- **P2** livrée : B-01, B-03, B-08–B-12, B-16, B-17, B-18, B-19, B-20, B-26.
- **P2.5 multi-nœuds** livrée : B-05 (ajout nœud), B-06 (Tailscale), B-07 (sonde distante).
- **Extensions livrées** : B-02a..f (UI Web locale stdlib), B-04 (drivers GPU), B-13/B-14 (templates), B-15 (gate plugins), B-21 (réévaluation des défauts par catégorie).
- **Reste** (backlog `manifests/backlog.yaml`) : B-22/B-23/B-24 (gouvernance/hooks substrat).

## Méthode
Pipeline par story (Étape 5) : branche depuis `main` → codeur crew (appel-direct LiteLLM) → TDD/gates → **revue aveugle scellée 3 vendors** (`civ_review.py`, dépouillement déterministe `revue.py tally`) → gate D9 → merge. Orchestrateur ne se relit jamais ; aucun LLM n'écrit un score.
