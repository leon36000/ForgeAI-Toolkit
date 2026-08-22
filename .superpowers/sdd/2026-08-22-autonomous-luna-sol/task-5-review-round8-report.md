# Task 5 review round 8 report — ORCH-LUNA-SOL-603

Parent reviewed: `a683a76810e3bc0febd318158a1b9be71af86792`.

## Fresh Sol rejection

The fresh blind `GPT-5.6-Sol` review found three blocking contract gaps:

- the current receipt did not retain `template_sha256`, so the gate could not
  bind the receipt itself to the versioned prompt template;
- declared `head_commit` and `reviewed_head_commit` were resolved, but their
  lineage to the current Git head was not required;
- `sol_blind` discarded the versioned template body and rebuilt the prompt from
  hard-coded Python strings, making the advertised template hash non-causal.

## Correction

The receipt schema and CLI now emit and verify `template_sha256` in both current
and archive paths. Declared review commits must resolve to their declared trees,
the reviewed commit must be an ancestor of the current head, and the declared
head must precede it on that lineage. `CANON/revue-template.md` now contains
explicit versioned `multi_vendor` and `sol_blind` sections; `build_prompt` selects
and renders the selected section, including the exact Sol metadata and response
schema, without reconstructing Sol prose in Python.

Focused Sol/gate/template tests, Ruff, noqa and `git diff --check` are green. No
final Sol approval is claimed; the coordinator must run the complete suite,
commit this correction, regenerate the exact prompt and obtain another fresh
blind review.
