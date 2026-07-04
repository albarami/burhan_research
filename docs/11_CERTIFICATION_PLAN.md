# Burhān — Certification Plan (docs/11_CERTIFICATION_PLAN.md)

**Scope:** Milestone M5 gate instrument — certification of the Stage-1A engine
**Status:** For review (Codex), then governs M5 execution
**Governed by:** Concept §14, `02_REQUIREMENTS.md` (FR-1501/1502/1504, FR-902/903, NFR-101), `08_BUILD_SPEC.md` (AT/IT identifiers), `10_PROJECT_PLAN.md` §M5, `04_ENVIRONMENT_AND_STACK.md` (certified-workstation marker and cross-platform numeric policy).

**What certification means.** Passing this plan is the formal declaration that the engine may touch real research data. It certifies the Stage-1A pipeline **on the certified workstation** — the environment where exactness is defined — with CI as the portable tolerance-band shadow. The researcher's signature at the end is Milestone M5; nothing in M6 may begin without it.

**Relationship to existing infrastructure.** This plan invents no new checks. The battery below binds artifacts that already exist as code — the golden suite (TC-08c), the benchmark runner and parity tooling (TC-12), the E-R5 anchor registry, and the module acceptance tests — into one executed, evidenced, signed event. Where an integration harness is missing (§C4), a bounded authorization is granted in §6.

---

## 1. Certified Environment (preflight — all mandatory)

| # | Check | Evidence captured |
|---|---|---|
| P1 | `git status` clean on `main`; HEAD SHA recorded | SHA |
| P2 | `uv run burhan doctor` green | full output |
| P3 | `BURHAN_CERTIFIED_WORKSTATION=1` present in the researcher's env | doctor line |
| P4 | `uv.lock` and `workers/r/renv.lock` hashes recorded | hashes |
| P5 | Playbook `CB_SEM_PLAYBOOK_v1.0`, policy, and registry hashes recorded | hashes |

All evidence lands in `CERTIFICATION_REPORT.md` (§5).

## 2. Certification Battery

### C1 — Golden-dataset certification (FR-1501)
Execute the complete golden suite on the certified workstation.
**Pass:** 100% detection of every defect class enumerated in `tests/golden/DEFECT_MATRIX.md`; zero false positives on clean twins; zero unexplained dual-path (Python↔R) cell differences at tolerance 0; N-chain exact on golden and adversarial fixtures; matrix-completeness meta-tests green.

### C2 — Benchmark replication (FR-1502)
Execute the benchmark set. The anchors are those already pinned in the test suite, and this plan freezes them as the certified list:
1. MacCallum–Browne–Sugawara close-fit power values (corroborated points, incl. min-N at df=100 → 132) — tolerance ≤ 0.001
2. Mardia diagnostics vs the published MVN reference values — tolerance ≤ 5e-5, Python and R independently
3. Higher-order CFA worked example — loadings, α/CR/AVE, and second-order reliability at the pinned `pytest.approx` tolerances with recorded provenance
4. Published mediation example — bootstrapped CIs within pinned tolerance at fixed seed
5. Monte Carlo power anchors — exact match to the E-R5 workstation-certified R=400 registry values (marker present), with the CI band's negative control demonstrably failing wrong values
**Pass:** every anchor within its pinned tolerance; anchor registry provenance complete (replications, environment, marker, date, band-as-data).

### C3 — Cross-engine parity map (FR-902/903)
Produce and commit the certified parity map from the TC-12 tooling: per-scope declaration of what the independent Python path verifies, at what tolerance, and which scopes are declared out-of-parity (flagged, never force-compared).
**Pass:** map generated from certification runs (not hand-written), committed with hash; every declared scope demonstrated by at least one passing comparison; at least one out-of-parity declaration path exercised; halt-multiplier breach demonstrably produces `HALTED_VERIFICATION`.

### C4 — System integration (IT-1..IT-4, build spec)
Executed on the certified workstation with **stubbed LLM nodes** (deterministic canned Node A/B/C responses; no provider calls):
- **IT-1 Pipeline dry run:** golden study end-to-end → `COMPLETED`; `METHOD_COMPLIANCE_CHECKLIST.md` covers PB-01..PB-19 with no step unaccounted.
- **IT-2 Rerun identity:** `burhan rerun` on the sealed IT-1 run regenerates byte-identical artifacts (NFR-101 at system level).
- **IT-3 Boundary run:** under-powered fixture → `METHOD_ADVISORY.md` emitted through governance → terminal state `COMPLETED_TO_BOUNDARY` with a defensible-scope package.
- **IT-4 Regression permanence:** the C1–C3 batteries are wired in CI (workstation-exact parts as value-band shadows per E-R5) and the wiring is demonstrated by the current green run IDs (FR-1504).
**Pass:** all four, each with terminal-state, checklist, and hash evidence.

## 3. Pass/Fail Rule

Binary, per Concept §14: **every** line in C1–C4 and P1–P5 passes, or the gate fails. A failed gate produces a fix (via a contract or a researcher-governed change, per change control), and the **entire** battery re-executes from §1 — partial re-runs do not certify.

## 4. Waivers

None are contemplated. If reality forces one, it must be researcher-signed in the report with rationale and an expiry condition, and it blocks nothing silently: a waived line is printed in the sign-off row itself.

## 5. Evidence & Report

M5 execution produces `docs/certification/CERTIFICATION_REPORT.md` (plus a `runs/` evidence folder outside the repo if artifacts are heavy):
commit SHA · preflight table · per-line battery results with named tests and outputs · CI run IDs · parity-map hash · IT terminal states and artifact hash roots · deviations (expected: none) · the sign-off block.

## 6. Bounded Harness Authorization

If executing C4 requires integration-test scaffolding that no contract delivered (stubbed-node fixtures, an IT runner under `tests/integration/`), this plan **authorizes that scaffolding as a researcher-governed change set on `main`**, with hard bounds: test/fixture code only; no `src/` behavior changes; no governed-document edits beyond adding the report; Codex reviews it exactly like a contract before the battery counts. Anything beyond these bounds returns to the researcher.

## 7. Sign-off Procedure

1. Claude Code executes §1–§2 battery per this plan and assembles the report; Codex verifies the report against ground truth (re-running gates itself, per AGENTS.md) and posts a gate verdict: **GATE PASS** or **GATE FAIL** with exact deficiencies.
2. On GATE PASS, the researcher reviews the report (expected 20–30 minutes) and records the signature in `docs/09_task_contracts/SIGNOFFS.md`, milestone table:
   `| M5 certification | <date> | Researcher | CERTIFICATION_REPORT.md @ <commit> |`
3. That row is the unlock for M6. It is also the sentence the AI-use disclosure will later cite: *the engine was certified against defect-seeded data, published benchmarks, and system-level integration before analyzing any real study.*

## 8. Regression Permanence (FR-1504)

The certified battery never retires: C1–C3 remain CI gates on every push; C4's IT set re-executes on the certified workstation before M6 begins and after any governed change that touches statistical modules, with the re-run noted in the report's appendix.
