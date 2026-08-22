# Task 3 fix round 2/5

Implemented the four independent Sol review fixes without expanding into Task 4 governance deliverables:

- Rebuild the Sol prompt from frozen exact Git object IDs and the versioned template; compare byte-for-byte against a regular non-symlink `SOL-PROMPT.md` and independently hash the stored bytes.
- Enforce aware current-PR freshness with an injectable clock, bounded skew, and finite nonnegative non-boolean windows; stale historical receipts remain informational.
- Require the exact active canonical Sol roster/policy identity and resolve codewriters to canonical roster IDs before applying the self-review rule.
- Require `recu-revue/2` for current and archive Sol receipts.

Verification:

```text
python3 -m pytest -q tests/test_revue_sol_round2.py tests/test_revue_sol_blind.py tests/test_revue_sol_round1.py tests/test_reviews_gate.py tests/test_autonomy_policy.py tests/test_revue.py
python3 -m ruff check scripts/revue.py scripts/reviews_gate.py tests/test_revue_sol_blind.py tests/test_revue_sol_round1.py tests/test_revue_sol_round2.py tests/test_reviews_gate.py tests/test_autonomy_policy.py tests/test_revue.py
git diff --check
```

All commands passed. The hanging full suite was intentionally not run. Task 4 registry/generated governance changes remain carried forward and untouched. The exact commit SHA is recorded in the implementation handoff.
