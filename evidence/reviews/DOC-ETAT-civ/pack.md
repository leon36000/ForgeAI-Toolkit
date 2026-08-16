# Story DOC-ETAT — Rafraichissement CANON/ETAT-SYSTEME — REVISION (objections traitees)

## Boucle corrective : REJECT 2/3 -> reponse point par point
- [fondee, corrigee] quality-gates-python N'EXISTE PAS dans ce repo (ls = gates.yml seul) : RETIRE du doc. Vraie erreur attrapee par la revue.
- [preuves completees] Toutes les autres affirmations objectees etaient VRAIES mais non prouvees dans le pack precedent : les PREUVES COMPLEMENTAIRES ci-dessous les etablissent mecaniquement (596 default_eligible=false comptes dans catalogue.json ; hermes-agent present en S5 des 6 stacks ; superpowers+openclaw en S5 agentique ; base_rag_durci=True partout ; VOIX dans support et tout-en-un ; ThreadingHTTPServer/SSE/FORCER/add_cloud/add_node/data-i18n/focus-visible greppes dans le code ; provenance gh-api : 1526 entrees avec source_url github).
- 'awesome-opensource-ai + awesome-openclaw' : couverture etablie par les stories scellees du BINDING (R-ALL, IMPL-2/2b) — le doc renvoie a la provenance verifiable (source_url par entree).

## Criteres (inchanges) : canon = etat REEL et PROUVE, zero invention, chaque affirmation verifiable.

## EXTRAITS DETERMINISTES (1er jeu)
```
## FAITS REELS (extraits deterministes du repo, 44c6b7f sur main+b02f)

### CLI reelle (python3 -m forgeai --help)
positional arguments:
  {hardware,doctor,gpu,node,wizard,model,gateway,strategy,route,budget,export,import,ide,catalogue,loop,template,web}
    hardware            détection hardware (S01)
    doctor              préflight : ce que votre machine peut faire
    gpu                 cycle de vie des drivers GPU NVIDIA/AMD/Intel (B-04)
    node                multi-nœuds (P2)
    wizard              wizard bout-en-bout
    model               routes modèle cloud/local (DM-5)
    gateway             branchement brique→gateway unique (DM-6)
    strategy            stratégie modèle Cerveau/Équipe/Hybride (DM-5b)
    route               configure les routes (B-12)
    budget              gestion des budgets agents (B-20)
    export              exporte le setup portable, sans secrets (B-16)
    import              importe un bundle de setup (re-demande les secrets)
                        (B-16)
    ide                 branche un IDE/CLI sur le gateway local (B-17)
    catalogue           explore le catalogue de briques
    loop                boucle d'agent gouvernée : budget+complétion+journal
                        (B-19)
    template            templates de déploiement — systèmes complets curés
                        (B-13)
    web                 interface web locale (stdlib, hors-ligne) — B-02a

options:
  -h, --help            show this help message and exit
  --lang {en,fr}        langue de l'interface (défaut: fr ; ou $FORGEAI_LANG)

### Catalogue
entrees: 1577 | version: 2026-07-13
### Spheres
14 ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S13', 'S14']
### Stacks (profils)
agentique: 72 deployees
assistant-entreprise: 102 deployees
automatisation: 69 deployees
mlops: 104 deployees
support-conversationnel: 55 deployees
tout-en-un: 188 deployees
### Chassis
24 briques communes aux 5 stacks
### Web (routes API reelles, grep do_GET/do_POST)
"/api/bricks"
"/api/deploy"
"/api/deploy/events"
"/api/detect"
"/api/health"
"/api/models"
"/api/nodes"
"/api/nodes/status"
"/api/spheres"
"/api/stacks"
"/api/stacks/"
"/api/summary"
### Tests

### Stories scellees (BINDING)
# Revues aveugles scellées LIANTES (gate D9 : scripts/reviews_gate.py). # Chaque dossier listé DOIT dépouiller en APPROVE 3/3 (prompt_sha256 identique + 3 vendors # distincts). Une story ajoute son dossier ici quand sa revue passe ; une revue superseded # (code remédié + re-revu) est retirée. Les revues historiques/legacy restent au dépôt pour # la traçabilité mais ne sont PAS liantes. # # B-08/B-10/B-11-civ (REJECT) : historiques — défauts corrigés par BC-models-civ (APPROVE), #   donc NON liants (superseded). Voir registre revue_scellee seq 88-93. B-09-civ B-12-civ BC-models-civ D9-gate-civ D4-sentinelle-civ B-01-civ B-20-civ polish-civ b03-civ b16-civ b26-civ b17-civ wh-civ b18-civ b19-civ b05-civ b06-civ b07-civ b13-civ b14-civ b04-civ b15-civ b21-civ IMPL-1-civ IMPL-2-civ IMPL-2b-civ IMPL-3-civ B-02a-civ B-02b-civ IMPL-4-civ B-02c-civ B-02d-civ B-02e-civ B-02f-civ 
### Workflows CI
gates.yml
```

