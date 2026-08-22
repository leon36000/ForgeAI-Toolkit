# Task 5 review round 10 correction report — ORCH-LUNA-SOL-603

Parent reviewed: `99e809e3fa0c814d4467d1446ee31bbed4f9221b`.

## Fresh Sol rejection

The fresh blind `GPT-5.6-Sol` review found two evidence-boundary gaps:

- excluding `.superpowers/sdd/**` from the blind artifact and product digest
  left those coordination changes unbound by the receipt;
- a historical Sol receipt whose current binding no longer matched could cause
  reconstruction, prompt or tally failures to be downgraded to information,
  even when the receipt itself was intrinsically malformed or tampered with.

## Correction

- Added `_diff_sdd_canonique`, a deterministic separate SHA-256 over the raw
  excluded SDD Git changes. `sdd_diff_digest` is now present in prompt metadata,
  the strict verdict contract, current receipts, archive validation and current
  binding classification.
- Historical Sol entries are first validated as immutable archive receipts
  against their declared Git objects, stored prompt, template, SDD digest and
  verdict. Only a valid receipt that merely does not cover the current base or
  digest is informational; malformed historical evidence remains blocking.
- Added regressions for the separate SDD digest and for tampered historical
  evidence alongside a valid current receipt. Updated the executable reference,
  design, story, AGENTS and CLAUDE contracts.

## Verification

- `python3 -m pytest -q tests/test_autonomy_docs.py tests/test_autonomy_policy.py tests/test_revue.py tests/test_revue_sol_blind.py tests/test_revue_sol_round1.py tests/test_revue_sol_round2.py tests/test_reviews_gate.py`: exit 0.
- `python3 -m pytest -q`: 3069 tests collected, exit 0; existing declared skips only.
- `python3 scripts/no_stub_scan.py --all`: OK.
- `python3 scripts/ruff_noqa_gate.py`: OK.
- authority, state-current and path-classification checks: OK after official renders.
- `git diff --check`: clean.

No final Sol approval is claimed by this report; the coordinator must commit
this correction, regenerate the exact final prompt and obtain another fresh
blind review.
