@AGENTS.md

# CLAUDE.md — ForgeAI Toolkit (adoption PROOF canonique 2026-07-16)
La constitution globale (~/.claude/CLAUDE.md) et les hooks git globaux peuvent compléter la
configuration locale, mais ils sont optionnels et informationnels pour ce dépôt.

## Clone propre : capacités toujours disponibles

Depuis un clone propre, les gates déterministes versionnés dans le dépôt restent reproductibles :
`no_stub_scan.py`, registres, authority-map, docs, metering-sites, catalogue, JavaScript, tests,
gitleaks, reviews-sealed et guard-fs-multi-os. Lancez
`python3 scripts/governance/capabilities.py` comme point d'entrée de diagnostic pour savoir
quelles capacités locales sont disponibles ; cet outil n'est pas un gate bloquant.

## Framework (rappel — actif globalement, rien à installer ici)

Superpowers est un plugin GLOBAL actif pour cette session (brainstorming → writing-plans →
subagent-driven → TDD). Les overrides PROOF s'appliquent : le skill `proof-review` REMPLACE la
self-review inline de Superpowers (hook `PreToolUse Agent|Task` bloque le « Senior Code Reviewer »),
et chaque subagent reçoit la discipline PROOF (hook `SubagentStart`). Complétion ⇒ skill `proof-done`.

## Réconciliation historique — mode `multi_vendor` (adoption pleine, décision Nathan)

Historical `multi_vendor` doctrine only: the legacy 3/3 review and merge statements below remain
unchanged. Ce bloc conserve le comportement historique uniquement pour les reçus
`multi_vendor`; le contrat actif `sol_blind` est distinct.


- **Livreur de revue** : la pièce qui manquait est fournie par le canon —
  `~/proof-method/scripts/civ_review.py`. Il livre le prompt byte-identique aux N reviewers,
  scelle les verdicts, et écrit désormais `prompt_sha256` + `reviewer_model` dans chaque verdict
  (garantie adoptée DE CE PROJET — le canon a absorbé ta vérification sha, méthodologie-as-code).
  → Le `tally`/`revue.py` STRICT du projet (qui exige prompt_sha256 + vendors distincts) accepte
  directement la sortie du livreur canonique. Plus de livraison manuelle, plus de dérive de sha.
- **Budget de sortie** : le livreur envoie max_tokens=16000 — fin des troncatures au cap 4096 qui
  faisaient « échouer » les reviewers verbeux (arbitrage Langfuse B-09, registre PROOF).
- **Roster** : reviewers = 3 vendors DISTINCTS ≠ vendor du codeur. Composer/Grok = CODEURS (xAI),
  jamais reviewers. Pool de swap route instable : Kimi-2.7 | MiMo-Pro-V2 | Qwen3.7-Max | GLM-OR.
  Le roster maintenu vit dans `manifests/roles.yaml`, donnée versionnée utilisée pour l'identité
  des vendors.

## Flux de revue externe optionnel

Le flux `civ_review.py` relève de l'outillage de gouvernance externe de Nathan : il est optionnel
pour la construction locale et ne conditionne aucun gate déterministe. Avant de l'utiliser, lancez
`python3 scripts/governance/capabilities.py` pour vérifier la présence de `~/proof-method`,
`LITELLM_API_KEY` et `LITELLM_BASE_URL` — le script ne révèle jamais la valeur d'un secret,
seulement sa présence. Exportez `LITELLM_API_KEY`/`LITELLM_BASE_URL` depuis votre propre gestion
de secrets, et `CIV_MODELS` (3 modèles de vendors distincts) avant d'invoquer `civ_review.py`.

```text
export LITELLM_BASE_URL=http://localhost:4000
export CIV_MODELS="DeepSeek-V4-Flash-0731,Qwen3.8-27B,gpt-daybreak-blue-latest"
PROOF_COMPRESS=0 bash ~/proof-method/scripts/pack_build.sh stories/<ID>.md /tmp/<ID>.diff /tmp/<ID>-pack.md
python3 ~/proof-method/scripts/civ_review.py --story evidence/reviews/<ID> --pack /tmp/<ID>-pack.md
python3 scripts/revue.py tally evidence/reviews/<ID>
```

## Contrat actif Luna/Sol — issue #603

La politique versionnée `governance/autonomy-policy.json` est la source de
vérité. Le roster actif est `luna_writer` / `GPT-5.6-Luna-Writer` pour l'écriture
(`GPT-5.6 Luna`) et `sol` / `GPT-5.6-Sol` pour la revue (`GPT-5.6 Sol`);
`GPT-5.6-Luna-Pro` est historique et
retiré. Le plafond est exactement `max_active_writer_lanes: 2`, donc exactement
deux writer lanes. Le mode est `sol_blind`: contexte frais, blind, read-only,
diff Git exact et identité Sol distincte du codeur.

La liaison minimale du reçu exige `story` (distinct du `dossier` d'artefacts),
`reviewer_model` exact `GPT-5.6-Sol`, `candidate_diff_digest`, `base_commit`,
`reviewed_head_commit`, `reviewed_head_tree`, `sdd_diff_digest`, `mission_diff_digest`, `prompt_sha256`, un `reviewed_at`
avec fuseau dans une fenêtre maximale de 24 heures, `verdict: APPROVE` et
`blocking_findings: []`. Le `dossier` doit correspondre au répertoire de revue
effectivement chargé.
Le reviewer ne reçoit aucun verdict attendu. Le claim est revérifié par le
gate contre Git courant; aucune preuve runtime ou externe n'est prétendue.
Les journaux `.superpowers/sdd/**` sont exclus de l’artefact aveugle pour ne pas
réinjecter d’anciens verdicts, mais restent liés par `sdd_diff_digest` et
`mission_diff_digest`.

In `reviews_gate.py`, receipt-mode dispatch preserves `multi_vendor`'s historical 3/3 tally; active
`sol_blind` requires exactly one `GPT-5.6-Sol` verdict.

Issue tracking may cover at most four disjoint issues, but it is subordinate to the policy: never
more than two active writer lanes.

Le merge sûr est repository-native : reprendre depuis l'issue/PR GitHub, l'état
Git et les registres vérifiés, exécuter les tests/gates, prolonger les registres
avec `scripts/registre.py append`, vérifier avec `scripts/registre.py verify`,
régénérer les vues, inspecter le diff et passer les hooks normaux. Aucun workflow
du contrat Luna/Sol ne doit utiliser `contents: write`, `force-push`, `decode`
de source embarquée ou un flux `self-writing`; les automatisations indépendantes
du dépôt restent hors de ce périmètre. Les seules sorties terminales sont
`DONE_WITH_EVIDENCE` et `BLOCKED_WITH_REASON`; les frontières T3 de Nathan
restent actives. Voir [la référence exécutable](Docs/reference/autonomy-luna-sol.md).
