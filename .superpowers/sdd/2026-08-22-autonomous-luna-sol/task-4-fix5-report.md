# Task 4 fix5 report — ORCH-LUNA-SOL-603

Parent: `349fcccc536da61c4c4f35607296fbca063e57f0`.

Scope: close the final Sol parser gap without changing the active documents,
legacy review behavior or claiming runtime, external-service, hardware or
final Sol evidence. The overall story remains `IN_PROGRESS`; Task 4's bounded
repository slice may be `DONE_WITH_EVIDENCE`, while Task 5 final fresh Sol
evidence stays pending.

## Corrections

- `STATUS_DECLARATION_RE` now detects singular `Terminal status:` and
  `Terminal state:` labels independently of value syntax, while accepting
  common Markdown emphasis and list prefixes. Numeric, opaque, bold and list
  mutations are rejected before terminal-value classification.
- `_assert_story_status` continues to require exactly one overall
  `IN_PROGRESS`, Task 4 `DONE_WITH_EVIDENCE` and Task 5 `PENDING`; plural
  terminal-state contract prose and the real story remain valid.
- `scripts/reviews_gate.py` has no fix5 diff or behavior change; its prior
  receipt-dispatch comment remains covered by the focused tests.
- The corrective mission record is appended only through
  `scripts/registre.py append`; generated views remain generator-owned.

## Verification record

The bounded fix5 verification is green:

- Focused documentation/policy/Sol/review plus legacy revue tests: `118
  passed` across `tests/test_autonomy_docs.py`,
  `tests/test_autonomy_policy.py`, `tests/test_revue_sol_blind.py`,
  `tests/test_reviews_gate.py` and `tests/test_revue.py`.
- Ruff on `scripts/reviews_gate.py` and `tests/test_autonomy_docs.py`: PASS.
- `scripts/no_stub_scan.py --all`: PASS, 400 files scanned, zero violations.
- Authority/state/path generators and their no-render checks, both
  append-only registry chains and `git diff --check` are recorded in the final
  handoff after the fix5 ledger is appended.
- The full suite is intentionally not run.
