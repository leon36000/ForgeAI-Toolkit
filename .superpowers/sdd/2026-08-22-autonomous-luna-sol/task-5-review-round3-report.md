# Task 5 review round 3 report — ORCH-LUNA-SOL-603

Parent reviewed: `dafeddd6c3edaa95cd93d231cb86bc4ee33efbc4`.

## Fresh Sol rejection

The fresh blind GPT-5.6-Sol review bound to candidate digest
`2abfeb2b15c4e5198ac0cf48a92850984c98068cb8d337a3ea5ffbbdc6e1008a` rejected three
remaining bypasses:

- the receipt-controlled freshness window had no upper bound;
- normalized Sol aliases such as `sol` or `GPT-5.6 Sol` were accepted instead of the exact
  provider ID `GPT-5.6-Sol` required by the response schema;
- `dossier` was required syntactically but was not type-checked or compared with the review
  directory actually used to read `SOL-PROMPT.md` and verdicts.

## Corrections

- Sol freshness windows now have a hard 24-hour maximum, including injected values;
- fresh Sol verdicts require the exact canonical provider identity `GPT-5.6-Sol`;
- receipt dossier names are simple directory identifiers and must match the loaded review
  directory in current and archive verification;
- regressions cover excessive windows, non-canonical reviewer aliases and dossier substitution;
- the reference, AGENTS, CLAUDE and design documents state the same invariants.

## Verification

- Focused Sol/review-gate suite: green, including all three new regressions.
- `python3 -m pytest -q`: 3046 collected, exit 0, 100% complete; existing declared skips only.
- Ruff changed-file check and `python3 scripts/ruff_noqa_gate.py`: OK.
- Authority/state/path generators were rerun after documentation and digest changes.
- `git diff --check`: clean.

No final Sol approval is claimed by this report. The coordinator must generate a new prompt from
the corrected final diff and obtain another fresh blind review.
