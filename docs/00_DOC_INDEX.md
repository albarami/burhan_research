# Burhān — Documentation Index (docs/00_DOC_INDEX.md)

Master inventory of every document the system needs to go from zero to live.
Rule: no module is built without its governing documents approved. Every document below is drafted, reviewed by Codex (approve / reject with exact fixes), and only then consumed by Claude Code.

Status legend: ✅ approved · ⬜ to produce · 🔒 user-supplied input

---

## Category 1 — Concept & Requirements (why and what)

| # | Document | Purpose | Status |
|---|---|---|---|
| 01 | `docs/01_CONCEPT.md` | The approved concept: doctrine, phases, governance, validation-first strategy. Source of truth for intent. | ✅ |
| 02 | `docs/02_REQUIREMENTS.md` | Numbered functional (FR-xx) and non-functional (NFR-xx) requirements distilled from the concept. Every acceptance test later traces to an ID here. | ✅ |

## Category 2 — Technical Design (how)

| # | Document | Purpose | Status |
|---|---|---|---|
| 03 | `docs/03_ARCHITECTURE.md` | Technical architecture: pipeline DAG and state model, component boundaries, the three LLM node integrations (A/B/C with lineage separation), halt/error semantics, artifact flow, run archive layout. | ✅ |
| 04 | `docs/04_ENVIRONMENT_AND_STACK.md` | Exact environment spec for the workstation: OS/WSL layout, Python and R versions, package pinning and lockfile strategy, LLM provider configuration per node, local paths, secrets handling. | ✅ |
| 05 | `schemas/` (repo root; canonical machine contracts) | The machine contracts code validates against: `study_config.schema.yaml` (+ worked example), `results_store.schema.json` (statistic-ID spec), `provenance_log.schema.json`, `decision_log` format, `run_manifest.schema.json`, benchmark comparison report format. | ✅ |
| 06 | `playbooks/` (repo root) | `PLAYBOOK_SCHEMA.md` (what a playbook file must contain) + `CB_SEM_PLAYBOOK_v1.0.yaml` — the executable CB-SEM protocol: stages, decision points, thresholds, citations, reporting structure. | ✅ |
| 07 | `policy/` (repo root) | `decision_policy.template.yaml` (operational rulebook with adopted defaults and citations) + `protected_decisions.registry.yaml` (human-only decisions, item-deletion default). | ✅ |

## Category 3 — Planning & Build Execution (who builds what, in what order)

| # | Document | Purpose | Status |
|---|---|---|---|
| 08 | `docs/08_BUILD_SPEC.md` | Phase 1 Build Specification: module decomposition (10–14 modules), module interfaces, 1A → 1B execution order, per-module acceptance tests. The master document Codex directs from. | ✅ |
| 09 | `docs/09_task_contracts/` | One work order per module (TC-01…TC-14), plus **TC-15** (researcher-authored M5 C4 remediation: production pipeline wiring): scope, inputs/outputs, acceptance criteria, test requirements, dependencies. The unit Codex issues and signs off against. | ✅ |
| 10 | `docs/10_PROJECT_PLAN.md` | Milestones M0–M7 (scaffold → contracts → prep core → measurement → structural/effects → reporting layer → certification → DBA validation), dependency map, definition-of-done per milestone. | ✅ |
| 15 | `docs/15_ENGINEERING_STANDARDS.md` | Coding standards (Python + R), typing/docstring rules, test conventions, git branch/commit discipline, review workflow mechanics. | ✅ |
| — | `CLAUDE.md` (repo root) | Standing instructions for Claude Code: role, what it may/may not decide, how to consume task contracts, test-first rules, where outputs go. | ✅ |
| — | `AGENTS.md` (repo root) | Standing instructions for Codex: reviewer mandate, approve/reject format, what to check per contract, sign-off record location. | ✅ |

## Category 4 — Verification & Validation (proof before trust)

| # | Document | Purpose | Status |
|---|---|---|---|
| 11 | `docs/11_CERTIFICATION_PLAN.md` | Golden-dataset defect matrix (every planted defect defined), the list of published worked examples to replicate with tolerances, cross-engine parity protocol, coverage requirements. | ⬜ |
| 12 | `docs/12_DBA_VALIDATION_PROTOCOL.md` | The known-case run: exactly what is compared against your manual analysis (cleaning decisions, N, loadings, fit, paths, mediation, hypothesis decisions), tolerances, divergence classification (manual weakness vs engine/policy fix), resolution and sign-off procedure. | ⬜ |

## Category 5 — Operations & Go-Live (running it)

| # | Document | Purpose | Status |
|---|---|---|---|
| 13 | `docs/13_RUNBOOK.md` | Operating manual: CLI usage, new-study onboarding checklist, reading DECISION_LOG/FLAGS, re-run procedure, troubleshooting, archive management. | ⬜ |
| 14 | `docs/14_GO_LIVE_CHECKLIST.md` | The gate: every condition that must be true (certification passed, DBA validation resolved, docs current) before Burhān is declared production-ready for new studies. | ⬜ |

## Category 6 — User-Supplied Inputs (only you can provide)

| # | Item | Needed for | Status |
|---|---|---|---|
| U1 | Completed DBA study document (model, hypotheses, methodology chapter) | Node A extraction; validation run | 🔒 |
| U2 | DBA raw survey data export (Excel/CSV) | Validation run | 🔒 |
| U3 | Your manual analysis outputs (SPSS/AMOS results, tables, final N, decisions) | Benchmark comparison (doc 12) | 🔒 |
| U4 | Data dictionary / instrument export, if available | Contract cross-validation | 🔒 |
| U5 | Adopted-thresholds decisions (where literature varies: fit bands, HTMT ceiling, inclusion threshold, etc.) | Playbook (06) and policy (07) authoring | 🔒 |

---

## Production Order (each wave Codex-reviewed before the next)

1. **Wave 1 — Define:** 02 Requirements → 03 Architecture → 04 Environment
2. **Wave 2 — Contracts:** 05 Schemas → 06 Playbook (needs U5) → 07 Policy + Registry
3. **Wave 3 — Build governance:** 15 Standards + CLAUDE.md + AGENTS.md → 08 Build Spec → 10 Project Plan → 09 Task Contracts
4. **Wave 4 — Verification:** 11 Certification Plan → 12 DBA Validation Protocol (needs U1–U4)
5. **Wave 5 — Operations:** 13 Runbook → 14 Go-Live Checklist (Runbook finalized alongside the build; Checklist before first production study)

Build starts when Wave 3 is approved; Waves 4–5 complete during and after the build, before go-live.

---

## Repository docs layout

```
burhan/
  CLAUDE.md
  AGENTS.md
  docs/
    00_DOC_INDEX.md            ← this file
    01_CONCEPT.md
    02_REQUIREMENTS.md
    03_ARCHITECTURE.md
    04_ENVIRONMENT_AND_STACK.md
    05_schemas/
    06_playbooks/
    07_policy/
    08_BUILD_SPEC.md
    09_task_contracts/
    10_PROJECT_PLAN.md
    11_CERTIFICATION_PLAN.md
    12_DBA_VALIDATION_PROTOCOL.md
    13_RUNBOOK.md
    14_GO_LIVE_CHECKLIST.md
    15_ENGINEERING_STANDARDS.md
```