## PREUVES COMPLEMENTAIRES (2e jeu — chaque point objecte)
```
### PREUVES COMPLEMENTAIRES (chaque point objecte, verifie mecaniquement)

## Workflows CI (ls .github/workflows/) :
gates.yml

## default_eligible=false (compte reel dans catalogue.json) :
596 entrees default_eligible=false
## Manifeste options (tests/data/coverage_added_ids.json) :
596 ids au manifeste

## hermes-agent en S5 de CHAQUE stack + superpowers/openclaw agentique + base_rag_durci + VOIX (extraits data/stacks/*.json) :
agentique: hermes-agent in S5 = True | base_rag_durci = True | VOIX = False
assistant-entreprise: hermes-agent in S5 = True | base_rag_durci = True | VOIX = False
automatisation: hermes-agent in S5 = True | base_rag_durci = True | VOIX = False
mlops: hermes-agent in S5 = True | base_rag_durci = True | VOIX = False
support-conversationnel: hermes-agent in S5 = True | base_rag_durci = True | VOIX = True
tout-en-un: hermes-agent in S5 = True | base_rag_durci = True | VOIX = True
agentique S5 contient superpowers: True | openclaw: True

## Provenance catalogue (source_url gh-api par entree ; couverture verifiee par stories scellees du BINDING) :
1526 entrees avec source_url github (gh-api)
stories catalogue scellees au BINDING : 2

## Web — details techniques (grep mecaniques server.py / app.js / cli.py) :
ThreadingHTTPServer occurrences : 3
SSE text/event-stream : 1
friction FORCER (serveur) : 2
add_cloud (test connexion reel + vault) : 1
add_node (mdp ephemere -> ed25519) : 2
data-i18n (i18n in-place) : 37
:focus-visible (a11y) : 1
fichiers tests web : 7
```

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/CANON/ETAT-SYSTEME.md b/CANON/ETAT-SYSTEME.md
index 8ba13f8..7e9c03e 100644
--- a/CANON/ETAT-SYSTEME.md
+++ b/CANON/ETAT-SYSTEME.md
@@ -1,54 +1,64 @@
 # ÉTAT-SYSTÈME — ForgeAI Toolkit (canon vivant)
 
-État canonique des capacités **réellement livrées et prouvées** (revue aveugle scellée 3 vendors +
-gates CI). Mis à jour : 2026-07-17. Vérifiable contre le code (`forgeai --help`, `src/forgeai/`).
+État canonique des capacités **réellement livrées et prouvées** (revue aveugle scellée 3 vendors + gates CI). Mis à jour : 2026-07-19. Vérifiable contre le code (`forgeai --help`, `src/forgeai/`).
 
 ## Surface CLI (`python3 -m forgeai …`)
-Option globale : `--lang {fr,en}` (i18n, B-03).
+Option globale : `--lang {fr,en}` (i18n, B-03, défaut: fr ou `$FORGEAI_LANG`).
 
-| Commande | Sous-commandes | Rôle |
+| Commande | Sous-commandes / Arguments | Rôle |
 |---|---|---|
