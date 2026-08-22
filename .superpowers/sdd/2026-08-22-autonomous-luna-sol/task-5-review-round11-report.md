# Task 5 review round 11 correction report — ORCH-LUNA-SOL-603

Parent reviewed: `0583b554758799f4df6baa2187703873123c7321`.

## Fresh Sol rejection

The fresh blind `GPT-5.6-Sol` review returned `REJECT`. It found that
`_sol_prompt_metadata` used the first global occurrence of the metadata marker
with `split(marker, 1)`. The canonical artifact itself can contain the
versioned `CANON/revue-template.md` diff, which includes that marker followed
by the literal `{metadata_json}` placeholder. As a result, `--mode sol_blind
recu` could parse the placeholder instead of the final generated JSON and
raise `ValueError` before producing the receipt.

The exact rejected prompt was bound to:

- `reviewed_head_commit`: `0583b554758799f4df6baa2187703873123c7321`
- `candidate_diff_digest`: `5f7950be5cd067928f2d4e9d0875a14510ba778e7562dfff7b2143225aa29d71`
- `sdd_diff_digest`: `082e19e1ed8a87eb952b37d02ffc7c40f581475d4456c84ea36e92b00f23fed0`
- `mission_diff_digest`: `96a20e4a3989f10bcb3853460f43c3785d46705059e0953135444b8b29dd556f`
- `prompt_sha256`: `bc53edb6494ad31f15300c3c82d1b095230ece41362e76058ad75ed0042e47e8`

## Correction

`_sol_prompt_metadata` now scans every marker occurrence, ignores malformed or
incomplete decoys, validates the complete metadata contract, and accepts
exactly one valid metadata object. Multiple valid candidates fail closed as
ambiguous. A regression reproduces the template-marker-inside-artifact case.

## Verification

- The new regression failed before the fix and passes after it.
- `python3 -m pytest -q tests/test_revue_sol_round2.py tests/test_revue_sol_blind.py tests/test_reviews_gate.py tests/test_revue.py`: exit 0.
- `python3 -m py_compile scripts/revue.py`: exit 0.

No final Sol approval is claimed by this report; the coordinator must commit
this correction, regenerate the exact final prompt and obtain another fresh
blind review.
