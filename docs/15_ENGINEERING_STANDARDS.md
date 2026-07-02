# Burhān — Engineering Standards (docs/15_ENGINEERING_STANDARDS.md)

**Status:** For review · **Governed by:** `02_REQUIREMENTS.md` (NFR-100/200/600), `03_ARCHITECTURE.md` (AD-01..08)
**Applies to:** every line of code in the engine. Task contracts inherit these standards implicitly; a contract may tighten them, never loosen them.

---

## 1. Python

- **Version/tooling:** CPython 3.12 via `uv`. Lint + format: `ruff` (line length 100). Types: `mypy --strict` on `src/`; no untyped `def`, no `Any` except at declared adapter edges.
- **Models:** every artifact crossing a stage boundary is a `pydantic` v2 model generated from / CI-checked against `docs/05_schemas` (README rule). No ad-hoc dicts across boundaries.
- **Structure:** modules mirror `03_ARCHITECTURE.md` §3 exactly; no cross-layer imports upward (e.g., `stats/` never imports `narrate/`); `package/` never imports back into statistical modules (AD-08).
- **Style rules:** `pathlib` over `os.path`; no bare `except`; no `print` — structured logging only; public functions carry Google-style docstrings; constants for every literal that appears in a requirement.
- **Determinism in code:** clocks and RNGs are injected, never called ambiently (`time.time()`/`random` at module scope are lint-banned); all serialization uses the canonical JSON writer (sorted keys, fixed float formatting); iteration feeding any output is explicitly ordered. Rationale: NFR-101 is a code-style property, not just an environment property.

## 2. R (workers)

- **Statelessness:** each worker is a pure function of `call_<id>.input.json` → `call_<id>.output.json`; no globals, no cached state, no writes outside the run directory (AD-02).
- **Namespacing:** explicit `pkg::fn()` everywhere; no `library()` side effects beyond the declared imports header.
- **Assertions:** inputs validated with `stopifnot()`/schema checks before use; every worker asserts `renv` status clean and sets seeds from input before any computation; `sessionInfo()` captured to the run log.
- **Style:** tidyverse style via `{styler}`; `{lintr}` clean.

## 3. Testing

- **Framework:** `pytest` (+ `testthat` for R-internal functions; R workers are additionally tested end-to-end from pytest via fixture JSON calls).
- **Layout:** `tests/unit/` mirrors `src/`; `tests/fixtures/` holds known-answer fixtures (NFR-602); `tests/golden/` and `tests/benchmark/` hold the certification suites (FR-1501/1502) and are regression gates forever (FR-1504).
- **Coverage gates:** ≥ 90% line coverage overall; **100%** for `prep/`, `core/policy`, `core/registry`, `results/store`, and `narrate/checker` — the modules where a silent gap is a scientific defect.
- **Test honesty:** a test that cannot fail is a defect; every FR referenced by a task contract has at least one test that fails when the behavior is removed (NFR-601). Snapshot tests are allowed only for rendered documents, never for statistics.
- **Prohibited-path tests:** the impossibility claims (FR-505 no mean-substitution path, FR-706 no batch deletion, FR-1202 no protected execution path) each get a test asserting the code path does not exist / raises by construction.

## 4. Failure Handling

Typed exceptions map 1:1 to the failure taxonomy in `03_ARCHITECTURE.md` §7 (`IntegrityHalt`, `VerificationHalt`, `GateExhausted`, `AdvisoryStop`). Catch-and-continue is forbidden in `prep/`, `stats/`, `verify/`, and `core/` — anything unclassifiable re-raises as `IntegrityHalt` (NFR-201). Every raised halt writes its machine-readable report before propagating.

## 5. Git Discipline

- **Model:** trunk-based; `main` is always green and protected (no force-push). One short-lived branch per task contract: `tc/TC-07-prep-reconciler`.
- **Commits:** Conventional Commits with contract reference — `feat(prep): cell-level reconciler [TC-07]`. Every commit passes `ruff`, `mypy`, and the unit suite.
- **PR = task contract:** one contract, one PR; the PR description links the contract and lists acceptance-criteria evidence. Milestone completion is tagged (`m1-contracts`, `m2-prep-core`, …).

## 6. Two-Agent Review Workflow (mechanics)

1. Codex issues the next task contract per the build order (`08_BUILD_SPEC.md`, `10_PROJECT_PLAN.md`).
2. Claude Code implements on the contract branch and posts a **completion report**: what was built, acceptance-criteria evidence (test names + results), gate outputs (ruff/mypy/pytest/coverage), deviations if any (with justification).
3. Codex reviews strictly against the contract and these standards; verdict is **APPROVE** or **REJECT with exact fixes** (numbered, each independently actionable). No partial approvals.
4. On APPROVE: merge, tag if milestone-closing, record the verdict in `docs/09_task_contracts/SIGNOFFS.md` (contract ID, commit, date, verdict). On REJECT: Claude Code addresses exactly the listed fixes; the cycle repeats.
5. The researcher coordinates, resolves escalations, and is the only party who may change governed documents (schemas, playbook, policy, registry, concept) — via a documented change, never inline during a contract.

**Definition of Done (every contract):** code + tests merged green · coverage gates met · `ruff`/`mypy`/`lintr` clean · `burhan doctor` unaffected · acceptance criteria evidenced · requirement traces updated · Codex APPROVE recorded in SIGNOFFS.

## 7. Security & Data Hygiene

No secrets in code, config, logs, or manifests (env only, per `04_ENVIRONMENT_AND_STACK.md` §6). Log metadata about raw data (counts, hashes, column names), never respondent values. The LLM adapter allowlists (AD-04) carry mandatory tests proving raw-data inputs are rejected (NFR-401). Studies content is never committed to the engine repository (FR-1402); `.gitignore` enforces it and CI fails on violation.

## 8. Documentation Duty

Code changes that alter behavior described in `docs/` update those docs in the same contract. `13_RUNBOOK.md` sections affected by a contract are listed in its completion report. Drift between docs and behavior is a REJECT.
