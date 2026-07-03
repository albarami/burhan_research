"""A priori power (AT-M09-1/2; FR-401/403; PB-01).

Known-answer anchors, with provenance:

- Close-fit power (df=15, N=200, ε0=.05, εa=.08, α=.05) = 0.378 —
  published in Jobst, Bader & Moshagen (2021), Behavior Research Methods
  53:1385–1406 (PMC8367885), Example 3: "the power to reject close fit
  when in reality there is not-close fit equals 0.378", computed by the
  MacCallum–Browne–Sugawara (1996) method.
- Minimum N for power .80 at df=100 is 132 — MacCallum et al.'s
  minimum-N result as reproduced in the applied literature (e.g. the
  sample-size review literature citing their Table 4; corroborated
  computationally here to the unit).

The N:q thresholds come from the governed playbook criterion (PB-01
``n_to_q_target``: "10:1 / 5:1"), never from code literals.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from generator import build_golden

from burhan.core.advisory import Advisory
from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import AdvisoryStop, IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.core.provenance import Provenance
from burhan.stats.power import (
    close_fit_power,
    free_parameter_count,
    minimum_n_close_fit,
    model_df,
    n_q_evaluation,
    power_gate,
    power_store_rows,
)

REPO = Path(__file__).resolve().parents[3]


class FixedClock:
    def now(self) -> dt.datetime:
        return dt.datetime(2026, 7, 3, 9, 0, 0, tzinfo=dt.UTC)


def _playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def _golden_config() -> StudyConfig:
    return validate_and_build(StudyConfig, build_golden(11).config)


def _example_config() -> StudyConfig:
    import yaml

    data = yaml.safe_load(
        (REPO / "schemas" / "study_config.example.yaml").read_text(encoding="utf-8")
    )
    return validate_and_build(StudyConfig, data)


# -- AT-M09-1: MacCallum close-fit anchors ---------------------------------------------


def test_close_fit_power_reproduces_published_378() -> None:  # AT-M09-1
    assert close_fit_power(df=15, n=200) == pytest.approx(0.378, abs=0.001)


def test_minimum_n_for_power_80_at_df_100_is_132() -> None:  # AT-M09-1
    assert minimum_n_close_fit(df=100) == 132
    assert close_fit_power(df=100, n=132) >= 0.80
    assert close_fit_power(df=100, n=131) < 0.80


def test_close_fit_power_is_monotone_in_n_and_df() -> None:
    assert close_fit_power(df=50, n=400) > close_fit_power(df=50, n=200)
    assert close_fit_power(df=100, n=200) > close_fit_power(df=25, n=200)


def test_close_fit_power_guards_halt_typed() -> None:
    with pytest.raises(IntegrityHalt):
        close_fit_power(df=0, n=200)
    with pytest.raises(IntegrityHalt):
        close_fit_power(df=50, n=1)
    with pytest.raises(IntegrityHalt):
        close_fit_power(df=50, n=200, rmsea0=0.08, rmsea_a=0.05)  # H0 must be below Ha


# -- free parameters and model df (documented marker-scaling convention) ---------------


def test_free_parameter_count_golden_hand_derived() -> None:
    # 12 items, 3 first-order constructs (marker fixed each), exogenous {RES},
    # endogenous {CUL, INT}, 2 direct paths:
    # loadings 12-3=9 + errors 12 + latent (co)variances/disturbances 3 +
    # exogenous covariances C(1,2)=0 + paths 2 = 26
    assert free_parameter_count(_golden_config()) == 26


def test_model_df_golden() -> None:
    assert model_df(_golden_config()) == 12 * 13 // 2 - 26  # 52


def test_free_parameter_count_worked_example_with_second_order() -> None:
    # 15 items, 5 first-order (markers fixed), ENB second-order over RES+CUL:
    # loadings 15-5=10 + errors 15 + ENB component loadings 2-1=1 +
    # component disturbances 2 + ENB variance 1 + endogenous disturbances
    # (PU, ATT, INT) 3 + exogenous covariances C(1,2)=0 + direct paths 4 = 36
    assert free_parameter_count(_example_config()) == 36


def test_model_df_worked_example() -> None:
    assert model_df(_example_config()) == 15 * 16 // 2 - 36  # 84


# -- AT-M09-2: N:q from playbook thresholds; advisory below floor ----------------------


def test_n_q_thresholds_come_from_the_playbook() -> None:  # AT-M09-2
    evaluation = n_q_evaluation(_golden_config(), n=300, playbook=_playbook())
    assert evaluation["q"] == 26
    assert evaluation["ratio"] == pytest.approx(300 / 26, abs=1e-9)
    assert evaluation["target"] == 10.0
    assert evaluation["floor"] == 5.0
    assert evaluation["status"] == "meets_target"


def test_n_q_below_target_flags() -> None:  # AT-M09-2
    evaluation = n_q_evaluation(_golden_config(), n=200, playbook=_playbook())
    assert evaluation["status"] == "below_target"


def test_n_q_below_floor_triggers_the_advisory_path(tmp_path: Path) -> None:  # AT-M09-2
    run_dir = tmp_path / "run"
    advisory = Advisory(
        run_dir, Provenance(run_dir / "PROVENANCE.jsonl", FixedClock()), FixedClock()
    )
    with pytest.raises(AdvisoryStop):
        power_gate(_golden_config(), n=100, playbook=_playbook(), advisory=advisory)
    text = (run_dir / "METHOD_ADVISORY.md").read_text(encoding="utf-8")
    assert "N:q" in text
    assert "kline2016" in text or "Kline" in text  # PB-01 criterion citations carried


def test_power_gate_passes_above_floor(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    advisory = Advisory(
        run_dir, Provenance(run_dir / "PROVENANCE.jsonl", FixedClock()), FixedClock()
    )
    report = power_gate(_golden_config(), n=300, playbook=_playbook(), advisory=advisory)
    assert report["n_q"]["status"] == "meets_target"
    assert not (run_dir / "METHOD_ADVISORY.md").exists()


# -- store rows -------------------------------------------------------------------------


def test_power_store_rows_are_schema_valid_under_power_ids() -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((REPO / "schemas" / "results_store.schema.json").read_text())
    validator = Draft202012Validator(schema)
    rows = power_store_rows(
        _golden_config(),
        n=300,
        playbook=_playbook(),
        created="2026-07-03T09:00:00Z",
    )
    ids = [row["id"] for row in rows]
    assert any(row_id.startswith("power.close_fit") for row_id in ids)
    assert any(row_id.startswith("power.n_to_q") for row_id in ids)
    for row in rows:
        validator.validate(row)
        assert row["stage"] == "power"
        assert row["engine"] == "py_pandas"
