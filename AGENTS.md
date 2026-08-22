# AGENTS — ForgeAI Toolkit

> Hiérarchie d'autorité de ce dépôt (sources normatives, statuts, conflits connus) :
> [governance/AUTHORITY-MAP.md](governance/AUTHORITY-MAP.md).

## Mission
Construire le ForgeAI Toolkit selon le plan maître BMAD
([CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md](CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md)).
Claude Code Opus est mission lead, gestionnaire du DAG et intégrateur ; les membres de l'équipe sont routés via
`forge-model-bridge` (LiteLLM, 127.0.0.1:4000) — voir `manifests/roles.yaml` et
`manifests/routes.yaml`.

## Règles non négociables
1. **§8bis — zéro stub, zéro faux** : une story sort en DONE-avec-preuve ou BLOCKED-avec-raison.
   Interdits dans tout code mergé : corps vides, `NotImplementedError`, marqueurs de travail
   inachevé, tests sans assertion, données inventées présentées comme réelles.
   Gate : `python3 scripts/no_stub_scan.py --all` (bloquant, aucune exception).
2. **Preuve au registre** : chaque livrable ⇒ une entrée dans `evidence/registres/*.jsonl` via
   `scripts/registre.py append`. Un livrable sans preuve n'existe pas.
3. **Revue aveugle scellée (§3)** : verdicts déposés dans
   `evidence/reviews/<étape>/<modèle>.verdict.json`
   sans accès aux verdicts des autres. Jamais de verdict attendu, de compte d'approbations
   ni d'identité de reviewers dans un prompt de revue.
4. **Sorties de modèles = CLAIMS non vérifiées** : toute réponse du bridge est marquée
   `_claim_status=UNVERIFIED` — vérifier avant de relayer ou merger.
5. **T3 = Nathan** : paiements, secrets de production, suppressions définitives,
   engagements externes. Le consensus recommande; l'humain lève.

## Contrat autonome Luna/Sol actif (#603)

La source de vérité du contrat actif est
`governance/autonomy-policy.json`, complétée par le roster versionné de
`manifests/roles.yaml`. GPT-5.6 Luna conduit et écrit dans le rôle
`luna_writer`; GPT-5.6 Sol est le reviewer dans le rôle `sol`. Le plafond est
exactement `max_active_writer_lanes: 2` : il y a exactement deux writer lanes
autorisées, jamais davantage. L'identité historique `GPT-5.6-Luna-Pro` reste
résoluble pour les anciens reçus mais n'est pas le writer actif.

Le mode actif de revue est `sol_blind`. Sol doit être un reviewer frais,
aveugle et strictement read-only (`fresh_context`, `blind` et
`reviewer_read_only` vrais). Le reçu doit lier la revue au diff Git exact par
`candidate_diff_digest`, `base_commit`, `reviewed_head_commit`,
`reviewed_head_tree`, `sdd_diff_digest` et `prompt_sha256`, avec un `reviewed_at` horodaté avec
fuseau, `verdict: APPROVE` et `blocking_findings: []`. Il conserve aussi un
identifiant `story` immuable, distinct du `dossier` d'artefacts, afin que la
reconstruction du prompt soit byte-identique; le dossier doit correspondre au
répertoire réellement chargé, le provider ID Sol est exactement
`GPT-5.6-Sol`, et la fenêtre de fraîcheur est plafonnée à 24 heures. L'identité du codeur ne
peut pas être Sol. Un reçu est un claim : le gate le réfute contre l'état Git
courant; `.superpowers/sdd/**` est exclu de l'artefact Sol mais lié par
`sdd_diff_digest`; aucune preuve externe, runtime ou matérielle n'est implicite.

In `reviews_gate.py`, receipt-mode dispatch preserves `multi_vendor`'s historical 3/3 tally; active
`sol_blind` requires exactly one `GPT-5.6-Sol` verdict.

Le chemin de merge sûr reste repository-native : reprendre depuis l'issue/PR
et l'arbre Git courants, lire la politique, travailler dans les deux lanes,
tester, vérifier les registres, régénérer les vues, inspecter le diff, puis
laisser les hooks normaux valider le commit et les checks requis avant merge.
Les registres se prolongent uniquement avec
`python3 scripts/registre.py append ...`, jamais par édition de hash; l'oracle
est `python3 scripts/registre.py verify ...`. Les vues se régénèrent avec les
commandes documentées dans [Docs/reference/autonomy-luna-sol.md](Docs/reference/autonomy-luna-sol.md).

Aucun workflow de ce contrat ne peut recevoir `contents: write`, faire un
`force-push`, utiliser `decode` pour du code source embarqué ou être
`self-writing`. Les reviewers
restent en lecture seule. La source de vérité pour une reprise est la politique
versionnée, l'issue/PR GitHub, l'état Git et les registres vérifiés; un transcript
ou un état runtime précédent ne suffit pas. Les frontières T3 de Nathan restent
inchangées.

Les seuls états terminaux sont `DONE_WITH_EVIDENCE` et
`BLOCKED_WITH_REASON`. Une livraison sans preuve vérifiable doit rester
bloquée avec sa raison concrète; elle ne doit pas être transformée en preuve
inventée.

## Commandes
```bash
python3 scripts/registre.py append evidence/registres/mission.jsonl --type <type> --actor <actor> --payload-json '<json>'
python3 scripts/registre.py verify evidence/registres/mission.jsonl
python3 scripts/no_stub_scan.py --all
pytest
```

