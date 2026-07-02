# TC-08c — prep-dual — golden certification suite

| | |
|---|---|
| **Module** | M08 — prep-dual  *(contracts TC-08a Python impl · TC-08b R impl + reconciler · TC-08c golden suite)* (08_BUILD_SPEC.md) |
| **Stage** | 1A |
| **State** | DRAFT → ISSUED → IN_PROGRESS → APPROVED (ledger: SIGNOFFS.md) |
| **Depends on** | TC-08b |
| **Branch** | `tc/tc-08c-prep-dual-golden-certificati` |

## Objective & Scope

The full preparation sequence twice (Python, R), cell-level reconciliation, hard invariants, exact N-chain accounting, and the golden-dataset generator + certification suite.

**Maps to (architecture):** `prep/*`, `tests/golden/`.

**In scope:** exactly the deliverables and acceptance tests below. **Out of scope:** everything else — adjacent refactors, governed-document edits, dependency additions (CLAUDE.md rules 2–3; standards §6). 

## Deliverables

- `tests/golden/`
- `tests/golden/DEFECT_MATRIX.md`

## Requirement Traces

FR-501–507; FR-1501; NFR-601 (golden as regression).

## Acceptance Tests (restated from 08_BUILD_SPEC.md — verbatim, binding)

- Re-execute AT-M08-1..8 against the completed suite (owned by TC-08a/b; must remain green).
- Suite wired as permanent CI regression (FR-1504); DEFECT_MATRIX.md enumerates every planted defect class with its detecting check.

## Delivery Notes

Complete the defect matrix per 11_CERTIFICATION_PLAN (all defined planted defects + clean twins + the adversarial overlapping-defect fixture reviewed against the DBA export's known pathologies), wire as permanent regression (FR-1504), and re-run AT-M08-1..8 against the full suite.

## Definition of Done

Standards §6 in full: gates green (ruff · mypy strict · pytest + coverage incl. 100%-modules where touched · lintr for R) · acceptance evidence per criterion in the completion report · absence tests intact where applicable · docs duty met · Codex APPROVE recorded in SIGNOFFS.md.
