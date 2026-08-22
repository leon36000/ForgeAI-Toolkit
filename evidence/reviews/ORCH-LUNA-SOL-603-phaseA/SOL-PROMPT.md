Tu es reviewer de code Sol. Analyse uniquement l'ARTEFACT ci-dessous dans un contexte
frais et en lecture seule.
Ne consulte aucun autre verdict et ne suppose aucun résultat attendu.

STORY : stories/ORCH-LUNA-SOL-603.md
CRITÈRES D'ACCEPTATION :
- [x] La politique versionnée fixe GPT-5.6 Luna, exactement deux writer lanes,
  GPT-5.6 Sol, le mode frais/aveugle/read-only et les états terminaux.
- [x] Le dispatch de revue conserve le tally historique `multi_vendor` et
  exige un unique reviewer Sol pour `sol_blind`.
- [x] Le reçu Sol lie le diff Git, l’arbre, le prompt, les journaux exclus et
  les limites de fraîcheur sans dépendre de la configuration locale de Git.
- [ ] La documentation, les registres, les vues finales et la preuve Sol
  finale sont scellés dans la phase de livraison bornée.

ARTEFACT — canonical-git-diff :
diff --git AGENTS.md AGENTS.md
index 4aa281263fcf0687b6df1ae5a0dd949098d43dcc..85aff6c84736ee5f7aabbf270994f1eaec859136 100644
--- AGENTS.md
+++ AGENTS.md
@@ -26,6 +26,55 @@ Claude Code Opus est mission lead, gestionnaire du DAG et intégrateur ; les mem
 5. **T3 = Nathan** : paiements, secrets de production, suppressions définitives,
    engagements externes. Le consensus recommande; l'humain lève.
 
+## Contrat autonome Luna/Sol actif (#603)
+
+La source de vérité du contrat actif est
+`governance/autonomy-policy.json`, complétée par le roster versionné de
+`manifests/roles.yaml`. GPT-5.6 Luna conduit et écrit dans le rôle
+`luna_writer`; GPT-5.6 Sol est le reviewer dans le rôle `sol`. Le plafond est
+exactement `max_active_writer_lanes: 2` : il y a exactement deux writer lanes
+autorisées, jamais davantage. L'identité historique `GPT-5.6-Luna-Pro` reste
+résoluble pour les anciens reçus mais n'est pas le writer actif.
+
+Le mode actif de revue est `sol_blind`. Sol doit être un reviewer frais,
+aveugle et strictement read-only (`fresh_context`, `blind` et
+`reviewer_read_only` vrais). Le reçu doit lier la revue au diff Git exact par
+`candidate_diff_digest`, `base_commit`, `reviewed_head_commit`,
+`reviewed_head_tree`, `sdd_diff_digest`, `mission_diff_digest` et `prompt_sha256`, avec un `reviewed_at` horodaté avec
+fuseau, `verdict: APPROVE` et `blocking_findings: []`. Il conserve aussi un
+identifiant `story` immuable, distinct du `dossier` d'artefacts, afin que la
+reconstruction du prompt soit byte-identique; le dossier doit correspondre au
+répertoire réellement chargé, le provider ID Sol est exactement
+`GPT-5.6-Sol`, et la fenêtre de fraîcheur est plafonnée à 24 heures. L'identité du codeur ne
+peut pas être Sol. Un reçu est un claim : le gate le réfute contre l'état Git
+courant; `.superpowers/sdd/**` est exclu de l'artefact Sol mais lié par
+`sdd_diff_digest` et `mission_diff_digest`; aucune preuve externe, runtime ou matérielle n'est implicite.
+
+In `reviews_gate.py`, receipt-mode dispatch preserves `multi_vendor`'s historical 3/3 tally; active
+`sol_blind` requires exactly one `GPT-5.6-Sol` verdict.
+
+Le chemin de merge sûr reste repository-native : reprendre depuis l'issue/PR
+et l'arbre Git courants, lire la politique, travailler dans les deux lanes,
+tester, vérifier les registres, régénérer les vues, inspecter le diff, puis
+laisser les hooks normaux valider le commit et les checks requis avant merge.
+Les registres se prolongent uniquement avec
+`python3 scripts/registre.py append ...`, jamais par édition de hash; l'oracle
+est `python3 scripts/registre.py verify ...`. Les vues se régénèrent avec les
+commandes documentées dans [Docs/reference/autonomy-luna-sol.md](Docs/reference/autonomy-luna-sol.md).
+
+Aucun workflow de ce contrat ne peut recevoir `contents: write`, faire un
+`force-push`, utiliser `decode` pour du code source embarqué ou être
+`self-writing`. Les reviewers
+restent en lecture seule. La source de vérité pour une reprise est la politique
+versionnée, l'issue/PR GitHub, l'état Git et les registres vérifiés; un transcript
+ou un état runtime précédent ne suffit pas. Les frontières T3 de Nathan restent
+inchangées.
+
+Les seuls états terminaux sont `DONE_WITH_EVIDENCE` et
+`BLOCKED_WITH_REASON`. Une livraison sans preuve vérifiable doit rester
+bloquée avec sa raison concrète; elle ne doit pas être transformée en preuve
+inventée.
+
 ## Commandes
 ```bash
 python3 scripts/registre.py append evidence/registres/mission.jsonl --type <type> --actor <actor> --payload-json '<json>'
@@ -47,7 +96,12 @@ pytest
 - `cli.py` — `forgeai` : hardware, doctor, node, wizard, **model add-cloud/add-local/list/test**,
   **gateway set-url/wire/verify**, **strategy set/show**, **route configure**.
 
-## Pipeline de développement (Étape 5 — opérationnel, prouvé BC-models/B-12/D9)
+## Pipeline de développement — doctrine historique `multi_vendor`
+
+Historical `multi_vendor` doctrine only: the legacy 3/3 review and merge statements below remain
+unchanged. Ce bloc ne s'applique pas au mode actif `sol_blind`, qui est dispatché par le mode du
+reçu et exige un verdict Sol unique.
+
 1. Story BMAD (`stories/<ID>.md`, critères testables) + revue d'archi si la structure est touchée
    (`crew_dispatch.py --model crew-architect`).
 2. **Codeur de la table par appel-direct** — `~/proof-method/scripts/crew_dispatch.py --model
@@ -55,15 +109,17 @@ pytest
    non câblé). **Le crew génère, l'Orchestrateur applique + teste + itère. L'Orchestrateur ne
    code jamais les stories.** TDD strict : test ROUGE sur l'ancien code AVANT le correctif.
 3. Gates : `pytest`, `no_stub_scan.py --all` (après `git add`).
-4. **Revue aveugle scellée 3/3** — `~/proof-method/scripts/civ_review.py --story
+4. **Revue aveugle scellée 3/3 (`multi_vendor`)** — `~/proof-method/scripts/civ_review.py --story
    evidence/reviews/<ID> --pack <pack>` (prompt byte-identique aux `CIV_MODELS`, 16k tokens,
    scelle `prompt_sha256`) → `scripts/revue.py tally evidence/reviews/<ID>` (dépouillement
    déterministe : 3 vendors distincts ≠ vendor du codeur, même sha, APPROVE-ssi-tous).
    **Artefact de revue = diff git**, jamais des snippets recollés. Pack via
    `pack_build.sh story diff out` (PROOF_COMPRESS=0).
-5. Signature Orchestrateur par-dessus (gates verts + revue APPROVE) → PR → merge (CODEOWNERS = Nathan).
-6. Gate CI **`reviews-sealed`** (`scripts/reviews_gate.py` + `evidence/reviews/BINDING.txt`) :
-   bloque tout merge où une revue liante n'est pas APPROVE 3/3.
+5. Signature Orchestrateur par-dessus (`multi_vendor`, gates verts + revue APPROVE) → PR → merge
+   (CODEOWNERS = Nathan).
+6. Gate CI historique **`reviews-sealed`** (`scripts/reviews_gate.py` +
+   `evidence/reviews/BINDING.txt`) : bloque tout merge `multi_vendor` où une revue liante n'est
+   pas APPROVE 3/3.
 
 Avant d'engager l'outillage `~/proof-method`, lancez
 `python3 scripts/governance/capabilities.py` pour vérifier sa disponibilité et celle des variables
@@ -89,8 +145,11 @@ traitement de chaque issue, selon le format exact :
 « Claim — session Claude Code (writer unique #NNN) ».
 Aucun fichier JSON de claims ne constitue le protocole de claim actif.
 
-Le parallélisme est limité à un maximum de 4 issues simultanées, uniquement sur des chemins de
-fichiers disjoints.
+Le parallélisme de suivi est limité à un maximum de 4 issues simultanées, uniquement sur des
+chemins de fichiers disjoints. Cette limite concerne le suivi de claims/branches, pas la capacité
+d'écriture : elle est subordonnée à la politique active.
+Issue tracking may cover at most four disjoint issues, but it is subordinate to the policy: never
+more than two active writer lanes.
 
 Les reviewers sont en lecture seule ; la revue aveugle scellée est définie à la règle 3.
 Nathan conserve les décisions T3, conformément à la règle 5.
diff --git CANON/revue-template.md CANON/revue-template.md
index a002a5ae38444c8444ddfe8473fb39ea666c44b7..9f1e038024e49ee94c4a72b3eae4149c266916e5 100644
--- CANON/revue-template.md
+++ CANON/revue-template.md
@@ -1,14 +1,16 @@
 <!-- TEMPLATE DE PROMPT DE REVUE AVEUGLE — NEUTRE, STANDARDISÉ (invariant #5).
-Rempli par scripts/revue.py (jamais écrit à la main par l'orchestrateur). Les seuls
-champs variables sont {story_id}, {criteres}, {artefact_path}, {artefact}. Aucun autre
-texte ne doit être ajouté au prompt envoyé aux reviewers : le prompt_sha256 émis par le
-générateur DOIT être identique pour les 3 reviewers (vérifié au dépouillement). Toute
-formulation orientant le verdict (ex. « note : X est correct », « vérifie que Y ») est
-INTERDITE dans ce template — c'est exactement la faute D8. -->
+Rempli par scripts/revue.py (jamais écrit à la main par l'orchestrateur). Les sections
+de mode sont sélectionnées depuis ce fichier versionné. Les champs variables sont
+{story_id}, {criteres}, {artefact_path}, {artefact}, {metadata_json} et {response_schema}.
+Aucun autre texte ne doit être ajouté au prompt envoyé aux reviewers : le prompt_sha256
+émis par le générateur DOIT être identique pour les reviewers (vérifié au dépouillement).
+Toute formulation orientant le verdict (ex. « note : X est correct », « vérifie que Y »)
+est INTERDITE dans ce template — c'est exactement la faute D8. -->
+<!-- MODE:multi_vendor -->
 Tu es reviewer de code. Analyse l'ARTEFACT ci-dessous pour sa correction et sa sécurité.
 
 Sortie STRICTE — réponds UNIQUEMENT un objet JSON valide, rien avant, rien après :
-{"verdict":"APPROVE ou REJECT","objections":[{"severity":"critique|eleve|moyen|faible","file":"chemin","line":entier ou null,"desc":"défaut réel et vérifiable"}]}
+{response_schema}
 
 Règles :
 - N'indique aucune préférence de verdict. Ne suppose rien.
@@ -23,3 +25,25 @@ CRITÈRES D'ACCEPTATION :
 
 ARTEFACT — {artefact_path} :
 {artefact}
+<!-- END MODE:multi_vendor -->
+
+<!-- MODE:sol_blind -->
+Tu es reviewer de code Sol. Analyse uniquement l'ARTEFACT ci-dessous dans un contexte
+frais et en lecture seule.
+Ne consulte aucun autre verdict et ne suppose aucun résultat attendu.
+
+STORY : {story_id}
+CRITÈRES D'ACCEPTATION :
+{criteres}
+
+ARTEFACT — {artefact_path} :
+{artefact}
+
+MODE DE REVUE : sol_blind
+MÉTADONNÉES GIT EXACTES (à recopier sans modification) :
+{metadata_json}
+
+Réponds STRICTEMENT avec un objet JSON valide, rien avant, rien après, conforme à ce
+schéma :
+{response_schema}
+<!-- END MODE:sol_blind -->
diff --git CLAUDE.md CLAUDE.md
index e9895ef8edb084b1b03a12a49851c54bfa0b0223..36df1c6ec81b93dca7e2e68c59abfd27a61c9725 100644
--- CLAUDE.md
+++ CLAUDE.md
@@ -19,7 +19,12 @@ subagent-driven → TDD). Les overrides PROOF s'appliquent : le skill `proof-rev
 self-review inline de Superpowers (hook `PreToolUse Agent|Task` bloque le « Senior Code Reviewer »),
 et chaque subagent reçoit la discipline PROOF (hook `SubagentStart`). Complétion ⇒ skill `proof-done`.
 
-## Réconciliation (adoption pleine, décision Nathan)
+## Réconciliation historique — mode `multi_vendor` (adoption pleine, décision Nathan)
+
+Historical `multi_vendor` doctrine only: the legacy 3/3 review and merge statements below remain
+unchanged. Ce bloc conserve le comportement historique uniquement pour les reçus
+`multi_vendor`; le contrat actif `sol_blind` est distinct.
+
 
 - **Livreur de revue** : la pièce qui manquait est fournie par le canon —
   `~/proof-method/scripts/civ_review.py`. Il livre le prompt byte-identique aux N reviewers,
