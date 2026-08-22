# Task 5 review round 4 report — ORCH-LUNA-SOL-603

Parent reviewed: `ea87afe255a9c2e9ad343fd94062781d5430c0d3`.

## Fresh Sol rejection

A fresh blind `GPT-5.6-Sol` review rejected four bypasses in the current-review
contract:

- the current gate could still treat a valid receipt-controlled `multi_vendor`
  receipt as the current binding;
- `tally_sol_blind` did not require or compare the verdict's exact
  `template_sha256` metadata;
- fresh evidence accepted active codewriter identities other than
  `luna_writer`;
- the receipt-controlled `story` string was only non-empty, allowing an
  unrelated story or newline/instruction injection to be reconstructed.

## Corrections

- current-review gate coverage now requires the policy's `sol_blind` default;
  legacy `multi_vendor` remains available for historical/archive evidence;
- the versioned policy carries the immutable story ID
  `stories/ORCH-LUNA-SOL-603.md`, and receipt validation matches both story and
  issue against it;
- `tally_sol_blind` derives the versioned template digest from Git and requires
  the verdict to match it exactly;
- fresh codewriter resolution requires exactly the active `luna_writer`
  identity, while archive mode retains explicit historical compatibility;
- the Sol archive validator replays the strict tally against the stored prompt,
  verdict and Git metadata.

Focused regressions cover all four findings, including an injection-shaped story,
missing/tampered template metadata, non-Luna codewriters and a current legacy
receipt. Documentation, policy assertions and deterministic fixtures were
updated to describe the same contract.

No final Sol approval is claimed by this report. The coordinator must rerun all
checks, regenerate the exact final prompt and obtain another fresh blind review.
