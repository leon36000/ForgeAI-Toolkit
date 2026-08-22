# Autonomous Luna/Sol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement issue #603 as a safe, repository-native `sol_blind` review mode with a machine-readable two-writer limit and no self-writing CI bootstrap.

**Architecture:** Keep the existing multi-vendor `revue.py` tally and receipt format compatible for historical evidence. Add a strict single-reviewer `sol_blind` path that binds a fresh Sol verdict to the canonical Git diff, and make `reviews_gate.py` dispatch from the receipt mode before applying the existing current-PR and archive checks.

**Tech Stack:** Python 3.10–3.13, pytest, JSON/YAML repository manifests, Git raw-diff hashing, existing governance generators, GitHub Actions read-only validation.

**Spec:** `Docs/superpowers/specs/2026-08-22-autonomous-luna-sol-design.md`

## Global Constraints

- Preserve historical multi-vendor receipts and the default `tally()` behavior.
- `max_active_writer_lanes` is exactly `2`; lane values outside `1..2` are rejected.
- `sol_blind` requires a recognized GPT-5.6 Sol identity, fresh context, blind prompt, read-only review, exact diff digest, and zero blocking findings.
- The codewriter cannot be the Sol reviewer, even when both identities resolve to the same vendor.
- No workflow in the PR may write repository contents, force-push, decode embedded source, or mutate itself.
- No secret, runtime/backend, hardware probe, external ruleset, or public release change is in scope.
- Every committed deliverable receives a registry entry and regenerated authority/state/path views.

### Task 1: Version the autonomy contract and update the roster

**Files:**
- Create: `governance/autonomy-policy.json`
- Create: `governance/decisions/D-2026-08-21-autonomie-luna-sol.md`
- Modify: `manifests/roles.yaml`
- Modify: `governance/authority.json`
- Test: `tests/test_autonomy_policy.py`

**Interfaces:**
- `tests/test_autonomy_policy.py` loads `governance/autonomy-policy.json` and asserts literal policy values.
- `scripts/revue.py` resolves `GPT-5.6-Luna-Pro` and `GPT-5.6-Sol` through `manifests/roles.yaml`.

- [ ] **Step 1: Write failing policy tests**

  Add tests that load the JSON policy and assert `worker.primary_model == "GPT-5.6 Luna"`, `worker.max_active_writer_lanes == 2`, `review.default_mode == "sol_blind"`, `review.reviewer_model == "GPT-5.6 Sol"`, and terminal states exactly equal `{"DONE_WITH_EVIDENCE", "BLOCKED_WITH_REASON"}`. Add a test that rejects a policy copy with `max_active_writer_lanes == 3` through the public loader.

- [ ] **Step 2: Run the policy tests and verify the expected RED result**

  Run `python3 -m pytest -q tests/test_autonomy_policy.py`; the new loader/import or the missing policy keys must fail before the policy is added.

- [ ] **Step 3: Add the policy, decision record, and active roster entries**

  Add the JSON contract, the dated decision record, an active `luna_writer` roster identity, and an active `sol` reviewer identity. Retain the retired `luna` identity for historical receipt resolution. Add the decision source and the active roles to `governance/authority.json` without deleting existing sources.

- [ ] **Step 4: Run the policy and roster tests GREEN**

  Run `python3 -m pytest -q tests/test_autonomy_policy.py tests/test_revue.py`; the tests must pass and existing historical vendor resolution must remain unchanged.

- [ ] **Step 5: Commit the contract slice**

  Run `git add governance/autonomy-policy.json governance/decisions/D-2026-08-21-autonomie-luna-sol.md manifests/roles.yaml governance/authority.json tests/test_autonomy_policy.py && git commit -m "feat(governance): version Luna Sol autonomy contract"`.

### Task 2: Specify the strict `sol_blind` behavior with failing tests

**Files:**
- Create: `tests/test_revue_sol_blind.py`
- Modify: `tests/test_reviews_gate.py`

**Interfaces:**
- The tests call `revue.tally_sol_blind(verdicts, expected=...)` and `revue.verifier_recu(...)` directly with deterministic in-memory fixtures.
- Historical tests continue to call `revue.tally(verdicts)` with three vendors.

