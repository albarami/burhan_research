"""Compliance tracker tests (AT-M03-4; FR-1106).

Rows are append-only and rendered only from recorded evidence (TC-03
Delivery Notes); a step whose ``outputs`` prefixes are absent from the
results store cannot be marked completed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pb_util import PLAYBOOK, FixedClock

from burhan.core.compliance import Compliance
from burhan.core.errors import HALT_REPORT_FILENAME, IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.results.store import ResultsStore

ALL_STEP_IDS = [f"PB-{n:02d}" for n in range(1, 22)]


@pytest.fixture
def playbook() -> Playbook:
    return Playbook.load(PLAYBOOK, mode="certification")


@pytest.fixture
def store(tmp_path: Path) -> ResultsStore:
    return ResultsStore(tmp_path / "results", FixedClock())


@pytest.fixture
def compliance(playbook: Playbook, store: ResultsStore, tmp_path: Path) -> Compliance:
    return Compliance(playbook, store, tmp_path / "compliance.jsonl", FixedClock())


def _feed_store(store: ResultsStore, prefixes: list[str], step_id: str) -> None:
    # IDs carry the step as a segment: two steps may share a prefix (e.g.
    # PB-08/PB-09 both emit under measurement.loadings) and statistic IDs
    # must stay unique per run.
    for prefix in prefixes:
        store.write(
            {
                "id": f"{prefix}.{step_id.replace('-', '').lower()}",
                "value": 1.0,
                "stage": prefix.split(".")[0],
                "engine": "r_lavaan",
                "playbook_step": step_id,
            }
        )


def test_completed_requires_outputs_in_store(
    compliance: Compliance, store: ResultsStore, playbook: Playbook, tmp_path: Path
) -> None:  # AT-M03-4
    with pytest.raises(IntegrityHalt) as excinfo:
        compliance.mark("PB-01", "completed", "power computed")  # store is empty
    details = excinfo.value.to_report()["details"]
    assert details["step"] == "PB-01"
    assert details["missing_prefix"] == "power.close_fit"
    assert not (tmp_path / "compliance.jsonl").exists()  # nothing recorded

    _feed_store(store, playbook.outputs("PB-01"), "PB-01")
    row = compliance.mark("PB-01", "completed", "power computed at N=312")
    assert row["step_id"] == "PB-01"
    line = json.loads((tmp_path / "compliance.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["status"] == "completed"
    assert line["ts"] == "2026-07-02T09:00:00Z"


def test_steps_without_outputs_can_complete_without_store(compliance: Compliance) -> None:
    compliance.mark("PB-20", "completed", "chapter drafted and checked")  # outputs: []


def test_failed_and_flagged_require_no_outputs(compliance: Compliance) -> None:
    compliance.mark("PB-01", "failed", "power below floor; advisory issued")
    compliance.mark("PB-02", "flagged", "recovered partials at threshold boundary")


def test_unknown_step_and_bad_status_halt(compliance: Compliance) -> None:
    with pytest.raises(IntegrityHalt):
        compliance.mark("PB-99", "completed", "x")
    with pytest.raises(IntegrityHalt):
        compliance.mark("PB-01", "skipped", "x")  # not in completed/failed/flagged


def test_rows_are_append_only_one_per_step(compliance: Compliance) -> None:
    compliance.mark("PB-01", "failed", "first verdict")
    with pytest.raises(IntegrityHalt):
        compliance.mark("PB-01", "completed", "revisionism")  # re-marking is mutation


def test_no_mutating_api_beyond_mark(compliance: Compliance) -> None:
    public = {
        name
        for name in dir(compliance)
        if not name.startswith("_") and callable(getattr(compliance, name))
    }
    assert public == {"mark", "render"}


def test_render_lists_every_step_exactly_once(
    playbook: Playbook, store: ResultsStore, tmp_path: Path
) -> None:  # AT-M03-4
    compliance = Compliance(playbook, store, tmp_path / "compliance.jsonl", FixedClock())
    for step_id in ALL_STEP_IDS:
        prefixes = playbook.outputs(step_id)
        if prefixes:
            _feed_store(store, prefixes, step_id)
            compliance.mark(step_id, "completed", f"{step_id} executed")
        else:
            compliance.mark(step_id, "flagged", f"{step_id} evidence pending package stage")
    rendered = compliance.render()
    assert rendered.startswith("# METHOD_COMPLIANCE_CHECKLIST")
    for step_id in ALL_STEP_IDS:
        assert rendered.count(f"\n| {step_id} |") == 1  # exactly one row per step
    assert rendered.count("| completed |") == 19
    assert rendered.count("| flagged |") == 2


def test_render_refuses_incomplete_sequence(compliance: Compliance) -> None:  # FR-1106
    compliance.mark("PB-01", "failed", "halted at power stage")
    with pytest.raises(IntegrityHalt) as excinfo:
        compliance.render()
    assert "PB-02" in str(excinfo.value.to_report()["details"])


def test_reopen_replays_rows_and_keeps_append_only(
    playbook: Playbook, store: ResultsStore, tmp_path: Path
) -> None:
    path = tmp_path / "compliance.jsonl"
    first = Compliance(playbook, store, path, FixedClock())
    first.mark("PB-01", "failed", "halted")
    reopened = Compliance(playbook, store, path, FixedClock())
    with pytest.raises(IntegrityHalt):
        reopened.mark("PB-01", "completed", "revisionism after reopen")
    reopened.mark("PB-02", "flagged", "still markable")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_tampered_rows_halt_on_reopen(
    playbook: Playbook, store: ResultsStore, tmp_path: Path
) -> None:
    path = tmp_path / "compliance.jsonl"
    Compliance(playbook, store, path, FixedClock()).mark("PB-01", "failed", "halted")
    path.write_text(path.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Compliance(playbook, store, path, FixedClock())
    assert (tmp_path / HALT_REPORT_FILENAME).exists()


def test_rows_for_foreign_steps_halt_on_reopen(
    playbook: Playbook, store: ResultsStore, tmp_path: Path
) -> None:
    path = tmp_path / "compliance.jsonl"
    row: dict[str, Any] = {
        "step_id": "PB-99",
        "status": "completed",
        "evidence": "forged",
        "ts": "2026-07-02T09:00:00Z",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Compliance(playbook, store, path, FixedClock())


def test_empty_evidence_is_refused(compliance: Compliance) -> None:
    with pytest.raises(IntegrityHalt):
        compliance.mark("PB-20", "completed", "")


@pytest.mark.parametrize(
    "row",
    [
        {"step_id": "PB-01", "status": "failed", "ts": "2026-07-02T09:00:00Z"},  # missing field
        {  # invalid status
            "step_id": "PB-01",
            "status": "skipped",
            "evidence": "x",
            "ts": "2026-07-02T09:00:00Z",
        },
    ],
)
def test_malformed_replayed_rows_halt(
    playbook: Playbook, store: ResultsStore, tmp_path: Path, row: dict[str, Any]
) -> None:
    path = tmp_path / "compliance.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Compliance(playbook, store, path, FixedClock())


def test_replayed_completed_rows_recheck_the_store_gate(
    playbook: Playbook, store: ResultsStore, tmp_path: Path
) -> None:  # REJECT fix: replay must not bypass FR-1106
    path = tmp_path / "compliance.jsonl"
    forged = {
        "step_id": "PB-01",
        "status": "completed",
        "evidence": "forged",
        "ts": "2026-07-02T09:00:00Z",
    }
    path.write_text(json.dumps(forged) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt) as excinfo:  # store is empty
        Compliance(playbook, store, path, FixedClock())
    details = excinfo.value.to_report()["details"]
    assert details["step"] == "PB-01"
    assert details["missing_prefix"] == "power.close_fit"


def test_forged_full_sequence_cannot_render_without_store_outputs(
    playbook: Playbook, store: ResultsStore, tmp_path: Path
) -> None:  # REJECT fix: a fully forged checklist is impossible
    path = tmp_path / "compliance.jsonl"
    rows = [
        {
            "step_id": step_id,
            "status": "completed",
            "evidence": "forged",
            "ts": "2026-07-02T09:00:00Z",
        }
        for step_id in ALL_STEP_IDS
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(IntegrityHalt):  # halts at replay; render is unreachable
        Compliance(playbook, store, path, FixedClock())


def test_legitimate_reopen_with_store_backed_completed_rows_replays(
    playbook: Playbook, store: ResultsStore, tmp_path: Path
) -> None:  # the gate must not reject honest histories
    path = tmp_path / "compliance.jsonl"
    first = Compliance(playbook, store, path, FixedClock())
    _feed_store(store, playbook.outputs("PB-01"), "PB-01")
    first.mark("PB-01", "completed", "power computed")
    reopened = Compliance(playbook, store, path, FixedClock())  # same run's store
    reopened.mark("PB-02", "flagged", "still markable after reopen")


def test_duplicate_replayed_rows_halt(
    playbook: Playbook, store: ResultsStore, tmp_path: Path
) -> None:
    path = tmp_path / "compliance.jsonl"
    row = {"step_id": "PB-01", "status": "failed", "evidence": "x", "ts": "2026-07-02T09:00:00Z"}
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Compliance(playbook, store, path, FixedClock())


def test_non_utc_clock_is_refused(playbook: Playbook, store: ResultsStore, tmp_path: Path) -> None:
    import datetime as dt

    class NaiveClock:
        def now(self) -> dt.datetime:
            return dt.datetime(2026, 7, 2, 9, 0, 0)  # noqa: DTZ001 — deliberate bad clock

    compliance = Compliance(playbook, store, tmp_path / "compliance.jsonl", NaiveClock())
    with pytest.raises(IntegrityHalt):
        compliance.mark("PB-20", "completed", "x")
