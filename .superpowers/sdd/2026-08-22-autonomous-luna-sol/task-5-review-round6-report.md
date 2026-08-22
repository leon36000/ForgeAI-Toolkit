# Task 5 review round 6 report — ORCH-LUNA-SOL-603

Parent reviewed: `941bfce53b75a09e733abd044ceb16e0c5d50272`.

## Fresh Sol rejection

The fresh blind `GPT-5.6-Sol` review found one high-severity roster
canonicalization gap: fresh `luna_writer` evidence was accepted from the member
ID alone. A malformed, disabled, duplicated or substituted roster record could
therefore satisfy the fresh tally.

## Correction

Fresh `sol_blind` tallying now requires the unique canonical active Luna writer
record: ID `luna_writer`, model `GPT-5.6 Luna`, vendor `openai`, provider ID
`GPT-5.6-Luna-Writer` and status `actif`. Archive mode retains its explicit
historical compatibility. Regression tests cover every field mutation and a
duplicate ID; the reference, design and story state the same invariant.

Focused Sol/gate/policy/documentation tests, Ruff, noqa and `git diff --check`
are green. No final Sol approval is claimed; the coordinator must regenerate
the exact final prompt after committing this fix and obtain another fresh blind
review.
