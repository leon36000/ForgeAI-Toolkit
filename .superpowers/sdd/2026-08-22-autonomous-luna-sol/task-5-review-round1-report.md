# Task 5 review round 1 report — ORCH-LUNA-SOL-603

Parent: `fad8980c8d6d69d9f1a38ba7efccca782550e568`.

## Finding and correction

The fresh blind Sol review rejected the receipt contract because
`_verifier_recu_sol_blind` did not require or validate receipt
`blocking_findings`. A `recu-revue/2` receipt could therefore omit the field,
or claim findings while the verdict and result were `APPROVE`.

- `scripts/revue.py` now requires `blocking_findings` in the Sol receipt,
  rejects a receipt value other than exactly `[]`, and compares the receipt
  value with the verdict value after the existing Sol tally.
- `scripts/revue.py::_cmd_recu` was inspected; its schema-2 producer already
  emits `blocking_findings` from the single verdict, defaulting to `[]` when
  constructing the receipt object.
- Direct verifier regressions cover a missing field and a non-empty,
  contradictory receipt field. Gate-path regressions cover both mutations and
  retain the valid `blocking_findings: []` fixture.
- `scripts/reviews_gate.py` has no behavior change.

## Verification scope

The focused Sol/review-gate tests pass: `46 passed` across
`tests/test_revue_sol_blind.py` and `tests/test_reviews_gate.py`.

The untracked final-evidence prompt/dossier was not inspected or modified.
No final evidence was regenerated in this round. The coordinator must
regenerate the prompt/digest and obtain fresh final Sol evidence after this
code commit; this report makes no external, runtime, or final Sol claim.
