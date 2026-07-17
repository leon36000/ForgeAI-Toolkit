# ÉTAT-SYSTÈME — ForgeAI Toolkit (canon vivant)

État canonique des capacités **réellement livrées et prouvées** (revue aveugle scellée 3 vendors +
gates CI). Mis à jour : 2026-07-17. Vérifiable contre le code (`forgeai --help`, `src/forgeai/`).

## Surface CLI (`python3 -m forgeai …`)
Option globale : `--lang {fr,en}` (i18n, B-03).

| Commande | Sous-commandes | Rôle |
|---|---|---|
| `hardware` | — | détection matérielle (Étape 0) |
| `doctor` | — | préflight : backends disponibles sur la machine |
| `wizard --ci` | — | enchaînement bout-en-bout détection→déploiement→RAG→preuve registre |
| `catalogue` | `--defaults` | explore le catalogue (948 briques), brique ⭐ par catégorie (B-01) |
| `model` | add-cloud, add-local, list, test | routes modèle cloud/local, clé au coffre chiffré (B-08/B-09) |
| `gateway` | set-url, wire, verify | branchement brique→gateway unique (B-11) |
| `strategy` | set, show | stratégie Cerveau/Équipe/Hybride (B-10) |
| `route` | configure | cache par route au gateway (B-12) |
| `budget` | set, status | token economy : quota/alerte/coupure par agent (B-20) |
| `export` / `import` | — | bundle de setup portable hash-vérifié, sans secrets (B-16) |
| `ide` | list, configure, mcp, governance | branchement IDE→gateway + serveurs MCP + skills/hooks (B-17/B-18) |
| `loop` | run | boucle d'agent gouvernée : budget + complétion + journal (B-19) |
| `node` | status, add, tailscale, probe | multi-nœuds P2.5 (B-05/B-06/B-07) |

## Sous-systèmes (`src/forgeai/`)
- **hardware/** détection ; **planner/** (profile, assemble) ; **preflight** matrice backend.
- **catalogue/** loader + `data/catalogue.json` (948 briques, `catalogue.schema.json` B-26) + `data/locales/` (i18n).
- **models/** routes, gateway, strategy, budget, vault (scrypt+HMAC), probe, local.
- **deploy/** + **renderers/** (compose, k3s) ; **rag/** client.
- **network/** bootstrap (JoinPlan EX-1/2/3), keys (ed25519), node_add (secret éphémère B-05),
  tailscale (install épinglé + LAN-only B-06), remote_probe (sonde distante B-07), nodes.
- **ide/** (branchement + bootstrap MCP/gouvernance) ; **portability** (export/import) ; **loop** (Ralph).
- **core/** models, registre (JSONL hash-chaîné), runner.

## Gouvernance (auto-appliquée)
- **Gates CI** (`.github/workflows/gates.yml`) : `no-stub-scan`, `registres` (intégrité hash-chaîne),
  `catalogue` (désambiguïsation B-26), `tests` (couverture ≥85 %, registre ≥95 %), `gitleaks`,
  `reviews-sealed` (D9 : chaque dossier de `reviews/BINDING.txt` = APPROVE 3/3, vendors distincts).
- **Hooks locaux** (globaux) : pre-commit (no-stub + secrets + docs-drift), post-merge.
- **Sentinelle** : balayage continu multi-vendor hors session (findings au registre).
- **Registre** `Registres/mission.jsonl` : append-only, hash-chaîné, une entrée `revue_scellee`
  par story livrée (sceau `prompt_sha256` + 3 vendors).

## État des phases
- **P1** COUVERTE (machine nue → RAG prouvé e2e, S01–S10).
- **P2** livrée : B-01, B-03, B-08–B-12, B-16, B-17, B-18, B-19, B-20, B-26.
- **P2.5 multi-nœuds** livrée : B-05 (ajout nœud), B-06 (Tailscale), B-07 (sonde distante).
- **Reste** (backlog `manifests/backlog.yaml`) : B-02 (TUI), B-04 (drivers GPU P4), B-13/B-14
  (templates), B-15/B-21 (P5), B-22/B-23/B-24 (gouvernance/hooks substrat).

## Méthode
Pipeline par story (Étape 5) : branche depuis `main` → codeur crew (appel-direct LiteLLM) →
TDD/gates → **revue aveugle scellée 3 vendors** (`civ_review.py`, dépouillement déterministe
`revue.py tally`) → gate D9 → merge. Orchestrateur ne se relit jamais ; aucun LLM n'écrit un score.