@@ -50,3 +55,40 @@ PROOF_COMPRESS=0 bash ~/proof-method/scripts/pack_build.sh stories/<ID>.md /tmp/
 python3 ~/proof-method/scripts/civ_review.py --story evidence/reviews/<ID> --pack /tmp/<ID>-pack.md
 python3 scripts/revue.py tally evidence/reviews/<ID>
 ```
+
+## Contrat actif Luna/Sol — issue #603
+
+La politique versionnée `governance/autonomy-policy.json` est la source de
+vérité. Le roster actif est `luna_writer` / `GPT-5.6-Luna-Writer` pour l'écriture
+(`GPT-5.6 Luna`) et `sol` / `GPT-5.6-Sol` pour la revue (`GPT-5.6 Sol`);
+`GPT-5.6-Luna-Pro` est historique et
+retiré. Le plafond est exactement `max_active_writer_lanes: 2`, donc exactement
+deux writer lanes. Le mode est `sol_blind`: contexte frais, blind, read-only,
+diff Git exact et identité Sol distincte du codeur.
+
+La liaison minimale du reçu exige `story` (distinct du `dossier` d'artefacts),
+`reviewer_model` exact `GPT-5.6-Sol`, `candidate_diff_digest`, `base_commit`,
+`reviewed_head_commit`, `reviewed_head_tree`, `sdd_diff_digest`, `mission_diff_digest`, `prompt_sha256`, un `reviewed_at`
+avec fuseau dans une fenêtre maximale de 24 heures, `verdict: APPROVE` et
+`blocking_findings: []`. Le `dossier` doit correspondre au répertoire de revue
+effectivement chargé.
+Le reviewer ne reçoit aucun verdict attendu. Le claim est revérifié par le
+gate contre Git courant; aucune preuve runtime ou externe n'est prétendue.
+Les journaux `.superpowers/sdd/**` sont exclus de l’artefact aveugle pour ne pas
+réinjecter d’anciens verdicts, mais restent liés par `sdd_diff_digest` et
+`mission_diff_digest`.
+
+In `reviews_gate.py`, receipt-mode dispatch preserves `multi_vendor`'s historical 3/3 tally; active
+`sol_blind` requires exactly one `GPT-5.6-Sol` verdict.
+
+Issue tracking may cover at most four disjoint issues, but it is subordinate to the policy: never
+more than two active writer lanes.
+
+Le merge sûr est repository-native : reprendre depuis l'issue/PR GitHub, l'état
+Git et les registres vérifiés, exécuter les tests/gates, prolonger les registres
+avec `scripts/registre.py append`, vérifier avec `scripts/registre.py verify`,
+régénérer les vues, inspecter le diff et passer les hooks normaux. Aucun workflow
+ne doit utiliser `contents: write`, `force-push`, `decode` de source embarquée
+ou un flux `self-writing`. Les seules sorties terminales sont
+`DONE_WITH_EVIDENCE` et `BLOCKED_WITH_REASON`; les frontières T3 de Nathan
+restent actives. Voir [la référence exécutable](Docs/reference/autonomy-luna-sol.md).
diff --git Docs/reference/autonomy-luna-sol.md Docs/reference/autonomy-luna-sol.md
new file mode 100644
index 0000000000000000000000000000000000000000..268c169951a81e904f312cf5928be9763ae48bb3
--- /dev/null
+++ Docs/reference/autonomy-luna-sol.md
@@ -0,0 +1,34 @@
+# Référence exécutable — autonomie Luna/Sol
+
+Cette phase versionne le noyau du contrat de l’issue #603. La source de vérité
+est `governance/autonomy-policy.json`; la décision associée est
+`governance/decisions/D-2026-08-21-autonomie-luna-sol.md`.
+
+Le writer actif est `luna_writer` / `GPT-5.6-Luna-Writer`, avec exactement deux
+writer lanes. Le reviewer actif est `sol` / `GPT-5.6-Sol`, en contexte frais,
+aveugle et strictement read-only. `multi_vendor` reste un mode historique
+d’archive et conserve son quorum 3/3.
+
+Le prompt Sol est reconstruit depuis le diff Git exact et les critères de la
+story `stories/ORCH-LUNA-SOL-603.md`. Le reçu lie les commits, arbres, digest
+du diff, prompt, template, journaux SDD et registre de mission; les digests
+neutralisent les configurations Git globales qui pourraient modifier ou
+ordonner la sortie. Le reviewer n’écrit jamais dans le dépôt.
+
+Les limites T3 restent humaines : paiements, secrets de production,
+suppressions définitives et engagements externes. Les états terminaux sont
+`DONE_WITH_EVIDENCE` et `BLOCKED_WITH_REASON`; cette phase ne prétend aucun
+résultat runtime, matériel ou externe.
+
+Vérifications de la phase :
+
+```bash
+python3 scripts/governance/validate_authority.py
+python3 scripts/governance/state_current.py
+python3 scripts/governance/classify_paths.py
+python3 scripts/reviews_gate.py --exiger-recu-courant --base-ref origin/main --issue <pr>
+python3 -m pytest -q
+```
+
+La preuve Sol et le dossier documentaire final sont ajoutés dans une phase
+bornée ultérieure, avec les fichiers qu’ils déclarent réellement.
diff --git governance/AUTHORITY-MAP.md governance/AUTHORITY-MAP.md
index 17fc08529070377f388f5d9326710d428e7687bf..762d00275ef62239a8ae040d240d4fbbfcaa9a39 100644
--- governance/AUTHORITY-MAP.md
+++ governance/AUTHORITY-MAP.md
@@ -47,7 +47,9 @@ Cette carte est le rendu de `governance/authority.json`.
 | `coord.active-claims` | `archive/coordination/active-claims.json` | superseded | `coordination_ops` | `copilot` | `gov.decision-mission-lead` |
 | `coord.work-packages` | `archive/coordination/work-packages.json` | superseded | `coordination_ops` | `copilot` | `gov.decision-mission-lead` |
 | `cursor.orchestration-rules` | `archive/cursor/rules/forgeai-orchestration.mdc` | superseded | `ide_contract` | `copilot` | `gov.decision-mission-lead` |
+| `gov.autonomy-policy` | `governance/autonomy-policy.json` | active | `orchestration` | `nathan` | `—` |
 | `gov.decision-arborescence-evidence-work-archive` | `governance/decisions/D-2026-08-15-arborescence-evidence-work-archive.md` | active | `governance_method` | `orchestrateur` | `—` |
+| `gov.decision-autonomie-luna-sol` | `governance/decisions/D-2026-08-21-autonomie-luna-sol.md` | active | `orchestration` | `nathan` | `—` |
 | `gov.decision-mission-lead` | `governance/decisions/D-2026-08-14-mission-lead.md` | conflicted | `orchestration` | `nathan` | `—` |
 | `gov.decision-racines-documentaires` | `governance/decisions/D-2026-08-15-racines-documentaires.md` | active | `governance_method` | `orchestrateur` | `—` |
 | `manifests.roles` | `manifests/roles.yaml` | active | `ide_contract` | `orchestrateur` | `—` |
@@ -63,11 +65,11 @@ Cette carte est le rendu de `governance/authority.json`.
 ## Positions déclarées
 
 - `agents-md` : `orchestration_seat` = `claude_code_opus_mission_lead` (AGENTS.md:9)
-- `agents-md` : `workspace_confinement` = `repo_plus_external_governance_tooling` (AGENTS.md:73-76)
+- `agents-md` : `workspace_confinement` = `repo_plus_external_governance_tooling` (AGENTS.md:130-133)
 - `canon.directives-perimetre` : `workspace_confinement` = `repo_only_strict` (CANON/directives-perimetre.md:7)
 - `canon.plan-integral` : `plan_of_record` = `canon_plan_integral` (CANON/plan-integral.md:4)
 - `canon.plan-integral` : `orchestration_seat` = `claude_code_opus_mission_lead` (CANON/plan-integral.md:27)
 - `canon.plan-maitre-bmad` : `plan_of_record` = `canon_plan_maitre_bmad_v1` (CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md:1-2)
-- `claude-md` : `workspace_confinement` = `repo_plus_external_governance_tooling` (CLAUDE.md:39)
+- `claude-md` : `workspace_confinement` = `repo_plus_external_governance_tooling` (CLAUDE.md:44-49)
 - `gov.decision-mission-lead` : `orchestration_seat` = `claude_code_opus_mission_lead` (governance/decisions/D-2026-08-14-mission-lead.md:9)
 - `master-plan` : `plan_of_record` = `master_plan_v1` (MASTER-PLAN.md:7)
diff --git governance/STATE-CURRENT.json governance/STATE-CURRENT.json
index 2dca22a9854adb7211478117035b07d7140ff5ba..10297a456ac4b6072a96d546df453ec2799cc358 100644
--- governance/STATE-CURRENT.json
+++ governance/STATE-CURRENT.json
@@ -680,7 +680,7 @@
       },
       {
         "path": "tests/test_rc1011_packs_md.py",
-        "sha256": "71363f9130dfca106e3ff1b8161303ba1c94525932dc527a763a9f930b908474"
+        "sha256": "0ccbe4116159aa1d3277bcf270e8000230bbce41f0688db5cf23c780d13387fc"
       },
       {
         "path": "tests/test_rc1016_sonar_suppressions.py",
@@ -768,11 +768,11 @@
       },
       {
         "path": "tests/test_reviews_gate.py",
-        "sha256": "28189c31d7b4d04b4b00b851fce69498f250555257ae021e20ff4d7c11dd7ffa"
+        "sha256": "eb237cd3cea284dacff1f975f67e049ae2bced9f5939ae4154eadd84811395cd"
       },
       {
         "path": "tests/test_revue.py",
-        "sha256": "d9209636686e2e4d2bde8004195aa5bc1b9a749b61eb5018eecb1c8471fdcaad"
+        "sha256": "f0fd58311fd5052a8c8480ccf81b8552549d8b32083384e561c30d376f1e0b83"
       },
       {
         "path": "tests/test_routestore_concurrence.py",
@@ -997,7 +997,7 @@
     "tests": {
       "js_files": 3,
       "python_files": 209,
-      "python_functions_declared": 2660
+      "python_functions_declared": 2675
     }
   },
   "observations": [
diff --git governance/STATE-CURRENT.md governance/STATE-CURRENT.md
index ab43a6ef635c58439b56f6ebb8541110060d5bf0..233fd2df3f69c9f4479101b412122c907638da6e 100644
--- governance/STATE-CURRENT.md
+++ governance/STATE-CURRENT.md
@@ -686,7 +686,7 @@
     },
     {
       "path": "tests/test_rc1011_packs_md.py",
-      "sha256": "71363f9130dfca106e3ff1b8161303ba1c94525932dc527a763a9f930b908474"
+      "sha256": "0ccbe4116159aa1d3277bcf270e8000230bbce41f0688db5cf23c780d13387fc"
     },
     {
       "path": "tests/test_rc1016_sonar_suppressions.py",
@@ -774,11 +774,11 @@
     },
     {
       "path": "tests/test_reviews_gate.py",
-      "sha256": "28189c31d7b4d04b4b00b851fce69498f250555257ae021e20ff4d7c11dd7ffa"
+      "sha256": "eb237cd3cea284dacff1f975f67e049ae2bced9f5939ae4154eadd84811395cd"
     },
     {
       "path": "tests/test_revue.py",
-      "sha256": "d9209636686e2e4d2bde8004195aa5bc1b9a749b61eb5018eecb1c8471fdcaad"
+      "sha256": "f0fd58311fd5052a8c8480ccf81b8552549d8b32083384e561c30d376f1e0b83"
     },
     {
       "path": "tests/test_routestore_concurrence.py",
@@ -1003,7 +1003,7 @@
   "tests": {
     "js_files": 3,
     "python_files": 209,
-    "python_functions_declared": 2660
+    "python_functions_declared": 2675
   }
 }
 ```
diff --git governance/authority.json governance/authority.json
index f48a36f9d73d0f08df833033989e45db578c6b15..fbc755f81bd96dc46642bf617be2a10e9653aaa0 100644
--- governance/authority.json
+++ governance/authority.json
@@ -105,13 +105,13 @@
         {
           "topic": "workspace_confinement",
           "position": "repo_plus_external_governance_tooling",
-          "locator": "AGENTS.md:73-76"
+          "locator": "AGENTS.md:130-133"
         }
       ],
       "digest": {
         "policy": "content_sha256",
-        "value": "490eebd6f8aa26b65eb80acfc4e0090bcf5c89b4609e35e1493a436df94454df",
-        "checked_at": "2026-08-16",
+        "value": "e1a396138be1435169bb6ad08267936b0d0d5639048e6ecbe07734fd6424ba9b",
+        "checked_at": "2026-08-22",
         "delegated_to": null
       },
       "retention": "in_force",
@@ -122,7 +122,7 @@
         "mission_seq": null,
         "ref": "issue-487"
       },
-      "notes": "Auto-contradiction interne resolue par #432 (Mission affirme desormais Claude Code Opus, section ORCH-001 remplacee) ; conflit RESIDUEL avec canon.plan-integral (toujours \"Fable orchestrateur unique\", hors perimetre de #432 -- CANON exige son propre circuit de revue) suivi par #487. Empreinte fusionnee (#433 x #437, merge sur main post-9d97b529) : #433 remplace les lignes 49-67 (pointe vers capabilities.py, decale le paragraphe Perimetre a +3 lignes) ; #437 insere un marqueur <!-- state:catalogue.entries_total --> autour du compteur manuel (AGENTS.md:38), sans decalage de lignes. Les deux changements sont sur des zones disjointes du fichier, fusionnes automatiquement par git (aucun conflit textuel) ; seule l'empreinte ci-dessus reflete desormais le contenu final combine. Locator workspace_confinement verifie a AGENTS.md:73-76 apres fusion."
+      "notes": "Auto-contradiction interne resolue par #432 (Mission affirme desormais Claude Code Opus, section ORCH-001 remplacee) ; conflit RESIDUEL avec canon.plan-integral (toujours \"Fable orchestrateur unique\", hors perimetre de #432 -- CANON exige son propre circuit de revue) suivi par #487. Empreinte fusionnee (#433 x #437, merge sur main post-9d97b529) : #433 remplace les lignes 49-67 (pointe vers capabilities.py, decale le paragraphe Perimetre a +3 lignes) ; #437 insere un marqueur <!-- state:catalogue.entries_total --> autour du compteur manuel (AGENTS.md:38), sans decalage de lignes. Les deux changements sont sur des zones disjointes du fichier, fusionnes automatiquement par git (aucun conflit textuel) ; seule l'empreinte ci-dessus reflete desormais le contenu final combine. Locator workspace_confinement pointe maintenant les lignes AGENTS.md:130-133, qui portent la doctrine active « Confinement au repo » et l'outillage de gouvernance autorise."
     },
     {
       "id": "agents-md.orch-001",
@@ -171,13 +171,13 @@
         {
           "topic": "workspace_confinement",
           "position": "repo_plus_external_governance_tooling",
-          "locator": "CLAUDE.md:39"
+          "locator": "CLAUDE.md:44-49"
         }
       ],
       "digest": {
         "policy": "content_sha256",
-        "value": "a5dc93ed5492c490ffc2e70d3c039d6374dd773fbd9126f8ef4670d2b1cd88ef",
-        "checked_at": "2026-08-16",
+        "value": "64b542e7d0ca60e6bd8c47f58018077447f33c16c5772bc614c6654b3530a511",
+        "checked_at": "2026-08-22",
         "delegated_to": null
       },
       "retention": "in_force",
@@ -188,7 +188,7 @@
         "mission_seq": null,
         "ref": "issue-484"
       },
-      "notes": "Le contrat autorise l'outillage de gouvernance externe pendant la construction. Empreinte/locator recalcules par #433 (reecriture complete : distingue capacites toujours disponibles vs outillage externe optionnel, supprime la commande d'extraction de secret docker inspect) -- la position et le statut CONFLICTED envers #484 restent inchanges, #433 ne tranche pas ce conflit."
+      "notes": "Le contrat autorise l'outillage de gouvernance externe pendant la construction. Empreinte/locator recalcules par #433 (reecriture complete : distingue capacites toujours disponibles vs outillage externe optionnel, supprime la commande d'extraction de secret docker inspect) -- la position et le statut CONFLICTED envers #484 restent inchanges, #433 ne tranche pas ce conflit. Locator workspace_confinement verifie maintenant a CLAUDE.md:44-49, qui porte le flux externe optionnel de construction."
     },
     {
       "id": "canon.directives-perimetre",
@@ -598,8 +598,8 @@
       "positions": [],
       "digest": {
         "policy": "content_sha256",
-        "value": "c5c68bd435e9e1da64d52747ffbf044763381e4770099e0c171c02c4d5cfdf00",
-        "checked_at": "2026-08-14",
+        "value": "ce7b4c9abaa253d543bd24c0d08d192847a924cda3e7778ac2cd2963ebcee34f",
+        "checked_at": "2026-08-22",
         "delegated_to": null
       },
       "retention": "in_force",
@@ -799,6 +799,66 @@
       "notes": "ADR inventorié sous le répertoire canonique des décisions."
     },
     {
+      "id": "gov.decision-autonomie-luna-sol",
+      "title": "Décision — contrat d’autonomie Luna/Sol",
+      "path": "governance/decisions/D-2026-08-21-autonomie-luna-sol.md",
+      "anchor": null,
+      "kind": "decision",
+      "scope": "orchestration",
+      "version": "2026-08-21",
+      "version_source": "declared_in_file",
+      "status": "active",
+      "owner": "nathan",
+      "superseded_by": null,
+      "prevails_over": [],
+      "positions": [],
+      "digest": {
+        "policy": "content_sha256",
+        "value": "746d57bf201121f5c9cbd716a5f508a6078eebecb967ab4c4cbcfd71c1023b2b",
+        "checked_at": "2026-08-22",
+        "delegated_to": null
+      },
+      "retention": "in_force",
+      "cleanup_issue": null,
+      "resolution_issue": 603,
+      "decision": {
+        "vision_log_seq": null,
+        "mission_seq": null,
+        "ref": "governance/decisions/D-2026-08-21-autonomie-luna-sol.md"
+      },
+      "notes": "Issue #603 : contrat versionné, plafond de deux writers, revue sol_blind et conservation des identités historiques."
+    },
+    {
+      "id": "gov.autonomy-policy",
+      "title": "Politique versionnée du contrat autonome Luna/Sol",
+      "path": "governance/autonomy-policy.json",
+      "anchor": null,
+      "kind": "doctrine",
+      "scope": "orchestration",
+      "version": "autonomy-policy/1",
+      "version_source": "declared_in_file",
+      "status": "active",
+      "owner": "nathan",
+      "superseded_by": null,
+      "prevails_over": [],
+      "positions": [],
+      "digest": {
+        "policy": "content_sha256",
+        "value": "50f8b11467e3219d2cf3df52fa0d075dce63a8ad8bced94fad6ba293c2a1f624",
+        "checked_at": "2026-08-22",
+        "delegated_to": null
+      },
+      "retention": "in_force",
+      "cleanup_issue": null,
+      "resolution_issue": 603,
+      "decision": {
+        "vision_log_seq": null,
+        "mission_seq": null,
+        "ref": "governance/decisions/D-2026-08-21-autonomie-luna-sol.md"
+      },
+      "notes": "Source exécutable de vérité pour les limites de lanes, l'identité Luna et le mode de revue Sol."
+    },
+    {
       "id": "adr.trust-019a",
       "title": "ADR-TRUST-019A — Registres modèle de menace racine de confiance",
       "path": "CANON/adr/ADR-TRUST-019A-registres-modele-de-menace-racine-confiance.md",
diff --git governance/autonomy-policy.json governance/autonomy-policy.json
new file mode 100644
index 0000000000000000000000000000000000000000..e0afca2849a174c163f5a3ec556358f1a76010b0
--- /dev/null
+++ governance/autonomy-policy.json
@@ -0,0 +1,27 @@
+{
+  "schema": "autonomy-policy/1",
+  "decision": "D-2026-08-21-autonomie-luna-sol",
+  "worker": {
+    "primary_model": "GPT-5.6 Luna",
+    "max_active_writer_lanes": 2
+  },
+  "review": {
+    "default_mode": "sol_blind",
+    "reviewer_model": "GPT-5.6 Sol",
+    "story_id": "stories/ORCH-LUNA-SOL-603.md",
+    "fresh_context": true,
+    "blind": true,
+    "reviewer_read_only": true,
+    "read_only": true
+  },
+  "terminal_states": [
+    "DONE_WITH_EVIDENCE",
+    "BLOCKED_WITH_REASON"
+  ],
+  "t3_limits": [
+    "payments",
+    "production_secrets",
+    "permanent_deletions",
+    "external_commitments"
+  ]
+}
diff --git governance/decisions/D-2026-08-21-autonomie-luna-sol.md governance/decisions/D-2026-08-21-autonomie-luna-sol.md
new file mode 100644
index 0000000000000000000000000000000000000000..a4bde9f46d8979b5c450fca05250a1b63c79a686
--- /dev/null
+++ governance/decisions/D-2026-08-21-autonomie-luna-sol.md
@@ -0,0 +1,28 @@
+# Décision — contrat d’autonomie Luna/Sol
+
+Date : 2026-08-21
+
+Référence : issue GitHub [#603 — mode autonome Luna/Sol](https://github.com/leon36000/ForgeAI-Toolkit/issues/603).
+
+## Décision
+
+GPT-5.6 Luna conduit et écrit les changements dans un mode explicite plafonné à
+deux lanes d’écriture actives. GPT-5.6 Sol intervient comme reviewer frais,
+aveugle et en lecture seule pour les livraisons soumises au mode sol_blind.
+
+La politique active définit `sol_blind` comme mode par défaut pour les PR
+courantes et exige ce mode dans le reçu qui les couvre. Le mode historique
+multi-vendor reste compatible pour les reçus d’archive; il ne peut pas couvrir
+une PR courante. Les identités actives luna_writer et sol sont ajoutées au
+roster sans supprimer l’identité historique luna, qui reste résoluble pour
+les reçus archivés.
+
+## Portée et limites
+
+Cette décision versionne le contrat observable dans
+governance/autonomy-policy.json. Les frontières T3 de Nathan restent
+inchangées : paiements, secrets de production, suppressions définitives et
+engagements externes ne sont pas délégués.
+
+Cette entrée matérialise la décision comme source d’autorité sous
+l’identifiant gov.decision-autonomie-luna-sol.
diff --git governance/path-classification-rules.json governance/path-classification-rules.json
index 136ec0af685415c75cb641c50d1f7a588bd34bf6..be629bfa6738e0d1425dce44176f958cd3c62983 100644
--- governance/path-classification-rules.json
+++ governance/path-classification-rules.json
@@ -714,6 +714,20 @@
       "target_kind": "keep",
       "load_bearing": true,
       "rationale": "RC1-010 (#440) lot 0 : racine de destination unique pour la migration de coordination/**, Phase-A/**, Rapports/**, Recherche/rall-1-agents-orchestration.yaml et .cursor/rules/forgeai-orchestration.mdc (lots 1-2). Ajoutée en amont de tout déplacement pour que classify_paths.py ne lève pas 'chemin non classé' dès le premier fichier déplacé. load_bearing=true car archive/coordination/work-packages.json restera lu par validate_coordination.py/state_current.py après son déplacement (lot 1)."
+    },
+    {
+      "id": "working-superpowers-sdd",
+      "match": {
+        "kind": "prefix",
+        "value": ".superpowers/sdd/"
+      },
+      "class": "WORKING",
+      "generated": false,
+      "owner": "working-cockpit",
+      "target": null,
+      "target_kind": "keep",
+      "load_bearing": false,
+      "rationale": "Les plans et rapports SDD sont des artefacts du cockpit de travail, versionnés pour la traçabilité de l'exécution mais non livrés comme code produit."
     }
   ]
 }
diff --git governance/vision-log.jsonl governance/vision-log.jsonl
index c6de16d1a59ba08037a18b875249b40059b3d657..a9686e4c331f4b65e3c872844be08fa8a95ab660 100644
--- governance/vision-log.jsonl
+++ governance/vision-log.jsonl
@@ -20,3 +20,4 @@
 {"actor":"orchestrateur","hash":"4c4019fb6f24670e5e368ececb16bc659998b7375d74bc8439be95cb6523e873","payload":{"de":{"status":"conflicted","superseded_by":null},"decision":"https://github.com/leon36000/ForgeAI-Toolkit/issues/487","mission_seq":null,"motif":"PR432_resout_autocontradiction_interne_position_mise_a_jour_vers_claude_code_opus_mission_lead_conflit_residuel_avec_canon_plan_integral_suivi_487","source_id":"agents-md","vers":{"status":"conflicted","superseded_by":null}},"prev_hash":"09520ea378e4f9e1242247850653b0a1aa3fc1e1435577c5826fae1f229f9392","seq":20,"ts":"2026-08-15T08:05:51+00:00","type":"vision_change"}
 {"actor":"orchestrateur","hash":"6bb96f389f005ff41ae1cf7d246edc56d2e611951b71d92014b828519f3e179c","payload":{"de":{"status":"conflicted","superseded_by":null},"decision":"https://github.com/leon36000/ForgeAI-Toolkit/issues/432","mission_seq":null,"motif":"PR432_retire_la_section_orch001_dAGENTS_md_cleanup_termine","source_id":"agents-md.orch-001","vers":{"status":"superseded","superseded_by":"gov.decision-mission-lead"}},"prev_hash":"4c4019fb6f24670e5e368ececb16bc659998b7375d74bc8439be95cb6523e873","seq":21,"ts":"2026-08-15T08:05:51+00:00","type":"vision_change"}
 {"actor":"orchestrateur","hash":"3a98b420540b2eb86dfdf93c0ae12ae6d603383448a62347f01328ed09034af9","payload":{"de":{"status":"active","superseded_by":null},"decision":"https://github.com/leon36000/ForgeAI-Toolkit/issues/440","mission_seq":null,"motif":"RC1-010_lot0_coord_work_packages_etait_actif_a_tort_alors_que_AGENTS_md_le_declare_archive_depuis_481_alignement_avec_son_pair_coord_active_claims_deja_superseded_depuis_431","source_id":"coord.work-packages","vers":{"status":"superseded","superseded_by":"gov.decision-mission-lead"}},"prev_hash":"6bb96f389f005ff41ae1cf7d246edc56d2e611951b71d92014b828519f3e179c","seq":22,"ts":"2026-08-15T23:19:51+00:00","type":"vision_change"}
+{"actor":"claude-code","hash":"4dafa47be8df7517e815565bf6c554c8fc37c117b11e50e57ec8f9c3e44adfcc","payload":{"decision":"governance/decisions/D-2026-08-21-autonomie-luna-sol.md","issue":603,"motif":"Task 4 documente le contrat actif Luna/Sol, les deux lanes, la reprise et le chemin de merge sûr","source_id":"gov.decision-autonomie-luna-sol","status":"active","terminal_states":["DONE_WITH_EVIDENCE","BLOCKED_WITH_REASON"]},"prev_hash":"3a98b420540b2eb86dfdf93c0ae12ae6d603383448a62347f01328ed09034af9","seq":23,"ts":"2026-08-22T09:41:04+00:00","type":"vision_change"}
diff --git manifests/roles.yaml manifests/roles.yaml
index 0948cd195ad71d18591b69ff0ec7d1154f57e7d0..fa70c8fc3d2dd7923ff087fedd5438d1db5fc65c 100644
--- manifests/roles.yaml
+++ manifests/roles.yaml
@@ -144,6 +144,24 @@ membres:
     phase_b: Pool rotation reviewers
     contrainte: route instable, journalisée ; pool de rotation uniquement
 
+  - id: luna_writer
+    modele: GPT-5.6 Luna
+    vendor: openai
+    provider_id: GPT-5.6-Luna-Writer
+    statut: actif
+    phase_a: Writer autonome
+    phase_b: Writer autonome
+    contrainte: maximum de deux lanes d’écriture actives ; ne décide pas des frontières T3
+
+  - id: sol
+    modele: GPT-5.6 Sol
+    vendor: openai
+    provider_id: GPT-5.6-Sol
+    statut: actif
+    phase_a: Reviewer aveugle sol_blind
+    phase_b: Reviewer aveugle sol_blind
+    contrainte: contexte frais, lecture seule ; ne review jamais un changement qu’il a écrit
+
   - id: mimo
     modele: MiMo 2.5 Pro
     vendor: xiaomi
diff --git scripts/governance/check_md_packs.py scripts/governance/check_md_packs.py
index a5b84d874c71eb0273b7e0e92f988c52aba896bc..19f681e4ae06bcfe9ef9220c59e728a65911db97 100644
--- scripts/governance/check_md_packs.py
+++ scripts/governance/check_md_packs.py
@@ -127,13 +127,27 @@ def analyser(texte: str) -> list[dict]:
 
 
 def scanner(racine: Path) -> dict[str, list[dict]]:
-    """Scanne récursivement `racine` pour tout fichier .md, retourne {chemin: défauts}.
+    """Scanne récursivement `racine` pour les documents Markdown de preuve.
+
+    Seuls les prompts générés situés sous le chemin canonique
+    `evidence/reviews/<dossier>/SOL-PROMPT.md` sont exclus : ils contiennent le diff brut
+    canonique, donc peuvent embarquer des fences imbriquées qui ne sont pas une structure de pack
+    à valider. Un document nommé `SOL-PROMPT.md` ailleurs reste entièrement soumis au scanner,
+    comme `pack.md` et `REVIEW-PACK.md`.
 
     N'utilise PAS git (Path.rglob uniquement) : doit fonctionner dans un clone/extraction sans
     .git (vérification "extraction dans un clone propre" du critère de l'issue #441).
     """
     resultats: dict[str, list[dict]] = {}
     for chemin in sorted(racine.rglob("*.md")):
+        parties = chemin.resolve().parts
+        if (
+            chemin.name == "SOL-PROMPT.md"
+            and len(parties) >= 4
+            and parties[-3:] == ("reviews", parties[-2], "SOL-PROMPT.md")
+            and parties[-4] == "evidence"
+        ):
+            continue
         try:
             texte = chemin.read_text(encoding="utf-8")
         except (OSError, UnicodeDecodeError):
diff --git scripts/reviews_gate.py scripts/reviews_gate.py
index 27a211627ab52b1dd3aaada45d37b4e53dcc985d..898901e9d73aad17eb3ff321448312dccbdbddd7 100644
--- scripts/reviews_gate.py
+++ scripts/reviews_gate.py
@@ -43,6 +43,7 @@ import argparse
 import importlib.util
 import json
 import subprocess
+from datetime import datetime
 from pathlib import Path
 from typing import Callable
 
@@ -173,6 +174,7 @@ def check(
     expected_issue: int | None = None,
     mode: str | None = None,
     runner: GitRunner | None = None,
+    now: datetime | None = None,
 ) -> tuple[bool, list[str]]:
     revue = _load_revue()
     execute = _default_runner if runner is None else runner
@@ -186,8 +188,13 @@ def check(
         return False, [f"ECHEC : mode inconnu {mode!r}"]
 
     etat_git = None
+    current_receipt_mode = None
     if exiger_recu_courant:
         try:
+            current_receipt_mode = revue.load_autonomy_policy()["review"]["default_mode"]
+        except (OSError, TypeError, ValueError, KeyError) as error:
+            return False, [f"ECHEC : politique de revue courante invalide : {error}"]
+        try:
             etat_git = revue._etat_git_reel(base_ref, "HEAD", runner=execute)
         except (OSError, ValueError, subprocess.CalledProcessError) as error:
             return False, [f"ECHEC : état git courant inaccessible : {error}"]
@@ -226,30 +233,112 @@ def check(
             report.append(f"ECHEC {entry} : verdict illisible : {error}")
             continue
 
-        result = revue.tally(verdicts)
+        receipt_path = directory / "RECU.json"
+        receipt = None
+        if receipt_path.is_file():
+            try:
+                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
+            except (OSError, json.JSONDecodeError) as error:
+                if exiger_recu_courant:
+                    ok = False
+                    report.append(f"ECHEC {entry} : reçu illisible : {error}")
+                    continue
+
+        # Receipt mode is the dispatch contract: legacy multi_vendor keeps its 3/3 tally;
+        # active sol_blind is delegated to the exact-one-Sol validator without weakening legacy.
+        receipt_mode = receipt.get("mode", "multi_vendor") if isinstance(receipt, dict) else "multi_vendor"
+        sol_covers_current = False
+        historical_sol = (
+            receipt_mode == "sol_blind"
+            and exiger_recu_courant
+            and not revue._sol_receipt_binding_matches_current(receipt, etat_git)
+        )
+        historical_sol_valid = True
+        if historical_sol:
+            # A historical receipt may stop covering the current diff, but that status must not
+            # turn an intrinsically malformed/tampered receipt into informational noise. Validate
+            # its own immutable contract against the reviewed Git objects and stored prompt first;
+            # only the later current-state mismatch is exempted.
+            try:
+                revue._validate_sol_archive_receipt(
+                    receipt,
+                    execute,
+                    verdicts=verdicts,
+                    review_dir=directory,
+                )
+            except (
+                OSError,
+                json.JSONDecodeError,
+                KeyError,
+                TypeError,
+                ValueError,
+                subprocess.CalledProcessError,
+            ) as error:
+                historical_sol_valid = False
+                historical_sol = False
+                ok = False
+                report.append(
+                    f"ECHEC {entry} : preuve Sol historique intrinsèquement invalide = {error}"
+                )
+        if receipt_mode not in ("multi_vendor", "sol_blind"):
+            result = {"result": "INVALIDE", "reason": f"mode de reçu inconnu : {receipt_mode!r}"}
+        elif receipt_mode == "sol_blind":
+            try:
+                expected = revue._sol_expected_from_git(
+                    receipt,
+                    etat_git,
+                    directory,
+                    verdicts,
+                    runner=execute,
+                )
+                sol_covers_current = bool(expected.pop("_covers_current", False))
+                result = revue.tally_sol_blind(
+                    verdicts,
+                    expected=expected,
+                    codeurs=receipt.get("codeur", []),
+                    allow_retired_codeurs=(mode == "archive"),
+                )
+                historical_sol = exiger_recu_courant and not sol_covers_current
+            except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
+                result = {"result": "INVALIDE", "reason": f"preuve Git/prompt Sol invalide : {error}"}
+        else:
+            result = revue.tally(verdicts)
         if result.get("result") != "APPROVE":
-            ok = False
-            report.append(
-                f"ECHEC {entry} : dépouillement = {result.get('result')} "
-                f"({result.get('reason', '')})"
-            )
+            if historical_sol:
+                report.append(
+                    f"info  {entry} : revue Sol historique non couvrante = "
+                    f"{result.get('result')} ({result.get('reason', '')})"
+                )
+            else:
+                ok = False
+                report.append(
+                    f"ECHEC {entry} : dépouillement = {result.get('result')} "
+                    f"({result.get('reason', '')})"
+                )
         else:
+            prefix = "info  " if historical_sol else "OK    "
             report.append(
-                f"OK    {entry} : APPROVE {result.get('reason', '')} "
+                f"{prefix}{entry} : APPROVE {result.get('reason', '')} "
                 f"vendors {result.get('vendors')}"
             )
 
-        receipt_path = directory / "RECU.json"
-
         if exiger_recu_courant and receipt_path.is_file():
-            try:
-                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
-            except (OSError, json.JSONDecodeError) as error:
-                ok = False
-                report.append(f"ECHEC {entry} : reçu illisible : {error}")
-                continue
-            receipt_result = revue.verifier_recu(receipt, verdicts, etat_git)
+            receipt_result = revue.verifier_recu(
+                receipt,
+                verdicts,
+                etat_git,
+                review_dir=directory,
+                runner=execute,
+                now=now,
+            )
             if receipt_result.get("result") == "APPROVE":
+                if receipt_mode != current_receipt_mode:
+                    ok = False
+                    report.append(
+                        f"ECHEC {entry} : reçu courant mode={receipt_mode!r} refusé ; "
+                        f"mode de politique requis = {current_receipt_mode!r}"
+                    )
+                    continue
                 if expected_issue is not None and (
                     not isinstance(receipt, dict) or receipt.get("issue") != expected_issue
                 ):
@@ -292,21 +381,45 @@ def check(
                 # bas via received_current). Régression #439/PR500 : le mode PR faisait
                 # échouer le gate sur CHAQUE reçu historique déjà mergé, bloquant toute PR
                 # future dès qu'une entrée liante antérieure portait un RECU.json.
-                report.append(
-                    f"info  {entry} : reçu invalide = {receipt_result.get('result')} "
-                    f"({receipt_result.get('reason', '')}) — ignoré si un autre reçu couvre "
-                    f"le changement courant"
-                )
+                if receipt_mode == "sol_blind" and not historical_sol_valid:
+                    ok = False
+                    report.append(
+                        f"ECHEC {entry} : reçu Sol historique intrinsèquement invalide = "
+                        f"{receipt_result.get('result')} ({receipt_result.get('reason', '')})"
+                    )
+                else:
+                    report.append(
+                        f"info  {entry} : reçu invalide = {receipt_result.get('result')} "
+                        f"({receipt_result.get('reason', '')}) — ignoré si un autre reçu couvre "
+                        f"le changement courant"
+                    )
 
         if mode == "archive" and receipt_path.is_file():
+            reviewed_commit = None
             try:
                 receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
-                commit = receipt["head_commit"]
-                # Anti-injection : commit vient d'un RECU.json lu au disque, même garde que
-                # les refs de _diff_canonique/_etat_git_reel (objection mineure revue scellée
-                # RC1-004-PR497-v2, DeepSeek-V4-Pro).
-                revue._validate_git_ref(commit)
-            except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as error:
+                if isinstance(receipt, dict) and receipt.get("mode") == "sol_blind":
+                    revue._validate_sol_archive_receipt(
+                        receipt,
+                        execute,
+                        verdicts=verdicts,
+                        review_dir=directory,
+                    )
+                    commit = receipt["head_commit"]
+                    reviewed_commit = receipt["reviewed_head_commit"]
+                else:
+                    commit = receipt["head_commit"]
+                    # Legacy receipts retain their historical ref validation; only the Sol
+                    # schema requires exact object IDs for every commit/tree field.
+                    revue._validate_git_ref(commit)
+            except (
+                OSError,
+                json.JSONDecodeError,
+                KeyError,
+                ValueError,
+                TypeError,
+                subprocess.CalledProcessError,
+            ) as error:
                 # TypeError : RECU.json valide en JSON mais pas un objet (ex. liste/null) —
                 # receipt["head_commit"] lèverait sinon une exception non gérée (objection
                 # mineure round 3, DeepSeek-V4-Pro).
@@ -316,6 +429,11 @@ def check(
             if not _is_ancestor(commit, execute):
                 ok = False
                 report.append(f"ECHEC {entry} : reçu pointe un commit jamais fusionné")
+            if reviewed_commit is not None and not _is_ancestor(reviewed_commit, execute):
+                ok = False
+                report.append(
+                    f"ECHEC {entry} : reçu Sol reviewed_head_commit jamais fusionné"
+                )
 
     if exiger_recu_courant and not received_current:
         ok = False
diff --git scripts/revue.py scripts/revue.py
index 32f104528cdf21c596534873508840f36bc27177..7cf15902f398124f4670376556243d18336b1f78 100644
--- scripts/revue.py
+++ scripts/revue.py
@@ -31,24 +31,65 @@ from __future__ import annotations
 
 import hashlib
 import json
+import math
 import re
 import subprocess
 import sys
-from datetime import datetime
+from datetime import datetime, timedelta
 from pathlib import Path
 from typing import Callable
 
-_PLACEHOLDER = re.compile(r"\{(story_id|criteres|artefact_path|artefact)\}")
+_TEMPLATE_FIELD = re.compile(
+    r"\{(story_id|criteres|artefact_path|artefact|metadata_json|response_schema)\}"
+)
 _MEMBER_START = re.compile(r"^\s*-\s*id:\s*(\S+)\s*(?:#.*)?$")
-_MEMBER_FIELD = re.compile(r"^\s+(vendor|provider_id|modele):\s*(.+?)\s*(?:#.*)?$")
+_MEMBER_FIELD = re.compile(r"^\s+(vendor|provider_id|modele|statut):\s*(.+?)\s*(?:#.*)?$")
 # manifests/routes.yaml : mapping flow-style (une route par ligne) — membre/modele_reponse
 # toujours sur la 1ère ligne de l'entrée (une éventuelle "note:" continue sur la ligne
 # suivante, jamais capturée ici, pas pertinente pour l'identité vendor).
 _ROUTE_ENTRY = re.compile(r"membre:\s*(\S+?),.*?modele_reponse:\s*([^,}]+)")
 _NON_ALNUM = re.compile(r"[^a-z0-9]")
+_OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
+_DIGEST = re.compile(r"^[0-9a-f]{64}$")
+_SOL_PROMPT_FILENAME = "SOL-PROMPT.md"
+_SOL_TEMPLATE_PATH = "CANON/revue-template.md"
+_SOL_ARTIFACT_PATH = "canonical-git-diff"
+_SOL_CRITERIA_HEADING = "## Critères d’acceptation"
+_SOL_CANONICAL_ID = "sol"
+_SOL_CANONICAL_MODEL = "GPT-5.6 Sol"
+_SOL_CANONICAL_VENDOR = "openai"
+_SOL_CANONICAL_PROVIDER_ID = "GPT-5.6-Sol"
+_SOL_CANONICAL_STATUS = "actif"
+_SOL_CANONICAL_CODEUR_ID = "luna_writer"
+_SOL_CANONICAL_STORY_ID = "stories/ORCH-LUNA-SOL-603.md"
+_SOL_CANONICAL_DECISION = "D-2026-08-21-autonomie-luna-sol"
+_SOL_CANONICAL_T3_LIMITS = (
+    "payments",
+    "production_secrets",
+    "permanent_deletions",
+    "external_commitments",
+)
+# Freeze every Git setting that can change the textual patch or make the diff
+# plumbing fail under a caller's global configuration. The order file is a
+# tracked empty repository file, so this remains portable across Git hosts.
+_SOL_GIT_DIFF_CONFIG = (
+    "-c",
+    "core.attributesFile=",
+    "-c",
+    "diff.orderFile=scripts/coordination/__init__.py",
+    "-c",
+    "diff.suppressBlankEmpty=false",
+)
+_LUNA_CANONICAL_MODEL = "GPT-5.6 Luna"
+_LUNA_CANONICAL_VENDOR = "openai"
+_LUNA_CANONICAL_PROVIDER_ID = "GPT-5.6-Luna-Writer"
+_LUNA_CANONICAL_STATUS = "actif"
+_SOL_CLOCK_SKEW = timedelta(minutes=5)
+_SOL_MAX_WINDOW_HOURS = 24
 
 REPO = Path(__file__).resolve().parent.parent
 TEMPLATE = REPO / "CANON" / "revue-template.md"
+AUTONOMY_POLICY = REPO / "governance" / "autonomy-policy.json"
 
 # _SEVERITY_RANK/_BLOCKING couvrent DEUX vocabulaires : les verdicts réels du dépôt écrivent
 # la clé française "severite" avec l'échelle mineure/majeure/critique, alors que le code
@@ -225,6 +266,222 @@ def _validate_git_ref(ref: str) -> None:
         raise ValueError(f"reference git invalide {ref!r}")
 
 
+def _validate_object_id(value: object, field: str = "object_id") -> str:
+    if not isinstance(value, str) or _OBJECT_ID.fullmatch(value) is None:
+        raise ValueError(f"{field} doit être un object ID hexadécimal exact")
+    return value
+
+
+def _validate_digest(value: object, field: str = "digest") -> str:
+    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
+        raise ValueError(f"{field} doit être un digest SHA-256 exact")
+    return value
+
+
+def _resolve_commit(execute: GitRunner, commit: str) -> str:
+    _validate_object_id(commit, "commit")
+    resolved = execute(["git", "rev-parse", "--verify", f"{commit}^{{commit}}"]).strip()
+    if resolved != commit:
+        raise ValueError("commit résolu différent de l'object ID fourni")
+    return resolved
+
+
+def _resolve_commit_tree(execute: GitRunner, commit: str) -> str:
+    _resolve_commit(execute, commit)
+    tree = execute(["git", "rev-parse", "--verify", f"{commit}^{{tree}}"]).strip()
+    _validate_object_id(tree, "tree")
+    return tree
+
+
+def _require_commit_ancestor(
+    execute: GitRunner,
+    ancestor: str,
+    descendant: str,
+    field: str,
+) -> None:
+    """Require a declared review commit to remain on the current Git lineage."""
+    try:
+        execute(["git", "merge-base", "--is-ancestor", ancestor, descendant])
+    except subprocess.CalledProcessError as error:
+        raise ValueError(f"{field} hors de la lignée Git courante") from error
+
+
+def _sol_prompt_bytes(review_dir: Path) -> bytes:
+    prompt_path = review_dir / _SOL_PROMPT_FILENAME
+    if prompt_path.is_symlink():
+        raise ValueError(f"{_SOL_PROMPT_FILENAME} doit être un fichier régulier, pas un symlink")
+    if not prompt_path.is_file():
+        raise ValueError(f"{_SOL_PROMPT_FILENAME} absent du dossier de revue")
+    try:
+        return prompt_path.read_bytes()
+    except OSError as error:
+        raise ValueError(f"{_SOL_PROMPT_FILENAME} illisible") from error
+
+
+def _sol_prompt_sha256(review_dir: Path) -> str:
+    return hashlib.sha256(_sol_prompt_bytes(review_dir)).hexdigest()
+
+
+def _validate_sol_dossier(dossier: object, review_dir: Path | None = None) -> str:
+    """Validate the receipt directory identifier and, when available, its loaded directory."""
+    if not isinstance(dossier, str) or not dossier.strip():
+        raise ValueError("dossier Sol invalide")
+    if dossier in {".", ".."} or Path(dossier).name != dossier:
+        raise ValueError("dossier Sol doit être un nom de répertoire simple")
+    if review_dir is not None and Path(review_dir).name != dossier:
+        raise ValueError("dossier Sol différent du répertoire de revue")
+    return dossier
+
+
+def _validate_sol_story_id(story: object, issue: object | None = None) -> str:
+    """Accept only the immutable story bound to this Sol contract.
+
+    The story is copied into the canonical prompt, so accepting an arbitrary receipt-controlled
+    string would make the prompt byte-identically reconstructable while silently changing the
+    work item (or injecting newlines/instructions).  The current policy has one explicit story
+    binding; future contracts must add a new policy constant rather than widening this input.
+    """
+    try:
+        policy_story = load_autonomy_policy()["review"]["story_id"]
+    except (KeyError, TypeError, ValueError) as error:
+        raise ValueError("story Sol impossible à lier à la politique") from error
+    if story != policy_story:
+        raise ValueError("story Sol différente de l'identifiant canonique")
+    # `story` identifies the immutable work item; `issue` identifies the PR that
+    # carries the receipt. They are intentionally different namespaces (for example
+    # story #603 may be covered by PR #607).
+    if issue is not None and (
+        isinstance(issue, bool) or not isinstance(issue, int) or issue <= 0
+    ):
+        raise ValueError("issue Sol doit être un numéro positif")
+    return policy_story
+
+
+def _diff_artifact_canonique(
+    base_ref: str,
+    head_ref: str,
+    *,
+    runner: GitRunner | None = None,
+) -> str:
+    """Retourne l'artefact texte généré par les mêmes refs que le digest Sol."""
+    _validate_git_ref(base_ref)
+    _validate_git_ref(head_ref)
+    execute = _default_runner if runner is None else runner
+    return execute(
+        [
+            "git",
+            *_SOL_GIT_DIFF_CONFIG,
+            "diff",
+            "--no-ext-diff",
+            "--no-textconv",
+            "--binary",
+            "--full-index",
+            "--diff-algorithm=myers",
+            "--no-indent-heuristic",
+            "--unified=3",
+            "--inter-hunk-context=0",
+            "--no-color",
+            "--no-prefix",
+            "--no-relative",
+            "--no-renames",
+            f"{base_ref}...{head_ref}",
+            "--",
+            ".",
+            ":(exclude)evidence/reviews/**",
+            ":(exclude).superpowers/sdd/**",
+            ":(exclude)evidence/registres/**",
+            ":(exclude)governance/path-classification.json",
+            ":(exclude)governance/PATH-CLASSIFICATION.md",
+        ]
+    )
+
+
+def _diff_sdd_canonique(
+    base_ref: str,
+    head_ref: str,
+    *,
+    runner: GitRunner | None = None,
+) -> str:
+    """Hash the excluded SDD coordination diff so its state remains receipt-bound."""
+    _validate_git_ref(base_ref)
+    _validate_git_ref(head_ref)
+    execute = _default_runner if runner is None else runner
+    raw = execute(
+        [
+            "git",
+            *_SOL_GIT_DIFF_CONFIG,
+            "diff",
+            "--raw",
+            "--no-renames",
+            "--no-abbrev",
+            "-z",
+            f"{base_ref}...{head_ref}",
+        ]
+    )
+    fields = raw.split("\0")
+    entries: list[tuple[str, str, str, str]] = []
+    index = 0
+    while index + 1 < len(fields):
+        metadata = fields[index]
+        path = fields[index + 1]
+        index += 2
+        if not metadata or not path.startswith(".superpowers/sdd/"):
+            continue
+        parts = metadata.split()
+        if len(parts) != 5 or not parts[0].startswith(":"):
+            raise ValueError(f"sortie git --raw SDD invalide: {metadata!r}")
+        entries.append((parts[1], parts[2], parts[3], path))
+    entries.sort()
+    canonical = "".join(
+        f"{mode}\0{base_sha}\0{head_sha}\0{path}\n"
+        for mode, base_sha, head_sha, path in entries
+    )
+    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
+
+
+def _diff_mission_canonique(
+    base_ref: str,
+    head_ref: str,
+    *,
+    runner: GitRunner | None = None,
+) -> str:
+    """Hash the excluded mission registry so prior review conclusions stay receipt-bound."""
+    _validate_git_ref(base_ref)
+    _validate_git_ref(head_ref)
+    execute = _default_runner if runner is None else runner
+    raw = execute(
+        [
+            "git",
+            *_SOL_GIT_DIFF_CONFIG,
+            "diff",
+            "--raw",
+            "--no-renames",
+            "--no-abbrev",
+            "-z",
+            f"{base_ref}...{head_ref}",
+        ]
+    )
+    fields = raw.split("\0")
+    entries: list[tuple[str, str, str, str]] = []
+    index = 0
+    while index + 1 < len(fields):
+        metadata = fields[index]
+        path = fields[index + 1]
+        index += 2
+        if not metadata or not path.startswith("evidence/registres/"):
+            continue
+        parts = metadata.split()
+        if len(parts) != 5 or not parts[0].startswith(":"):
+            raise ValueError(f"sortie git --raw mission invalide: {metadata!r}")
+        entries.append((parts[1], parts[2], parts[3], path))
+    entries.sort()
+    canonical = "".join(
+        f"{mode}\0{base_sha}\0{head_sha}\0{path}\n"
+        for mode, base_sha, head_sha, path in entries
+    )
+    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
+
+
 def _diff_canonique(
     base_ref: str,
     head_ref: str,
@@ -233,6 +490,13 @@ def _diff_canonique(
     # préfixe legacy "reviews/" est retiré de l'exclusion par défaut (mort : plus aucun fichier
     # de revue n'y vit).
     #
+    # #603 : les journaux .superpowers/sdd/ contiennent les résultats des itérations de
+    # coordination; les exclure empêche une revue Sol aveugle de recevoir des verdicts
+    # antérieurs par transitivité. Ils restent versionnés pour l'audit, mais ne sont pas
+    # des changements produit évalués par le prompt courant.
+    # Le registre append-only evidence/registres/mission.jsonl porte également des conclusions
+    # de rounds antérieurs; il est hors du prompt courant et lié par mission_diff_digest.
+    #
     # #504 : governance/path-classification.json (+ son rendu .md) trace individuellement
     # chaque fichier sous evidence/reviews/**, RECU.json compris — le régénérer APRÈS avoir
     # scellé un reçu change donc TOUJOURS le diff que ce reçu prétend attester (interblocage
@@ -245,6 +509,8 @@ def _diff_canonique(
     # main, load_bearing) ne doit surtout PAS matcher par accident.
     exclude: tuple[str, ...] = (
         "evidence/reviews/",
+        ".superpowers/sdd/",
+        "evidence/registres/",
         "governance/path-classification.json",
         "governance/PATH-CLASSIFICATION.md",
     ),
@@ -261,7 +527,9 @@ def _diff_canonique(
     artefacts de sa propre revue (le dossier evidence/reviews/<ID>/*.verdict.json + la ligne
     BINDING.txt sont ajoutés dans LA MÊME PR que le code qu'ils attestent) — sans cette
     exclusion, l'empreinte calculée par le reçu ne pourrait JAMAIS correspondre à celle du diff
-    final (les reviewers ont vu un diff SANS ces fichiers). Même raisonnement pour
+    final (les reviewers ont vu un diff SANS ces fichiers). Les journaux `.superpowers/sdd/`
+    sont également exclus du prompt Sol : ils peuvent contenir des conclusions de revues
+    antérieures et ne sont pas du code produit. Même raisonnement pour
     governance/path-classification.json/.md (#504) : entièrement dérivés, re-vérifiés octet à
     octet par leur propre gate (classify_paths.py check), jamais montrés aux reviewers non plus.
     """
@@ -280,7 +548,16 @@ def _diff_canonique(
     # format `--raw`. Vérifié : avec --no-abbrev, les deux environnements produisent des hash
     # SHA-1 complets (40 caractères) strictement identiques pour un même diff logique.
     raw = execute(
-        ["git", "diff", "--raw", "--no-renames", "--no-abbrev", "-z", f"{base_ref}...{head_ref}"]
+        [
+            "git",
+            *_SOL_GIT_DIFF_CONFIG,
+            "diff",
+            "--raw",
+            "--no-renames",
+            "--no-abbrev",
+            "-z",
+            f"{base_ref}...{head_ref}",
+        ]
     )
     fields = raw.split("\0")
     entries: list[tuple[str, str, str, str]] = []
@@ -323,33 +600,741 @@ def _etat_git_reel(
         "head_commit": execute(["git", "rev-parse", head_ref]).strip(),
         "head_tree": execute(["git", "rev-parse", f"{head_ref}^{{tree}}"]).strip(),
         "diff_digest": _diff_canonique(base_ref, head_ref, runner=execute),
+        "sdd_diff_digest": _diff_sdd_canonique(base_ref, head_ref, runner=execute),
+        "mission_diff_digest": _diff_mission_canonique(base_ref, head_ref, runner=execute),
     }
 
 
-def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str,
-                 template_path: Path = TEMPLATE) -> tuple[str, str]:
-    """Rend (prompt_exact, sha256). Le template est lu au canon ; aucun texte n'est ajouté."""
-    tpl = template_path.read_text(encoding="utf-8")
-    # On ne garde que le corps (après le commentaire HTML d'en-tête) pour le prompt envoyé.
-    # Le marqueur est OBLIGATOIRE : sans lui, l'en-tête (instructions internes) fuiterait dans
-    # le prompt envoyé aux reviewers → non-neutralité (revue aveugle Nemotron). On échoue fort.
-    if "-->" not in tpl:
+def _template_mode_body(template_content: str, mode: str, template_path: Path) -> str:
+    """Select one mode section from the versioned template without adding prose in code."""
+    if "-->" not in template_content:
         raise ValueError(f"template {template_path} sans marqueur '-->' : en-tête non séparable")
-    tpl = tpl.split("-->", 1)[1].lstrip("\n")
-    values = {"story_id": story_id, "criteres": criteres.strip(),
-              "artefact_path": artefact_path, "artefact": artefact}
-    # Substitution EN UN SEUL PASSAGE (re.sub) : le texte substitué n'est JAMAIS re-scanné,
-    # donc un champ contenant « {artefact} » ne peut pas injecter un autre champ. Corrige le
-    # défaut d'injection croisée des .replace() chaînés (revue aveugle Qwen, criterion #4).
-    prompt = _PLACEHOLDER.sub(lambda m: values[m.group(1)], tpl)
+    body = template_content.split("-->", 1)[1].lstrip("\n")
+    start = f"<!-- MODE:{mode} -->"
+    end = f"<!-- END MODE:{mode} -->"
+    if start not in body or end not in body:
+        raise ValueError(f"template {template_path} sans section {mode!r}")
+    selected = body.split(start, 1)[1].split(end, 1)[0]
+    return selected.strip("\n")
+
+
+def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str,
+                 template_path: Path = TEMPLATE, *, mode: str = "multi_vendor",
+                 expected: dict | None = None, base_ref: str | None = None,
+                 head_ref: str | None = None, runner: GitRunner | None = None,
+                 template_content: str | None = None) -> tuple[str, str]:
+    """Render one exact, versioned prompt section and return its SHA-256."""
+    if template_content is None:
+        tpl = template_path.read_text(encoding="utf-8")
+    elif isinstance(template_content, str):
+        tpl = template_content
+    else:
+        raise ValueError("contenu du template invalide")
+    if mode not in ("multi_vendor", "sol_blind"):
+        raise ValueError(f"mode de revue inconnu : {mode!r}")
+    template_sha256 = hashlib.sha256(tpl.encode("utf-8")).hexdigest()
+    template_path_label = template_path
+    if mode == "sol_blind":
+        if not base_ref or not head_ref:
+            raise ValueError("base_ref et head_ref requis pour le mode sol_blind")
+        if runner is None:
+            canonical_artifact = _diff_artifact_canonique(base_ref, head_ref)
+            git_state = _etat_git_reel(base_ref, head_ref)
+        else:
+            canonical_artifact = _diff_artifact_canonique(
+                base_ref, head_ref, runner=runner
+            )
+            git_state = _etat_git_reel(base_ref, head_ref, runner=runner)
+        if artefact != canonical_artifact:
+            raise ValueError("artefact fourni différent du diff Git canonique")
+        metadata = {
+            "base_commit": git_state["base_commit"],
+            "reviewed_head_commit": git_state["head_commit"],
+            "reviewed_head_tree": git_state["head_tree"],
+            "candidate_diff_digest": git_state["diff_digest"],
+            "sdd_diff_digest": git_state["sdd_diff_digest"],
+            "mission_diff_digest": git_state["mission_diff_digest"],
+            "template_sha256": template_sha256,
+        }
+        if expected is not None:
+            for field, value in metadata.items():
+                expected_value = expected.get(field)
+                if expected_value is not None and expected_value != value:
+                    raise ValueError(f"métadonnée Git {field} contradictoire")
+        response_schema = {
+            "fresh_context": True,
+            "blind": True,
+            "reviewer_read_only": True,
+            "reviewer_model": "GPT-5.6-Sol",
+            **metadata,
+            "prompt_sha256": "sha256 du prompt reçu",
+            "verdict": "APPROVE ou REJECT",
+            "blocking_findings": [],
+            "reviewed_at": "timestamp ISO-8601 avec fuseau",
+        }
+        values = {
+            "story_id": story_id,
+            "criteres": criteres.strip(),
+            "artefact_path": artefact_path,
+            "artefact": artefact,
+            "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
+            "response_schema": json.dumps(response_schema, ensure_ascii=False, sort_keys=True),
+        }
+    else:
+        values = {
+            "story_id": story_id,
+            "criteres": criteres.strip(),
+            "artefact_path": artefact_path,
+            "artefact": artefact,
+            "metadata_json": "",
+            "response_schema": json.dumps(
+                {
+                    "verdict": "APPROVE ou REJECT",
+                    "objections": [
+                        {
+                            "severity": "critique|eleve|moyen|faible",
+                            "file": "chemin",
+                            "line": "entier ou null",
+                            "desc": "défaut réel et vérifiable",
+                        }
+                    ],
+                },
+                ensure_ascii=False,
+                separators=(",", ":"),
+            ),
+        }
+    template_body = _template_mode_body(tpl, mode, template_path_label)
+    # One substitution pass: substituted fields are never rescanned for placeholders.
+    prompt = _TEMPLATE_FIELD.sub(lambda match: values[match.group(1)], template_body)
     return prompt, hashlib.sha256(prompt.encode("utf-8")).hexdigest()
 
 
+def _git_blob(execute: GitRunner, commit: str, path: str) -> str:
+    """Read a fixed versioned text input from an already frozen commit."""
+    _validate_object_id(commit, "commit")
+    if not path or path.startswith("/") or ".." in Path(path).parts:
+        raise ValueError("chemin Git versionné invalide")
+    content = execute(["git", "show", f"{commit}:{path}"])
+    if not isinstance(content, str):
+        raise ValueError("entrée Git versionnée illisible")
+    return content
+
+
+def _sol_criteria_from_git(execute: GitRunner, commit: str, story_id: str) -> str:
+    """Read only the acceptance section from the story frozen in the reviewed commit."""
+    _validate_sol_story_id(story_id)
+    story = _git_blob(execute, commit, story_id)
+    lines = story.splitlines()
+    try:
+        start = lines.index(_SOL_CRITERIA_HEADING) + 1
+    except ValueError as error:
+        raise ValueError("story Sol sans section Critères d’acceptation") from error
+    end = next(
+        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
+        len(lines),
+    )
+    criteria = "\n".join(lines[start:end]).strip()
+    if not criteria:
+        raise ValueError("section Critères d’acceptation Sol vide")
+    return criteria
+
+
+def _canonical_sol_prompt(
+    story_id: str,
+    base_commit: str,
+    reviewed_head_commit: str,
+    *,
+    runner: GitRunner | None = None,
+) -> tuple[bytes, str]:
+    """Rebuild the exact Sol prompt from frozen Git objects and versioned inputs."""
+    execute = _default_runner if runner is None else runner
+    frozen_base = _resolve_commit(execute, base_commit)
+    frozen_head = _resolve_commit(execute, reviewed_head_commit)
+    criteria = _sol_criteria_from_git(execute, frozen_head, story_id)
+    template_content = _git_blob(execute, frozen_head, _SOL_TEMPLATE_PATH)
+    artifact = _diff_artifact_canonique(frozen_base, frozen_head, runner=execute)
+    prompt, prompt_sha = build_prompt(
+        story_id,
+        criteria,
+        _SOL_ARTIFACT_PATH,
+        artifact,
+        mode="sol_blind",
+        base_ref=frozen_base,
+        head_ref=frozen_head,
+        runner=execute,
+        template_content=template_content,
+    )
+    return prompt.encode("utf-8"), prompt_sha
+
+
+def _sol_prompt_metadata(prompt: bytes) -> dict:
+    """Extract the exact Git metadata object from a generated Sol prompt."""
+    try:
+        text = prompt.decode("utf-8")
+    except UnicodeDecodeError as error:
+        raise ValueError("prompt Sol non UTF-8") from error
+    marker = "MÉTADONNÉES GIT EXACTES (à recopier sans modification) :\n"
+    if marker not in text:
+        raise ValueError("métadonnées Git absentes du prompt Sol")
+    candidates: list[dict] = []
+    offset = 0
+    while True:
+        marker_start = text.find(marker, offset)
+        if marker_start < 0:
+            break
+        line = text[marker_start + len(marker) :].split("\n", 1)[0]
+        offset = marker_start + len(marker)
+        try:
+            metadata = json.loads(line)
+        except json.JSONDecodeError:
+            continue
+        if not isinstance(metadata, dict):
+            continue
+        try:
+            for field in ("base_commit", "reviewed_head_commit", "reviewed_head_tree"):
+                if field not in metadata:
+                    raise ValueError(f"métadonnée Git absente du prompt Sol : {field}")
+                _validate_object_id(metadata[field], field)
+            for field in (
+                "candidate_diff_digest",
+                "sdd_diff_digest",
+                "mission_diff_digest",
+                "template_sha256",
+            ):
+                if field not in metadata:
+                    raise ValueError(f"métadonnée Git absente du prompt Sol : {field}")
+                _validate_digest(metadata[field], field)
+        except (TypeError, ValueError):
+            continue
+        candidates.append(metadata)
+    if not candidates:
+        raise ValueError("métadonnées Git du prompt Sol invalides")
+    if len(candidates) != 1:
+        raise ValueError("métadonnées Git du prompt Sol ambiguës")
+    return candidates[0]
+
+
 def _severity(objection: dict) -> str:
     """Sévérité normalisée d'une objection — accepte les clés française ET anglaise."""
     return str(objection.get("severite") or objection.get("severity") or "faible").lower()
 
 
+def load_autonomy_policy(path: Path = AUTONOMY_POLICY) -> dict:
+    """Charge et valide le contrat d'autonomie utilisé par les chemins de production."""
+    try:
+        policy = json.loads(path.read_text(encoding="utf-8"))
+    except (OSError, json.JSONDecodeError) as error:
+        raise ValueError(f"politique d'autonomie illisible : {path}") from error
+    if not isinstance(policy, dict):
+        raise ValueError("politique d'autonomie invalide")
+    if policy.get("schema") != "autonomy-policy/1":
+        raise ValueError("schema de politique d'autonomie invalide")
+    worker = policy.get("worker")
+    if not isinstance(worker, dict):
+        raise ValueError("politique d'autonomie: worker manquant")
+    if worker.get("primary_model") != "GPT-5.6 Luna":
+        raise ValueError("worker.primary_model doit être GPT-5.6 Luna")
+    lanes = worker.get("max_active_writer_lanes")
+    if isinstance(lanes, bool) or not isinstance(lanes, int) or lanes != 2:
+        raise ValueError("max_active_writer_lanes doit être exactement 2")
+    review = policy.get("review")
+    if not isinstance(review, dict):
+        raise ValueError("politique d'autonomie: review manquant")
+    if review.get("default_mode") != "sol_blind":
+        raise ValueError("review.default_mode doit être sol_blind")
+    if review.get("reviewer_model") != "GPT-5.6 Sol":
+        raise ValueError("review.reviewer_model doit être GPT-5.6 Sol")
+    if review.get("story_id") != _SOL_CANONICAL_STORY_ID:
+        raise ValueError("review.story_id doit être l'identifiant Sol canonique")
+    for requirement in ("fresh_context", "blind", "reviewer_read_only", "read_only"):
+        if review.get(requirement) is not True:
+            raise ValueError(f"review.{requirement} doit être true")
+    if policy.get("terminal_states") != ["DONE_WITH_EVIDENCE", "BLOCKED_WITH_REASON"]:
+        raise ValueError("terminal_states de politique d'autonomie invalides")
+    if policy.get("decision") != _SOL_CANONICAL_DECISION:
+        raise ValueError("decision de politique d'autonomie invalide")
+    if policy.get("t3_limits") != list(_SOL_CANONICAL_T3_LIMITS):
+        raise ValueError("t3_limits de politique d'autonomie invalides")
+    return policy
+
+
+def _canonical_sol_member() -> dict[str, str] | None:
+    """Return Sol only when the active roster entry matches the policy contract exactly."""
+    try:
+        policy = load_autonomy_policy()
+    except ValueError:
+        return None
+    if policy["review"]["reviewer_model"] != _SOL_CANONICAL_MODEL:
+        return None
+    roles = _load_roles_yaml(REPO / "manifests" / "roles.yaml")
+    matches = [member for member in roles if member.get("id") == _SOL_CANONICAL_ID]
+    if len(matches) != 1:
+        return None
+    member = matches[0]
+    expected = {
+        "id": _SOL_CANONICAL_ID,
+        "modele": _SOL_CANONICAL_MODEL,
+        "statut": _SOL_CANONICAL_STATUS,
+        "vendor": _SOL_CANONICAL_VENDOR,
+        "provider_id": _SOL_CANONICAL_PROVIDER_ID,
+    }
+    if any(member.get(field) != value for field, value in expected.items()):
+        return None
+    return expected
+
+
+def _sol_aliases(table: dict[str, str] | None) -> set[str] | None:
+    """Return only aliases of the exact canonical active Sol member."""
+    member = _canonical_sol_member()
+    if table is None or member is None:
+        return None
+    aliases = {
+        _normalize(member["id"]),
+        _normalize(member["provider_id"]),
+        _normalize(member["modele"]),
+    }
+    if any(table.get(alias) != _SOL_CANONICAL_VENDOR for alias in aliases):
+        return None
+    return aliases
+
+
+def _canonical_luna_member() -> dict[str, str] | None:
+    """Return Luna writer only when the active roster entry is canonical and unique."""
+    try:
+        policy = load_autonomy_policy()
+    except ValueError:
+        return None
+    if policy["worker"]["primary_model"] != _LUNA_CANONICAL_MODEL:
+        return None
+    roles = _load_roles_yaml(REPO / "manifests" / "roles.yaml")
+    matches = [member for member in roles if member.get("id") == _SOL_CANONICAL_CODEUR_ID]
+    if len(matches) != 1:
+        return None
+    member = matches[0]
+    expected = {
+        "id": _SOL_CANONICAL_CODEUR_ID,
+        "modele": _LUNA_CANONICAL_MODEL,
+        "statut": _LUNA_CANONICAL_STATUS,
+        "vendor": _LUNA_CANONICAL_VENDOR,
+        "provider_id": _LUNA_CANONICAL_PROVIDER_ID,
+    }
+    if any(member.get(field) != value for field, value in expected.items()):
+        return None
+    return expected
+
+
+def _codeur_identity_table(
+    roles_path: Path = REPO / "manifests" / "roles.yaml",
+    *,
+    include_retired: bool = False,
+) -> dict[str, str] | None:
+    """Resolve selectable codewriter aliases to canonical roster member IDs.
+
+    Retired identities remain resolvable by legacy audit paths, but are not accepted for fresh
+    ``sol_blind`` evidence unless an archive caller explicitly opts into them.
+    """
+    roles = _load_roles_yaml(roles_path)
+    if not roles:
+        return None
+    table: dict[str, str] = {}
+    for member in roles:
+        if not include_retired and member.get("statut") == "retire":
+            continue
+        member_id = member.get("id")
+        if not isinstance(member_id, str) or not member_id:
+            continue
+        aliases = [member.get("id"), member.get("provider_id"), member.get("modele")]
+        for alias in aliases:
+            if not isinstance(alias, str) or not alias:
+                continue
+            key = _normalize(alias)
+            previous = table.get(key)
+            if previous is not None and previous != member_id:
+                return None
+            table[key] = member_id
+    return table or None
+
+
+def _aware_timestamp(value: object) -> datetime | None:
+    if not isinstance(value, str):
+        return None
+    try:
+        timestamp = datetime.fromisoformat(value)
+    except ValueError:
+        return None
+    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
+        return None
+    return timestamp
+
+
+def _validation_time(now: datetime | None) -> datetime:
+    if now is None:
+        return datetime.now().astimezone()
+    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
+        raise ValueError("horloge de validation doit être un timestamp avec fuseau")
+    return now
+
+
+def _sol_window_hours(value: object, default: object) -> float:
+    window = default if value is None else value
+    if isinstance(window, bool) or not isinstance(window, (int, float)):
+        raise ValueError("fenêtre Sol invalide")
+    try:
+        numeric_window = float(window)
+    except (OverflowError, ValueError) as error:
+        raise ValueError("fenêtre Sol invalide") from error
+    if (
+        not math.isfinite(numeric_window)
+        or numeric_window < 0
+        or numeric_window > _SOL_MAX_WINDOW_HOURS
+    ):
+        raise ValueError("fenêtre Sol invalide")
+    return numeric_window
+
+
+def _validate_sol_freshness(
+    recu: dict,
+    verdicts: list[dict],
+    *,
+    fenetre_heures_defaut: int | float = 24,
+    now: datetime | None = None,
+) -> None:
+    """Validate current Sol receipt timestamps with an injectable validation clock."""
+    if len(verdicts) != 1 or not isinstance(verdicts[0], dict):
+        raise ValueError("sol_blind exige exactement un verdict objet")
+    validation_time = _validation_time(now)
+    receipt_time = _aware_timestamp(recu.get("date_heure"))
+    receipt_reviewed_at = _aware_timestamp(recu.get("reviewed_at"))
+    verdict_reviewed_at = _aware_timestamp(verdicts[0].get("reviewed_at"))
+    if receipt_time is None:
+        raise ValueError("date_heure du reçu doit avoir un fuseau")
+    if receipt_reviewed_at is None or verdict_reviewed_at is None:
+        raise ValueError("reviewed_at doit avoir un fuseau")
+    if receipt_reviewed_at != verdict_reviewed_at:
+        raise ValueError("reviewed_at du reçu ne correspond pas au verdict")
+    verdict_date_value = verdicts[0].get("date_heure")
+    verdict_date = None
+    if verdict_date_value is not None:
+        verdict_date = _aware_timestamp(verdict_date_value)
+        if verdict_date is None:
+            raise ValueError("date_heure du verdict doit avoir un fuseau")
+    window = _sol_window_hours(recu.get("fenetre_heures"), fenetre_heures_defaut)
+    if receipt_reviewed_at > receipt_time:
+        raise ValueError("reviewed_at postérieur à date_heure")
+    if verdict_date is not None and verdict_date < receipt_reviewed_at:
+        raise ValueError("date_heure du verdict antérieure à reviewed_at")
+    if receipt_time > validation_time + _SOL_CLOCK_SKEW:
+        raise ValueError("date_heure du reçu futur")
+    if receipt_reviewed_at > validation_time + _SOL_CLOCK_SKEW:
+        raise ValueError("reviewed_at du verdict futur")
+    if verdict_date is not None and verdict_date > validation_time + _SOL_CLOCK_SKEW:
+        raise ValueError("date_heure du verdict futur")
+    if validation_time - receipt_reviewed_at > timedelta(hours=window):
+        raise ValueError("preuve Sol périmée")
+
+
+def _sol_expected_from_git(
+    recu: dict,
+    etat_git: dict | None,
+    review_dir: Path,
+    verdicts: list[dict],
+    *,
+    runner: GitRunner | None = None,
+) -> dict:
+    """Construit les attentes Sol depuis Git, le prompt stocké et le verdict séparé."""
+    if not isinstance(recu, dict):
+        raise ValueError("reçu Sol invalide")
+    if recu.get("schema") != "recu-revue/2":
+        raise ValueError("schema Sol doit être exactement recu-revue/2")
+    required = (
+        "story", "base_commit", "head_commit", "head_tree", "reviewed_head_commit",
+        "reviewed_head_tree", "candidate_diff_digest", "diff_digest", "prompt_sha256",
+        "sdd_diff_digest", "mission_diff_digest", "template_sha256", "reviewed_at",
+    )
+    for field in required:
+        if field not in recu:
+            raise ValueError(f"métadonnée Sol absente : {field}")
+    _validate_sol_story_id(recu["story"], recu.get("issue"))
+    for field in ("base_commit", "head_commit", "head_tree", "reviewed_head_commit", "reviewed_head_tree"):
+        _validate_object_id(recu[field], field)
+    for field in (
+        "candidate_diff_digest", "diff_digest", "sdd_diff_digest", "mission_diff_digest",
+        "prompt_sha256"
+    ):
+        _validate_digest(recu[field], field)
+    execute = _default_runner if runner is None else runner
+    base_commit = _resolve_commit(execute, recu["base_commit"])
+    head_commit = _resolve_commit(execute, recu["head_commit"])
+    head_tree = _resolve_commit_tree(execute, head_commit)
+    reviewed_head_commit = _resolve_commit(execute, recu["reviewed_head_commit"])
+    reviewed_head_tree = _resolve_commit_tree(execute, reviewed_head_commit)
+    if recu["head_tree"] != head_tree:
+        raise ValueError("head_tree différent de l'arbre Git du head_commit")
+    if recu["reviewed_head_tree"] != reviewed_head_tree:
+        raise ValueError("reviewed_head_tree différent de l'arbre Git examiné")
+    canonical_digest = _diff_canonique(base_commit, reviewed_head_commit, runner=execute)
+    _validate_digest(canonical_digest, "candidate_diff_digest Git")
+    if recu["candidate_diff_digest"] != canonical_digest:
+        raise ValueError("candidate_diff_digest différent du diff Git examiné")
+    if recu["diff_digest"] != canonical_digest:
+        raise ValueError("diff_digest différent du diff Git examiné")
+    canonical_sdd_digest = _diff_sdd_canonique(
+        base_commit, reviewed_head_commit, runner=execute
+    )
+    if recu["sdd_diff_digest"] != canonical_sdd_digest:
+        raise ValueError("sdd_diff_digest différent du journal SDD Git examiné")
+    canonical_mission_digest = _diff_mission_canonique(
+        base_commit, reviewed_head_commit, runner=execute
+    )
+    if recu["mission_diff_digest"] != canonical_mission_digest:
+        raise ValueError("mission_diff_digest différent du registre de mission Git examiné")
+    if len(verdicts) != 1 or not isinstance(verdicts[0], dict):
+        raise ValueError("sol_blind exige exactement un verdict objet")
+    canonical_prompt, canonical_prompt_sha = _canonical_sol_prompt(
+        recu["story"],
+        base_commit,
+        reviewed_head_commit,
+        runner=execute,
+    )
+    template_content = _git_blob(execute, reviewed_head_commit, _SOL_TEMPLATE_PATH)
+    template_sha = hashlib.sha256(template_content.encode("utf-8")).hexdigest()
+    _validate_digest(recu["template_sha256"], "template_sha256")
+    if recu["template_sha256"] != template_sha:
+        raise ValueError("template_sha256 différent du template Git examiné")
+    stored_prompt = _sol_prompt_bytes(review_dir)
+    if stored_prompt != canonical_prompt:
+        raise ValueError(
+            f"{_SOL_PROMPT_FILENAME} différent du prompt Sol canonique généré depuis Git"
+        )
+    prompt_sha = hashlib.sha256(stored_prompt).hexdigest()
+    if prompt_sha != canonical_prompt_sha:
+        raise ValueError("sha256 du prompt canonique incohérent")
+    if recu["prompt_sha256"] != prompt_sha:
+        raise ValueError("prompt_sha256 différent des octets de SOL-PROMPT.md canonique")
+    reviewed_at = verdicts[0].get("reviewed_at")
+    if _aware_timestamp(reviewed_at) is None:
+        raise ValueError("reviewed_at du verdict doit avoir un fuseau")
+    if recu["reviewed_at"] != reviewed_at:
+        raise ValueError("reviewed_at du reçu ne correspond pas au verdict")
+
+    covers_current = False
+    if etat_git is not None:
+        current_base = _validate_object_id(etat_git.get("base_commit"), "base_commit courant")
+        current_head = _validate_object_id(etat_git.get("head_commit"), "head_commit courant")
+        current_tree = _validate_object_id(etat_git.get("head_tree"), "head_tree courant")
+        current_digest = _validate_digest(etat_git.get("diff_digest"), "diff_digest courant")
+        current_sdd_digest = _validate_digest(
+            etat_git.get("sdd_diff_digest"), "sdd_diff_digest courant"
+        )
+        current_mission_digest = _validate_digest(
+            etat_git.get("mission_diff_digest"), "mission_diff_digest courant"
+        )
+        covers_current = (
+            base_commit == current_base
+            and canonical_digest == current_digest
+            and recu["candidate_diff_digest"] == current_digest
+            and recu["sdd_diff_digest"] == current_sdd_digest
+            and recu["mission_diff_digest"] == current_mission_digest
+        )
+        # current_head/current_tree are resolved by _etat_git_reel; retaining the explicit
+        # shape checks here prevents a malformed injected state from becoming an expectation.
+        if not current_head or not current_tree:
+            raise ValueError("état Git courant incomplet")
+        _require_commit_ancestor(
+            execute, head_commit, reviewed_head_commit, "head_commit"
+        )
+        _require_commit_ancestor(
+            execute, reviewed_head_commit, current_head, "reviewed_head_commit"
+        )
+    return {
+        "candidate_diff_digest": canonical_digest,
+        "diff_digest": canonical_digest,
+        "base_commit": base_commit,
+        "head_commit": head_commit,
+        "head_tree": head_tree,
+        "reviewed_head_commit": reviewed_head_commit,
+        "reviewed_head_tree": reviewed_head_tree,
+        "prompt_sha256": prompt_sha,
+        "sdd_diff_digest": canonical_sdd_digest,
+        "mission_diff_digest": canonical_mission_digest,
+        "template_sha256": template_sha,
+        "reviewed_at": reviewed_at,
+        "_covers_current": covers_current,
+    }
+
+
+def _sol_receipt_binding_matches_current(recu: object, etat_git: object) -> bool:
+    """Classifie uniquement la liaison base/diff; full proof reste séparée."""
+    if not isinstance(recu, dict) or not isinstance(etat_git, dict):
+        return False
+    try:
+        receipt_base = _validate_object_id(recu.get("base_commit"), "base_commit")
+        receipt_digest = _validate_digest(recu.get("diff_digest"), "diff_digest")
+        candidate_digest = _validate_digest(
+            recu.get("candidate_diff_digest"), "candidate_diff_digest"
+        )
+        receipt_sdd_digest = _validate_digest(
+            recu.get("sdd_diff_digest"), "sdd_diff_digest"
+        )
+        receipt_mission_digest = _validate_digest(
+            recu.get("mission_diff_digest"), "mission_diff_digest"
+        )
+        current_base = _validate_object_id(etat_git.get("base_commit"), "base_commit courant")
+        current_digest = _validate_digest(etat_git.get("diff_digest"), "diff_digest courant")
+        current_sdd_digest = _validate_digest(
+            etat_git.get("sdd_diff_digest"), "sdd_diff_digest courant"
+        )
+        current_mission_digest = _validate_digest(
+            etat_git.get("mission_diff_digest"), "mission_diff_digest courant"
+        )
+    except ValueError:
+        return False
+    return (
+        receipt_base == current_base
+        and receipt_digest == current_digest
+        and candidate_digest == current_digest
+        and receipt_sdd_digest == current_sdd_digest
+        and receipt_mission_digest == current_mission_digest
+    )
+
+
+def tally_sol_blind(
+    verdicts: list[dict],
+    expected: dict,
+    codeurs: list[str],
+    *,
+    allow_retired_codeurs: bool = False,
+) -> dict:
+    """Dépouille strictement l'unique verdict frais du reviewer Sol."""
+    if not isinstance(verdicts, list) or len(verdicts) != 1:
+        count = len(verdicts) if isinstance(verdicts, list) else "invalide"
+        return {"result": "INVALIDE", "reason": f"sol_blind exige exactement 1 verdict (reçu: {count})"}
+    verdict = verdicts[0]
+    if not isinstance(verdict, dict):
+        return {"result": "INVALIDE", "reason": "verdict Sol invalide"}
+    try:
+        load_autonomy_policy()
+    except ValueError as error:
+        return {"result": "INVALIDE", "reason": str(error)}
+
+    table = _vendor_table()
+    sol_aliases = _sol_aliases(table)
+    if sol_aliases is None:
+        return {
+            "result": "INVALIDE",
+            "reason": "identité Sol active absente du roster ou non vérifiable",
+        }
+    reviewer_model = verdict.get("reviewer_model")
+    if reviewer_model != _SOL_CANONICAL_PROVIDER_ID:
+        return {
+            "result": "INVALIDE",
+            "reason": "reviewer_model n'est pas l'identité provider canonique Sol",
+        }
+    if "vendor" in verdict:
+        vendor = verdict.get("vendor")
+        if not isinstance(vendor, str) or _normalize(vendor) not in {
+            _normalize(_SOL_CANONICAL_ID),
+            _normalize(_SOL_CANONICAL_VENDOR),
+        }:
+            return {"result": "INVALIDE", "reason": "vendor du reviewer n'est pas Sol/openai"}
+
+    if not isinstance(codeurs, list) or not codeurs:
+        return {"result": "INVALIDE", "reason": "codeur requis pour sol_blind"}
+    codeur_table = _codeur_identity_table(include_retired=allow_retired_codeurs)
+    if codeur_table is None:
+        return {"result": "INVALIDE", "reason": "roster de codeurs introuvable"}
+    if not allow_retired_codeurs and _canonical_luna_member() is None:
+        return {
+            "result": "INVALIDE",
+            "reason": "identité active canonique luna_writer absente du roster",
+        }
+    resolved_codeurs = []
+    for codeur in codeurs:
+        if not isinstance(codeur, str):
+            return {"result": "INVALIDE", "reason": f"codeur invalide : {codeur!r}"}
+        codeur_key = _normalize(codeur)
+        if codeur_key not in codeur_table:
+            return {"result": "INVALIDE", "reason": f"codeur inconnu : {codeur}"}
+        resolved_codeurs.append(codeur_table[codeur_key])
+        if codeur_table[codeur_key] == _SOL_CANONICAL_ID:
+            return {"result": "INVALIDE", "reason": "le codeur ne peut pas être Sol"}
+    if not allow_retired_codeurs and (
+        len(resolved_codeurs) != 1 or resolved_codeurs[0] != _SOL_CANONICAL_CODEUR_ID
+    ):
+        return {
+            "result": "INVALIDE",
+            "reason": "le codeur Sol frais doit résoudre vers luna_writer",
+        }
+
+    for field in ("fresh_context", "blind", "reviewer_read_only"):
+        if verdict.get(field) is not True:
+            return {"result": "INVALIDE", "reason": f"{field} doit être true"}
+
+    if not isinstance(expected, dict):
+        return {"result": "INVALIDE", "reason": "métadonnées attendues invalides"}
+    expected_fields = (
+        "candidate_diff_digest", "diff_digest", "base_commit", "reviewed_head_commit",
+        "reviewed_head_tree", "prompt_sha256", "sdd_diff_digest", "mission_diff_digest",
+        "template_sha256",
+        "reviewed_at",
+    )
+    missing = [field for field in expected_fields if field not in expected]
+    if missing:
+        return {"result": "INVALIDE", "reason": f"métadonnées attendues absentes : {missing[0]}"}
+    try:
+        for field in ("base_commit", "reviewed_head_commit", "reviewed_head_tree"):
+            _validate_object_id(expected[field], field)
+        for field in (
+            "candidate_diff_digest", "diff_digest", "sdd_diff_digest", "mission_diff_digest",
+            "prompt_sha256",
+            "template_sha256",
+        ):
+            _validate_digest(expected[field], field)
+    except ValueError as error:
+        return {"result": "INVALIDE", "reason": str(error)}
+    if expected["candidate_diff_digest"] != expected["diff_digest"]:
+        return {"result": "INVALIDE", "reason": "diff_digest différent du diff attendu"}
+    expected_digest = expected["candidate_diff_digest"]
+    if verdict.get("candidate_diff_digest") != expected_digest:
+        return {"result": "INVALIDE", "reason": "candidate_diff_digest différent du diff attendu"}
+    try:
+        _validate_digest(verdict.get("candidate_diff_digest"), "candidate_diff_digest verdict")
+        for field in ("base_commit", "reviewed_head_commit", "reviewed_head_tree"):
+            _validate_object_id(verdict.get(field), f"{field} verdict")
+        for field in (
+            "prompt_sha256", "sdd_diff_digest", "mission_diff_digest", "template_sha256"
+        ):
+            _validate_digest(verdict.get(field), f"{field} verdict")
+    except ValueError as error:
+        return {"result": "INVALIDE", "reason": str(error)}
+    for field in (
+        "base_commit", "reviewed_head_commit", "reviewed_head_tree",
+        "prompt_sha256", "sdd_diff_digest", "mission_diff_digest", "template_sha256",
+    ):
+        if verdict.get(field) != expected[field]:
+            return {"result": "INVALIDE", "reason": f"{field} différent des métadonnées attendues"}
+    if verdict.get("reviewed_at") != expected["reviewed_at"]:
+        return {"result": "INVALIDE", "reason": "reviewed_at différent ou non frais"}
+    if _aware_timestamp(verdict.get("reviewed_at")) is None:
+        return {"result": "INVALIDE", "reason": "reviewed_at doit être un timestamp avec fuseau"}
+    if verdict.get("verdict") != "APPROVE":
+        return {"result": "REJECT", "reason": "verdict Sol différent de APPROVE"}
+    if verdict.get("blocking_findings") != []:
+        return {"result": "REJECT", "reason": "blocking_findings non vide"}
+    return {
+        "result": "APPROVE",
+        "reason": "Sol APPROVE sur le diff exact",
+        "vendors": ["openai"],
+        "reviewer_model": reviewer_model,
+        "prompt_sha256": expected["prompt_sha256"],
+        "sdd_diff_digest": expected["sdd_diff_digest"],
+        "mission_diff_digest": expected["mission_diff_digest"],
+        "template_sha256": expected["template_sha256"],
+        "reviewed_at": expected["reviewed_at"],
+        "blocking_findings": [],
+    }
+
+
 def tally(verdicts: list[dict]) -> dict:
     """Dépouillement déterministe. Retourne {result, reason, vendors, objections, prompt_sha256,
     bloquantes}. APPROVE ssi tous les verdicts sont APPROVE ET aucune objection bloquante."""
@@ -392,12 +1377,12 @@ def tally(verdicts: list[dict]) -> dict:
             "objections": objections, "bloquantes": bloquantes}
 
 
-def verifier_recu(
+def _verifier_recu_multi_vendor(
     recu: dict,
     verdicts: list[dict],
     etat_git: dict,
     *,
-    fenetre_heures_defaut: int = 24,
+    fenetre_heures_defaut: int | float = 24,
 ) -> dict:
     """Vérifie PUREMENT un reçu de revue (reviews/<ID>/RECU.json) contre son état git déjà
     résolu (aucun appel git ici — testable sans git réel, cf. `_etat_git_reel` pour
@@ -489,10 +1474,294 @@ def verifier_recu(
     }
 
 
+def _verifier_recu_sol_blind(
+    recu: dict,
+    verdicts: list[dict],
+    etat_git: dict,
+    *,
+    review_dir: Path | None = None,
+    runner: GitRunner | None = None,
+    fenetre_heures_defaut: int | float = 24,
+    now: datetime | None = None,
+) -> dict:
+    required = (
+        "schema", "mode", "story", "dossier", "issue", "round", "base_commit", "head_commit",
+        "head_tree", "diff_digest", "candidate_diff_digest", "reviewed_head_commit",
+        "reviewed_head_tree", "prompt_sha256", "sdd_diff_digest", "mission_diff_digest",
+        "template_sha256",
+        "reviewers_attendus",
+        "codeur", "resultat",
+        "reviewed_at", "verdict", "reviewer_model", "date_heure",
+        "fenetre_heures", "blocking_findings",
+    )
+    if not isinstance(recu, dict):
+        return {"result": "INVALIDE", "reason": "données absentes : reçu"}
+    for key in required:
+        if key not in recu:
+            return {"result": "INVALIDE", "reason": f"données absentes : {key}"}
+    if recu.get("schema") != "recu-revue/2":
+        return {"result": "INVALIDE", "reason": "schema Sol doit être exactement recu-revue/2"}
+    if recu.get("mode") != "sol_blind":
+        return {"result": "INVALIDE", "reason": "mode de reçu inconnu"}
+    if not isinstance(etat_git, dict):
+        return {"result": "INVALIDE", "reason": "état Git courant invalide"}
+    try:
+        _validate_sol_dossier(recu["dossier"])
+    except ValueError as error:
+        return {"result": "INVALIDE", "reason": str(error)}
+    try:
+        current_base = _validate_object_id(etat_git.get("base_commit"), "base_commit courant")
+        current_digest = _validate_digest(etat_git.get("diff_digest"), "diff_digest courant")
+        current_sdd_digest = _validate_digest(
+            etat_git.get("sdd_diff_digest"), "sdd_diff_digest courant"
+        )
+        current_mission_digest = _validate_digest(
+            etat_git.get("mission_diff_digest"), "mission_diff_digest courant"
+        )
+    except ValueError as error:
+        return {"result": "INVALIDE", "reason": str(error)}
+    if recu["base_commit"] != current_base:
+        return {"result": "INVALIDE", "reason": "reçu lié à un autre commit"}
+    if recu["diff_digest"] != current_digest:
+        return {"result": "INVALIDE", "reason": "diff modifié après revue"}
+    if recu["candidate_diff_digest"] != current_digest:
+        return {"result": "INVALIDE", "reason": "candidate_diff_digest différent du diff courant"}
+    if recu["sdd_diff_digest"] != current_sdd_digest:
+        return {"result": "INVALIDE", "reason": "sdd_diff_digest différent du journal SDD courant"}
+    if recu["mission_diff_digest"] != current_mission_digest:
+        return {"result": "INVALIDE", "reason": "mission_diff_digest différent du registre courant"}
+    try:
+        _validate_digest(recu["sdd_diff_digest"], "sdd_diff_digest")
+        _validate_digest(recu["mission_diff_digest"], "mission_diff_digest")
+        _validate_digest(recu["template_sha256"], "template_sha256")
+    except ValueError as error:
+        return {"result": "INVALIDE", "reason": str(error)}
+    try:
+        _validate_sol_freshness(
+            recu,
+            verdicts,
+            fenetre_heures_defaut=fenetre_heures_defaut,
+            now=now,
+        )
+    except ValueError as error:
+        return {"result": "INVALIDE", "reason": str(error)}
+    if review_dir is None:
+        return {"result": "INVALIDE", "reason": f"{_SOL_PROMPT_FILENAME} requis pour sol_blind"}
+    try:
+        _validate_sol_dossier(recu["dossier"], Path(review_dir))
+    except ValueError as error:
+        return {"result": "INVALIDE", "reason": str(error)}
+    try:
+        expected = _sol_expected_from_git(
+            recu, etat_git, Path(review_dir), verdicts, runner=runner
+        )
+    except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
+        return {"result": "INVALIDE", "reason": f"preuve Git/prompt Sol invalide : {error}"}
+    tally_result = tally_sol_blind(verdicts, expected=expected, codeurs=recu["codeur"])
+    if tally_result["result"] != "APPROVE":
+        return {"result": tally_result["result"], "reason": tally_result["reason"]}
+    if recu["prompt_sha256"] != tally_result.get("prompt_sha256"):
+        return {"result": "INVALIDE", "reason": "réponse contradictoire"}
+    if recu["template_sha256"] != tally_result.get("template_sha256"):
+        return {"result": "INVALIDE", "reason": "template_sha256 du reçu contradictoire"}
+    if recu["sdd_diff_digest"] != tally_result.get("sdd_diff_digest"):
+        return {"result": "INVALIDE", "reason": "sdd_diff_digest du reçu contradictoire"}
+    if recu["mission_diff_digest"] != tally_result.get("mission_diff_digest"):
+        return {"result": "INVALIDE", "reason": "mission_diff_digest du reçu contradictoire"}
+    if recu["resultat"] != tally_result["result"]:
+        return {"result": "INVALIDE", "reason": "réponse contradictoire"}
+    if recu["blocking_findings"] != []:
+        return {"result": "REJECT", "reason": "blocking_findings du reçu non vide"}
+    if recu["blocking_findings"] != verdicts[0].get("blocking_findings"):
+        return {
+            "result": "INVALIDE",
+            "reason": "blocking_findings du reçu différent du verdict Sol",
+        }
+    reviewers = recu["reviewers_attendus"]
+    if not isinstance(reviewers, list) or len(reviewers) != 1:
+        return {"result": "INVALIDE", "reason": "nombre incorrect de reviewers Sol"}
+    reviewer_model = verdicts[0].get("reviewer_model") if verdicts else None
+    if reviewers != [reviewer_model]:
+        return {"result": "INVALIDE", "reason": "identité reviewer contradictoire"}
+    if recu["reviewer_model"] != reviewer_model or recu["verdict"] != verdicts[0].get("verdict"):
+        return {"result": "INVALIDE", "reason": "verdict Sol contradictoire dans le reçu"}
+    return {
+        **tally_result,
+        "result": "APPROVE",
+        "reason": f"reçu Sol valide, lié au commit {etat_git.get('head_commit')}",
+    }
+
+
+def _validate_sol_archive_receipt(
+    recu: object,
+    execute: GitRunner,
+    *,
+    verdicts: list[dict] | None = None,
+    review_dir: Path | None = None,
+) -> None:
+    """Validate the immutable Sol receipt contract and exact archive object IDs."""
+    if not isinstance(recu, dict):
+        raise ValueError("reçu Sol archive invalide")
+    required = (
+        "schema", "mode", "story", "dossier", "issue", "round", "base_commit",
+        "head_commit", "head_tree", "candidate_diff_digest", "diff_digest",
+        "reviewed_head_commit", "reviewed_head_tree", "prompt_sha256",
+        "sdd_diff_digest", "mission_diff_digest", "template_sha256", "reviewers_attendus",
+        "codeur", "resultat",
+        "reviewed_at", "verdict",
+        "reviewer_model", "date_heure", "fenetre_heures", "blocking_findings",
+    )
+    for field in required:
+        if field not in recu:
+            raise ValueError(f"métadonnée Sol archive absente : {field}")
+    if recu.get("schema") != "recu-revue/2":
+        raise ValueError("schema Sol doit être exactement recu-revue/2")
+    if recu.get("mode") != "sol_blind":
+        raise ValueError("mode Sol archive invalide")
+    _validate_sol_story_id(recu["story"], recu.get("issue"))
+    _validate_sol_dossier(recu["dossier"], review_dir)
+    if _aware_timestamp(recu["date_heure"]) is None:
+        raise ValueError("date_heure Sol archive doit avoir un fuseau")
+    if _aware_timestamp(recu["reviewed_at"]) is None:
+        raise ValueError("reviewed_at Sol archive doit avoir un fuseau")
+    _sol_window_hours(recu["fenetre_heures"], 24)
+    if recu["resultat"] != "APPROVE":
+        raise ValueError("resultat Sol archive doit être APPROVE")
+    if recu["verdict"] != "APPROVE":
+        raise ValueError("verdict Sol archive doit être APPROVE")
+    if recu["blocking_findings"] != []:
+        raise ValueError("blocking_findings Sol archive doit être vide")
+    reviewers = recu["reviewers_attendus"]
+    if not isinstance(reviewers, list) or len(reviewers) != 1:
+        raise ValueError("reviewers_attendus Sol archive invalide")
+    if reviewers != [recu["reviewer_model"]]:
+        raise ValueError("reviewer_model Sol archive contradictoire")
+    if not isinstance(recu["codeur"], list) or not recu["codeur"]:
+        raise ValueError("codeur Sol archive requis")
+    if verdicts is not None:
+        if len(verdicts) != 1 or not isinstance(verdicts[0], dict):
+            raise ValueError("sol_blind exige exactement un verdict objet")
+        verdict = verdicts[0]
+        for field in (
+            "reviewer_model",
+            "verdict",
+            "blocking_findings",
+            "reviewed_at",
+            "sdd_diff_digest",
+            "mission_diff_digest",
+            "template_sha256",
+        ):
+            if recu[field] != verdict.get(field):
+                raise ValueError(f"{field} du reçu Sol archive contradictoire")
+        if review_dir is None:
+            raise ValueError("dossier de revue Sol archive requis")
+        expected = _sol_expected_from_git(
+            recu, None, Path(review_dir), verdicts, runner=execute
+        )
+        tally_result = tally_sol_blind(
+            verdicts,
+            expected=expected,
+            codeurs=recu["codeur"],
+            allow_retired_codeurs=True,
+        )
+        if tally_result["result"] != "APPROVE":
+            raise ValueError(
+                f"verdict Sol archive non conforme : {tally_result.get('reason', '')}"
+            )
+    for field in (
+        "base_commit", "head_commit", "head_tree", "reviewed_head_commit",
+        "reviewed_head_tree",
+    ):
+        _validate_object_id(recu.get(field), field)
+    for field in ("base_commit", "head_commit", "reviewed_head_commit"):
+        _resolve_commit(execute, recu[field])
+    for field in (
+        "candidate_diff_digest", "diff_digest", "sdd_diff_digest", "mission_diff_digest",
+        "prompt_sha256",
+        "template_sha256",
+    ):
+        _validate_digest(recu[field], field)
+    for commit_field, tree_field in (
+        ("head_commit", "head_tree"),
+        ("reviewed_head_commit", "reviewed_head_tree"),
+    ):
+        actual_tree = execute(
+            ["git", "rev-parse", "--verify", f"{recu[commit_field]}^{{tree}}"]
+        ).strip()
+        _validate_object_id(actual_tree, f"{commit_field} tree Git")
+        if actual_tree != recu[tree_field]:
+            raise ValueError(f"{tree_field} différent de l'arbre Git du commit")
+
+
+def verifier_recu(
+    recu: dict,
+    verdicts: list[dict],
+    etat_git: dict,
+    *,
+    fenetre_heures_defaut: int | float = 24,
+    review_dir: Path | None = None,
+    runner: GitRunner | None = None,
+    now: datetime | None = None,
+) -> dict:
+    """Dispatch le mode explicite; les reçus sans mode restent multi-vendor."""
+    if isinstance(recu, dict):
+        mode = recu.get("mode", "multi_vendor")
+        if mode == "sol_blind":
+            return _verifier_recu_sol_blind(
+                recu,
+                verdicts,
+                etat_git,
+                review_dir=review_dir,
+                runner=runner,
+                fenetre_heures_defaut=fenetre_heures_defaut,
+                now=now,
+            )
+        if mode not in ("multi_vendor", "sol_blind"):
+            return {"result": "INVALIDE", "reason": f"mode de reçu inconnu : {mode!r}"}
+    return _verifier_recu_multi_vendor(
+        recu, verdicts, etat_git, fenetre_heures_defaut=fenetre_heures_defaut
+    )
+
+
 def _cmd_prompt(args) -> int:
     artefact = Path(args.artefact).read_text(encoding="utf-8")
     criteres = Path(args.criteres).read_text(encoding="utf-8") if args.criteres else "(voir story)"
-    prompt, sha = build_prompt(args.story, criteres, args.artefact, artefact)
+    mode = getattr(args, "mode", "multi_vendor")
+    template_content = None
+    if mode == "sol_blind":
+        base_ref = getattr(args, "base_ref", None)
+        if not base_ref:
+            raise ValueError("--base-ref est obligatoire avec --mode sol_blind")
+        if not args.out or Path(args.out).name != _SOL_PROMPT_FILENAME:
+            raise ValueError(f"--out doit désigner {_SOL_PROMPT_FILENAME} en mode sol_blind")
+        head_ref = getattr(args, "head_ref", "HEAD")
+        git_state = _etat_git_reel(base_ref, head_ref)
+        frozen_base = _validate_object_id(git_state["base_commit"], "base_commit Git")
+        frozen_head = _validate_object_id(git_state["head_commit"], "head_commit Git")
+        canonical_artifact = _diff_artifact_canonique(frozen_base, frozen_head)
+        if artefact != canonical_artifact:
+            raise ValueError("artefact fourni différent du diff Git canonique")
+        artefact = canonical_artifact
+        base_ref = frozen_base
+        head_ref = frozen_head
+        _validate_sol_story_id(args.story)
+        criteres = _sol_criteria_from_git(_default_runner, frozen_head, args.story)
+        template_content = _git_blob(_default_runner, frozen_head, _SOL_TEMPLATE_PATH)
+        artefact_path = _SOL_ARTIFACT_PATH
+    else:
+        base_ref = None
+        head_ref = None
+        artefact_path = args.artefact
+    prompt, sha = build_prompt(
+        args.story,
+        criteres,
+        artefact_path,
+        artefact,
+        mode=mode,
+        base_ref=base_ref,
+        head_ref=head_ref,
+        template_content=template_content,
+    )
     if args.out:
         Path(args.out).write_text(prompt, encoding="utf-8")
     else:
@@ -516,24 +1785,93 @@ def _cmd_recu(args) -> int:
         json.loads(path.read_text(encoding="utf-8"))
         for path in sorted(dossier.glob("*.verdict.json"))
     ]
-    result = tally(verdicts)
     etat = _etat_git_reel(args.base_ref, args.head_ref)
-    recu = {
-        "schema": "recu-revue/1",
-        "dossier": args.dossier,
-        "issue": args.issue,
-        "round": args.round,
-        "replanned": getattr(args, "replanned", False),
-        **etat,
-        "prompt_sha256": result.get("prompt_sha256"),
-        "reviewers_attendus": [
-            v.get("vendor") or v.get("reviewer_model", "") for v in verdicts
-        ],
-        "codeur": args.codeur,
-        "resultat": result["result"],
-        "date_heure": datetime.now().astimezone().isoformat(),
-        "fenetre_heures": args.fenetre_heures,
-    }
+    mode = getattr(args, "mode", "multi_vendor")
+    if mode == "sol_blind":
+        template_sha256 = None
+        sdd_diff_digest = None
+        mission_diff_digest = None
+        story = getattr(args, "story", None)
+        if not isinstance(story, str) or not story.strip():
+            raise ValueError("--story est obligatoire avec --mode sol_blind")
+        _validate_sol_story_id(story, args.issue)
+        try:
+            canonical_prompt, prompt_sha = _canonical_sol_prompt(
+                story,
+                etat["base_commit"],
+                etat["head_commit"],
+            )
+            if _sol_prompt_bytes(dossier) != canonical_prompt:
+                raise ValueError(
+                    f"{_SOL_PROMPT_FILENAME} différent du prompt Sol canonique généré depuis Git"
+                )
+        except (OSError, ValueError, subprocess.CalledProcessError) as error:
+            prompt_sha = None
+            result = {"result": "INVALIDE", "reason": str(error)}
+        if len(verdicts) != 1:
+            result = {"result": "INVALIDE", "reason": "sol_blind exige exactement 1 verdict"}
+        elif prompt_sha is not None:
+            prompt_metadata = _sol_prompt_metadata(canonical_prompt)
+            template_sha256 = prompt_metadata["template_sha256"]
+            sdd_diff_digest = prompt_metadata["sdd_diff_digest"]
+            mission_diff_digest = prompt_metadata["mission_diff_digest"]
+            expected = {
+                **etat,
+                "candidate_diff_digest": etat["diff_digest"],
+                "reviewed_head_commit": etat["head_commit"],
+                "reviewed_head_tree": etat["head_tree"],
+                "prompt_sha256": prompt_sha,
+                "sdd_diff_digest": sdd_diff_digest,
+                "mission_diff_digest": mission_diff_digest,
+                "template_sha256": template_sha256,
+                "reviewed_at": verdicts[0].get("reviewed_at"),
+            }
+            result = tally_sol_blind(verdicts, expected=expected, codeurs=args.codeur)
+        reviewer = verdicts[0] if len(verdicts) == 1 else {}
+        recu = {
+            "schema": "recu-revue/2",
+            "mode": "sol_blind",
+            "story": story,
+            "dossier": args.dossier,
+            "issue": args.issue,
+            "round": args.round,
+            "replanned": getattr(args, "replanned", False),
+            **etat,
+            "candidate_diff_digest": etat["diff_digest"],
+            "reviewed_head_commit": etat["head_commit"],
+            "reviewed_head_tree": etat["head_tree"],
+            "prompt_sha256": result.get("prompt_sha256"),
+            "reviewers_attendus": [reviewer.get("reviewer_model", "")],
+            "codeur": args.codeur,
+            "resultat": result["result"],
+            "reviewed_at": reviewer.get("reviewed_at"),
+            "verdict": reviewer.get("verdict"),
+            "reviewer_model": reviewer.get("reviewer_model"),
+            "template_sha256": template_sha256,
+            "sdd_diff_digest": sdd_diff_digest,
+            "mission_diff_digest": mission_diff_digest,
+            "blocking_findings": reviewer.get("blocking_findings", []),
+            "date_heure": datetime.now().astimezone().isoformat(),
+            "fenetre_heures": args.fenetre_heures,
+        }
+    else:
+        result = tally(verdicts)
+        recu = {
+            "schema": "recu-revue/1",
+            "dossier": args.dossier,
+            "issue": args.issue,
+            "round": args.round,
+            "replanned": getattr(args, "replanned", False),
+            **etat,
+            "prompt_sha256": result.get("prompt_sha256"),
+            "reviewers_attendus": [
+                v.get("vendor") or v.get("reviewer_model", "") for v in verdicts
+            ],
+            "codeur": args.codeur,
+            "resultat": result["result"],
+            "date_heure": datetime.now().astimezone().isoformat(),
+            "fenetre_heures": args.fenetre_heures,
+        }
     content = json.dumps(recu, ensure_ascii=False, indent=2)
     if args.out:
         Path(args.out).write_text(content + "\n", encoding="utf-8")
@@ -556,6 +1894,9 @@ def main() -> None:
     pp.add_argument("--artefact", required=True)
     pp.add_argument("--story", required=True)
     pp.add_argument("--criteres", default=None)
+    pp.add_argument("--mode", choices=("multi_vendor", "sol_blind"), default="multi_vendor")
+    pp.add_argument("--base-ref", default=None)
+    pp.add_argument("--head-ref", default="HEAD")
     pp.add_argument("--out", default=None)
     pp.set_defaults(func=_cmd_prompt)
 
@@ -569,6 +1910,12 @@ def main() -> None:
     pr.add_argument("--head-ref", default="HEAD")
     pr.add_argument("--issue", required=True, type=int)
     pr.add_argument("--round", required=True, type=int)
+    pr.add_argument("--mode", choices=("multi_vendor", "sol_blind"), default="multi_vendor")
+    pr.add_argument(
+        "--story",
+        default=None,
+        help="identifiant immuable de la story pour --mode sol_blind",
+    )
     pr.add_argument("--replanned", action="store_true")
     # OBLIGATOIRE (≥1) : un --codeur silencieusement optionnel (défaut []) permettait de
     # contourner l'anti-auto-review par simple omission (revue scellée RC1-004-PR497,
diff --git stories/ORCH-LUNA-SOL-603.md stories/ORCH-LUNA-SOL-603.md
new file mode 100644
index 0000000000000000000000000000000000000000..4de7840e0e5e94261afd87f75be6080195b4af87
--- /dev/null
+++ stories/ORCH-LUNA-SOL-603.md
@@ -0,0 +1,28 @@
+# Story ORCH-LUNA-SOL-603 — contrat autonome Luna/Sol
+
+Status: IN_PROGRESS — phase compacte du contrat versionné; la preuve finale et
+la livraison documentaire complète restent dans une phase bornée ultérieure.
+
+## Contexte et périmètre
+
+Cette story fixe le contrat observable de la politique autonome Luna/Sol. Elle
+ne prétend aucune réussite runtime, matérielle, réseau ou externe. Le mode
+actif est `sol_blind`; le mode historique `multi_vendor` reste compatible pour
+les archives uniquement.
+
+## Critères d’acceptation
+
+- [x] La politique versionnée fixe GPT-5.6 Luna, exactement deux writer lanes,
+  GPT-5.6 Sol, le mode frais/aveugle/read-only et les états terminaux.
+- [x] Le dispatch de revue conserve le tally historique `multi_vendor` et
+  exige un unique reviewer Sol pour `sol_blind`.
+- [x] Le reçu Sol lie le diff Git, l’arbre, le prompt, les journaux exclus et
+  les limites de fraîcheur sans dépendre de la configuration locale de Git.
+- [ ] La documentation, les registres, les vues finales et la preuve Sol
+  finale sont scellés dans la phase de livraison bornée.
+
+## Limites
+
+Les paiements, secrets de production, suppressions définitives et engagements
+externes restent des décisions T3 humaines. Aucun workflow ne reçoit un droit
+d’écriture distant, ne force-push ou ne s’auto-écrit.
diff --git tests/test_rc1011_packs_md.py tests/test_rc1011_packs_md.py
index f9c99575fca4fc352f9a54328ffa00b4b0726cbd..e6a8fe2aa3ae222d62a228c7ab0feedad36f54e5 100644
--- tests/test_rc1011_packs_md.py
+++ tests/test_rc1011_packs_md.py
@@ -227,3 +227,21 @@ def test_main_retourne_1_si_defaut_non_connu(tmp_path, monkeypatch):
     monkeypatch.setattr(sys, "argv", ["check_md_packs.py", "--racine", str(tmp_path)])
     rc = check_md_packs.main()
     assert rc == 1
+
+
+def test_scanner_ignore_prompt_sol_genere_mais_scan_pack_voisin(tmp_path):
+    dossier = tmp_path / "evidence" / "reviews" / "S-sol"
+    dossier.mkdir(parents=True)
+    prompt = dossier / "SOL-PROMPT.md"
+    prompt.write_text("```diff\n+diff brut\n", encoding="utf-8")
+    pack = dossier / "pack.md"
+    pack.write_text("```diff\ndiff --git a b\n```\n", encoding="utf-8")
+    decoy = tmp_path / "not-a-review" / "SOL-PROMPT.md"
+    decoy.parent.mkdir(parents=True)
+    decoy.write_text("```diff\nnon canonique\n", encoding="utf-8")
+
+    resultats = check_md_packs.scanner(tmp_path)
+
+    assert str(prompt) not in resultats
+    assert resultats[str(pack)] == []
+    assert resultats[str(decoy)] == [{"regle": "R1", "ligne": 1}]
diff --git tests/test_reviews_gate.py tests/test_reviews_gate.py
index feb694a5d1580dcfb671d5ed3032b34865cb57b7..b6dc7e814851e8a47c1bd58e9bfe56bdeed0adb4 100644
--- tests/test_reviews_gate.py
+++ tests/test_reviews_gate.py
@@ -5,9 +5,11 @@ Réutilise le dépouillement déterministe (scripts/revue.py) via scripts/review
 """
 from __future__ import annotations
 
+import hashlib
 import importlib.util
 import json
 import subprocess
+from datetime import datetime
 from pathlib import Path
 
 REPO = Path(__file__).resolve().parent.parent
@@ -15,8 +17,11 @@ spec = importlib.util.spec_from_file_location("reviews_gate", REPO / "scripts" /
 gate = importlib.util.module_from_spec(spec)
 spec.loader.exec_module(gate)
 
-SHA = "a" * 64
+SOL_PROMPT_BYTES = b""
+SOL_SHA = ""
+SHA = hashlib.sha256(b"historical multi-vendor prompt\n").hexdigest()
 DATE = "2025-01-01T12:00:00+00:00"
+SOL_NOW = datetime.fromisoformat("2026-08-22T12:00:00+00:00")
 
 
 def _verdict(vendor, verdict="APPROVE"):
@@ -50,13 +55,45 @@ def _runner(command):
         return ""
     if command[:2] == ["git", "merge-base"]:
         return "b" * 40
+    if command[0] == "git" and "diff" in command and "--raw" in command:
+        return ""
+    if command[:8] == [
+        "git",
+        "-c",
+        "core.attributesFile=",
+        "-c",
+        "diff.orderFile=scripts/coordination/__init__.py",
+        "-c",
+        "diff.suppressBlankEmpty=false",
+        "diff",
+    ]:
+        return ""
+    if command[:3] == ["git", "rev-parse", "--verify"]:
+        ref = command[-1]
+        if ref.endswith("^{tree}"):
+            return "d" * 40
+        return ref[: -len("^{commit}")] if ref.endswith("^{commit}") else ref
     if command[:2] == ["git", "rev-parse"]:
         return ("d" * 40 if command[-1].endswith("^{tree}") else "c" * 40)
-    if command[:3] == ["git", "diff", "--raw"]:
+    if command[:2] == ["git", "diff"]:
         return ""
+    if command[:2] == ["git", "show"]:
+        if command[-1].endswith(gate._load_revue()._SOL_CANONICAL_STORY_ID):
+            return "# Story\n\n## Critères d’acceptation\n\n- [x] contrat\n\n## Limites\n"
+        return gate._load_revue().TEMPLATE.read_text(encoding="utf-8")
     raise AssertionError(command)
 
 
+SOL_PROMPT_BYTES, SOL_SHA = gate._load_revue()._canonical_sol_prompt(
+    gate._load_revue()._SOL_CANONICAL_STORY_ID, "b" * 40, "c" * 40, runner=_runner
+)
+SOL_TEMPLATE_SHA = hashlib.sha256(
+    gate._load_revue().TEMPLATE.read_bytes()
+).hexdigest()
+SOL_SDD_DIGEST = hashlib.sha256(b"").hexdigest()
+SOL_MISSION_DIGEST = hashlib.sha256(b"").hexdigest()
+
+
 def _receipt():
     return {
         "schema": "recu-revue/1",
@@ -67,7 +104,10 @@ def _receipt():
         "head_commit": "c" * 40,
         "head_tree": "d" * 40,
         "diff_digest": __import__("hashlib").sha256(b"").hexdigest(),
+        "sdd_diff_digest": SOL_SDD_DIGEST,
+        "mission_diff_digest": SOL_MISSION_DIGEST,
         "prompt_sha256": SHA,
+        "template_sha256": SOL_TEMPLATE_SHA,
         "reviewers_attendus": ["deepseek", "gemini_flash", "mimo"],
         "codeur": ["fable"],
         "resultat": "APPROVE",
@@ -76,6 +116,73 @@ def _receipt():
     }
 
 
+def _make_sol_blind_gate_review(
+    root: Path,
+    *,
+    include_receipt_blocking_findings: bool = True,
+    receipt_blocking_findings: list[dict] | None = None,
+) -> Path:
+    directory = _make_review(
+        root,
+        "S-sol",
+        [
+            {
+                "vendor": "sol",
+                "fresh_context": True,
+                "blind": True,
+                "reviewer_read_only": True,
+                "reviewer_model": "GPT-5.6-Sol",
+                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+                "diff_digest": hashlib.sha256(b"").hexdigest(),
+                "sdd_diff_digest": SOL_SDD_DIGEST,
+                "mission_diff_digest": SOL_MISSION_DIGEST,
+                "base_commit": "b" * 40,
+                "reviewed_head_commit": "c" * 40,
+                "reviewed_head_tree": "d" * 40,
+                "prompt_sha256": SOL_SHA,
+                "template_sha256": SOL_TEMPLATE_SHA,
+                "verdict": "APPROVE",
+                "blocking_findings": [],
+                "reviewed_at": "2026-08-22T12:00:00+00:00",
+            }
+        ],
+    )
+    (directory / "SOL-PROMPT.md").write_bytes(SOL_PROMPT_BYTES)
+    receipt = {
+        "schema": "recu-revue/2",
+        "mode": "sol_blind",
+        "story": gate._load_revue()._SOL_CANONICAL_STORY_ID,
+        "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+        "diff_digest": hashlib.sha256(b"").hexdigest(),
+        "sdd_diff_digest": SOL_SDD_DIGEST,
+        "mission_diff_digest": SOL_MISSION_DIGEST,
+        "base_commit": "b" * 40,
+        "head_commit": "c" * 40,
+        "head_tree": "d" * 40,
+        "reviewed_head_commit": "c" * 40,
+        "reviewed_head_tree": "d" * 40,
+        "prompt_sha256": SOL_SHA,
+        "template_sha256": SOL_TEMPLATE_SHA,
+        "dossier": "S-sol",
+        "issue": 603,
+        "round": 1,
+        "reviewers_attendus": ["GPT-5.6-Sol"],
+        "codeur": ["luna_writer"],
+        "resultat": "APPROVE",
+        "reviewed_at": "2026-08-22T12:00:00+00:00",
+        "verdict": "APPROVE",
+        "reviewer_model": "GPT-5.6-Sol",
+        "date_heure": "2026-08-22T12:00:00+00:00",
+        "fenetre_heures": 24,
+    }
+    if include_receipt_blocking_findings:
+        receipt["blocking_findings"] = (
+            [] if receipt_blocking_findings is None else receipt_blocking_findings
+        )
+    (directory / "RECU.json").write_text(json.dumps(receipt), encoding="utf-8")
+    return directory
+
+
 def test_gate_ok_si_toutes_approve(tmp_path):
     # RC1-010 (#440) lot 5d : reviews/ est intégralement migré vers evidence/reviews/ — le
     # repli bi-racine posé au lot 5a (une entrée liante pouvait vivre sous l'une OU l'autre
@@ -137,7 +244,7 @@ def test_mode_pr_echoue_sans_recu_couvrant(tmp_path):
     assert ok is False and any("aucun reçu ne couvre le changement courant" in line for line in report)
 
 
-def test_mode_pr_reussit_avec_recu_valide(tmp_path):
+def test_mode_pr_rejette_recu_multi_vendor_courant(tmp_path):
     root = tmp_path / "reviews"
     directory = _make_review(
         root, "S", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
@@ -150,7 +257,8 @@ def test_mode_pr_reussit_avec_recu_valide(tmp_path):
         base_ref="origin/main",
         runner=_runner,
     )
-    assert ok is True and any("reçu couvre le changement courant" in line for line in report)
+    assert ok is False
+    assert any("mode de politique requis" in line for line in report)
 
 
 def test_mode_pr_rejette_un_recu_dune_autre_issue(tmp_path):
@@ -167,7 +275,7 @@ def test_mode_pr_rejette_un_recu_dune_autre_issue(tmp_path):
         expected_issue=435,
         runner=_runner,
     )
-    assert ok is False and any("différent de la PR" in line for line in report)
+    assert ok is False and any("mode de politique requis" in line for line in report)
 
 
 def test_mode_archive_rejette_recu_commit_non_fusionne(tmp_path):
@@ -201,6 +309,31 @@ def test_mode_archive_recu_malforme_echoue_proprement(tmp_path):
     assert ok is False and any("reçu archive illisible" in line for line in report)
 
 
+def test_mode_archive_recu_sol_commit_absent_echoue_proprement(tmp_path):
+    root = tmp_path / "reviews"
+    directory = _make_sol_blind_gate_review(root)
+    receipt_path = directory / "RECU.json"
+    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
+    missing_commit = "f" * 40
+    receipt["head_commit"] = missing_commit
+    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
+
+    def missing_commit_runner(command):
+        if command[:2] == ["git", "rev-parse"] and missing_commit in command[-1]:
+            raise subprocess.CalledProcessError(128, command)
+        return _runner(command)
+
+    ok, report = gate.check(
+        _manifest(tmp_path, [directory.name]),
+        root,
+        mode="archive",
+        runner=missing_commit_runner,
+    )
+
+    assert ok is False
+    assert any("reçu archive illisible" in line for line in report)
+
+
 def test_mode_archive_accepte_recu_ancetre_valide(tmp_path):
     root = tmp_path / "reviews"
     directory = _make_review(
@@ -287,14 +420,21 @@ def test_mode_pr_ignore_recu_historique_non_couvrant(tmp_path):
     courante = _make_review(
         root, "S-courante", [_verdict("deepseek"), _verdict("gemini_flash"), _verdict("mimo")]
     )
-    (courante / "RECU.json").write_text(json.dumps(_receipt()), encoding="utf-8")
+    recu_courante_historique = _receipt()
+    recu_courante_historique["base_commit"] = "e" * 40
+    (courante / "RECU.json").write_text(
+        json.dumps(recu_courante_historique), encoding="utf-8"
+    )
+    current_sol = _make_sol_blind_gate_review(root)
 
     ok, report = gate.check(
-        _manifest(tmp_path, ["S-ancienne", "S-courante"]),
+        _manifest(tmp_path, ["S-ancienne", "S-courante", current_sol.name]),
         root,
         exiger_recu_courant=True,
         base_ref="origin/main",
+        expected_issue=603,
         runner=_runner,
+        now=SOL_NOW,
     )
 
     assert ok is True, report
@@ -302,6 +442,166 @@ def test_mode_pr_ignore_recu_historique_non_couvrant(tmp_path):
     assert not any("ECHEC S-ancienne" in line for line in report)
 
 
+def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
+    root = tmp_path / "reviews"
+    historical = _make_review(
+        root,
+        "S-ancienne-sol",
+        [
+            {
+                "vendor": "sol",
+                "fresh_context": True,
+                "blind": True,
+                "reviewer_read_only": True,
+                "reviewer_model": "GPT-5.6-Sol",
+                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+                "diff_digest": hashlib.sha256(b"").hexdigest(),
+                "base_commit": "a" * 40,
+                "sdd_diff_digest": SOL_SDD_DIGEST,
+                "mission_diff_digest": SOL_MISSION_DIGEST,
+                "reviewed_head_commit": "3" * 40,
+                "reviewed_head_tree": "d" * 40,
+                "prompt_sha256": SOL_SHA,
+                "template_sha256": SOL_TEMPLATE_SHA,
+                "verdict": "APPROVE",
+                "blocking_findings": [],
+                "reviewed_at": "2026-08-22T12:00:00+00:00",
+            }
+        ],
+    )
+    (historical / "SOL-PROMPT.md").write_bytes(SOL_PROMPT_BYTES)
+    (historical / "RECU.json").write_text(
+        json.dumps(
+            {
+                "schema": "recu-revue/2",
+                "mode": "sol_blind",
+                "story": gate._load_revue()._SOL_CANONICAL_STORY_ID,
+                "dossier": "S-ancienne-sol",
+                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+                "diff_digest": hashlib.sha256(b"").hexdigest(),
+                "base_commit": "a" * 40,
+                "sdd_diff_digest": SOL_SDD_DIGEST,
+                "mission_diff_digest": SOL_MISSION_DIGEST,
+                "head_commit": "c" * 40,
+                "head_tree": "d" * 40,
+                "reviewed_head_commit": "3" * 40,
+                "reviewed_head_tree": "d" * 40,
+                "prompt_sha256": SOL_SHA,
+                "template_sha256": SOL_TEMPLATE_SHA,
+                "issue": 603,
+                "round": 1,
+                "reviewers_attendus": ["GPT-5.6-Sol"],
+                "codeur": ["luna_writer"],
+                "resultat": "APPROVE",
+                "reviewed_at": "2026-08-22T12:00:00+00:00",
+                "verdict": "APPROVE",
+                "blocking_findings": [],
+                "reviewer_model": "GPT-5.6-Sol",
+                "date_heure": "2026-08-22T12:00:00+00:00",
+                "fenetre_heures": 24,
+            }
+        ),
+        encoding="utf-8",
+    )
+
+    current = _make_review(
+        root,
+        "S-courante-sol",
+        [
+            {
+                "vendor": "sol",
+                "fresh_context": True,
+                "blind": True,
+                "reviewer_read_only": True,
+                "reviewer_model": "GPT-5.6-Sol",
+                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+                "diff_digest": hashlib.sha256(b"").hexdigest(),
+                "base_commit": "b" * 40,
+                "reviewed_head_commit": "c" * 40,
+                "reviewed_head_tree": "d" * 40,
+                "prompt_sha256": SOL_SHA,
+                "sdd_diff_digest": SOL_SDD_DIGEST,
+                "mission_diff_digest": SOL_MISSION_DIGEST,
+                "template_sha256": SOL_TEMPLATE_SHA,
+                "verdict": "APPROVE",
+                "blocking_findings": [],
+                "reviewed_at": "2026-08-22T12:00:00+00:00",
+            }
+        ],
+    )
+    (current / "SOL-PROMPT.md").write_bytes(SOL_PROMPT_BYTES)
+    (current / "RECU.json").write_text(
+        json.dumps(
+            {
+                **_receipt(),
+                    "schema": "recu-revue/2",
+                    "mode": "sol_blind",
+                    "story": gate._load_revue()._SOL_CANONICAL_STORY_ID,
+                    "dossier": "S-courante-sol",
+                    "issue": 603,
+                "prompt_sha256": SOL_SHA,
+                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+                "reviewed_head_commit": "c" * 40,
+                "reviewed_head_tree": "d" * 40,
+                "reviewed_at": "2026-08-22T12:00:00+00:00",
+                "verdict": "APPROVE",
+                "blocking_findings": [],
+                "reviewer_model": "GPT-5.6-Sol",
+                "codeur": ["luna_writer"],
+                "reviewers_attendus": ["GPT-5.6-Sol"],
+                "date_heure": "2026-08-22T12:00:00+00:00",
+            }
+        ),
+        encoding="utf-8",
+    )
+
+    ok, report = gate.check(
+        _manifest(tmp_path, [historical.name, current.name]),
+        root,
+        exiger_recu_courant=True,
+        base_ref="origin/main",
+        expected_issue=603,
+        runner=_runner,
+        now=SOL_NOW,
+    )
+
+    assert ok is True, report
+    assert any("info  S-ancienne-sol" in line for line in report)
+    assert any("reçu couvre le changement courant" in line for line in report)
+
+
+def test_mode_pr_historical_sol_tampering_is_blocking_even_with_current_receipt(tmp_path):
+    root = tmp_path / "reviews"
+    current = _make_sol_blind_gate_review(root)
+    current.rename(root / "S-current-sol")
+    current_receipt_path = root / "S-current-sol" / "RECU.json"
+    current_receipt = json.loads(current_receipt_path.read_text(encoding="utf-8"))
+    current_receipt["dossier"] = "S-current-sol"
+    current_receipt_path.write_text(json.dumps(current_receipt), encoding="utf-8")
+
+    historical = _make_sol_blind_gate_review(root)
+    historical_receipt_path = historical / "RECU.json"
+    historical_receipt = json.loads(historical_receipt_path.read_text(encoding="utf-8"))
+    historical_receipt["dossier"] = historical.name
+    historical_receipt["base_commit"] = "a" * 40
+    historical_receipt["sdd_diff_digest"] = "0" * 64
+    historical_receipt_path.write_text(json.dumps(historical_receipt), encoding="utf-8")
+
+    ok, report = gate.check(
+        _manifest(tmp_path, [historical.name, "S-current-sol"]),
+        root,
+        exiger_recu_courant=True,
+        base_ref="origin/main",
+        expected_issue=603,
+        runner=_runner,
+        now=SOL_NOW,
+    )
+
+    assert ok is False
+    assert any("intrinsèquement invalide" in line for line in report)
+    assert any("S-current-sol : reçu couvre" in line for line in report)
+
+
 def test_mode_pr_recu_invalide_rapporte_raison(tmp_path):
     root = tmp_path / "reviews"
     directory = _make_review(
@@ -349,6 +649,61 @@ def test_defaut_sans_drapeau_comportement_inchange(tmp_path):
     assert ok is True and any("APPROVE" in line for line in report)
 
 
+def test_gate_dispatch_sol_blind_receipt_avec_un_seul_verdict(tmp_path):
+    root = tmp_path / "reviews"
+    _make_sol_blind_gate_review(root)
+
+    ok, report = gate.check(
+        _manifest(tmp_path, ["S-sol"]),
+        root,
+        exiger_recu_courant=True,
+        base_ref="origin/main",
+        runner=_runner,
+        now=SOL_NOW,
+    )
+
+    assert ok is True, report
+    assert not any("< 3" in line for line in report)
+    assert any("APPROVE" in line for line in report)
+
+
+def test_gate_dispatch_sol_blind_receipt_requires_blocking_findings(tmp_path):
+    root = tmp_path / "reviews"
+    _make_sol_blind_gate_review(root, include_receipt_blocking_findings=False)
+
+    ok, report = gate.check(
+        _manifest(tmp_path, ["S-sol"]),
+        root,
+        exiger_recu_courant=True,
+        base_ref="origin/main",
+        runner=_runner,
+        now=SOL_NOW,
+    )
+
+    assert ok is False
+    assert any("blocking_findings" in line for line in report)
+
+
+def test_gate_dispatch_sol_blind_receipt_rejects_non_empty_blocking_findings(tmp_path):
+    root = tmp_path / "reviews"
+    _make_sol_blind_gate_review(
+        root,
+        receipt_blocking_findings=[{"severity": "critical", "description": "unsafe"}],
+    )
+
+    ok, report = gate.check(
+        _manifest(tmp_path, ["S-sol"]),
+        root,
+        exiger_recu_courant=True,
+        base_ref="origin/main",
+        runner=_runner,
+        now=SOL_NOW,
+    )
+
+    assert ok is False
+    assert any("blocking_findings" in line for line in report)
+
+
 def test_manifeste_reel_du_depot_est_approve():
     ok, report = gate.check(
         REPO / "evidence" / "reviews" / "BINDING.txt", REPO / "evidence" / "reviews"
diff --git tests/test_revue.py tests/test_revue.py
index 314bfa6362c8cbf2e53dc625e4eeb8342edcc97e..e4bab12c03e63e303326d66ccd479b038ea95bb5 100644
--- tests/test_revue.py
+++ tests/test_revue.py
@@ -269,6 +269,38 @@ def test_diff_canonique_exclut_path_classification_json():
     )
 
 
+def test_diff_canonique_exclut_sdd_review_history():
+    code = ":100644 100644 a b M\0src/a.py\0"
+    reviewed = code + ":100644 100644 d e M\0.superpowers/sdd/old-review.md\0"
+    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
+        "base", "HEAD", runner=lambda _: reviewed
+    )
+
+
+def test_diff_sdd_canonique_lie_le_journal_exclu_separement():
+    code = ":100644 100644 a b M\0src/a.py\0"
+    reviewed = code + ":100644 100644 d e M\0.superpowers/sdd/old-review.md\0"
+    empty_sdd = revue._diff_sdd_canonique("base", "HEAD", runner=lambda _: code)
+    changed_sdd = revue._diff_sdd_canonique("base", "HEAD", runner=lambda _: reviewed)
+
+    assert empty_sdd != changed_sdd
+    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
+        "base", "HEAD", runner=lambda _: reviewed
+    )
+
+
+def test_diff_mission_canonique_lie_le_registre_exclu_separement():
+    code = ":100644 100644 a b M\0src/a.py\0"
+    reviewed = code + ":100644 100644 d e M\0evidence/registres/mission.jsonl\0"
+    empty_mission = revue._diff_mission_canonique("base", "HEAD", runner=lambda _: code)
+    changed_mission = revue._diff_mission_canonique("base", "HEAD", runner=lambda _: reviewed)
+
+    assert empty_mission != changed_mission
+    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
+        "base", "HEAD", runner=lambda _: reviewed
+    )
+
+
 def test_diff_canonique_exclut_path_classification_markdown():
     # Même motif que ci-dessus pour le rendu Markdown (les compteurs affichés varient pour la
     # même raison — sans cette exclusion, le cycle se rouvrirait via ce second fichier généré).
@@ -308,6 +340,99 @@ def test_diff_canonique_invoque_git_avec_no_abbrev():
     assert "--no-abbrev" in commandes_recues[0]
 
 
+def test_diff_artifact_sol_fige_la_configuration_git():
+    commandes_recues = []
+
+    revue._diff_artifact_canonique(
+        "base",
+        "HEAD",
+        runner=lambda commande: commandes_recues.append(commande) or "",
+    )
+    commande = commandes_recues[0]
+    assert commande[:8] == [
+        "git",
+        "-c",
+        "core.attributesFile=",
+        "-c",
+        "diff.orderFile=scripts/coordination/__init__.py",
+        "-c",
+        "diff.suppressBlankEmpty=false",
+        "diff",
+    ]
+    for option in (
+        "--no-textconv",
+        "--full-index",
+        "--diff-algorithm=myers",
+        "--no-indent-heuristic",
+        "--unified=3",
+        "--inter-hunk-context=0",
+        "--no-color",
+        "--no-prefix",
+        "--no-relative",
+    ):
+        assert option in commande
+
+
+def test_digests_sol_figent_la_configuration_git():
+    expected_prefix = [
+        "git",
+        "-c",
+        "core.attributesFile=",
+        "-c",
+        "diff.orderFile=scripts/coordination/__init__.py",
+        "-c",
+        "diff.suppressBlankEmpty=false",
+        "diff",
+    ]
+    for digest in (
+        revue._diff_canonique,
+        revue._diff_sdd_canonique,
+        revue._diff_mission_canonique,
+    ):
+        commands = []
+        digest("base", "HEAD", runner=lambda command: commands.append(command) or "")
+        assert commands[0][:8] == expected_prefix
+
+
+def test_sol_criteria_lit_la_section_de_la_story_figee():
+    story = "# Story\n\n## Critères d’acceptation\n\n- [x] contrat\n\n## Limites\n"
+
+    def runner(command):
+        assert command[:2] == ["git", "show"]
+        return story
+
+    criteria = revue._sol_criteria_from_git(
+        runner,
+        "b" * 40,
+        revue._SOL_CANONICAL_STORY_ID,
+    )
+    assert criteria == "- [x] contrat"
+
+
+def test_sol_issue_est_le_numero_de_pr_et_non_le_numero_de_story():
+    assert (
+        revue._validate_sol_story_id(revue._SOL_CANONICAL_STORY_ID, 607)
+        == revue._SOL_CANONICAL_STORY_ID
+    )
+    with pytest.raises(ValueError):
+        revue._validate_sol_story_id(revue._SOL_CANONICAL_STORY_ID, 0)
+
+
+def test_politique_sol_verifie_decision_et_frontieres_t3(tmp_path):
+    policy = revue.load_autonomy_policy()
+    policy["decision"] = "arbitrary"
+    path = tmp_path / "policy.json"
+    path.write_text(json.dumps(policy), encoding="utf-8")
+    with pytest.raises(ValueError, match="decision"):
+        revue.load_autonomy_policy(path)
+
+    policy = revue.load_autonomy_policy()
+    policy["t3_limits"] = []
+    path.write_text(json.dumps(policy), encoding="utf-8")
+    with pytest.raises(ValueError, match="t3_limits"):
+        revue.load_autonomy_policy(path)
+
+
 def test_verifier_recu_approve_nominal():
     result = revue.verifier_recu(_recu(), [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")], _etat())
     assert result["result"] == "APPROVE" and "reçu valide" in result["reason"]


MODE DE REVUE : sol_blind
MÉTADONNÉES GIT EXACTES (à recopier sans modification) :
{"base_commit": "d4d46ef36fcac3cdeb92a00577f78c8e698c17c0", "candidate_diff_digest": "475c66af11c5647bde41fa83895855dc3bc973f2e5b75d75ba7c16e8bddd49fa", "mission_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "reviewed_head_commit": "6211210a8e894164889249a05f59027bb8cece6e", "reviewed_head_tree": "e681251cb74e0a584901d93fd1a946e91066db26", "sdd_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137"}

Réponds STRICTEMENT avec un objet JSON valide, rien avant, rien après, conforme à ce
schéma :
{"base_commit": "d4d46ef36fcac3cdeb92a00577f78c8e698c17c0", "blind": true, "blocking_findings": [], "candidate_diff_digest": "475c66af11c5647bde41fa83895855dc3bc973f2e5b75d75ba7c16e8bddd49fa", "fresh_context": true, "mission_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "prompt_sha256": "sha256 du prompt reçu", "reviewed_at": "timestamp ISO-8601 avec fuseau", "reviewed_head_commit": "6211210a8e894164889249a05f59027bb8cece6e", "reviewed_head_tree": "e681251cb74e0a584901d93fd1a946e91066db26", "reviewer_model": "GPT-5.6-Sol", "reviewer_read_only": true, "sdd_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137", "verdict": "APPROVE ou REJECT"}