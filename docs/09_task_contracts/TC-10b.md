# TC-10b — measurement — deletion protocol + respecification

| | |
|---|---|
| **Module** | M10 — measurement  *(TC-10a CFA/validity/CMB · TC-10b deletion + respecification)* (08_BUILD_SPEC.md) |
| **Stage** | 1A |
| **State** | DRAFT → ISSUED → IN_PROGRESS → APPROVED (ledger: SIGNOFFS.md) |
| **Depends on** | TC-10a |
| **Branch** | `tc/tc-10b-measurement-deletion-protoco` |

## Objective & Scope

CFA incl. second-order (both approaches), reliability/convergent/discriminant (α, CR, AVE, Fornell–Larcker, HTMT), CMB (Harman + CLF/marker), the item-deletion protocol behind M02's permit token, and the respecification controller.

**Maps to (architecture):** `stats/measurement`.

**In scope:** exactly the deliverables and acceptance tests below. **Out of scope:** everything else — adjacent refactors, governed-document edits, dependency additions (CLAUDE.md rules 2–3; standards §6). This contract owns only the listed subset of M10's acceptance tests; sibling contracts own the rest.

## Deliverables

- `src/burhan/stats/deletion.py`
- `src/burhan/stats/respecification.py`
- `tests/unit/stats_deletion/`

## Requirement Traces

FR-701–709; PB-08–PB-14.

## Acceptance Tests (restated from 08_BUILD_SPEC.md — verbatim, binding)

- AT-M10-4: deletion protected path — candidate yields Recommendation only; with permit token: one-at-a-time with full re-estimation between deletions (call-sequence asserted), dual trigger enforced (statistical signal alone insufficient), three-item floor and two-item deletion-lock enforced, before/after audit emitted, validated-instrument deviation flagged (FR-705–708).
- AT-M10-5 (absence): batch deletion has no code path (FR-706).
- AT-M10-6: respecification — cross-construct MI suggestions filtered out; within-construct applied one-at-a-time in MI order; cap from policy stops at 3; each logged with MI + EPC + rule (FR-709). ---

## Delivery Notes

Deletion executes only against a permit token from TC-02; call-sequence assertions prove one-at-a-time re-estimation; the two-item deletion-lock and three-item floor are tested at the boundary.

## Definition of Done

Standards §6 in full: gates green (ruff · mypy strict · pytest + coverage incl. 100%-modules where touched · lintr for R) · acceptance evidence per criterion in the completion report · absence tests intact where applicable · docs duty met · Codex APPROVE recorded in SIGNOFFS.md.
