# TC-08b — prep-dual — R implementation + reconciler

| | |
|---|---|
| **Module** | M08 — prep-dual  *(contracts TC-08a Python impl · TC-08b R impl + reconciler · TC-08c golden suite)* (08_BUILD_SPEC.md) |
| **Stage** | 1A |
| **State** | DRAFT → ISSUED → IN_PROGRESS → APPROVED (ledger: SIGNOFFS.md) |
| **Depends on** | TC-08a |
| **Branch** | `tc/tc-08b-prep-dual-r-implementation-r` |

## Objective & Scope

The full preparation sequence twice (Python, R), cell-level reconciliation, hard invariants, exact N-chain accounting, and the golden-dataset generator + certification suite.

**Maps to (architecture):** `prep/*`, `tests/golden/`.

**In scope:** exactly the deliverables and acceptance tests below. **Out of scope:** everything else — adjacent refactors, governed-document edits, dependency additions (CLAUDE.md rules 2–3; standards §6). This contract owns only the listed subset of M08's acceptance tests; sibling contracts own the rest.

## Deliverables

- `workers/r/prep_worker.R`
- `src/burhan/prep/reconciler.py`
- `tests/unit/prep_r/`

## Requirement Traces

FR-501–507; FR-1501; NFR-601 (golden as regression).

## Acceptance Tests (restated from 08_BUILD_SPEC.md — verbatim, binding)

- AT-M08-6: R impl on golden matches Python **cell-for-cell at tolerance 0**; a planted one-cell divergence halts with a discrepancy report naming row/column (FR-501).

## Delivery Notes

The R implementation is written blind to the Python source where feasible (independent-chain discipline); the reconciler diffs at tolerance 0 and reports row/column on the first divergence.

## Definition of Done

Standards §6 in full: gates green (ruff · mypy strict · pytest + coverage incl. 100%-modules where touched · lintr for R) · acceptance evidence per criterion in the completion report · absence tests intact where applicable · docs duty met · Codex APPROVE recorded in SIGNOFFS.md.
