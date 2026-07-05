# Burhān — Certification Report (M5 gate execution)

**Instrument:** `docs/11_CERTIFICATION_PLAN.md` (approved as M5 gate instrument).
**Executed by:** Claude Code (implementer), on the certified workstation.
**Commit under test:** `e8b324fdde688ceafb839f1aa785ca837400ea21` (branch `main`).
**Date (UTC):** 2026-07-05.
**Re-run of:** the 2026-07-04 GATE FAIL at `c02d70a` (blocked at C4). See Appendix A.

## Verdict (for Codex per §7)

**All battery lines pass on the certified workstation — submitted for Codex's
GATE verdict.** P1–P5 and C1–C4 each pass. The C4 blocker from the prior run is
resolved: the production Stage-1A pipeline is now wired into `src/` by contract
**TC-15** (PR #17, squash-merged to `main` as `a0c0cde`), so IT-1..IT-3 execute
end-to-end and `burhan run --certification` reaches `COMPLETED`. The P3
evidence-form deviation is also resolved: `burhan doctor` now emits the
certified-workstation line the plan names.

Per §3 the gate is binary and this battery was re-executed in full from §1.
Per §7 the GATE PASS/FAIL verdict is Codex's to post, and the researcher records
the M5 signature **only after** a GATE PASS — this report does **not** record it.

---

## §1 Preflight (P1–P5)

| # | Check | Result | Evidence |
|---|---|---|---|
| P1 | `git status` clean on `main`; HEAD SHA recorded | **PASS** | clean tree; HEAD `e8b324fdde688ceafb839f1aa785ca837400ea21`; independently confirmed by doctor `git_state: clean at e8b324fdde68` |
| P2 | `uv run burhan doctor` green | **PASS** | exit 0; 9 `[PASS]`, 0 `[FAIL]`; final verdict `PASS`; `provider_connectivity [SKIP]` (deferred until LLM adapters land, TC-06/M06 — no network outside adapters, by design) |
| P3 | `BURHAN_CERTIFIED_WORKSTATION=1` present (evidence: doctor line) | **PASS** | doctor emits `[PASS] certified_workstation: BURHAN_CERTIFIED_WORKSTATION=1 (certified)`. The prior run's evidence-form deviation (no doctor line) is **resolved** — TC-15 added the marker check to `burhan doctor`. |
| P4 | `uv.lock` + `workers/r/renv.lock` hashes | **PASS** | `uv.lock` `ba58ef5b55a3f431b45b1f0ad860d5b780d38e7b5cf2a841b01d8807f2ab8e0e`; `workers/r/renv.lock` `069c2b33829cb0fd2cc7bda578b94b86d22ec3c333bcf6376244c061af0f3306` |
| P5 | Playbook / policy / registry hashes | **PASS** | playbook `playbooks/CB_SEM_PLAYBOOK_v1.0.yaml` `a88fab40d873a4c7a65b87d41704f55eca3a7ad0c88cdc4e5a3ea50d60820fe1`; policy `policy/decision_policy.template.yaml` `250539f785826ae63414f55eed746dff5f09f271599ab340fa8ed4523f0a28e3`; registry `policy/protected_decisions.registry.yaml` `e05357eefb7545310ff429692a0a62cd0c3af6b0528cb732726a38c504f32bc6` |

*P5 path note:* the governed artifacts are tracked at the repo-root paths above
(`playbooks/`, `policy/`); the prior report labelled them `docs/06_*`/`docs/07_*`
in error. The bytes — and therefore the hashes — are unchanged.

All battery suites below were run with the certified environment:
`source ~/.config/burhan/.env` + determinism pins (`TZ=UTC LC_ALL=C.UTF-8
PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`) +
`BURHAN_CERTIFIED_WORKSTATION=1`, `-p no:cacheprovider`.

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

Benchmark set + power/effects anchor suites
(`tests/benchmark/ tests/unit/stats_power/ tests/unit/stats_effects/test_effects_benchmark.py`)
→ **86 passed, 0 skipped**. (Superset of the prior run's 76 — the lane now
carries the full `stats_power` suite; all five published anchors are present and
passed.)

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
gated on `BURHAN_CERTIFIED_WORKSTATION=1` (`test_certified_anchor_values`).
On-workstation it asserts the R=400 values byte-equal; off-workstation (CI) the
same test asserts only the tolerance band. The exact branch was exercised here.

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

### C4 — System integration (IT-1..IT-4) — **PASS**

`uv run pytest tests/integration/` → **11 passed, 0 skipped** (457.78s), covering
the plan's IT-1..IT-3 plus the TC-15 CLI/manifest acceptance tests; the plan's
IT-4 (regression permanence, FR-1504) is CI-evidenced by the green run IDs below.

| IT | Requirement | Result | Evidence |
|---|---|---|---|
| IT-1 | Golden study end-to-end → `COMPLETED`; Stage-1A steps carry store-backed evidence | **PASS** | `test_it1_dry_run.py::test_golden_study_runs_end_to_end_to_completed`, `::test_completed_stage_1a_steps_have_store_backed_evidence` (AT-M15-1) |
| IT-2 | `burhan rerun` on sealed run → byte-identical; identity assertion catches nondeterminism | **PASS** | `test_it2_rerun.py::test_real_pipeline_reruns_byte_identical`, `::test_identity_assertion_catches_a_nondeterministic_stub` (AT-M15-2) |
| IT-3 | Under-powered fixture → advisory boundary → `COMPLETED_TO_BOUNDARY` | **PASS** | `test_it3_boundary.py::test_underpowered_study_stops_at_the_advisory_boundary` (AT-M15-3) |
| IT-4 | C1–C3 wired in CI as permanent regression (FR-1504), green run IDs | **PASS** | CI `certification` job runs golden+benchmark+verify+coverage+R lintr on every push to `main`, green at run **28743737378** (squash `a0c0cde`) and run **28743763894** (sign-off `e8b324f`); off-workstation montecarlo as value-band shadow per E-R5 |

Additional `tests/integration/` coverage (delivered by TC-15, all PASSED),
strengthening C4 beyond the plan's minimum:

- `test_it4_cli_run.py::test_certification_run_reaches_completed` — `burhan run --certification` reaches `COMPLETED` (AT-M15-4).
- `test_it5_manifest_hash.py::test_manifest_hashes_track_their_own_source_files` — manifest `study_config`/`decision_policy` hashes track their own source (NFR-102).
- `test_it6_cli_certification.py::test_run_command_reaches_completed_via_cli`, `::test_rerun_command_is_byte_identical_via_cli` — the Typer CLI run/rerun exercised end-to-end (byte-identical rerun, NFR-101).

**Resolution of the prior C4 blocker.** The 2026-07-04 run failed C4 because the
production Stage-1A pipeline was unwired in `src/` and wiring it exceeded §6's
bounds (test/fixture only), so it required a contract. That contract —
**TC-15** — was issued, implemented, reviewed, APPROVED, and squash-merged to
`main` as `a0c0cde` (PR #17): it wired the 13-stage DAG into the orchestrator,
added the concrete Stage adapters and a non-empty production registry, made
`burhan run --certification` execute to `COMPLETED`, sealed the rerun clock
(NFR-101), hashed the actual consumed sources into the manifest (NFR-102), and
added the certified-workstation doctor line. No `src/` change is made under this
gate; the only governed-document change is adding this report (§6).

## §5 Evidence pointers

- Commit under test: `e8b324fdde688ceafb839f1aa785ca837400ea21`.
- CI (IT-4 / FR-1504): runs `28743737378` (`a0c0cde`) and `28743763894`
  (`e8b324f`) on `main` — `governed-documents` and `certification` jobs both success.
- Parity-map hash: `1aa5511c69c0e514b19ee9abb724b5ec5dff820c5ebc6d14fc8c69fb9c54e355`.
- Battery lane results (certified workstation): C1 `tests/golden/` 32 passed;
  C2 benchmark+power/effects anchors 86 passed; C3 `tests/unit/verify/` 97 passed;
  C4 `tests/integration/` 11 passed.
- Governed-artifact hashes: P4/P5 rows above.

## Appendix A — Re-run delta from the 2026-07-04 GATE FAIL (§8 permanence)

| Item | 2026-07-04 (`c02d70a`) | 2026-07-05 (`e8b324f`) | What changed |
|---|---|---|---|
| P3 | PASS (deviation: no doctor line; env-inspection substitute) | PASS (doctor line present) | TC-15 added the `certified_workstation` check to `burhan doctor` |
| C4 IT-1 | BLOCKED (pipeline unwired) | PASS | TC-15 wired the 13-stage pipeline; golden study reaches `COMPLETED` |
| C4 IT-2 | BLOCKED (depended on IT-1) | PASS | sealed-base rerun is byte-identical |
| C4 IT-3 | BLOCKED | PASS | under-powered fixture reaches `COMPLETED_TO_BOUNDARY` |
| C4 IT-4 | PASS (CI green, unwired src) | PASS (CI green, wired src) | run IDs updated to the merged-TC-15 commits |
| C1/C2/C3 | PASS (32 / 76 / 97) | PASS (32 / 86 / 97) | unchanged; C2 lane broadened to the full `stats_power` suite |

## Deviations

None material. Two clarifications carried into this report:

1. **P5 path labels corrected.** Governed artifacts are tracked at
   `playbooks/` and `policy/` (repo root); the prior report's `docs/06_*`/`docs/07_*`
   labels were wrong. Bytes and hashes are unchanged.
2. **C2 lane is a superset** of the prior run (86 vs 76 tests) because it now
   includes the complete `tests/unit/stats_power/` suite; all five published
   anchors are present and passed. Reported as run so Codex can reproduce.

## Sign-off

| Role | Verdict | Date | Note |
|---|---|---|---|
| Codex (gate) | *pending* | — | GATE PASS / GATE FAIL with exact deficiencies (§7.1) |
| Researcher (M5) | *not recorded* | — | recorded by the researcher only after a Codex GATE PASS (§7); intentionally left blank |
