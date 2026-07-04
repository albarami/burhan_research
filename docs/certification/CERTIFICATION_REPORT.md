# Burhān — Certification Report (M5 gate execution)

**Instrument:** `docs/11_CERTIFICATION_PLAN.md` (approved as M5 gate instrument).
**Executed by:** Claude Code (implementer), on the certified workstation.
**Commit under test:** `c02d70a4f97f50c75606bf15f2c1450894cacbef` (branch `main`).
**Date (UTC):** 2026-07-04.

## Verdict (for Codex per §7)

**GATE FAIL — blocked at C4.** P1–P5, C1, C2, and C3 pass on the certified
workstation. **C4 (IT-1..IT-4) cannot execute**: the production Stage-1A
pipeline is not wired into `src/` — `burhan run`/`rerun` refuse cleanly with
`HALTED_INTEGRITY` (exit 10) because the production stage registry is empty.
Wiring the 13 pipeline stages is a `src/` behavior change that §6's bounded
harness authorization explicitly forbids, so it cannot be done under this gate;
it requires a researcher-issued contract. Details in C4 below.

Per §3 (binary pass/fail) the gate does not certify until the entire battery
passes and re-executes from §1. This report is submitted for Codex's GATE
verdict; the researcher M5 signature is **not** unlocked.

---

## §1 Preflight (P1–P5)

| # | Check | Result | Evidence |
|---|---|---|---|
| P1 | `git status` clean on `main`; HEAD SHA | **PASS** | clean tree; HEAD `c02d70a4f97f50c75606bf15f2c1450894cacbef` |
| P2 | `uv run burhan doctor` green | **PASS** | exit 0; all `[PASS]`; `provider_connectivity [SKIP]` (deferred pre-adapters, by design); no `[FAIL]` |
| P3 | `BURHAN_CERTIFIED_WORKSTATION=1` present in researcher env | **PASS (deviation on evidence form)** | marker present = `1`, sourced from the documented secrets path `~/.config/burhan/.env`. **Deviation:** the plan's evidence column names a "doctor line," but `burhan doctor` emits none — `src/` has zero references to the marker. Evidenced by direct env inspection instead; doctor was **not** modified (prohibited `src/` change). See Deviations. |
| P4 | `uv.lock` + `workers/r/renv.lock` hashes | **PASS** | `uv.lock` `ba58ef5b55a3f431b45b1f0ad860d5b780d38e7b5cf2a841b01d8807f2ab8e0e`; `workers/r/renv.lock` `069c2b33829cb0fd2cc7bda578b94b86d22ec3c333bcf6376244c061af0f3306` |
| P5 | Playbook / policy / registry hashes | **PASS** | playbook `CB_SEM_PLAYBOOK_v1.0.yaml` `a88fab40d873a4c7a65b87d41704f55eca3a7ad0c88cdc4e5a3ea50d60820fe1`; policy `decision_policy.template.yaml` `250539f785826ae63414f55eed746dff5f09f271599ab340fa8ed4523f0a28e3`; registry `protected_decisions.registry.yaml` `e05357eefb7545310ff429692a0a62cd0c3af6b0528cb732726a38c504f32bc6` |

All battery suites below were run with the certified environment:
`source ~/.config/burhan/.env` + determinism pins (`TZ=UTC LC_ALL=C.UTF-8
PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`) +
`BURHAN_CERTIFIED_WORKSTATION=1`.

## §2 Battery

### C1 — Golden-dataset certification (FR-1501) — **PASS**

`uv run pytest tests/golden/` → **32 passed, 0 skipped** (`test_certification.py`).

| C1 condition | Named tests (all PASSED) |
|---|---|
| 100% detection per defect class | `test_matrix_detection_is_exact_per_class[11/23/47]` |
| Zero false positives on clean twins | `test_matrix_clean_twins_have_zero_detections[11/23/47]` |
| Zero unexplained dual-path (Py↔R) cell diffs at tol 0 | `test_matrix_dual_path_parity[True/False-11/23/47]`, `test_adversarial_dual_path_parity` (R engine live per P2) |
| N-chain exact (golden + adversarial) | `test_matrix_chains_sum_exactly[11/23/47]`, `test_adversarial_overlaps_drop_exactly_once_at_the_first_link` |
| Matrix completeness meta-tests | `test_defect_matrix_enumerates_every_planted_class`, `test_defect_matrix_detecting_checks_exist` |
| MCAR keep-FIML / MNAR reject+flag; un-reversed halt; absence scan | `test_matrix_mcar_fixtures_keep_fiml[7/21/29]`, `test_matrix_mnar_fixtures_reject_and_flag[7/21/29]`, `test_matrix_un_reversed_item_halts_the_invariant_gate[11/23/47]`, `test_absence_scan_re_executed_over_prep_layer` |

