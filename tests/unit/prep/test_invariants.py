"""Post-preparation invariants I1–I7 (AT-M08-5/8; FR-507).

Each of the seven assertions has a fixture that trips exactly it — earlier
invariants pass on that fixture, the named one halts. The baseline frame
(clean golden twin, reversal applied) passes all seven.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from generator import build_golden

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.prep.invariants import assert_invariants


def _config(mutate: Any = None) -> StudyConfig:
    data = build_golden(11).config
    if mutate is not None:
        mutate(data)
    return validate_and_build(StudyConfig, data)


def _frame(config: StudyConfig, seed: int = 5, n: int = 40) -> pd.DataFrame:
    """A clean prepared frame: reversal applied, construct-consistent."""
    rng = np.random.default_rng(seed)
    constructs = {c.code: c.indicators or [] for c in config.constructs if c.indicators}
    columns: dict[str, list[float]] = {i.code: [] for i in config.instrument.items}
    for _ in range(n):
        latents = {code: rng.normal(0.0, 0.55) for code in constructs}
        for construct, indicators in constructs.items():
            for code in indicators:
                value = 4.0 + latents[construct] + rng.normal(0.0, 0.45)
                columns[code].append(float(np.clip(round(value), 1, 7)))
    index = pd.Index([f"R_{i:03d}" for i in range(1, n + 1)], name="case")
    return pd.DataFrame(columns, index=index)


def test_baseline_prepared_frame_passes_all_seven() -> None:
    config = _config()
    assert_invariants(_frame(config), config, min_items=2)


def test_i1_out_of_range_value_trips_exactly_ranges() -> None:  # AT-M08-5
    config = _config()
    frame = _frame(config)
    frame.loc["R_003", "RS2"] = 9.0
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(frame, config, min_items=2)
    assert excinfo.value.message.startswith("I1")
    details = str(excinfo.value.to_report()["details"])
    assert "RS2" in details and "R_003" in details
    assert "9.0" not in details  # metadata only — never respondent values


def test_i2_un_reversed_item_trips_sign_flip() -> None:  # AT-M08-5 + AT-M08-8
    config = _config()  # CU4 declared reverse-coded — correctly, per contract
    frame = _frame(config)
    # the data arrives un-reversed although the declaration is right:
    # after the pipeline's reversal the item anti-correlates with siblings.
    frame["CU4"] = 8.0 - frame["CU4"]
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(frame, config, min_items=2)
    assert excinfo.value.message.startswith("I2")
    assert "CU4" in str(excinfo.value.to_report()["details"])


def test_i3_missing_item_column_trips_unmapped_items() -> None:  # AT-M08-5
    config = _config()
    frame = _frame(config).drop(columns=["IN4"])
    with pytest.raises(IntegrityHalt) as excinfo:
        # min_items=3 keeps I6 satisfied with INT at 3 of 4 — only I3 trips
        assert_invariants(frame, config, min_items=3)
    assert excinfo.value.message.startswith("I3")
    assert "IN4" in str(excinfo.value.to_report()["details"])


def test_i4_orphan_frame_column_trips() -> None:  # AT-M08-5
    config = _config()
    frame = _frame(config)
    frame["GHOST"] = 4.0
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(frame, config, min_items=2)
    assert excinfo.value.message.startswith("I4")
    assert "GHOST" in str(excinfo.value.to_report()["details"])


def test_i5_unresolvable_hypothesis_path_trips() -> None:  # AT-M08-5
    def declare_ghost_path(data: dict[str, Any]) -> None:
        data["hypotheses"].append(
            {"id": "H9", "effect": "direct", "from": "INT", "to": "GHOST", "sign": "positive"}
        )
        data["model"]["endogenous"] = ["CUL", "INT", "GHOST"]

    config = _config(declare_ghost_path)
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(_frame(config), config, min_items=2)
    assert excinfo.value.message.startswith("I5")
    assert "H9" in str(excinfo.value.to_report()["details"])


def test_i6_construct_below_minimum_items_trips() -> None:  # AT-M08-5
    config = _config()
    frame = _frame(config)
    # NaN a full column: RES drops to 3 informative items under min_items=4.
    frame["RS2"] = np.nan
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(frame, config, min_items=4)
    assert excinfo.value.message.startswith("I6")
    assert "RES" in str(excinfo.value.to_report()["details"])


def test_i7_second_order_without_higher_order_block_trips() -> None:  # AT-M08-5
    def declare_incomplete_second_order(data: dict[str, Any]) -> None:
        # A second-order construct with no higher_order specification: the
        # frame and every first-order structure stay intact, so I1–I6 pass
        # and exactly I7 trips (post-prep re-assertion, independent of V3).
        data["constructs"].append(
            {
                "code": "ENB",
                "name": "Enablement",
                "level": "second_order",
                "measurement": "reflective",
                "components": ["RES", "CUL"],
            }
        )

    config = _config(declare_incomplete_second_order)
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(_frame(config), config, min_items=2)
    assert excinfo.value.message.startswith("I7")
    assert "ENB" in str(excinfo.value.to_report()["details"])


def test_invariants_run_in_order_and_name_exactly_one() -> None:
    config = _config()
    frame = _frame(config)
    frame.loc["R_002", "RS1"] = 0.0  # I1
    frame["GHOST"] = 4.0  # would be I4
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(frame, config, min_items=2)
    assert excinfo.value.message.startswith("I1")  # first defect wins, named alone
