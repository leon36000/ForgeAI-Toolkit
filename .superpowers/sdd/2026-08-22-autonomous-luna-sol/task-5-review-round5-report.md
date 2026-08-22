# Task 5 review round 5 report — ORCH-LUNA-SOL-603

Parent reviewed: `343058c8b16190a988a99f45545617af165f5f4f`.

## Fresh Sol rejection

The fresh blind `GPT-5.6-Sol` review found two documentation/scanner boundary
issues:

- `check_md_packs.py` skipped every file named `SOL-PROMPT.md`, not only the
  generated prompt in the canonical `evidence/reviews/<dossier>/` location;
- the active decision record still described `multi_vendor` as the default,
  contradicting the policy and current-PR gate, whose active default is
  `sol_blind`.

## Corrections

- scanner exclusion is now structural and path-bound to
  `evidence/reviews/<dossier>/SOL-PROMPT.md`; a same-named Markdown pack
  elsewhere is scanned, with a regression fixture proving the distinction;
- the decision record now states `sol_blind` as the current-PR policy default
  and limits `multi_vendor` to historical/archive compatibility;
- the design and documentation tests assert that authority wording remains
  synchronized with the policy default and historical scope.

Focused scanner, documentation, policy, Sol and gate tests, Ruff, noqa and
`git diff --check` are green. No final Sol approval is claimed by this report;
the coordinator must regenerate the exact prompt after committing these fixes
and obtain another fresh blind review.