### C2 — Benchmark replication (FR-1502) — **PASS**

Full benchmark set + anchor suites → **76 passed, 0 skipped**.

| # | Anchor | Named tests (all PASSED) |
|---|---|---|
| 1 | MacCallum close-fit power (df=15,N=200→0.378; min-N df=100→132) ≤1e-3 | `test_close_fit_power_reproduces_published_378`, `test_minimum_n_for_power_80_at_df_100_is_132` |
| 2 | Mardia vs published MVN ≤5e-5, Python **and** R independently | `test_mardia_reproduces_published_setosa_values` (Py), `test_assumptions_worker_reproduces_published_mardia` (R) + Py↔R cross-check at 1e-9 |
| 3 | Higher-order CFA worked example (Mplus ex5.6): loadings, α/CR/AVE, 2nd-order reliability | `test_repeated_indicator_reproduces_published_anchors`, `test_repeated_indicator_reports_reliability_at_both_levels` |
| 4 | Published mediation (Mplus ex3.16): bootstrap CIs, fixed seed | `test_point_estimates_match_published`, `test_bootstrap_cis_within_tolerance_of_published` |
| 5 | Monte Carlo power anchors — **exact** to E-R5 R=400 registry (marker present) + negative control | `test_certified_anchor_values` (exact branch taken under marker=1), `test_registry_integrity_unconditional`, `test_band_check_negative_control` |

Benchmark runner + parity-map write/reproduce: `test_runner_replicates_published_set_and_writes_map`,
`test_committed_map_matches_runner_output`, `test_committed_map_is_loadable_and_consumed_by_verification` — PASSED.

**Note (material to why CI cannot substitute):** anchor #5's exact assertion is
gated on `BURHAN_CERTIFIED_WORKSTATION=1` (`test_certified_anchor_values` line
~378). On-workstation it asserts the R=400 values byte-equal; off-workstation
(CI) the same test asserts only the tolerance band. The exact branch was
exercised here.

### C3 — Cross-engine parity map (FR-902/903) — **PASS**

`uv run pytest tests/unit/verify/` → **97 passed, 0 skipped**.

- **Generated, not hand-written; committed with hash.** The runner reproduces
  the committed map byte-for-byte: committed `tests/benchmark/parity_map.json`
  sha256 = regenerated sha256 =
  `1aa5511c69c0e514b19ee9abb724b5ec5dff820c5ebc6d14fc8c69fb9c54e355` (git-tracked).
- **Every declared scope demonstrated by a passing comparison.** The map's 8
  certified scopes each carry their justifying anchor, and each anchor passed in
  C2:

  | Scope | Tolerance | Anchor | Demonstrating C2 test (PASSED) |
  |---|---|---|---|
  | measurement.loadings | 0.001 | mplus-ex5.6 | `test_repeated_indicator_reproduces_published_anchors` |
  | measurement.reliability | 0.0001 | mplus-ex5.6/semtools | `test_repeated_indicator_reports_reliability_at_both_levels` |
  | structural.paths | 0.001 | mplus-ex5.11 | `test_structural_paths_match_published_estimates` + live semopy↔engine `test_semopy_agrees_with_published_engine_values` |
  | structural.fit | 0.001 | mplus-ex5.11 | `test_fit_indices_match_lavaan_reference` |
  | structural.r_squared | 0.001 | mplus-ex5.11/lavaan | `test_r_squared_reported_per_endogenous_construct` |
  | effects.indirect | 0.001 | mplus-ex3.16 | `test_point_estimates_match_published` |
  | effects.indirect_ci | 0.025 | mplus-ex3.16 | `test_bootstrap_cis_within_tolerance_of_published` |
  | power.close_fit | 0.001 | maccallum-1996/jobst-2021 | `test_close_fit_power_reproduces_published_378` |

  Scope of the **live cross-engine** independent path (semopy recompute vs R
  engine, `run_verification`): `structural.paths` (stated precisely — the other
  scopes are demonstrated by their anchor comparisons, not a live semopy
  recompute).
- **Out-of-parity declaration exercised:** `estimator.wlsmv` declared, never
  compared — `test_out_of_parity_scope_is_declared_never_compared`,
  `test_out_of_parity_declaration_is_deduplicated_per_scope`.
