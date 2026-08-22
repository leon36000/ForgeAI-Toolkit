# Task 3 — Fix round 1 report

## Result

All seven scoped Sol blind-review findings are addressed in the Task 3 slice.
The fix is limited to `scripts/revue.py`, `scripts/reviews_gate.py`, and focused
regressions. Registry and generated governance deliverables remain carried to
Task 4.

## Fixes

- Sol receipt expectations now validate exact hexadecimal Git objects and SHA-256
  values, hash the stored `SOL-PROMPT.md` bytes, take `reviewed_at` from the
  verdict, and compute the canonical base-to-reviewed-head diff through Git.
- Historical Sol receipts that do not bind to the current base/diff are reported
  informationally; only a validated current receipt sets `received_current`.
- Every codewriter is resolved through the roster and unknown identities fail
  closed. Exact Sol self-review remains forbidden; Luna/Sol same-vendor review is
  allowed.
- Sol prompt construction verifies the caller artifact against a diff generated
  from the same base/head refs and derives its Git metadata from those refs.
- `load_autonomy_policy` validates the versioned contract, exact two writer lanes,
  Sol mode/model, required literal booleans, and terminal states.
- Sol archive receipts require exact commit object IDs and Git-matching trees;
  symbolic refs are rejected.

## Verification

Focused red regressions were observed before implementation. Final targeted checks:

```text
python3 -m pytest -q tests/test_revue.py tests/test_revue_sol_blind.py tests/test_revue_sol_round1.py tests/test_autonomy_policy.py tests/test_reviews_gate.py tests/test_fix_audit_1_reviews_gate.py tests/test_fix_audit_1b_reviews_gate_in_process.py tests/test_orch_578_review_round_gate.py
........................................................................ [ 54%]
.............................................................            [100%]

python3 -m ruff check scripts/revue.py scripts/reviews_gate.py tests/test_revue_sol_blind.py tests/test_revue_sol_round1.py tests/test_autonomy_policy.py tests/test_reviews_gate.py
All checks passed!
```

`git diff --check` also passed. No full-suite run was attempted because the
repository ledger records the full suite as hanging/terminated in this
environment.
