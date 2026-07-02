# TC-10a — measurement — CFA, validity, CMB

| | |
|---|---|
| **Module** | M10 — measurement  *(TC-10a CFA/validity/CMB · TC-10b deletion + respecification)* (08_BUILD_SPEC.md) |
| **Stage** | 1A |
| **State** | DRAFT → ISSUED → IN_PROGRESS → APPROVED (ledger: SIGNOFFS.md) |
| **Depends on** | TC-09 |
| **Branch** | `tc/tc-10a-measurement-cfa-validity-cmb` |

## Objective & Scope

CFA incl. second-order (both approaches), reliability/convergent/discriminant (α, CR, AVE, Fornell–Larcker, HTMT), CMB (Harman + CLF/marker), the item-deletion protocol behind M02's permit token, and the respecification controller.

**Maps to (architecture):** `stats/measurement`.

**In scope:** exactly the deliverables and acceptance tests below. **Out of scope:** everything else — adjacent refactors, governed-document edits, dependency additions (CLAUDE.md rules 2–3; standards §6). This contract owns only the listed subset of M10's acceptance tests; sibling contracts own the rest.

## Deliverables

- `workers/r/measurement_worker.R`
- `src/burhan/stats/measurement.py`
- `tests/unit/stats_measurement/`
- `tests/benchmark/higher_order_example/`

## Requirement Traces

FR-701–709; PB-08–PB-14.

## Acceptance Tests (restated from 08_BUILD_SPEC.md — verbatim, binding)

- AT-M10-1: on a published higher-order worked example, first- and second-order loadings, α/CR/AVE match reference within tolerance; both-level reporting present (FR-701/702, FR-1502).
- AT-M10-2: HTMT and Fornell–Larcker match `semTools` reference on fixtures; an engineered near-redundant pair (r² ≈ .80) passes F–L but trips the HTMT flag/fail bands exactly per PB-11 (FR-703).
- AT-M10-3: CMB — CLF/marker comparison flags a fixture with injected method variance; Harman alone passing does not mark PB-12 complete (FR-704).

## Delivery Notes

Higher-order support covers both repeated-indicator and two-stage from day one; the near-redundant HTMT trap fixture (r²≈.80 passing F–L) is part of this contract.

## Definition of Done

Standards §6 in full: gates green (ruff · mypy strict · pytest + coverage incl. 100%-modules where touched · lintr for R) · acceptance evidence per criterion in the completion report · absence tests intact where applicable · docs duty met · Codex APPROVE recorded in SIGNOFFS.md.
