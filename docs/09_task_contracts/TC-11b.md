# TC-11b — effects + hypothesis matrix

| | |
|---|---|
| **Module** | M11 — structural-effects  *(TC-11a structural · TC-11b effects)* (08_BUILD_SPEC.md) |
| **Stage** | 1A |
| **State** | DRAFT → ISSUED → IN_PROGRESS → APPROVED (ledger: SIGNOFFS.md) |
| **Depends on** | TC-11a |
| **Branch** | `tc/tc-11b-effects-hypothesis-matrix` |

## Objective & Scope

Structural estimation and fit reporting per PB-15/16; bootstrapped mediation/moderation with Zhao–Lynch–Chen classification per PB-17; higher-order carry recorded.

**Maps to (architecture):** `stats/structural`, `stats/effects`.

**In scope:** exactly the deliverables and acceptance tests below. **Out of scope:** everything else — adjacent refactors, governed-document edits, dependency additions (CLAUDE.md rules 2–3; standards §6). This contract owns only the listed subset of M11's acceptance tests; sibling contracts own the rest.

## Deliverables

- `workers/r/effects_worker.R`
- `src/burhan/stats/effects.py`
- `src/burhan/stats/hypothesis_matrix.py`
- `tests/unit/stats_effects/`

## Requirement Traces

FR-801–803; PB-15–17.

## Acceptance Tests (restated from 08_BUILD_SPEC.md — verbatim, binding)

- AT-M11-2: bootstrap effects reproduce a published mediation example's CIs within tolerance at fixed seed; resamples read from policy (FR-802, FR-1502).
- AT-M11-3: classification — five fixtures (complementary, competitive, indirect-only, direct-only, no-effect) each classified correctly; every hypothesized indirect effect receives a classification entry (PB-17).
- AT-M11-4: hypothesis matrix — verdicts follow PB-16 significance rule incl. marginal-p = not supported; matrix rows carry statistic IDs for every number (FR-1103 backbone, FR-1003-adjacent).

## Delivery Notes

Five-way classification fixtures come first; the hypothesis matrix is assembled exclusively from statistic IDs so TC-13's checker inherits a clean substrate.

## Definition of Done

Standards §6 in full: gates green (ruff · mypy strict · pytest + coverage incl. 100%-modules where touched · lintr for R) · acceptance evidence per criterion in the completion report · absence tests intact where applicable · docs duty met · Codex APPROVE recorded in SIGNOFFS.md.
