"""Python preparation pipeline (AT-M08-1/2/3/8; FR-501/502/506).

Detection is measured against the generator's ground-truth manifest, class
by class, with zero false positives on the clean twin. Every screening
rule reads policy paths — proven by swapping policy values, never code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from generator import build_golden

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.core.policy import Policy
from burhan.prep.invariants import assert_invariants
from burhan.prep.py_impl.pipeline import run_prep

REPO = Path(__file__).resolve().parents[3]


def _policy(tmp_path: Path | None = None, mutate: Any = None) -> Policy:
    template = REPO / "policy" / "decision_policy.template.yaml"
    if mutate is None:
        return Policy.load(template, mode="certification")
    assert tmp_path is not None
    data = yaml.safe_load(template.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return Policy.load(path, mode="certification")


@pytest.fixture(scope="module")
def golden_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    directory = tmp_path_factory.mktemp("golden")
    golden = build_golden(11, with_defects=True)
    config = validate_and_build(StudyConfig, golden.config)
    template = REPO / "policy" / "decision_policy.template.yaml"
    policy = Policy.load(template, mode="certification")
    result = run_prep(golden.write(directory), config, policy)
    return golden, config, result


# -- AT-M08-1: 100% detection by class; zero false positives on the clean twin --------


def test_detects_all_duplicates_by_policy_keys(golden_run: Any) -> None:  # AT-M08-1
    golden, _, result = golden_run
    expected = {entry["case"] for entry in golden.manifest["duplicates"]}
    link = {link.name: link for link in result.n_chain.links}["duplicates"]
    assert set(link.dropped_cases) == expected
    detected = {entry["case"] for entry in result.screening["duplicates"]}
    assert detected == expected


def test_detects_the_attention_failure(golden_run: Any) -> None:  # AT-M08-1
    golden, _, result = golden_run
    expected = {entry["case"] for entry in golden.manifest["attention_fails"]}
    assert {e["case"] for e in result.screening["attention_fails"]} == expected


def test_detects_the_straight_liner(golden_run: Any) -> None:  # AT-M08-1
    golden, _, result = golden_run
    expected = {entry["case"] for entry in golden.manifest["straight_liners"]}
    assert {e["case"] for e in result.screening["straight_liners"]} == expected


def test_detects_out_of_range_cells_as_metadata(golden_run: Any) -> None:  # AT-M08-1
    golden, _, result = golden_run
    expected = {(e["case"], e["item"]) for e in golden.manifest["out_of_range"]}
    detected = {(e["case"], e["item"]) for e in result.screening["out_of_range"]}
    assert detected == expected
    assert all(set(e) == {"case", "item"} for e in result.screening["out_of_range"])


def test_detects_the_un_reversed_item_by_sign_flip(golden_run: Any) -> None:  # AT-M08-1
    golden, _, result = golden_run
    expected = {entry["item"] for entry in golden.manifest["un_reversed"]}
    assert {e["item"] for e in result.screening["reverse_coding_violations"]} == expected


def test_missing_cell_census_matches_engineered_missingness(golden_run: Any) -> None:
    golden, _, result = golden_run  # AT-M08-1
    expected = {(e["case"], e["item"]) for e in golden.manifest["engineered_missingness"]}
    detected = {(e["case"], e["item"]) for e in result.screening["missing_cells"]}
    assert detected == expected


def test_detects_exactly_the_known_outlier(golden_run: Any) -> None:  # AT-M08-1
    golden, _, result = golden_run
    expected = {entry["case"] for entry in golden.manifest["known_outliers"]}
    assert {e["case"] for e in result.outliers["flagged"]} == expected
    assert result.outliers["treatment"] == "retain_with_sensitivity"


def test_clean_twin_has_zero_detections_anywhere(tmp_path: Path) -> None:  # AT-M08-1
    clean = build_golden(11, with_defects=False)
    config = validate_and_build(StudyConfig, clean.config)
    result = run_prep(clean.write(tmp_path), config, _policy())
    assert all(not entries for entries in result.screening.values())
    assert result.outliers["flagged"] == []
    assert result.n_chain.raw_n == result.n_chain.final_n == 32
    assert all(link.dropped_n == 0 for link in result.n_chain.links)
    assert_invariants(result.frame, config, min_items=2)  # clean end to end


# -- AT-M08-2: partial recovery from policy ------------------------------------------


def test_completion_profile_lists_every_partial_with_pct(golden_run: Any) -> None:
    golden, _, result = golden_run  # AT-M08-2
    profile = {entry["case"]: entry for entry in result.completion_profile["partials"]}
    recovered = golden.manifest["partials_recovered"][0]["case"]
    dropped = golden.manifest["partials_dropped"][0]["case"]
    assert set(profile) == {recovered, dropped}
    assert profile[recovered]["completion_pct"] == pytest.approx(91.67, abs=0.01)
    assert profile[recovered]["disposition"] == "recovered"
    assert profile[dropped]["completion_pct"] == pytest.approx(66.67, abs=0.01)
    assert profile[dropped]["disposition"] == "dropped"
    assert result.completion_profile["threshold_pct"] == 90
    assert result.completion_profile["basis"] == "model_items"


def test_recovery_threshold_is_read_from_policy_not_code(tmp_path: Path) -> None:
    def raise_threshold(data: dict[str, Any]) -> None:  # AT-M08-2
        data["prep"]["inclusion_threshold"]["min_completion_pct"] = 95

    golden = build_golden(11, with_defects=True)
    config = validate_and_build(StudyConfig, golden.config)
    result = run_prep(golden.write(tmp_path), config, _policy(tmp_path, raise_threshold))
    profile = {entry["case"]: entry for entry in result.completion_profile["partials"]}
    recovered_case = golden.manifest["partials_recovered"][0]["case"]
    assert profile[recovered_case]["disposition"] == "dropped"  # 91.7% < 95%


def test_straightliner_block_length_is_read_from_policy(tmp_path: Path) -> None:
    def widen_block(data: dict[str, Any]) -> None:
        data["prep"]["straightliner"]["min_block_length"] = 12

    golden = build_golden(11, with_defects=True)
    config = validate_and_build(StudyConfig, golden.config)
    result = run_prep(golden.write(tmp_path), config, _policy(tmp_path, widen_block))
    assert result.screening["straight_liners"] == []  # the 8-run no longer qualifies


# -- AT-M08-3: chain exactness on golden and adversarial overlap ----------------------


def test_chain_sums_exactly_on_golden(golden_run: Any) -> None:  # AT-M08-3
    _, _, result = golden_run
    chain = result.n_chain
    assert [link.name for link in chain.links] == [
        "consent",
        "duplicates",
        "attention_checks",
        "straight_liners",
        "partial_recovery",
        "outlier_policy",
    ]
    assert chain.raw_n == 41
    assert chain.final_n == 36
    for link in chain.links:
        assert link.leaving == link.entering - link.dropped_n
    total_dropped = sum(link.dropped_n for link in chain.links)
    assert chain.raw_n - total_dropped == chain.final_n
    assert set(result.frame.index) == set(chain.final_cases)


def test_adversarial_overlap_drops_each_case_exactly_once(tmp_path: Path) -> None:
    # A case that is BOTH a ResponseId duplicate and an attention failure
    # leaves at the first applicable link only (AT-M08-3).
    golden = build_golden(11, with_defects=True)
    overlap = list(golden.rows[3])  # R_001's row again...
    overlap[14] = "2"  # ...now also failing the attention check
    golden.rows.append(overlap)
    config = validate_and_build(StudyConfig, golden.config)
    result = run_prep(golden.write(tmp_path), config, _policy())
    links = {link.name: link for link in result.n_chain.links}
    assert "R_001#3" in links["duplicates"].dropped_cases
    assert "R_001#3" not in links["attention_checks"].dropped_cases
    assert result.n_chain.raw_n == 42
    assert result.n_chain.final_n == 36


# -- AT-M08-8: the golden un-reversed item halts at the invariant gate ----------------


def test_un_reversed_golden_item_halts_the_invariant_gate(golden_run: Any) -> None:
    golden, config, result = golden_run  # AT-M08-8
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(result.frame, config, min_items=2)
    assert excinfo.value.message.startswith("I2")
    assert "CU4" in str(excinfo.value.to_report()["details"])


# -- policy-driven outlier treatment and hygiene --------------------------------------


def test_remove_with_sensitivity_drops_flagged_outliers(tmp_path: Path) -> None:
    def remove_policy(data: dict[str, Any]) -> None:
        data["prep"]["outliers"]["treatment"] = "remove_with_sensitivity"

    golden = build_golden(11, with_defects=True)
    config = validate_and_build(StudyConfig, golden.config)
    result = run_prep(golden.write(tmp_path), config, _policy(tmp_path, remove_policy))
    outlier_case = golden.manifest["known_outliers"][0]["case"]
    links = {link.name: link for link in result.n_chain.links}
    assert outlier_case in links["outlier_policy"].dropped_cases
    assert result.n_chain.final_n == 35
    assert result.outliers["sensitivity_comparison_required"] is True


def test_artifacts_carry_no_respondent_values(golden_run: Any) -> None:
    _, _, result = golden_run
    text = str(result.screening) + str(result.completion_profile) + str(result.outliers)
    # stored responses are 1-7 single digits; artifacts speak in cases/items/counts
    for leaked in ("'4'", "'5'", "'6'", "'7'", "'1'", "'2'", "'3'"):
        assert leaked not in text


def test_prepared_frame_is_reversed_and_typed(golden_run: Any) -> None:
    golden, config, result = golden_run
    assert list(result.frame.columns) == [i.code for i in config.instrument.items]
    # RS4 was stored flipped at collection; preparation flips it back:
    # its correlation with RES siblings is positive again.
    siblings = result.frame[["RS1", "RS2", "RS3"]].mean(axis=1)
    assert result.frame["RS4"].corr(siblings) > 0


def test_runs_are_deterministic(golden_run: Any, tmp_path: Path) -> None:
    golden, config, result = golden_run
    again = run_prep(golden.write(tmp_path), config, _policy())
    assert again.n_chain.to_payload() == result.n_chain.to_payload()
    assert again.screening == result.screening
    assert again.missingness == result.missingness
    assert again.outliers == result.outliers
    assert again.frame.equals(result.frame)
