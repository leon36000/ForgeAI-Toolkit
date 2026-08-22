# Story ORCH-LUNA-SOL-603 — Contrat autonome Luna/Sol

Status: IN_PROGRESS — overall story remains active. No final runtime or external
evidence is claimed.

Task 4 status: DONE_WITH_EVIDENCE — the repository documentation, ledgers,
generated views and deterministic checks for this slice are complete.

Task 5 status: PENDING — final fresh Sol evidence remains pending.

Checkpoint: Task 4 records the active policy, safe repository-native merge
path, `max_active_writer_lanes: 2` and exactly two writer lanes, `sol_blind`
binding, restart source of truth, T3 boundary and terminal states. Final fresh
Sol evidence remains a Task 5 gate.

## Contexte et périmètre

La politique canonique est
`governance/autonomy-policy.json`. GPT-5.6 Luna writes through the active
`luna_writer` identity; GPT-5.6 Sol reviews through the active `sol` identity.
The exact limit is two writer lanes. The historical Luna identity remains
resolvable only for historical receipts. This story changes governance prose,
the executable-contract reference, the ledgers and generated views; it does
not claim runtime, hardware, external-service or final review evidence.
The active policy binds fresh Sol receipts to the immutable story identifier
`stories/ORCH-LUNA-SOL-603.md`, the exact `luna_writer` codewriter identity and
the versioned prompt `template_sha256`; a current PR cannot be covered by a
legacy `multi_vendor` receipt.

## Critères d’acceptation

- [x] `AGENTS.md` and `CLAUDE.md` name the policy source of truth, the active
  roster, exactly two writer lanes, the fresh blind read-only Sol contract,
  the safe merge path, the restart source of truth, the T3 boundary and the
  only terminal states.
- [x] `Docs/reference/autonomy-luna-sol.md` lists the exact verdict/receipt
  binding fields, including `template_sha256`, immutable story binding and
  active `luna_writer` codewriter, the two lanes, loop/resume behavior,
  no-write rule, safe merge gates, T3 boundary and verification commands.
- [x] No workflow described by this story uses `contents: write`, `force-push`,
  `decode` of embedded source or a `self-writing` path.
- [x] The decision and deliverable records are appended with
  `scripts/registre.py append`; `scripts/registre.py verify` reports intact
  append-only chains.
- [x] `validate_authority.py --render`, `state_current.py --render` and
  `classify_paths.py --render` produce synchronized authority, state and path
  views without manually maintained generated hashes.
- [x] Focused documentation/generator tests machine-check the required prose,
  paths and terminal states; no test treats an unverified claim as evidence.
- [ ] Task 5 obtains and binds one fresh final `sol_blind` verdict over the
  exact final diff, or records a concrete `BLOCKED_WITH_REASON`.

## Evidence plan and status discipline

The Task 4 evidence is limited to repository files, append-only ledger output,
generated views and deterministic checks. The final Sol review, if obtained,
must use a fresh prompt over the exact final diff and be recorded separately.
The status rule is: no final runtime or external evidence is claimed. Task 4
may be `DONE_WITH_EVIDENCE` only for this bounded repository/documentation
slice. The overall story remains `IN_PROGRESS` while Task 5's final binding is
pending; Task 5 may terminate only as `DONE_WITH_EVIDENCE` or
`BLOCKED_WITH_REASON` with a concrete reason. These are the only terminal
states.

## Safe verification path

```text
python3 -m pytest -q tests/test_autonomy_docs.py tests/test_autonomy_policy.py tests/test_revue_sol_blind.py tests/test_reviews_gate.py
python3 scripts/registre.py verify governance/vision-log.jsonl evidence/registres/mission.jsonl
python3 scripts/governance/validate_authority.py
python3 scripts/governance/state_current.py
python3 scripts/governance/classify_paths.py
git diff --check
```
