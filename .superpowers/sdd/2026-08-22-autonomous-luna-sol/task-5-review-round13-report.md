# Task 5 review round 13 correction report — ORCH-LUNA-SOL-603

Parent reviewed: `a82d93dc3be1929e5a83cafc2d26bfe1f9d074d2`.

## Fresh Sol rejection

The fresh blind `GPT-5.6-Sol` review returned `REJECT`. It found that
`_validate_sol_archive_receipt` required `fenetre_heures` and `date_heure` but
did not validate their types or enforce the 24-hour maximum. A tampered
historical receipt with `fenetre_heures: 1000000` could therefore be treated as
an informational non-covering receipt after the current verifier failed,
allowing a gate with another valid current receipt to proceed.

The exact rejected prompt was bound to:

- `reviewed_head_commit`: `a82d93dc3be1929e5a83cafc2d26bfe1f9d074d2`
- `candidate_diff_digest`: `d3032ddede547c26daaf1d0bfc817b69a050441a5dd48b9af3978cda66b29a8b`
- `sdd_diff_digest`: `c67c0dbd3f9eaf3c81be3b5a54c3d489e3fe6ecae1ed760f3dcdb64dfaf224b5`
- `mission_diff_digest`: `a9d2277d3abee06d359c00a43c83f90e5a90c35536ee10a023e71aa9a6c4b486`
- `prompt_sha256`: `d4280921457ab0fa59e95d6d1da7c26a46c02bf330d79c51c47e71ee39447fa8`

## Correction

Archive validation now requires timezone-aware `date_heure` and `reviewed_at`
and invokes the same strict `_sol_window_hours` validator with the hard 24-hour
maximum. Historical receipts remain exempt from current-age expiry, but their
declared freshness contract can no longer be malformed.

## Verification

- The new archive-contract regressions failed before the fix and pass after it.
- `python3 -m pytest -q tests/test_revue_sol_round2.py tests/test_revue_sol_blind.py tests/test_reviews_gate.py tests/test_revue.py`: exit 0.
- `python3 -m pytest -q`: 3069 tests collected, exit 0; existing declared skips only.
- no-stub, noqa, authority, state-current, path-classification and registry checks: OK.

No final Sol approval is claimed by this report; the coordinator must commit
this correction, regenerate the exact final prompt and obtain another fresh
blind review.
