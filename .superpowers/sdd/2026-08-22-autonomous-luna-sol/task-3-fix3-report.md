# Task 3 fix round 3/5

Fixed the independent Sol archive-binding finding. Archive validation still checks the receipt's
`head_commit` for ancestry and now also requires the exact Sol `reviewed_head_commit` to be an
ancestor of the archive/current `HEAD`. The existing exact object/tree/diff validation remains in
force, and legacy receipts retain their previous ancestry behavior.

Added a regression where `head_commit` is an ancestor but `reviewed_head_commit` is not; archive
validation now fails with an explicit `reviewed_head_commit` diagnostic.

Verification:

```text
python3 -m pytest -q tests/test_reviews_gate.py tests/test_revue_sol_blind.py tests/test_revue_sol_round1.py tests/test_revue_sol_round2.py
ruff check scripts/reviews_gate.py tests/test_revue_sol_round1.py
git diff --check
```

All commands passed. The full suite was intentionally not run. Task 4 registry/generated
governance deliverables remain carried forward and untouched. The exact commit SHA is recorded in
the implementation handoff.