- [ ] **Step 1: Add a positive exact-binding fixture and assertion**

  Build one literal Sol verdict containing `fresh_context: true`, `blind: true`, `reviewer_read_only: true`, `reviewer_model: "GPT-5.6-Sol"`, `candidate_diff_digest`, `base_commit`, `reviewed_head_commit`, `reviewed_head_tree`, `prompt_sha256`, `verdict: "APPROVE"`, `blocking_findings: []`, and a timezone-aware `reviewed_at`. Assert the public tally returns `APPROVE` and the receipt verifier accepts the same base and digest.

- [ ] **Step 2: Add rejection tests for each bypass**

  Parameterize `fresh_context: false`, `blind: false`, `reviewer_read_only: false`, a historical/non-fresh timestamp, a mismatched digest, a missing Sol identity, `reviewer_model: "GPT-5.6-Luna-Pro"`, `verdict: "REJECT"`, and one blocking finding. Assert each result is not `APPROVE` and the reason names the violated contract.

- [ ] **Step 3: Add compatibility and gate-dispatch tests**

  Keep a three-vendor historical fixture and assert `revue.tally()` still returns `APPROVE`. Add a `reviews_gate.check` fixture whose receipt declares `mode: "sol_blind"`; assert it dispatches to the Sol path instead of reporting `<3 verdicts`.

- [ ] **Step 4: Run the new tests and verify they fail for missing behavior**

  Run `python3 -m pytest -q tests/test_revue_sol_blind.py tests/test_reviews_gate.py`; failures must be caused by the absent mode/validator, not by malformed fixtures.

### Task 3: Implement `sol_blind` in the review pipeline

**Files:**
- Modify: `scripts/revue.py`
- Modify: `scripts/reviews_gate.py`
- Modify: `tests/test_revue_sol_blind.py`
- Modify: `tests/test_reviews_gate.py`

**Interfaces:**
- `tally_sol_blind(verdicts: list[dict], expected: dict, codeurs: list[str]) -> dict` validates one fresh Sol verdict against exact Git metadata.
- `verifier_recu` dispatches on `recu.get("mode", "multi_vendor")`; legacy receipts keep the old path.
- `revue.py recu` accepts `--mode multi_vendor|sol_blind` and writes the mode into the receipt.

- [ ] **Step 1: Implement the minimal strict tally**

  Add a validator that requires exactly one verdict, resolves the Sol identity through the active roster, checks all four freshness/blindness/read-only fields, compares the candidate digest and reviewed Git metadata to `expected`, requires an aware `reviewed_at`, `APPROVE`, and an empty `blocking_findings` list. Reject any codewriter that resolves to Sol or is the same model.

- [ ] **Step 2: Implement prompt and receipt mode plumbing**

  Add the `sol_blind` prompt mode with the exact canonical diff metadata and a JSON response schema. Add `--mode` to `prompt` and `recu`; preserve the default multi-vendor command output byte-for-byte where practical. Include `mode`, `reviewed_head_commit`, and `reviewed_head_tree` in the new receipt without comparing a receipt commit to itself.

- [ ] **Step 3: Dispatch the CI gate without weakening legacy checks**

  Load a receipt before tallying. For `mode == "sol_blind"`, use the strict tally and `verifier_recu`; otherwise call the existing multi-vendor tally. Keep current-PR round and monotonic-chain checks and archive ancestor checks active for both modes.

- [ ] **Step 4: Run the focused tests GREEN**

  Run `python3 -m pytest -q tests/test_autonomy_policy.py tests/test_revue_sol_blind.py tests/test_reviews_gate.py tests/test_revue.py`. Then run `python3 -m ruff check scripts/revue.py scripts/reviews_gate.py tests/test_autonomy_policy.py tests/test_revue_sol_blind.py tests/test_reviews_gate.py`.

- [ ] **Step 5: Commit the review-mode slice**

  Run `git add scripts/revue.py scripts/reviews_gate.py tests/test_autonomy_policy.py tests/test_revue_sol_blind.py tests/test_reviews_gate.py && git commit -m "feat(review): add exact-diff Sol blind mode"`.

### Task 4: Synchronize governance, documentation, ledgers, and generated views

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `Docs/reference/autonomy-luna-sol.md`
- Modify: `stories/ORCH-LUNA-SOL-603.md`
- Modify: `governance/vision-log.jsonl`
- Modify: `evidence/registres/mission.jsonl`
- Regenerate: `governance/AUTHORITY-MAP.md`, `governance/state-current.json`, `governance/STATE-CURRENT.md`, `governance/path-classification.json`, `governance/PATH-CLASSIFICATION.md`