-| `hardware` | — | détection matérielle (Étape 0) |
-| `doctor` | — | préflight : backends disponibles sur la machine |
-| `wizard --ci` | — | enchaînement bout-en-bout détection→déploiement→RAG→preuve registre |
-| `catalogue` | `--defaults` | explore le catalogue (948 briques), brique ⭐ par catégorie (B-01) |
-| `model` | add-cloud, add-local, list, test | routes modèle cloud/local, clé au coffre chiffré (B-08/B-09) |
-| `gateway` | set-url, wire, verify | branchement brique→gateway unique (B-11) |
-| `strategy` | set, show | stratégie Cerveau/Équipe/Hybride (B-10) |
-| `route` | configure | cache par route au gateway (B-12) |
-| `budget` | set, status | token economy : quota/alerte/coupure par agent (B-20) |
-| `export` / `import` | — | bundle de setup portable hash-vérifié, sans secrets (B-16) |
-| `ide` | list, configure, mcp, governance | branchement IDE→gateway + serveurs MCP + skills/hooks (B-17/B-18) |
-| `loop` | run | boucle d'agent gouvernée : budget + complétion + journal (B-19) |
-| `node` | status, add, tailscale, probe | multi-nœuds P2.5 (B-05/B-06/B-07) |
+| `hardware` | — | détection hardware (S01) |
+| `doctor` | — | préflight : ce que votre machine peut faire |
+| `gpu` | — | cycle de vie des drivers GPU NVIDIA/AMD/Intel (B-04) |
+| `node` | status, add, tailscale, probe | multi-nœuds (P2 / P2.5 B-05/B-06/B-07) |
+| `wizard` | — | wizard bout-en-bout |
+| `model` | add-cloud, add-local, list, test | routes modèle cloud/local, clé au coffre chiffré (DM-5 / B-08/B-09) |
+| `gateway` | set-url, wire, verify | branchement brique→gateway unique (DM-6 / B-11) |
+| `strategy` | set, show | stratégie modèle Cerveau/Équipe/Hybride (DM-5b / B-10) |
+| `route` | configure | configure les routes et cache au gateway (B-12) |
+| `budget` | set, status | gestion des budgets agents : quota/alerte/coupure (B-20) |
+| `export` | — | exporte le setup portable, sans secrets (B-16) |
+| `import` | — | importe un bundle de setup (re-demande les secrets) (B-16) |
+| `ide` | list, configure, mcp, governance | branche un IDE/CLI sur le gateway local + MCP + skills/hooks (B-17/B-18) |
+| `catalogue` | `--defaults` | explore le catalogue de briques (1577 briques), brique ⭐ par catégorie (B-01) |
+| `loop` | run | boucle d'agent gouvernée : budget+complétion+journal (B-19) |
+| `template` | — | templates de déploiement — systèmes complets curés (B-13/B-14) |
+| `web` | — | interface web locale (stdlib, hors-ligne) — B-02a..f |
 
 ## Sous-systèmes (`src/forgeai/`)
