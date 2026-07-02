# TC-08a — prep-dual — Python implementation

| | |
|---|---|
| **Module** | M08 — prep-dual  *(contracts TC-08a Python impl · TC-08b R impl + reconciler · TC-08c golden suite)* (08_BUILD_SPEC.md) |
| **Stage** | 1A |
| **State** | DRAFT → ISSUED → IN_PROGRESS → APPROVED (ledger: SIGNOFFS.md) |
| **Depends on** | TC-04, TC-05 |
| **Branch** | `tc/tc-08a-prep-dual-python-implementat` |

## Objective & Scope

The full preparation sequence twice (Python, R), cell-level reconciliation, hard invariants, exact N-chain accounting, and the golden-dataset generator + certification suite.

**Maps to (architecture):** `prep/*`, `tests/golden/`.

**In scope:** exactly the deliverables and acceptance tests below. **Out of scope:** everything else — adjacent refactors, governed-document edits, dependency additions (CLAUDE.md rules 2–3; standards §6). This contract owns only the listed subset of M08's acceptance tests; sibling contracts own the rest.

## Deliverables

- `src/burhan/prep/py_impl/`
- `src/burhan/prep/invariants.py`
- `src/burhan/prep/n_chain.py`
- `tests/golden/generator.py (core)`
- `tests/unit/prep/`

## Requirement Traces

FR-501–507; FR-1501; NFR-601 (golden as regression).

## Acceptance Tests (restated from 08_BUILD_SPEC.md — verbatim, binding)

- AT-M08-1: on the golden dataset, the Python pipeline detects 100% of planted defects by class (duplicates, attention fails, straight-liners, out-of-range, un-reversed, engineered missingness, known outliers) with zero false positives on clean twins (FR-1501).
- AT-M08-2: partial-response recovery — cases ≥ policy threshold on model items enter the sample; profile artifact lists every partial with its completion %; threshold is read from policy, not code (FR-502).
- AT-M08-3: N-chain sums exactly at every link on golden and on an adversarial fixture (overlapping defect classes); a planted double-count breaks the run with `IntegrityHalt` (FR-506).
- AT-M08-4 (absence): no mean-substitution and no synthetic-case code path exists — absence tests per standards §3 (FR-505).
- AT-M08-5: invariants — each of the seven FR-507 assertions has a fixture that trips exactly it.
- AT-M08-7: Little's MCAR + pattern map computed before treatment; FIML selected under MCAR fixture, MI under the policy-alternative fixture, MNAR fixture flags with sensitivity note (FR-503/504).
- AT-M08-8: reverse-coding verified by sign-flip; an un-reversed golden item is caught here even if declared correctly (FR-507). ---

## Delivery Notes

Includes the golden-generator CORE (enough defect classes to drive these ATs); TC-08c completes the matrix. Every screening rule reads policy paths — no literals.

## Definition of Done

Standards §6 in full: gates green (ruff · mypy strict · pytest + coverage incl. 100%-modules where touched · lintr for R) · acceptance evidence per criterion in the completion report · absence tests intact where applicable · docs duty met · Codex APPROVE recorded in SIGNOFFS.md.
