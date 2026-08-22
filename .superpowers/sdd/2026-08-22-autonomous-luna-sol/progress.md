# SDD ledger — plan: docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md

## Preflight

Workspace: `/home/pc1/Documents/Codex/2026-08-20/analyse-le-fichier-au-complet-et-4/work/ForgeAI-Toolkit-rc1-015`
Branch: `codex/issue-603-clean`
Base: `d4d46ef36fcac3cdeb92a00577f78c8e698c17c0`
Unsafe predecessor: PR #604, not executed and not copied.

The written spec is `docs/superpowers/specs/2026-08-22-autonomous-luna-sol-design.md`. The plan was self-reviewed for criterion coverage, type/name consistency, and prohibited placeholders; `git diff --check` passed before its design commit.

The first full baseline command, `python3 -m pytest -q`, was terminated with exit 143 by the environment after reaching approximately 9% without a reported assertion failure. This is recorded as partial baseline evidence, not as a product pass; focused tests and a later proportionate suite run remain required.

### Task-pair/interface scan

| Pair | Shared surface | Producer/consumer check | Ruling |
|---|---|---|---|
| Task 1 ↔ Task 2 | `manifests/roles.yaml`, policy identities | Task 1 produces resolvable Luna/Sol identities; Task 2 consumes them in fixtures. | Compatible; Task 2 must use the exact provider IDs from Task 1. |
| Task 1 ↔ Task 3 | policy lane cap and roster | Task 3 reads the policy/roster; Task 1 must retain historical aliases. | Compatible; no legacy identity deletion. |
| Task 1 ↔ Task 4 | authority source and decision record | Task 4 regenerates the authority map after Task 1 adds the source. | Compatible; generation is serialized after policy commit. |
| Task 2 ↔ Task 3 | `tally_sol_blind`, `verifier_recu`, gate dispatch | Task 2 defines observable failures; Task 3 implements only those public seams. | Compatible; historical `tally()` remains the default. |
| Task 2 ↔ Task 4 | test fixtures and documented contract | Task 4 extends contract assertions without changing the Sol oracle. | Compatible; prose must describe executable behavior only. |
| Task 3 ↔ Task 4 | `reviews_gate.py`, generated receipts | Task 3 provides mode-aware validation; Task 4 records and renders the result. | Compatible; no evidence is fabricated before final review. |
| Task 3 ↔ Task 5 | CLI mode, receipt schema, exact digest | Task 5 invokes the interfaces from Task 3 and binds the final receipt. | Compatible; receipt is generated only after final code diff is stable. |
| Task 4 ↔ Task 5 | `BINDING.txt`, story, ledgers | Task 4 documents the contract; Task 5 adds the binding proof. | Compatible; binding entry is last and must pass classification. |
| Task 5 ↔ Task 6 | PR disposition | Task 5 provides the clean replacement PR; Task 6 closes only #604. | Compatible; old branch remains for audit and is never executed. |

### Task self-consistency scan

| Task | Files and steps | Result |
|---|---|---|
| 1 | Policy tests precede policy/roster files; the public loader is the asserted seam. | Consistent. |
| 2 | In-memory verdict/receipt fixtures exercise exact binding, bypass rejection, and historical compatibility. | Consistent. |
| 3 | Implemented names match the interfaces consumed by Tasks 2 and 5; CLI mode is explicit. | Consistent. |
| 4 | Documentation, append-only ledgers, and existing generators are updated after behavior exists. | Consistent. |
| 5 | Final review evidence is created only from the stable code diff and then added to the binding manifest. | Consistent. |
| 6 | Only GitHub PR metadata is changed; no bootstrap source is copied or run. | Consistent. |

### Rulings

- Ruling: Treat issue #603's Nathan decision and the user's explicit carte blanche as approval of the design; this avoids an unnecessary pause while retaining the written spec and review gates. Cost if wrong: the design commit would need to be amended before further code changes.
- Ruling: Replace PR #604 with a normal repository-native implementation rather than repairing its self-writing workflow. The contents-write/force-push/decode path is a security-sensitive boundary outside the safe design. Cost if wrong: the old PR remains closed and a clean replacement carries the same functional intent.
- Ruling: Do not claim the killed full baseline passed. Use focused red/green evidence and rerun the broad suite after implementation, classifying any repeat termination separately. Cost if wrong: completion evidence may be less broad than the project's slowest baseline command.

