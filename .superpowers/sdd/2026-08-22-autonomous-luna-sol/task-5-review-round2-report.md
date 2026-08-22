# Task 5 review round 2 report — ORCH-LUNA-SOL-603

Parent reviewed: `f4ebd882dc26022f1f40598d31a1b7303a244280`.

## Fresh Sol rejection

The fresh blind GPT-5.6-Sol review rejected three concrete contract gaps:

1. prompt generation used the story argument, while receipt reconstruction used the review
   directory name; a real `stories/ORCH-LUNA-SOL-603.md` prompt could not be reproduced from
   `evidence/reviews/ORCH-LUNA-SOL-603`;
2. archive-mode validation checked only Git object IDs and omitted the Sol receipt outcome,
   reviewer identity and `blocking_findings` consistency;
3. the retired `luna` / `GPT-5.6-Luna-Pro` roster identity was accepted as a fresh Sol-mode
   codewriter.

## Corrections

- `recu-revue/2` Sol receipts now require an immutable `story` field, the CLI accepts and emits
  `--story`, and prompt reconstruction uses that field while retaining `dossier` as the artifact
  directory.
- Archive validation now requires the complete Sol receipt contract, enforces APPROVE and an empty
  `blocking_findings` list, compares receipt fields with the single verdict, and receives the
  verdict list from `reviews_gate.py`. Historical archive checks may still resolve retired
  codewriters; fresh Sol checks do not.
- Fresh codewriter resolution excludes explicitly retired roster identities. A regression covers
  `luna` rejection while `luna_writer` remains accepted.
- Documentation and design text now describe the story/dossier distinction.

## Verification

- Focused Sol/review-gate suite: green, including the new story, archive-contract and retired-
  writer regressions.
- `python3 -m pytest -q`: 3042 collected, exit 0, 100% complete; existing declared skips only.
- `python3 -m ruff check` on changed Python files: OK.
- `python3 scripts/ruff_noqa_gate.py`: OK.
- `validate_authority.py --render`, `state_current.py --render` and `classify_paths.py --render`:
  synchronized after the documentation and authority digest changes.
- `git diff --check`: clean.

No final Sol approval is claimed by this report. The coordinator must regenerate the exact prompt
from the corrected final diff and obtain a new fresh blind review.