**Interfaces:**
- The docs state `DONE_WITH_EVIDENCE` and `BLOCKED_WITH_REASON` as the only terminal states.
- `scripts/registre.py verify` remains the ledger oracle; generated views are produced by their existing `--render` commands.

- [ ] **Step 1: Add the failing documentation/generator checks**

  Extend the story and policy tests to assert the documented mode, no-write workflow rule, restart source of truth, and terminal states. Run the focused checks to establish the missing-text failure.

- [ ] **Step 2: Update prose and append-only records**

  Update AGENTS/CLAUDE with the active policy and the safe merge path, add the reference document and story, then append a decision entry and a deliverable entry through `scripts/registre.py append` rather than editing ledger hashes manually.

- [ ] **Step 3: Regenerate and validate all views**

  Run `python3 scripts/governance/validate_authority.py --render`, `python3 scripts/governance/state_current.py --render --docs README.md --docs AGENTS.md`, `python3 scripts/governance/classify_paths.py --render`, `python3 scripts/registre.py verify governance/vision-log.jsonl evidence/registres/mission.jsonl`, and the corresponding check commands.

- [ ] **Step 4: Commit synchronized governance**

  Run `git add AGENTS.md CLAUDE.md Docs/reference/autonomy-luna-sol.md stories/ORCH-LUNA-SOL-603.md governance evidence/registres/mission.jsonl && git commit -m "docs(governance): document Luna Sol recovery and merge policy"`.

### Task 5: Verify, obtain blind Sol review, and integrate

**Files:**
- Create: `evidence/reviews/ORCH-LUNA-SOL-603/` containing the exact prompt, request, one Sol verdict, and `RECU.json`
- Modify: `evidence/reviews/BINDING.txt`
- Modify: `stories/ORCH-LUNA-SOL-603.md`

- [ ] **Step 1: Run the proportionate local evidence set**

  Run the focused tests, `python3 -m pytest -q`, `python3 scripts/no_stub_scan.py --all`, `python3 scripts/ruff_noqa_gate.py`, authority/state/path-classification checks, registry verification, `git diff --check`, and `python3 scripts/reviews_gate.py --exiger-recu-courant --base-ref origin/main --issue 603` after the receipt is present.

- [ ] **Step 2: Render the prompt from the final code diff**

  Generate the `sol_blind` prompt from `origin/main...HEAD`, record base/head/tree and the canonical digest, and send only that prompt to one fresh read-only GPT-5.6 Sol reviewer. Do not provide another reviewer’s verdict or a desired outcome.

- [ ] **Step 3: Reject or repair any blocking Sol finding**

  If Sol rejects, reproduce the finding with a focused test, fix only the causal issue, rerun the focused and broad checks, and regenerate a fresh review round. If Sol approves, validate the receipt mechanically and bind it in `BINDING.txt`.

- [ ] **Step 4: Open the PR and wait for all repository checks**

  Push `codex/issue-603-clean`, create the PR for #603, and inspect every required workflow job. Do not merge on a skipped, stale, or unreported gate.

- [ ] **Step 5: Merge with expected head SHA and verify post-merge state**

  Merge only after the exact head SHA is still current, all required checks are successful, and the Sol receipt verifies. Confirm `origin/main`, the issue disposition, and the post-merge archive gate.

### Task 6: Dispose of the unsafe bootstrap and resume the loop

**Files:**
- Modify: PR #604 metadata/comments only; no source files from that branch are copied.

- [ ] **Step 1: Comment the concrete disposition**

  State that #604 is superseded because it contains only encoded source fragments and self-writing workflows with `contents: write`, and link the clean PR/commit that replaces it.

- [ ] **Step 2: Close #604 without deleting its branch**

  Close the draft PR while preserving the branch for audit history. Do not force-push or run either bootstrap workflow.

- [ ] **Step 3: Reconcile the next loop checkpoint**

  Re-fetch `main`, inspect open issues, and either begin the next independently authorized checkpoint or record a concrete T3 blocker. Keep at most one active subagent and close it after its verdict.
