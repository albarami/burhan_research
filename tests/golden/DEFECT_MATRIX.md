# Golden Defect Matrix (TC-08c; FR-1501/1504; NFR-601)

Every planted defect class in the golden certification suite, its ground
truth in the generator, the pipeline check that detects it, and the
permanent regression tests that pin the behavior. The completeness of
this table is itself enforced by
`tests/golden/test_certification.py::test_defect_matrix_enumerates_every_planted_class`
and every referenced test's existence by
`tests/golden/test_certification.py::test_defect_matrix_detecting_checks_exist` —
the enumeration cannot silently rot (FR-1504).

Golden seeds {11, 23, 47} are certified detection-exact with
zero-false-positive clean twins; MCAR fixture seeds {7, 21, 29} are
pinned (seed 13 falsely rejects MCAR at p = .012 — the statistic's
designed 5% false-rejection rate, not a defect). Provenance: FR-501–507,
FR-1501 (02_REQUIREMENTS.md), AT-M08-1..8 (08_BUILD_SPEC.md M08),
PB-02/03/04 (CB_SEM_PLAYBOOK v1.0).

| Class id | Planted by (generator) | Detecting check | AT | Regression tests |
|---|---|---|---|---|
| duplicates | `build_golden`: repeated ResponseId (`R_001#2`, exact row copy) and an identical-model-vector twin (`R_034`) | duplicates link, policy keys `prep.duplicates.keys`, drop-later-keep-first; screening `duplicates` | AT-M08-1/3 | `tests/unit/prep/test_pipeline.py::test_detects_all_duplicates_by_policy_keys`; `tests/golden/test_certification.py::test_matrix_detection_is_exact_per_class` |
| attention_fails | `build_golden`: `R_035` answers 3 where Q9_4 expects 5 | attention link, `prep.attention_checks.action_on_fail`; screening `attention_fails` | AT-M08-1 | `tests/unit/prep/test_pipeline.py::test_detects_the_attention_failure`; `tests/golden/test_certification.py::test_matrix_detection_is_exact_per_class` |
| straight_liners | `build_golden`: `R_036` constant across the first 8 model items; clean runs capped at 5 by construction | zero-variance contiguous answered runs ≥ `prep.straightliner.min_block_length`; screening `straight_liners` | AT-M08-1 | `tests/unit/prep/test_pipeline.py::test_detects_the_straight_liner`; `tests/unit/prep/test_pipeline.py::test_straightliner_block_length_is_read_from_policy` |
| out_of_range | `build_golden`: `R_037` RS2=9, `R_038` CU2=0; unparseable cells same class | range enforcement: cell nulled, case kept (FR-506 has no range link; I1 must hold post-prep); screening `out_of_range` `{case, item}` only | AT-M08-1/5 | `tests/unit/prep/test_pipeline.py::test_detects_out_of_range_cells_as_metadata`; `tests/unit/prep/test_pipeline_edges.py::test_unparseable_cell_is_out_of_range_metadata` |
| un_reversed | `build_golden` defect build stores CU4 unflipped although declared reverse-coded; clean twin stores it correctly | sign-flip screening (detection) + invariant I2 (halting gate) — caught even though the declaration is correct | AT-M08-1/8 | `tests/unit/prep/test_pipeline.py::test_detects_the_un_reversed_item_by_sign_flip`; `tests/unit/prep/test_invariants.py::test_i2_un_reversed_item_trips_sign_flip`; `tests/golden/test_certification.py::test_matrix_un_reversed_item_halts_the_invariant_gate` |
| engineered_missingness | `build_golden`: blank cells on `R_039` (1) and `R_040` (4); `build_missingness_fixture` MCAR scatter / MNAR value-dependent silence | missing-cell census on the profiled sample before range nulling; `prep.item_missing_flag_pct` item flags; Little's MCAR + pattern map before treatment | AT-M08-1/7 | `tests/unit/prep/test_pipeline.py::test_missing_cell_census_matches_engineered_missingness`; `tests/golden/test_certification.py::test_matrix_mcar_fixtures_keep_fiml`; `tests/golden/test_certification.py::test_matrix_mnar_fixtures_reject_and_flag` |
| partials_recovered | `build_golden`: `R_039` at 11/12 ≈ 91.7% ≥ policy 90% | completion profiling on model items, `prep.inclusion_threshold`; profile lists every partial with % and disposition | AT-M08-2 | `tests/unit/prep/test_pipeline.py::test_completion_profile_lists_every_partial_with_pct`; `tests/unit/prep/test_pipeline.py::test_recovery_threshold_is_read_from_policy_not_code` |
| partials_dropped | `build_golden`: `R_040` at 8/12 ≈ 66.7% < policy 90% | partial_recovery link drop; profile disposition `dropped` | AT-M08-2/3 | `tests/unit/prep/test_pipeline.py::test_completion_profile_lists_every_partial_with_pct`; `tests/golden/test_certification.py::test_matrix_partial_profile_is_complete` |
| known_outliers | `build_golden`: `R_041` coherent extreme responder (reversed items stored mirrored; no constant run ≥ 8); clean values clamped to 2..6 so only planted cases can cross the criterion | univariate \|z\| > `prep.outliers.univariate_z`; Mahalanobis D² > χ²(1−`prep.outliers.mahalanobis_p`); treatment per policy (retain flags, remove drops) | AT-M08-1 | `tests/unit/prep/test_pipeline.py::test_detects_exactly_the_known_outlier`; `tests/unit/prep/test_pipeline.py::test_remove_with_sensitivity_drops_flagged_outliers`; `tests/unit/prep/test_pipeline_edges.py::test_mahalanobis_criterion_flags_pattern_breaking_case` |
| adversarial_overlaps | `build_adversarial`: id-dup ∧ attention-fail; straight-liner ∧ out-of-range; attention-fail ∧ dropped-partial; outlier ∧ recovered-partial (survives) | each case leaves exactly once at the first applicable link; the survivor is recovered AND flagged-retained; chain sums exactly | AT-M08-3 | `tests/golden/test_certification.py::test_adversarial_overlaps_drop_exactly_once_at_the_first_link`; `tests/unit/prep/test_pipeline.py::test_adversarial_overlap_drops_each_case_exactly_once` |
| n_chain_double_count | hostile input to the accountant (same case in two links, or twice within one link's dropped/recovered list) | `NChainAccountant` halts `IntegrityHalt` naming link + case before any link is constructed; serialized links always satisfy leaving = entering − dropped_n | AT-M08-3 | `tests/unit/prep/test_n_chain.py::test_planted_double_count_halts`; `tests/unit/prep/test_n_chain.py::test_duplicate_case_within_one_dropped_list_halts`; `tests/unit/prep/test_n_chain.py::test_no_serialized_link_can_break_the_leaving_identity` |
| dual_path_divergence | doctored R result (one cell ±1, missing/observed flip, column order, case set, chain counts); live R-side mutation evidence in PR #9 | `reconcile_prep` at `verification.prep_cell_tolerance` (exactly 0) → `VerificationHalt` naming row/column, metadata only | AT-M08-6 | `tests/unit/prep_r/test_reconciler.py::test_planted_one_cell_divergence_halts_naming_row_and_column`; `tests/golden/test_certification.py::test_matrix_dual_path_parity`; `tests/golden/test_certification.py::test_adversarial_dual_path_parity` |
| malformed_r_cell | doctored R result: `"not-a-number"` in one cell | typed guard before comparison → `VerificationHalt`, `{kind, row, column}` only | AT-M08-6 | `tests/unit/prep_r/test_reconciler.py::test_nonnumeric_r_cell_halts_typed_naming_row_and_column` |
| clean_twin | `build_golden(seed, with_defects=False)` — same draws, no plants, CU4 correctly reversed | zero detections in every class, zero drops at every link, invariants pass end to end (the zero-false-positive control) | AT-M08-1 | `tests/unit/prep/test_pipeline.py::test_clean_twin_has_zero_detections_anywhere`; `tests/golden/test_certification.py::test_matrix_clean_twins_have_zero_detections` |

## Absence proofs (FR-505; AT-M08-4)

No mean-substitution and no synthetic-case code path exists anywhere in
`src/burhan/prep/` — token scans, public-surface introspection, and
behavioral subset/missing-stays-missing tests:
`tests/unit/prep/test_absence.py::test_no_mean_substitution_code_path`,
`tests/unit/prep/test_absence.py::test_no_synthetic_case_code_path`,
`tests/unit/prep/test_absence.py::test_behavior_no_new_cases_and_missing_stays_missing`,
re-executed over the whole layer by
`tests/golden/test_certification.py::test_absence_scan_re_executed_over_prep_layer`.

## Permanent regression wiring (FR-1504)

- `tests/golden/` is collected by the default `uv run pytest` battery
  (`testpaths = ["tests"]`) — every local gate run re-executes the suite.
- CI (`.github/workflows/ci.yml`, job `certification`) runs ruff, format
  check, mypy strict, the full pytest battery including this suite and
  the dual-path R parity tests (R + renv restored from
  `workers/r/renv.lock`), and lintr on the R workers, on every push and
  pull request. The suite is a permanent regression gate; removing it
  breaks CI.
