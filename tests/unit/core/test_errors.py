"""Typed failure taxonomy tests (standards §4; architecture §7; PLAN v2 Fix 5).

Every halt raised through ``halt()`` must emit its machine-readable report to
the halt sink BEFORE propagating; components that own a live working directory
additionally write ``halt_report.json`` via ``halt_with_file()``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from burhan.core.errors import (
    HALT_REPORT_FILENAME,
    AdvisoryStop,
    BurhanHalt,
    GateExhausted,
    IntegrityHalt,
    VerificationHalt,
    get_halt_sink,
    halt,
    halt_with_file,
    reset_halt_sink,
    set_halt_sink,
)


class CapturingSink:
    """Test sink recording every emitted report in order."""

    def __init__(self) -> None:
        self.reports: list[dict[str, Any]] = []

    def emit(self, report: dict[str, Any]) -> None:
        self.reports.append(report)


@pytest.fixture(autouse=True)
def _restore_sink() -> Any:
    yield
    reset_halt_sink()


def test_taxonomy_maps_one_to_one_to_run_states() -> None:
    # Architecture §7 failure classes -> run_manifest run_state enum values.
    assert IntegrityHalt.run_state == "HALTED_INTEGRITY"
    assert VerificationHalt.run_state == "HALTED_VERIFICATION"
    assert GateExhausted.run_state == "HALTED_GATE"
    assert AdvisoryStop.run_state == "COMPLETED_TO_BOUNDARY"
    for cls in (IntegrityHalt, VerificationHalt, GateExhausted, AdvisoryStop):
        assert issubclass(cls, BurhanHalt)


def test_to_report_is_machine_readable() -> None:
    exc = IntegrityHalt("n-chain broken", report={"expected": 4, "actual": 5})
    assert exc.to_report() == {
        "halt_class": "IntegrityHalt",
        "run_state": "HALTED_INTEGRITY",
        "message": "n-chain broken",
        "details": {"expected": 4, "actual": 5},
    }


def test_report_details_default_to_empty_dict() -> None:
    exc = AdvisoryStop("power shortfall")
    assert exc.to_report()["details"] == {}
    assert str(exc) == "power shortfall"


def test_halt_emits_report_before_propagating() -> None:
    sink = CapturingSink()
    set_halt_sink(sink)
    exc = VerificationHalt("parity breach", report={"scope": "prep"})
    with pytest.raises(VerificationHalt) as excinfo:
        halt(exc)
    assert excinfo.value is exc
    assert sink.reports == [exc.to_report()]


def test_set_halt_sink_returns_previous_and_reset_restores_default() -> None:
    default = get_halt_sink()
    sink = CapturingSink()
    previous = set_halt_sink(sink)
    assert previous is default
    assert get_halt_sink() is sink
    reset_halt_sink()
    assert get_halt_sink() is default


def test_halt_with_file_writes_canonical_report_then_raises(tmp_path: Path) -> None:
    sink = CapturingSink()
    set_halt_sink(sink)
    exc = GateExhausted("gate 1 retries exhausted", report={"retries": 2})
    with pytest.raises(GateExhausted):
        halt_with_file(exc, tmp_path)
    written = json.loads((tmp_path / HALT_REPORT_FILENAME).read_text(encoding="utf-8"))
    assert written == exc.to_report()
    assert sink.reports == [exc.to_report()]


def test_halt_with_file_creates_missing_directory(tmp_path: Path) -> None:
    set_halt_sink(CapturingSink())
    target = tmp_path / "results"
    with pytest.raises(IntegrityHalt):
        halt_with_file(IntegrityHalt("duplicate id"), target)
    assert (target / HALT_REPORT_FILENAME).exists()
