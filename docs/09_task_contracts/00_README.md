# Burhān — Task Contracts (docs/09_task_contracts/00_README.md)

**Status:** For review · **Governed by:** `08_BUILD_SPEC.md` (source of truth), `10_PROJECT_PLAN.md` (order & gates), `15_ENGINEERING_STANDARDS.md` §6 (workflow), `CLAUDE.md` / `AGENTS.md` (roles).

A task contract is the unit of work: one contract → one branch → one PR → one binary verdict. Contracts **restate** their module's scope, traces, and acceptance tests from the build spec verbatim and add delivery detail only — a contract can never introduce scope the build spec lacks. These files were generated mechanically from `08_BUILD_SPEC.md` with an ownership check proving every acceptance test (75/75) is owned by exactly one contract.

## Lifecycle

`DRAFT` (authored) → `ISSUED` (Codex issues; dependencies all APPROVED) → `IN_PROGRESS` (Claude Code on branch) → `APPROVED` (verdict recorded in `SIGNOFFS.md`). REJECT keeps the contract `IN_PROGRESS` with the fix list attached to the PR. State lives in the ledger, not by editing contract files.

## Issue order

TC-01 → TC-02 → TC-03 → TC-04 → TC-05 → TC-06 → TC-07 → TC-08a → TC-08b → TC-08c → TC-09 → TC-10a → TC-10b → TC-11a → TC-11b → TC-12 → *(M5 gate → GATE FAIL at C4)* → TC-15 → *(M5 gate re-execution → GATE PASS)* → TC-16 → *(M6 validation run)* → TC-13 → TC-14. One active contract at a time; milestone gates per the project plan interleave where marked.

**TC-15** is a researcher-authored remediation contract (not part of the mechanical TC-01..TC-14 / 75-AT generation above): it wires the full fixed 13-stage DAG into the orchestrator — Stage-1A stages (S0–S8, S1, G1) as thin adapters over their certified modules, Stage-1B stages (S9 narrate, G2, S10 package) as certification pass-through stubs whose real behavior stays with TC-13/TC-14 — the integration work item the build spec never created, so certification C4 (IT-1..IT-3) can pass. It carries its own acceptance tests (AT-M15-1..6) and must be APPROVED before the M5 battery re-executes from §1.

**TC-16** is a researcher-authored contract (like TC-15, not part of the mechanical TC-01..TC-14 / 75-AT generation): it assembles the existing adapter components — TC-06's `NodeA.extract` / `NodeC` / `resolve_provider_call` and TC-15's wired Stage-1A registry — into a governed **live-provider** `burhan run`, the "later contract" the CLI defers real runs to (non-certification `run` currently refuses with exit 10). Scope is assembly + I/O plumbing: DOCX→text ingestion, real `llm.yaml` loading through the existing adapter boundary, live Node A extraction with `study_config.yaml` write-back, an **un-bypassable researcher-glance pause** before Gate 1, live Node C Gate 1, the unchanged headless Stage-1A registry, and LLM prompt/response archival+replay so `rerun` stays byte-identical (NFR-101) despite non-deterministic LLM calls. It adds **no statistics and no governance rules**; the certification path stays canned and offline (proven by AT-M16-2), and raw CSV never reaches an LLM (AT-M16-4). It carries acceptance tests AT-M16-1..8 and must be APPROVED and merged before the M6 validation run executes.

## Change control

Contract text is researcher-owned. If implementation reveals a contract defect (wrong criterion, untestable clause, conflict with a governed document), the lane STOPS and escalates (AGENTS.md); the researcher amends the build spec first, contracts are regenerated or edited to match, and the hash trail records it. Codex and Claude Code never patch a contract to fit the code.
