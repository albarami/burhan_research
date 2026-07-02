"""Rerun byte-identity tests (AT-M04-4; NFR-101; FR-1403; AD-03).

``rerun`` re-executes a sealed run from its manifest into a fresh directory
and asserts byte-identity of every regenerated artifact (manifest.json
excluded — it carries the seal); a planted nondeterminism (unseeded RNG in
a stub stage) must be caught by the identity assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from orch_util import StubStage, TickingClock, manifest_fields, stub_registry

from burhan.core.errors import IntegrityHalt, VerificationHalt
from burhan.core.orchestrator import Orchestrator, StageContext


def _artifact_map(run_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path.relative_to(run_dir).as_posix() != "manifest.json"
    }


def test_rerun_regenerates_byte_identical_artifacts(tmp_path: Path) -> None:  # AT-M04-4
    source = tmp_path / "runs" / "source"
    target = tmp_path / "runs" / "rerun"
    Orchestrator(TickingClock()).run(source, stub_registry(), manifest_fields=manifest_fields())
    result = Orchestrator(TickingClock()).rerun(source, stub_registry(), target_run_dir=target)
    assert result.state == "COMPLETED"
    source_map = _artifact_map(source)
    target_map = _artifact_map(target)
    assert source_map.keys() == target_map.keys()
    for name, content in source_map.items():
        assert target_map[name] == content, f"artifact differs: {name}"


def test_planted_nondeterminism_is_caught(tmp_path: Path) -> None:  # AT-M04-4
    import random

    def unseeded(ctx: StageContext) -> None:
        # The planted defect: ambient RNG, exactly what standards §1 bans.
        (ctx.run_dir / "effects.txt").write_text(str(random.random()), encoding="utf-8")

    registry = stub_registry({"effects": StubStage("effects", unseeded)})
    source = tmp_path / "runs" / "source"
    Orchestrator(TickingClock()).run(source, registry, manifest_fields=manifest_fields())
    with pytest.raises(VerificationHalt) as excinfo:
        Orchestrator(TickingClock()).rerun(
            source, registry, target_run_dir=tmp_path / "runs" / "rerun"
        )
    assert "effects.txt" in str(excinfo.value.to_report()["details"])


def test_rerun_requires_a_sealed_source(tmp_path: Path) -> None:
    empty = tmp_path / "runs" / "empty"
    empty.mkdir(parents=True)
    with pytest.raises(IntegrityHalt):
        Orchestrator(TickingClock()).rerun(
            empty, stub_registry(), target_run_dir=tmp_path / "runs" / "rerun"
        )


def test_rerun_halts_if_target_exists(tmp_path: Path) -> None:  # write-once discipline
    source = tmp_path / "runs" / "source"
    Orchestrator(TickingClock()).run(source, stub_registry(), manifest_fields=manifest_fields())
    target = tmp_path / "runs" / "rerun"
    target.mkdir(parents=True)
    (target / "leftover.txt").write_text("x", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Orchestrator(TickingClock()).rerun(source, stub_registry(), target_run_dir=target)


def test_rerun_of_halted_source_reproduces_the_halt_state(tmp_path: Path) -> None:
    from burhan.core.errors import halt

    def invariant_fail(ctx: StageContext) -> None:
        halt(IntegrityHalt("invariant fail", report={"which": "range"}))

    registry = stub_registry({"prep": StubStage("prep", invariant_fail)})
    source = tmp_path / "runs" / "source"
    Orchestrator(TickingClock()).run(source, registry, manifest_fields=manifest_fields())
    target = tmp_path / "runs" / "rerun"
    result = Orchestrator(TickingClock()).rerun(source, registry, target_run_dir=target)
    assert result.state == "HALTED_INTEGRITY"  # same terminal state reproduced
    assert _artifact_map(source) == _artifact_map(target)  # incl. halt reports