## Architecture (`src/forgeai/`)
- `hardware/`, `planner/`, `preflight` — détection matérielle → profil → plan Minimal.
- `catalogue/` + `src/forgeai/data/catalogue.json` — <!-- state:catalogue.entries_total -->1576<!-- /state --> briques R-ALL (vérifiées + bilingues), chargées
  par `importlib.resources` (portable après `pip install`, `dependencies=[]` stdlib pur).
- `deploy/`, `renderers/` — Compose + K3s ; `network/` — multi-nœuds (clés ed25519, bootstrap).
- `rag/` — client RAG e2e (preuve P1). `core/` — models, registre hash-chaîné, runner injectable.
- **`models/`** — cœur modèles/gateway (DM-5/DM-6) : `vault` (coffre chiffré stdlib), `probe`
  (test connexion réel, transport injectable), `routes` (routes cloud + cache par route, clés au
  coffre jamais en clair), `gateway` (invariant « aucune brique ne pointe un modèle »), `local`
  (download hash-vérifié + déploiement + test), `strategy` (Cerveau/Équipe/Hybride → slots).
- `cli.py` — `forgeai` : hardware, doctor, node, wizard, **model add-cloud/add-local/list/test**,
  **gateway set-url/wire/verify**, **strategy set/show**, **route configure**.

## Pipeline de développement — doctrine historique `multi_vendor`

Historical `multi_vendor` doctrine only: the legacy 3/3 review and merge statements below remain
unchanged. Ce bloc ne s'applique pas au mode actif `sol_blind`, qui est dispatché par le mode du
reçu et exige un verdict Sol unique.

1. Story BMAD (`stories/<ID>.md`, critères testables) + revue d'archi si la structure est touchée
   (`crew_dispatch.py --model crew-architect`).
2. **Codeur de la table par appel-direct** — `~/proof-method/scripts/crew_dispatch.py --model
   crew-coder-long|bulk --spec … --context …` (le subagent natif `codeur-*` échoue : passthrough
   non câblé). **Le crew génère, l'Orchestrateur applique + teste + itère. L'Orchestrateur ne
   code jamais les stories.** TDD strict : test ROUGE sur l'ancien code AVANT le correctif.
3. Gates : `pytest`, `no_stub_scan.py --all` (après `git add`).
4. **Revue aveugle scellée 3/3 (`multi_vendor`)** — `~/proof-method/scripts/civ_review.py --story
   evidence/reviews/<ID> --pack <pack>` (prompt byte-identique aux `CIV_MODELS`, 16k tokens,
   scelle `prompt_sha256`) → `scripts/revue.py tally evidence/reviews/<ID>` (dépouillement
   déterministe : 3 vendors distincts ≠ vendor du codeur, même sha, APPROVE-ssi-tous).
   **Artefact de revue = diff git**, jamais des snippets recollés. Pack via
   `pack_build.sh story diff out` (PROOF_COMPRESS=0).
5. Signature Orchestrateur par-dessus (`multi_vendor`, gates verts + revue APPROVE) → PR → merge
   (CODEOWNERS = Nathan).
6. Gate CI historique **`reviews-sealed`** (`scripts/reviews_gate.py` +
   `evidence/reviews/BINDING.txt`) : bloque tout merge `multi_vendor` où une revue liante n'est
   pas APPROVE 3/3.

Avant d'engager l'outillage `~/proof-method`, lancez
`python3 scripts/governance/capabilities.py` pour vérifier sa disponibilité et celle des variables
d'environnement nécessaires. Le script ne révèle jamais la valeur d'un secret (présence
uniquement) ; exportez les variables depuis votre propre gestion de secrets avant d'invoquer le
flux de revue externe.

## Périmètre
Confinement au repo (directive `CANON/directives-perimetre.md`) : aucune source produit hors du
dépôt ; le produit ne dépend d'aucun fichier de la machine (portabilité). L'outillage de
gouvernance (`~/proof-method`, `forge-model-bridge`/LiteLLM) est autorisé pour CONSTRUIRE le
toolkit, jamais embarqué dans le produit livré.

## Modèle de coordination (issue #481 — remplace ORCH-001)

Claude Code est l'orchestrateur en session et le seul mission lead ; actuellement, cette
responsabilité est exercée par Claude Code Opus. Il n'y a pas de cockpit multi-IDE actif.

L'invariant de traitement est : une issue = une branche = un worktree = un writer.

Le claim est visible par un commentaire sur l'issue GitHub concernée, posté au début du
traitement de chaque issue, selon le format exact :
« Claim — session Claude Code (writer unique #NNN) ».
Aucun fichier JSON de claims ne constitue le protocole de claim actif.

Le parallélisme de suivi est limité à un maximum de 4 issues simultanées, uniquement sur des
chemins de fichiers disjoints. Cette limite concerne le suivi de claims/branches, pas la capacité
d'écriture : elle est subordonnée à la politique active.
Issue tracking may cover at most four disjoint issues, but it is subordinate to the policy: never
more than two active writer lanes.

Les reviewers sont en lecture seule ; la revue aveugle scellée est définie à la règle 3.
Nathan conserve les décisions T3, conformément à la règle 5.

Le modèle multi-IDE ORCH-001, `archive/coordination/*.json` (RC1-010/#440, lot 1) et
`archive/cursor/rules/forgeai-orchestration.mdc` (lot 2) sont archivés/historiques et remplacés
par ce modèle ;
voir [governance/AUTHORITY-MAP.md](governance/AUTHORITY-MAP.md) pour les statuts, empreintes et
la succession.