### Task 1 review disposition

The Sol task review found four Important items. The review correctly identifies gaps in the eventual branch, but three are explicitly owned by later plan tasks rather than Task 1's contract slice:

- Public production policy validation and exact `sol_blind` prerequisite enforcement belong to Task 3 (`scripts/revue.py` / `scripts/reviews_gate.py`); carry them forward as load-bearing requirements.
- Registry entries, authority digests, and generated state/path views belong to Task 4; carry them forward and do not treat the stale intermediate view as final evidence.
- Fresh public-boundary review evidence belongs to Task 5; do not claim it from the Task 1 report.

Ruling: accept Task 1 as a scoped contract/roster commit, with the review findings carried into Tasks 3–5 rather than duplicating edits in this slice. This follows the plan's explicit file boundaries and preserves one owner per write surface. Cost if wrong: the later tasks must implement all carried requirements before the branch can be considered complete; no merge is allowed on this intermediate state.

Task 1: complete (commits e2799c3..360b9da, cross-task findings carried to Tasks 3–5)

Task 2: fix round 1/5 (3 findings addressed, 0 open; commits b071a22..48c96e7)
Task 2: fix round 2/5 (1 finding addressed, 0 open; commit 0d1b952)
Task 2: complete (commits 360b9da..0d1b952, review clean; intentional RED retained for Task 3)
Task 3: fix round 1 (all seven scoped blind-review findings addressed; focused verification green; Task 4 generated governance deliverables carried forward)
Task 3: fix round 2/5 (four independent Sol findings addressed; focused verifier/gate/policy/Ruff verification green; Task 4 generated governance deliverables carried forward; exact commit SHA in final handoff)
Task 3: fix round 3/5 (Sol archive ancestry now covers the exact reviewed head; focused archive/Sol/review-gate verification and Ruff green; Task 4 generated governance deliverables carried forward)
Task 3: complete (commits 4a6cfe1..454eed7; three scoped fix/review rounds; final Sol re-review clean; full-suite run deferred to Task 5)
Task 4: complete (DONE_WITH_EVIDENCE for the documentation/governance slice; policy contract, two-lane/no-write/restart/T3 prose, executable reference, story, append-only records, generated views and focused checks synchronized; final fresh Sol evidence remains Task 5; added narrowly scoped WORKING classification rules for the pre-existing tracked .superpowers/sdd and docs/superpowers paths required by classify_paths.py)
Task 4: fix1 complete (stale AGENTS and CLAUDE authority locators corrected and semantically tested; historical multi_vendor 3/3 doctrine explicitly scoped; active receipt-mode dispatch and exact-one-Sol contract documented and covered; story status split between completed Task 4 and pending Task 5; corrective mission seq 504, report and regenerated views verified; focused deterministic checks green; final fresh Sol evidence remains Task 5)
Task 4: fix2 complete (active four-issue tracking is explicitly subordinate to the exact two-lane policy; adversarial no-write/mode/status/policy/classification/authority tests are green; mission sequences 505-506, authority digest refresh, regenerated views and focused verification are complete; final fresh Sol evidence remains Task 5)
Task 4: fix3 complete (no-write authorization mutations are rejected across the full document; story status declarations are unique and terminal-safe; focused tests, Ruff and no-stub checks are green; final fresh Sol evidence remains Task 5)
Task 4: fix4 complete (authorization/action pairs are rejected in either word order across real documents; every singular terminal status/state declaration is rejected while terminal-state prose remains valid; focused and legacy revue tests, Ruff and no-stub checks are green; final fresh Sol evidence remains Task 5)
Task 4: fix5 complete (singular terminal status/state labels are detected with numeric, opaque, bold and list-formatted declarations; plural terminal-state prose and required story declarations remain valid; focused and legacy revue tests, Ruff and no-stub checks are green; final fresh Sol evidence remains Task 5)
Task 4: fix6 complete (singular terminal declarations are normalized across block quotes, headings, ordered/unordered/task lists, emphasis and inline code; all seven Markdown mutations are rejected while plural prose and the real story remain valid; focused and legacy revue tests, Ruff and no-stub checks are green; final fresh Sol evidence remains Task 5)
