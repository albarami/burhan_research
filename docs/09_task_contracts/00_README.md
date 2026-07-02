# Burhān — Task Contracts (docs/09_task_contracts/00_README.md)

**Status:** For review · **Governed by:** `08_BUILD_SPEC.md` (source of truth), `10_PROJECT_PLAN.md` (order & gates), `15_ENGINEERING_STANDARDS.md` §6 (workflow), `CLAUDE.md` / `AGENTS.md` (roles).

A task contract is the unit of work: one contract → one branch → one PR → one binary verdict. Contracts **restate** their module's scope, traces, and acceptance tests from the build spec verbatim and add delivery detail only — a contract can never introduce scope the build spec lacks. These files were generated mechanically from `08_BUILD_SPEC.md` with an ownership check proving every acceptance test (75/75) is owned by exactly one contract.

## Lifecycle

`DRAFT` (authored) → `ISSUED` (Codex issues; dependencies all APPROVED) → `IN_PROGRESS` (Claude Code on branch) → `APPROVED` (verdict recorded in `SIGNOFFS.md`). REJECT keeps the contract `IN_PROGRESS` with the fix list attached to the PR. State lives in the ledger, not by editing contract files.

## Issue order

TC-01 → TC-02 → TC-03 → TC-04 → TC-05 → TC-06 → TC-07 → TC-08a → TC-08b → TC-08c → TC-09 → TC-10a → TC-10b → TC-11a → TC-11b → TC-12 → *(M5 gate + M6 validation run)* → TC-13 → TC-14. One active contract at a time; milestone gates per the project plan interleave where marked.

## Change control

Contract text is researcher-owned. If implementation reveals a contract defect (wrong criterion, untestable clause, conflict with a governed document), the lane STOPS and escalates (AGENTS.md); the researcher amends the build spec first, contracts are regenerated or edited to match, and the hash trail records it. Codex and Claude Code never patch a contract to fit the code.