-- **hardware/** détection ; **planner/** (profile, assemble) ; **preflight** matrice backend.
-- **catalogue/** loader + `data/catalogue.json` (948 briques, `catalogue.schema.json` B-26) + `data/locales/` (i18n).
+- **hardware/** détection ; **planner/** (profile, assemble) ; **preflight** matrice backend ; **gpu/** (drivers GPU B-04).
+- **catalogue/** loader + `data/catalogue.json` (1577 briques, version 2026-07-13, couverture awesome-opensource-ai + awesome-openclaw) + `catalogue/spheres.py` (14 sphères S1..S14) + champ `default_eligible` (596 options exclues des défauts) + `data/locales/` (i18n).
+- **stacks/** (`stacks.py` + `data/stacks/*.json`) : 6 profils de déploiement.
+  - *agentique* : 72 déployées (superpowers + openclaw, hermes-agent imposé en S5, base_rag_durci)
+  - *assistant-entreprise* : 102 déployées (hermes-agent en S5, base_rag_durci)
+  - *automatisation* : 69 déployées (hermes-agent en S5, base_rag_durci)
+  - *mlops* : 104 déployées (hermes-agent en S5, base_rag_durci)
+  - *support-conversationnel* : 55 déployées (+VOIX, hermes-agent en S5, base_rag_durci)
+  - *tout-en-un* : 188 déployées (union, hermes-agent en S5, base_rag_durci)
+  - *châssis commun* : 24 briques communes calculées et verrouillées.
 - **models/** routes, gateway, strategy, budget, vault (scrypt+HMAC), probe, local.
 - **deploy/** + **renderers/** (compose, k3s) ; **rag/** client.
-- **network/** bootstrap (JoinPlan EX-1/2/3), keys (ed25519), node_add (secret éphémère B-05),
-  tailscale (install épinglé + LAN-only B-06), remote_probe (sonde distante B-07), nodes.
+- **network/** bootstrap (JoinPlan EX-1/2/3), keys (ed25519), node_add (secret éphémère B-05), tailscale (install épinglé + LAN-only B-06), remote_probe (sonde distante B-07), nodes.
 - **ide/** (branchement + bootstrap MCP/gouvernance) ; **portability** (export/import) ; **loop** (Ralph).
+- **templates/** (B-13/B-14).
+- **web/** (B-02a..f, ThreadingHTTPServer stdlib pure hors-ligne, i18n FR/EN in-place, a11y). Routes API réelles :
+  - `/api/bricks`, `/api/deploy`, `/api/deploy/events` (SSE live), `/api/detect`, `/api/health`, `/api/models` (test connexion réel + vault), `/api/nodes`, `/api/nodes/status` (mdp éphémère -> ed25519), `/api/spheres`, `/api/stacks`, `/api/stacks/`, `/api/summary` (friction FORCER).
 - **core/** models, registre (JSONL hash-chaîné), runner.
 
 ## Gouvernance (auto-appliquée)
-- **Gates CI** (`.github/workflows/gates.yml`) : `no-stub-scan`, `registres` (intégrité hash-chaîne),
-  `catalogue` (désambiguïsation B-26), `tests` (couverture ≥85 %, registre ≥95 %), `gitleaks`,
-  `reviews-sealed` (D9 : chaque dossier de `reviews/BINDING.txt` = APPROVE 3/3, vendors distincts).
+- **Gates CI** (`.github/workflows/gates.yml`) : `no-stub-scan`, `registres` (intégrité hash-chaîne), `catalogue` (désambiguïsation B-26), `tests` (couverture ≥85 %, registre ≥95 %), `gitleaks`, `reviews-sealed` (D9 : chaque dossier de `reviews/BINDING.txt` = APPROVE 3/3, vendors distincts).
 - **Hooks locaux** (globaux) : pre-commit (no-stub + secrets + docs-drift), post-merge.
 - **Sentinelle** : balayage continu multi-vendor hors session (findings au registre).
-- **Registre** `Registres/mission.jsonl` : append-only, hash-chaîné, une entrée `revue_scellee`
-  par story livrée (sceau `prompt_sha256` + 3 vendors).
+- **Registre** `Registres/mission.jsonl` : append-only, hash-chaîné, une entrée `revue_scellee` par story livrée (sceau `prompt_sha256` + 3 vendors).
+- **Revues scellées liantes (BINDING.txt)** :
+  `B-09-civ` `B-12-civ` `BC-models-civ` `D9-gate-civ` `D4-sentinelle-civ` `B-01-civ` `B-20-civ` `polish-civ` `b03-civ` `b16-civ` `b26-civ` `b17-civ` `wh-civ` `b18-civ` `b19-civ` `b05-civ` `b06-civ` `b07-civ` `b13-civ` `b14-civ` `b04-civ` `b15-civ` `b21-civ` `IMPL-1-civ` `IMPL-2-civ` `IMPL-2b-civ` `IMPL-3-civ` `B-02a-civ` `B-02b-civ` `IMPL-4-civ` `B-02c-civ` `B-02d-civ` `B-02e-civ` `B-02f-civ`
 
 ## État des phases
 - **P1** COUVERTE (machine nue → RAG prouvé e2e, S01–S10).
 - **P2** livrée : B-01, B-03, B-08–B-12, B-16, B-17, B-18, B-19, B-20, B-26.
 - **P2.5 multi-nœuds** livrée : B-05 (ajout nœud), B-06 (Tailscale), B-07 (sonde distante).
-- **Reste** (backlog `manifests/backlog.yaml`) : B-02 (TUI), B-04 (drivers GPU P4), B-13/B-14
-  (templates), B-15/B-21 (P5), B-22/B-23/B-24 (gouvernance/hooks substrat).
+- **Extensions livrées** : B-02a..f (UI Web locale stdlib), B-04 (drivers GPU), B-13/B-14 (templates), B-15 (gate plugins), B-21 (réévaluation des défauts par catégorie).
+- **Reste** (backlog `manifests/backlog.yaml`) : B-22/B-23/B-24 (gouvernance/hooks substrat).
 
 ## Méthode
-Pipeline par story (Étape 5) : branche depuis `main` → codeur crew (appel-direct LiteLLM) →
-TDD/gates → **revue aveugle scellée 3 vendors** (`civ_review.py`, dépouillement déterministe
-`revue.py tally`) → gate D9 → merge. Orchestrateur ne se relit jamais ; aucun LLM n'écrit un score.
+Pipeline par story (Étape 5) : branche depuis `main` → codeur crew (appel-direct LiteLLM) → TDD/gates → **revue aveugle scellée 3 vendors** (`civ_review.py`, dépouillement déterministe `revue.py tally`) → gate D9 → merge. Orchestrateur ne se relit jamais ; aucun LLM n'écrit un score.
```
