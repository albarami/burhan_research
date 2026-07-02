# TC-11a — structural

| | |
|---|---|
| **Module** | M11 — structural-effects  *(TC-11a structural · TC-11b effects)* (08_BUILD_SPEC.md) |
| **Stage** | 1A |
| **State** | DRAFT → ISSUED → IN_PROGRESS → APPROVED (ledger: SIGNOFFS.md) |
| **Depends on** | TC-10b |
| **Branch** | `tc/tc-11a-structural` |

## Objective & Scope

Structural estimation and fit reporting per PB-15/16; bootstrapped mediation/moderation with Zhao–Lynch–Chen classification per PB-17; higher-order carry recorded.

**Maps to (architecture):** `stats/structural`, `stats/effects`.

**In scope:** exactly the deliverables and acceptance tests below. **Out of scope:** everything else — adjacent refactors, governed-document edits, dependency additions (CLAUDE.md rules 2–3; standards §6). This contract owns only the listed subset of M11's acceptance tests; sibling contracts own the rest.

## Deliverables

- `workers/r/structural_worker.R`
- `src/burhan/stats/structural.py`
- `tests/unit/stats_structural/`

## Requirement Traces

FR-801–803; PB-15–17.

## Acceptance Tests (restated from 08_BUILD_SPEC.md — verbatim, binding)

- AT-M11-1: fit indices (χ², χ²/df, CFI, TLI, RMSEA+CI, SRMR) match lavaan reference outputs on the benchmark example; band evaluation recorded as `report`, never mutating the model (FR-801, PB-15).
- AT-M11-5: `structural_carrier` from the contract (full hierarchy vs latent scores) demonstrably changes the fitted model and is recorded with rationale (FR-803). ---

## Delivery Notes

Fit evaluation is report-only by construction — no code path mutates the model from a fit result. structural_carrier switches are integration-tested against distinguishable fixtures.

## Definition of Done

Standards §6 in full: gates green (ruff · mypy strict · pytest + coverage incl. 100%-modules where touched · lintr for R) · acceptance evidence per criterion in the completion report · absence tests intact where applicable · docs duty met · Codex APPROVE recorded in SIGNOFFS.md.
