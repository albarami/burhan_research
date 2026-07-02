"""Cross-field validator tests (V1–V7; FR-205/507; study_config.schema.yaml:230-246).

Each validator is a pure function over the model, unit-tested individually
(TC-06 Delivery Notes); every violation is a hard failure naming exactly
its validator — no guessing, no silent defaults.
"""

from __future__ import annotations

from typing import Any

import pytest
from contract_util import EXAMPLE_REVERSED, EXPORTS, example_config

from burhan.contract.validators import (
    cross_check_dictionary,
    v1_construct_refs,
    v2_indicators,
    v3_higher_order,
    v4_model_references,
    v5_hypotheses,
    v6_column_accounting,
    v7_reverse_coding,
    validate_contract,
)
from burhan.core.errors import IntegrityHalt


def test_worked_example_passes_all_validators() -> None:  # AT-M06-3 baseline
    config = example_config()
    validate_contract(config, source_reversed=EXAMPLE_REVERSED, min_designed_items=3)


def test_v1_unresolved_construct_ref() -> None:  # V1
    def mutate(data: dict[str, Any]) -> None:
        data["instrument"]["items"][0]["construct_ref"] = "GHOST"

    with pytest.raises(IntegrityHalt) as excinfo:
        v1_construct_refs(example_config(mutate))
    assert "V1" in excinfo.value.message
    details = str(excinfo.value.to_report()["details"])
    assert "RS1" in details and "GHOST" in details


def test_v1_second_order_ref_is_not_first_order() -> None:  # V1
    def mutate(data: dict[str, Any]) -> None:
        data["instrument"]["items"][0]["construct_ref"] = "ENB"  # second_order

    with pytest.raises(IntegrityHalt) as excinfo:
        v1_construct_refs(example_config(mutate))
    assert "V1" in excinfo.value.message


def test_v2_indicator_missing_from_instrument() -> None:  # V2
    def mutate(data: dict[str, Any]) -> None:
        data["constructs"][0]["indicators"] = ["RS1", "RS2", "GHOST9"]

    with pytest.raises(IntegrityHalt) as excinfo:
        v2_indicators(example_config(mutate), min_designed_items=2)
    assert "V2" in excinfo.value.message
    assert "GHOST9" in str(excinfo.value.to_report()["details"])


def test_v2_designed_pool_below_playbook_minimum() -> None:  # V2
    config = example_config()
    with pytest.raises(IntegrityHalt) as excinfo:
        v2_indicators(config, min_designed_items=4)  # all pools are 3
    assert "V2" in excinfo.value.message
    assert "minimum" in excinfo.value.message


def test_v3_component_not_first_order() -> None:  # V3
    def mutate(data: dict[str, Any]) -> None:
        data["constructs"][2]["components"] = ["RES", "GHOST"]

    with pytest.raises(IntegrityHalt) as excinfo:
        v3_higher_order(example_config(mutate))
    assert "V3" in excinfo.value.message


def test_v3_higher_order_block_iff_second_order() -> None:  # V3
    def drop_block(data: dict[str, Any]) -> None:
        del data["higher_order"]

    with pytest.raises(IntegrityHalt) as excinfo:
        v3_higher_order(example_config(drop_block))
    assert "V3" in excinfo.value.message

    def orphan_block(data: dict[str, Any]) -> None:
        data["constructs"] = [c for c in data["constructs"] if c["level"] == "first_order"]
        data["model"]["exogenous"] = ["RES"]  # keep the model resolvable

    with pytest.raises(IntegrityHalt) as excinfo:
        v3_higher_order(example_config(orphan_block))
    assert "V3" in excinfo.value.message


def test_v4_unresolved_model_reference() -> None:  # V4
    def mutate(data: dict[str, Any]) -> None:
        data["model"]["exogenous"] = ["GHOST"]

    with pytest.raises(IntegrityHalt) as excinfo:
        v4_model_references(example_config(mutate))
    assert "V4" in excinfo.value.message


