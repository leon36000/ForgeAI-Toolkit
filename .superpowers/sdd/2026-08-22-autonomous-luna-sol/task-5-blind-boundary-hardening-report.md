# Task 5 blind-boundary hardening report — ORCH-LUNA-SOL-603

## Finding before the next fresh review

The candidate artifact audit found that `evidence/registres/mission.jsonl`
still exposed prior review-round conclusions even after the SDD ledger was
excluded. That append-only registry is useful coordination evidence but is not
part of the product change Sol must read blindly.

## Correction

`evidence/registres/**` is now excluded from the Sol artifact and product
digest. Its raw Git state is bound by the independent `mission_diff_digest`,
which is required in prompt metadata, verdicts, current receipts, archive
validation and current binding classification. A regression proves that the
mission digest changes while the product digest remains stable. Documentation
now describes both excluded audit boundaries.

## Verification

The focused documentation, revue, Sol and gate suite passes. Governance
renders and registry verification pass. The full `python3 -m pytest -q`
suite was then run on this final hardening tree before sealing the commit:
exit 0, with 3069 tests collected. A fresh Sol review remains required.