- **Halt-multiplier breach → `HALTED_VERIFICATION`:**
  `test_doctored_engine_value_beyond_halt_multiplier_halts`,
  `test_beyond_halt_multiplier_raises_verification_halt`.

### C4 — System integration (IT-1..IT-4) — **FAIL (blocked; out of §6 bounds)**

| IT | Requirement | Result |
|---|---|---|
| IT-1 | Golden study end-to-end → `COMPLETED`; `METHOD_COMPLIANCE_CHECKLIST.md` covers PB-01..19 | **BLOCKED** |
| IT-2 | `burhan rerun` on sealed IT-1 → byte-identical | **BLOCKED** (depends on IT-1) |
| IT-3 | Under-powered fixture → `METHOD_ADVISORY.md` → `COMPLETED_TO_BOUNDARY` | **BLOCKED** |
| IT-4 | C1–C3 wired in CI as permanent regression (FR-1504), green run IDs | **PASS** — CI `certification` job runs golden+benchmark+verify+coverage+R lintr on every push; green at run **28708401860** for `c02d70a` (with off-workstation montecarlo as value-band shadow per E-R5). |

**Root cause (concrete evidence).** The production Stage-1A pipeline is not
wired into `src/`:

- `burhan run <study>` → `no run: production stage implementations land with
  M05+ contracts ... Missing stages: ingest, contract, gate1, power, prep,
  assumptions, measurement, structural, effects, robustness, narrate, gate2,
  package.` — **exit 10 (HALTED_INTEGRITY)**.
- `burhan rerun <run>` → same refusal, **exit 10**.
- `src/burhan/cli/__init__.py::_production_registry()` returns `{}`; the
  orchestrator's `PIPELINE` lists all 13 stages as missing.
- No concrete `Stage` implementations exist in `src/` (only the `Stage`
  Protocol + generic `Orchestrator` engine in `core/orchestrator.py`). The
  checklist/advisory **generators** exist as libraries (`core/compliance.py`,
  `core/advisory.py`) but are not wired into a runnable pipeline.

**Why this cannot be resolved under this gate.** IT-1..IT-3 require a real
Stage-1A run (only the LLM nodes stubbed, per C4). That means 13 concrete stage
adapters + a production registry factory + pipeline wiring in `src/` — a `src/`
behavior change. §6 authorizes **test/fixture code only, no `src/` behavior
changes**; it authorizes scaffolding to *drive* an existing pipeline, not to
*build* the pipeline. So §6 does not cover this, and no contract (TC-01..TC-12)
delivered the stage-wiring — TC-04 delivered the orchestrator engine + the CLI
that deliberately refuses while the registry is empty. This is missing
contracted work, not a harness gap.

**Recommended fix (researcher/Codex).** Issue a contract that wires the 13
production stages into the orchestrator (assembling the existing
prep/stats/verify/compliance/advisory modules into `Stage` adapters + a
non-empty production registry), then re-execute the full battery from §1 per §3.
No `src/` change was made under this gate.

## §5 Evidence pointers

- Commit under test: `c02d70a4f97f50c75606bf15f2c1450894cacbef`.
- CI (IT-4 / FR-1504): run `28708401860` on `c02d70a` — jobs `governed-documents`
  and `certification` both success.
- Parity-map hash: `1aa5511c69c0e514b19ee9abb724b5ec5dff820c5ebc6d14fc8c69fb9c54e355`.
- IT terminal states: `burhan run`/`rerun` → `HALTED_INTEGRITY` (exit 10); no
  sealed run produced (pipeline unwired), so no IT artifact hash roots.

## Deviations

1. **P3 evidence form.** Marker present in the researcher env (check satisfied),
   but `burhan doctor` emits no certified-workstation line (no `src/` reference
   to the marker). Evidenced by direct env inspection, not a doctor line. Doctor
   was not modified (prohibited `src/` change). For Codex to accept the
   substitute evidence, or to treat the missing doctor line as a harness gap for
   a future governed change.
2. **C4 blocker** (see above): production pipeline unwired; out of §6 bounds;
   requires a contract.

## Sign-off

| Role | Verdict | Date | Note |
|---|---|---|---|
| Codex (gate) | *pending* | — | GATE PASS / GATE FAIL with exact deficiencies (§7.1) |
| Researcher (M5) | *blocked* | — | not unlocked; requires GATE PASS after C4 remediation |
