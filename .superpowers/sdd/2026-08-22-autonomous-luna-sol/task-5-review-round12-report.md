# Task 5 review round 12 correction report — ORCH-LUNA-SOL-603

Parent reviewed: `51aa02bd44ca6880a4e6e1746684852d69d6e684`.

## Fresh Sol rejection

The fresh blind `GPT-5.6-Sol` review returned `REJECT`. It found that the
freshness check added `_SOL_CLOCK_SKEW` to the configured freshness window:
with `fenetre_heures: 24`, a receipt could therefore remain acceptable for up
to 24 hours and 5 minutes, contrary to the explicit 24-hour maximum.

The exact rejected prompt was bound to:

- `reviewed_head_commit`: `51aa02bd44ca6880a4e6e1746684852d69d6e684`
- `candidate_diff_digest`: `f61c89392dfad82794b860f609000cda624679395cb96c9b90949adbe2d33382`
- `sdd_diff_digest`: `981d9b30597e7b46d68319b0ed20b8367d977f6e30d74ba4b04b21e18dba8324`
- `mission_diff_digest`: `7e912187e5927bbcd408867584b83dcb76e7d945a050a2b779be3251d778d20d`
- `prompt_sha256`: `3fd1897b119c999c54fb745225daf9a93429a1606d3ad0ec698a5465dfe5e6b9`

## Correction

The clock skew remains limited to future-timestamp tolerance only. Freshness
now compares the receipt age directly against the configured window, so a
receipt one second beyond 24 hours is rejected. A regression covers exactly
that boundary.

## Verification

- The new boundary regression failed before the fix and passes after it.
- `python3 -m pytest -q tests/test_revue_sol_round2.py tests/test_revue_sol_blind.py tests/test_reviews_gate.py tests/test_revue.py`: exit 0.
- `python3 -m pytest -q`: 3069 tests collected, exit 0; existing declared skips only.
- no-stub, noqa, authority, state-current, path-classification and registry checks: OK.

No final Sol approval is claimed by this report; the coordinator must commit
this correction, regenerate the exact final prompt and obtain another fresh
blind review.
