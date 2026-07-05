"""TC-15 shared adapter helpers (``burhan.stages.context``).

The cross-stage hand-off (StageContext carries neither frame nor config),
store-row hygiene (helpers that embed store-owned fields must not reach the
store unchanged), and the two sample sizes the pipeline threads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from generator import build_golden
from stages_util import stage_context

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.stages import context


def _config() -> StudyConfig:
    return validate_and_build(StudyConfig, build_golden(11, with_defects=False).config)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"RS1": [4.0, 3.0, 5.0], "RS2": [4.0, 4.0, 6.0]},
        index=pd.Index(["R_001", "R_002", "R_003"], name=context.FRAME_INDEX),
    )


def test_config_round_trips_through_the_contract_artifact(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="contract")
    config = _config()
    context.write_config(ctx, config)
    assert (tmp_path / context.CONTRACT_CONFIG).is_file()
    assert context.load_config(ctx) == config


def test_frame_round_trips_and_is_byte_identical_across_writes(tmp_path: Path) -> None:
    frame = _frame()
    ctx_a = stage_context(tmp_path / "a", stage="prep")
    ctx_b = stage_context(tmp_path / "b", stage="prep")
    context.write_frame(ctx_a, frame)
    context.write_frame(ctx_b, frame)
    reloaded = context.load_frame(ctx_a)
    pd.testing.assert_frame_equal(reloaded, frame)
    # determinism: the same frame serializes to identical bytes (IT-2 identity)
    assert (ctx_a.run_dir / context.PREP_FRAME).read_bytes() == (
        ctx_b.run_dir / context.PREP_FRAME
    ).read_bytes()


def test_store_row_strips_store_owned_fields(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="power")
    # a helper-style row carrying the three store-owned fields (power_store_rows shape)
    context.store_row(
        ctx,
        {
            "id": "power.n_to_q.ratio",
            "value": 7.5,
            "stage": "power",
            "engine": "py_pandas",
            "playbook_step": "PB-01",
            "schema_version": 1,
            "created": "2020-01-01T00:00:00Z",
            "hash": "0" * 64,
        },
    )
    entry = ctx.store.resolve("power.n_to_q.ratio")
    assert entry.value == 7.5
    assert entry.hash != "0" * 64  # the store re-injected its own hash


def test_store_rows_writes_each_in_order(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="robustness")
    rows = [
        {
            "id": "robustness.achieved_power",
            "value": 0.83,
            "stage": "robustness",
            "engine": "py_pandas",
            "playbook_step": "PB-19",
        },
        {
            "id": "robustness.alternatives.reversed_paths.preferred",
            "value": False,
            "stage": "robustness",
            "engine": "py_pandas",
            "playbook_step": "PB-18",
        },
    ]
    context.store_rows(ctx, rows)
    assert ctx.store.resolve("robustness.achieved_power").value == 0.83
    assert ctx.store.resolve("robustness.alternatives.reversed_paths.preferred").value is False


def test_raw_n_reads_the_ingest_summary(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="power")
    (tmp_path / "ingest").mkdir()
    (tmp_path / context.INGEST_SUMMARY).write_text(json.dumps({"raw_n": 300}), encoding="utf-8")
    assert context.raw_n(ctx) == 300


def test_analytical_n_counts_the_persisted_frame(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="robustness")
    context.write_frame(ctx, _frame())
    assert context.analytical_n(ctx) == 3


def test_decision_log_opens_at_the_run_wide_path(tmp_path: Path) -> None:
    ctx = stage_context(tmp_path, stage="assumptions")
    log = context.decision_log(ctx)
    assert log.path == tmp_path / context.DECISION_LOG
