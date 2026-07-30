# ÉTAT-SYSTÈME — ForgeAI Toolkit (canon vivant)

État canonique des capacités **réellement livrées et prouvées** (revue aveugle scellée >=3 vendors + gates CI). Mis à jour : 2026-07-19. Vérifiable contre le code (`forgeai --help`, `src/forgeai/`).

## Audit 2026-07-19 (48 constats) — ENTIÈREMENT SOLDÉ
- **P0 (Déploiement réel)** : Intégration complète du `wizard` avec les flags `--stack`, `--node`, `--probe-host`, `--dry-run`, `--selection`. Génération du plan dérivé `deploy-specs`, exécution e2e sans mock et ingestion idempotente validée.
- **P1 (Architecture & i18n)** : Fusion des templates vers les stacks avec alias hérités rétro-compatibles. Unification de l'i18n (`data/locales/`) pour la section web, servie par la route `/api/i18n`. Hiérarchie des défauts gravée par les gates : `default_by_sphere` (autorité de déploiement) / étoiles du catalogue (exploration seule) / overlay (repli Minimal). Intégration de la 15e sphère : `VOIX`.
- **P2 (Recommandations & Stars)** : Source unique de vérité via `forgeai_home/parse_stars`. Recommandation serveur exposée sur `/api/stacks/recommended`.

## Surface CLI (`python3 -m forgeai …`)
Option globale : `--lang {fr,en}` (i18n, défaut: fr ou `$FORGEAI_LANG`).

| Commande | Sous-commandes / Arguments | Rôle |
|---|---|---|
| `hardware` | — | détection hardware (S01) |
| `doctor` | — | préflight : ce que votre machine peut faire |
| `gpu` | — | cycle de vie des drivers GPU NVIDIA/AMD (qualifiés labo) + Intel (implémenté, qualification labo en attente — voir Docs/reference/gpu-drivers-support.md) |
| `node` | status, add, tailscale, probe | multi-nœuds |
| `wizard` | *flags ci-dessous* | wizard d'installation bout-en-bout |
| `model` | add-cloud, add-local, list, test | routes modèle cloud/local, clé au coffre chiffré |
| `gateway` | set-url, wire, verify | branchement brique→gateway unique |
| `strategy` | set, show | stratégie modèle Cerveau/Équipe/Hybride |
| `route` | configure | configure les routes et cache au gateway |
| `budget` | set, status | gestion des budgets agents : quota/alerte/coupure |
| `export` | — | exporte le setup portable, sans secrets |
| `import` | — | importe un bundle de setup (re-demande les secrets) |
| `ide` | list, configure, mcp, governance | branche un IDE/CLI sur le gateway local + MCP + skills/hooks |
| `catalogue` | `--defaults` | explore le catalogue de briques (1577 briques), brique ⭐ par catégorie |
| `loop` | run | boucle d'agent gouvernée : budget+complétion+journal |
| `template` | — | alias de déploiement hérités rétro-compatibles |
| `web` | — | interface web locale (stdlib, hors-ligne) |

### Wizard Flags
`--ci --backend --workdir --catalogue --overlay --stack --node --probe-host --selection --dry-run --registre --document --question --expected-fact --health-timeout --teardown --teardown-volumes --skip-preflight --help`

## Interface Utilisateur (Installateur Web)
L'installateur web est structuré en **6 étapes** :
1. **Matériel** : Détection et diagnostic de l'infrastructure locale.
2. **Stack** : Sélection du profil de déploiement (recommandations via `/api/stacks/recommended`).
3. **Modèles IA** : Registre universel de **113 modèles open-weight vérifiés HF** (répartis en 10 familles, aucun filtrage restrictif par matériel local).
4. **Briques** : Personnalisation des briques additionnelles par sphère.
5. **Nœuds** : Configuration multi-nœuds et sondes distantes.
6. **Déploiement** : Lancement réel, génération du plan et suivi des événements.

La sélection finale de l'utilisateur (briques + modèles + nœud) est transmise et tracée de manière déterministe dans `selection.json`.

## Sous-systèmes (`src/forgeai/`)
- **hardware/** détection ; **planner/** (profile, assemble, deploy-specs) ; **preflight** matrice backend ; **gpu/** (drivers GPU).
- **catalogue/** loader + `data/catalogue.json` (1577 briques) + `catalogue/spheres.py` (15 sphères S1..S14 + VOIX) + source unique `forgeai_home/parse_stars` + `data/locales/` (i18n unifiée, 94 clés web fr).
- **stacks/** (`stacks.py` + `data/stacks/*.json`) : 5 profils de déploiement + 1 profil global.
  - *agentique* : 72 briques déployées
  - *assistant-entreprise* : 102 briques déployées
  - *automatisation* : 69 briques déployées
  - *mlops* : 104 briques déployées
  - *support-conversationnel* : 55 briques déployées (incluant la sphère VOIX)
  - *tout-en-un* : 188 briques déployées (union des profils)
  - *châssis commun* : 24 briques communes calculées (intersection stricte des 5 stacks).
- **models/** routes, gateway, strategy, budget, vault, probe, local (113 modèles vérifiés HF, 10 familles).
- **deploy/** + **renderers/** (compose, k3s) ; **rag/** client.
- **network/** bootstrap, keys (ed25519), node_add, tailscale, remote_probe, nodes.
- **ide/** (branchement + bootstrap MCP/gouvernance) ; **portability** (export/import) ; **loop** (Ralph).
- **web/** ThreadingHTTPServer stdlib pure hors-ligne. Routes API réelles :
  - `/api/bricks`, `/api/deploy`, `/api/deploy/events` (SSE live), `/api/detect`, `/api/health`, `/api/i`, `/api/i18n`, `/api/models`, `/api/models/local`, `/api/nodes`, `/api/nodes/status`, `/api/spheres`, `/api/stacks`, `/api/stacks/`, `/api/stacks/recommended`, `/api/summary`.

## Gouvernance & CI
- **Gates CI** (`.github/workflows/gates.yml` uniquement) : `no-stub-scan`, `registres` (intégrité hash-chaîne), `catalogue` (désambiguïsation), `tests` (couverture ≥85 %, registre ≥95 %), `gitleaks`, `reviews-sealed`.
- **Règle du Repo (Gate D9)** : Tout dossier de `reviews/BINDING.txt` (54 dossiers scellés) doit obligatoirement être approuvé par **au moins 3 vendors distincts** (cette règle stricte prime sur le minimum T1=1 du canon global).
- **Registre** `Registres/mission.jsonl` : append-only, hash-chaîné, une entrée `revue_scellee` par story livrée (sceau `prompt_sha256` + 3 vendors).

## État des phases
- **P0** COUVERTE (déploiement réel, wizard complet, plan deploy-specs, e2e sans mock, ingestion idempotente).
- **P1** COUVERTE (fusion templates->stacks, alias hérités, i18n unifiée servie par `/api/i18n`, hiérarchie des défauts gravée, 15e sphère VOIX).
- **P2** COUVERTE (source unique `parse_stars`, recommandation serveur `/api/stacks/recommended`).
- **P2.5 multi-nœuds** COUVERTE (ajout nœud, Tailscale, sonde distante).
- **Extensions** COUVERTE (UI Web locale 6 étapes, drivers GPU NVIDIA/AMD (qualifiés labo) + Intel (implémenté, qualification labo en attente — voir Docs/reference/gpu-drivers-support.md), plugins, réévaluation des défauts).
