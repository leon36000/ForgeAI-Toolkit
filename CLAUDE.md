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

## Réconciliation (adoption pleine, décision Nathan)

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
