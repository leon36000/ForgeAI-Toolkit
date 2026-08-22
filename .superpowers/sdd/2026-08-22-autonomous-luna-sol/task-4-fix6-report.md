# Task 4 fix6 report — ORCH-LUNA-SOL-603

Parent: `e14c2ef03dd12677c263caeb6547e989742d72aa`.

Scope: close the final Markdown status-parser bypasses without changing the
active documents, legacy review behavior or claiming runtime, external-service,
hardware or final Sol evidence. The overall story remains `IN_PROGRESS`; Task
4's bounded repository slice may be `DONE_WITH_EVIDENCE`, while Task 5 final
fresh Sol evidence stays pending.

## Corrections

- `_normalize_status_line` now consumes common Markdown block quotes,
  headings, ordered/unordered/task-list prefixes, emphasis and backticks before
  singular status-label detection. Numeric, opaque, emphasis, quote, heading,
  ordered-list, task-list and inline-code mutations are rejected.
- `_assert_story_status` still requires exactly one overall `IN_PROGRESS`,
  Task 4 `DONE_WITH_EVIDENCE` and Task 5 `PENDING`; plural terminal-state
  contract prose and the real story remain valid.
- `scripts/reviews_gate.py` has no fix6 diff or behavior change; its prior
  receipt-dispatch comment remains covered by the focused tests.
- The corrective mission record is appended only through
  `scripts/registre.py append`; generated views remain generator-owned.

## Verification record

The bounded fix6 verification is green:

- Focused documentation/policy/Sol/review plus legacy revue tests: `118
  passed` across `tests/test_autonomy_docs.py`,
  `tests/test_autonomy_policy.py`, `tests/test_revue_sol_blind.py`,
  `tests/test_reviews_gate.py` and `tests/test_revue.py`.
- Ruff on `scripts/reviews_gate.py` and `tests/test_autonomy_docs.py`: PASS.
- `scripts/no_stub_scan.py --all`: PASS, 400 files scanned, zero violations.
- Authority/state/path generators and their no-render checks, both
  append-only registry chains and `git diff --check` are recorded in the final
  handoff after the fix6 ledger is appended.
- The full suite is intentionally not run.
