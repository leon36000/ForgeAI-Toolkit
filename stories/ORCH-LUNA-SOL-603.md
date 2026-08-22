# Story ORCH-LUNA-SOL-603 — Contrat autonome Luna/Sol

Status: IN_PROGRESS — Task 4 documentation, ledgers and generated views are
being synchronized. No final runtime or external evidence is claimed.

Checkpoint: Task 4 records the active policy, safe repository-native merge
path, two writer lanes, `sol_blind` binding, restart source of truth, T3
boundary and terminal states. Final fresh Sol evidence remains a Task 5 gate.

## Contexte et périmètre

La politique canonique est
`governance/autonomy-policy.json`. GPT-5.6 Luna writes through the active
`luna_writer` identity; GPT-5.6 Sol reviews through the active `sol` identity.
The exact limit is two writer lanes. The historical Luna identity remains
resolvable only for historical receipts. This story changes governance prose,
the executable-contract reference, the ledgers and generated views; it does
not claim runtime, hardware, external-service or final review evidence.

## Critères d’acceptation

- [ ] `AGENTS.md` and `CLAUDE.md` name the policy source of truth, the active
  roster, exactly two writer lanes, the fresh blind read-only Sol contract,
  the safe merge path, the restart source of truth, the T3 boundary and the
  only terminal states.
- [ ] `Docs/reference/autonomy-luna-sol.md` lists the exact verdict/receipt
  binding fields, the two lanes, loop/resume behavior, no-write rule, safe
  merge gates, T3 boundary and verification commands.
- [ ] No workflow described by this story uses `contents: write`, `force-push`,
  `decode` of embedded source or a `self-writing` path.
- [ ] The decision and deliverable records are appended with
  `scripts/registre.py append`; `scripts/registre.py verify` reports intact
  append-only chains.
- [ ] `validate_authority.py --render`, `state_current.py --render` and
  `classify_paths.py --render` produce synchronized authority, state and path
  views without manually maintained generated hashes.
- [ ] Focused documentation/generator tests machine-check the required prose,
  paths and terminal states; no test treats an unverified claim as evidence.

## Evidence plan and status discipline

The Task 4 evidence is limited to repository files, append-only ledger output,
generated views and deterministic checks. The final Sol review, if obtained,
must use a fresh prompt over the exact final diff and be recorded separately.
The status rule is: no final runtime or external evidence is claimed.
Until every required check and final binding exists, the story cannot claim
`DONE_WITH_EVIDENCE`; if the work cannot safely proceed it must end as
`BLOCKED_WITH_REASON` with the concrete reason. These are the only terminal
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
