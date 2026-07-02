"""Orchestrator-owned halts must emit to the halt sink (REJECT-TC04 fix 3).

Standards §4: every raised halt writes its machine-readable report before
propagating. These regression tests install a capturing sink and prove each
Orchestrator-owned raise path emits exactly one report — without writing
into sealed source directories.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest
from orch_util import StubStage, TickingClock, manifest_fields, stub_registry

from burhan.core.errors import (
    IntegrityHalt,
    VerificationHalt,
    reset_halt_sink,
    set_halt_sink,
)
from burhan.core.orchestrator import Orchestrator, StageContext


class CapturingSink:
    def __init__(self) -> None:
        self.reports: list[dict[str, Any]] = []

    def emit(self, report: dict[str, Any]) -> None:
        self.reports.append(report)


@pytest.fixture
def sink() -> Any:
    capturing = CapturingSink()
    set_halt_sink(capturing)
    yield capturing
    reset_halt_sink()


def test_registry_mismatch_emits_exactly_one_sink_report(
    tmp_path: Path, sink: CapturingSink
) -> None:
    registry = stub_registry()
    del registry["prep"]
    with pytest.raises(IntegrityHalt):
        Orchestrator(TickingClock()).run(
            tmp_path / "run", registry, manifest_fields=manifest_fields()
        )
    reports = [r for r in sink.reports if r["halt_class"] == "IntegrityHalt"]
    assert len(reports) == 1
    assert "prep" in str(reports[0]["details"])


def test_rerun_existing_target_emits_exactly_one_sink_report(
    tmp_path: Path, sink: CapturingSink
) -> None:
    source = tmp_path / "runs" / "source"
    Orchestrator(TickingClock()).run(source, stub_registry(), manifest_fields=manifest_fields())
    target = tmp_path / "runs" / "rerun"
    target.mkdir(parents=True)
    sink.reports.clear()  # only the rerun path under test
    with pytest.raises(IntegrityHalt):
        Orchestrator(TickingClock()).rerun(source, stub_registry(), target_run_dir=target)
    assert len(sink.reports) == 1
    assert sink.reports[0]["halt_class"] == "IntegrityHalt"
    assert "written once" in sink.reports[0]["message"]


def test_rerun_identity_mismatch_emits_exactly_one_sink_report(
    tmp_path: Path, sink: CapturingSink
) -> None:
    def unseeded(ctx: StageContext) -> None:
        (ctx.run_dir / "effects.txt").write_text(str(random.random()), encoding="utf-8")

    registry = stub_registry({"effects": StubStage("effects", unseeded)})
    source = tmp_path / "runs" / "source"
    Orchestrator(TickingClock()).run(source, registry, manifest_fields=manifest_fields())
    source_files_before = sorted(p.name for p in source.rglob("*") if p.is_file())
    sink.reports.clear()
    with pytest.raises(VerificationHalt):
        Orchestrator(TickingClock()).rerun(
            source, registry, target_run_dir=tmp_path / "runs" / "rerun"
        )
    verification_reports = [r for r in sink.reports if r["halt_class"] == "VerificationHalt"]
    assert len(verification_reports) == 1
    assert "effects.txt" in str(verification_reports[0]["details"])
    # and nothing was written into the sealed source directory
    assert sorted(p.name for p in source.rglob("*") if p.is_file()) == source_files_before
