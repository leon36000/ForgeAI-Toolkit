@AGENTS.md

# CLAUDE.md — ForgeAI Toolkit (adoption PROOF canonique 2026-07-16)
La constitution globale (~/.claude/CLAUDE.md) et les hooks git globaux s'appliquent.
La méthode PROPRE de ce projet (AGENTS.md ci-dessus : §8bis no-stub, registre.py, revue scellée,
CLAIMS UNVERIFIED, T3=Nathan) est CONSERVÉE — elle est une instance PROOF mature, non remplacée.

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

## Flux de revue B-09 (et suivantes)
```
export LITELLM_BASE_URL=http://localhost:4000
export CIV_MODELS="DeepSeek-V4-Pro,Gemini-3.1-Pro,LongCat-2.0"
export LITELLM_API_KEY=$(docker inspect serveur-litellm --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^LITELLM_MASTER_KEY=//p')  # proof:allow — commande, pas un secret en clair
PROOF_COMPRESS=0 bash ~/proof-method/scripts/pack_build.sh stories/<ID>.md /tmp/<ID>.diff /tmp/<ID>-pack.md
python3 ~/proof-method/scripts/civ_review.py --story reviews/<ID> --pack /tmp/<ID>-pack.md
python3 scripts/revue.py tally reviews/<ID>   # ton dépouillement strict (sha + vendors) accepte la sortie
```
