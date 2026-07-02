# Burhān (برهان)

Autonomous research analysis engine — Phase 1: CB-SEM v1 Core Release. Deterministic R/Python is the runtime; LLM nodes are bounded adapters; every run is reproducible, policy-governed, and provenance-logged.

- **Start here:** `docs/00_DOC_INDEX.md` → `docs/01_CONCEPT.md`
- **Build governance:** `CLAUDE.md` (implementer) · `AGENTS.md` (director/reviewer) · `docs/15_ENGINEERING_STANDARDS.md`
- **Machine contracts (canonical):** `schemas/` · `playbooks/` · `policy/` — CI validates them on every push
- **Environment:** `docs/04_ENVIRONMENT_AND_STACK.md` (WSL2, uv, renv; bootstrap in §8)
- **Plan & work orders:** `docs/10_PROJECT_PLAN.md` · `docs/09_task_contracts/`

**Studies are engine-external** (`~/research/burhan-studies/`, FR-1402) and are never committed here — `.gitignore` and CI enforce it.

M0 notes: `uv.lock` is committed from the workstation at bootstrap; `renv.lock` is created at TC-04 (first R worker).