def test_v4_indirect_hypothesis_requires_resolvable_via() -> None:  # V4
    def drop_via(data: dict[str, Any]) -> None:
        del data["hypotheses"][4]["via"]  # H4b is indirect

    with pytest.raises(IntegrityHalt) as excinfo:
        v4_model_references(example_config(drop_via))
    assert "V4" in excinfo.value.message
    assert "H4b" in str(excinfo.value.to_report()["details"])

    def ghost_via(data: dict[str, Any]) -> None:
        data["hypotheses"][4]["via"] = ["GHOST"]

    with pytest.raises(IntegrityHalt) as excinfo:
        v4_model_references(example_config(ghost_via))
    assert "V4" in excinfo.value.message


def test_v5_duplicate_hypothesis_id() -> None:  # V5
    def mutate(data: dict[str, Any]) -> None:
        data["hypotheses"][1]["id"] = "H1"

    with pytest.raises(IntegrityHalt) as excinfo:
        v5_hypotheses(example_config(mutate))
    assert "V5" in excinfo.value.message
    assert "H1" in str(excinfo.value.to_report()["details"])


def test_v5_indirect_chain_must_be_reachable() -> None:  # V5
    def break_chain(data: dict[str, Any]) -> None:
        # Remove H2 (PU -> ATT): H4b's chain ENB->PU->ATT->INT loses a link.
        data["hypotheses"] = [h for h in data["hypotheses"] if h["id"] != "H2"]

    with pytest.raises(IntegrityHalt) as excinfo:
        v5_hypotheses(example_config(break_chain))
    assert "V5" in excinfo.value.message
    assert "H4b" in str(excinfo.value.to_report()["details"])


def test_v6_delegates_to_the_crosswalk() -> None:  # V6 (TC-05 accounting)
    from ingest_fixture_config import base_config, base_dict

    from burhan.core.artifacts.loader import validate_and_build
    from burhan.core.artifacts.models import StudyConfig

    v6_column_accounting(base_config(), EXPORTS / "adoption_3header.csv")  # passes

    data = base_dict()
    data["data"]["metadata_columns"] = []  # StartDate becomes an orphan
    with pytest.raises(IntegrityHalt) as excinfo:
        v6_column_accounting(
            validate_and_build(StudyConfig, data), EXPORTS / "adoption_3header.csv"
        )
    assert "V6" in excinfo.value.message
    assert "StartDate" in str(excinfo.value.to_report()["details"])


def test_v7_reverse_coding_is_single_source() -> None:  # V7
    config = example_config()
    v7_reverse_coding(config, source_reversed=EXAMPLE_REVERSED)  # passes

    with pytest.raises(IntegrityHalt) as excinfo:  # invented reversal
        v7_reverse_coding(config, source_reversed={"RS3"})  # CU3 unsourced
    assert "V7" in excinfo.value.message
    assert "CU3" in str(excinfo.value.to_report()["details"])

    with pytest.raises(IntegrityHalt) as excinfo:  # dropped reversal
        v7_reverse_coding(config, source_reversed={"RS3", "CU3", "PU1"})
    assert "V7" in excinfo.value.message
    assert "PU1" in str(excinfo.value.to_report()["details"])


def test_dictionary_cross_check_conflict_cited() -> None:  # FR-204 core
    config = example_config()
    conflicting = "RS1 | reverse-coded\n"  # config says RS1 is NOT reversed
    with pytest.raises(IntegrityHalt) as excinfo:
        cross_check_dictionary(config, conflicting)
    assert "FR-204" in excinfo.value.message
    assert "RS1" in str(excinfo.value.to_report()["details"])


def test_dictionary_unknown_item_is_a_conflict() -> None:  # FR-204
    config = example_config()
    with pytest.raises(IntegrityHalt) as excinfo:
        cross_check_dictionary(config, "ZZ9 | reverse-coded\n")
    assert "ZZ9" in str(excinfo.value.to_report()["details"])


def test_dictionary_consistent_passes() -> None:
    config = example_config()
    cross_check_dictionary(config, "RS3 | reverse-coded\nCU3 | reverse-coded\n")


def test_dictionary_non_matching_lines_are_ignored() -> None:
    config = example_config()
    text = "# comment header\n\nRS3 | reverse-coded\nCU3 | reverse-coded\nfree prose line\n"
    cross_check_dictionary(config, text)  # comments/prose don't parse as declarations
