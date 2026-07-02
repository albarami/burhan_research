"""Provenance appender tests (AT-M01-5; NFR-301).

``seq`` is strictly increasing and gap-free — including under concurrent
stage writes — and every entry validates against the governed schema before
anything is written. Content tamper-evidence for the sanad log itself is the
manifest seal (the schema defines no per-entry hash); structural tampering
(gaps, reordering, malformed lines) is detected on reopen.
"""

from __future__ import annotations

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from burhan.core.artifacts.schemas import check_instance
from burhan.core.errors import HALT_REPORT_FILENAME, IntegrityHalt
from burhan.core.provenance import Provenance

FIXED_NOW = dt.datetime(2026, 7, 2, 9, 0, 0, tzinfo=dt.UTC)


class FixedClock:
    def now(self) -> dt.datetime:
        return FIXED_NOW


def _fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "stage": "prep",
        "actor": "invariant",
        "event_type": "invariant_pass",
        "trigger": "post-preparation invariant sweep",
        "effect": "all values within declared scale ranges",
    }
    base.update(overrides)
    return base


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "PROVENANCE.jsonl"


def test_seq_is_strictly_increasing_and_gapfree(log_path: Path) -> None:  # AT-M01-5
    log = Provenance(log_path, FixedClock())
    seqs = [log.append(_fields()).seq for _ in range(5)]
    assert seqs == [1, 2, 3, 4, 5]


def test_ts_stamped_from_injected_clock(log_path: Path) -> None:
    entry = Provenance(log_path, FixedClock()).append(_fields())
    assert entry.ts == FIXED_NOW


def test_every_written_line_validates_against_schema(log_path: Path) -> None:  # AT-M01-5
    log = Provenance(log_path, FixedClock())
    log.append(_fields())
    log.append(
        _fields(
            event_type="artifact_written",
            rule_ref="policy.prep.range_check",
            artifact_refs=[{"path": "prep/invariants.json", "sha256": "b" * 64}],
            details={"checked_items": 15},
        )
    )
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        check_instance("provenance_entry", json.loads(line))  # raises on violation


def test_appender_owns_seq_ts_and_schema_version(log_path: Path) -> None:
    log = Provenance(log_path, FixedClock())
    for owned, value in (("seq", 7), ("ts", "2026-07-02T09:00:00Z"), ("schema_version", 1)):
        with pytest.raises(IntegrityHalt):
            log.append(_fields(**{owned: value}))


def test_invalid_entry_rejected_before_write_and_no_gap(log_path: Path) -> None:  # AT-M01-5
    log = Provenance(log_path, FixedClock())
    log.append(_fields())
    with pytest.raises(IntegrityHalt):
        log.append(_fields(event_type="not_an_event"))
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1
    assert log.append(_fields()).seq == 2  # failed attempt consumed no seq
    assert (log_path.parent / HALT_REPORT_FILENAME).exists()


def test_concurrent_stage_writes_stay_gapfree(log_path: Path) -> None:  # AT-M01-5
    log = Provenance(log_path, FixedClock())
    stages = ["prep", "assumptions", "measurement", "structural"]

    def hammer(worker: int) -> None:
        for _ in range(125):
            log.append(_fields(stage=stages[worker % len(stages)]))

    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in [pool.submit(hammer, worker) for worker in range(8)]:
            future.result()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    seqs = [json.loads(line)["seq"] for line in lines]
    assert seqs == list(range(1, 1001))  # strictly increasing, gap-free, in file order


def test_reopen_resumes_seq(log_path: Path) -> None:
    first = Provenance(log_path, FixedClock())
    for _ in range(3):
        first.append(_fields())
    reopened = Provenance(log_path, FixedClock())
    assert reopened.append(_fields()).seq == 4


def test_reopen_detects_seq_gap(log_path: Path) -> None:
    log = Provenance(log_path, FixedClock())
    log.append(_fields())
    line = log_path.read_text(encoding="utf-8").splitlines()[0]
    forged = json.loads(line)
    forged["seq"] = 3
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(forged) + "\n")
    with pytest.raises(IntegrityHalt):
        Provenance(log_path, FixedClock())


def test_reopen_rejects_malformed_line(log_path: Path) -> None:
    log = Provenance(log_path, FixedClock())
    log.append(_fields())
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    with pytest.raises(IntegrityHalt):
        Provenance(log_path, FixedClock())


def test_non_serializable_details_halt_typed_with_report(log_path: Path) -> None:  # REJECT fix 2
    log = Provenance(log_path, FixedClock())
    log.append(_fields())
    with pytest.raises(IntegrityHalt):
        log.append(_fields(details={"bad": object()}))
    assert (log_path.parent / HALT_REPORT_FILENAME).exists()
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1
    assert log.append(_fields()).seq == 2  # failed attempt consumed no seq


def test_no_mutating_api_exists(log_path: Path) -> None:
    log = Provenance(log_path, FixedClock())
    public = {
        name for name in dir(log) if not name.startswith("_") and callable(getattr(log, name))
    }
    assert public == {"append"}


def test_non_utc_clock_is_refused(log_path: Path) -> None:
    class NaiveClock:
        def now(self) -> dt.datetime:
            return dt.datetime(2026, 7, 2, 9, 0, 0)  # noqa: DTZ001 — deliberate bad clock

    log = Provenance(log_path, NaiveClock())
    with pytest.raises(IntegrityHalt):
        log.append(_fields())
