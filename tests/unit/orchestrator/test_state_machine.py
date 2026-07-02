"""Orchestrator state-machine tests (AT-M04-1/2/3; architecture §4/§7).

The DAG is fixed; transitions are typed; every terminal state writes its
report; injected faults map to exactly their halt class; partial artifacts
are preserved and marked non-final; after Gate-1-pass no code path reads
stdin (proven by a closed-stdin subprocess run of the full stub pipeline).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from orch_util import StubStage, TickingClock, manifest_fields, stub_registry

from burhan.core.errors import (
    AdvisoryStop,
    GateExhausted,
    IntegrityHalt,
    VerificationHalt,
    halt,
)
from burhan.core.manifest import Manifest
from burhan.core.orchestrator import (
    NON_FINAL_MARKER,
    PIPELINE,
    RUN_REPORT_FILENAME,
    Orchestrator,
    StageContext,
)

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs" / "20260702T090000Z"


def test_pipeline_is_the_fixed_dag() -> None:  # AT-M04-1 / AD-01
    assert PIPELINE == (
        "ingest",
        "contract",
        "gate1",
        "power",
        "prep",
        "assumptions",
        "measurement",
        "structural",
        "effects",
        "robustness",
        "narrate",
        "gate2",
        "package",
    )


def test_full_stub_run_completes_and_seals(run_dir: Path) -> None:  # AT-M04-1
    result = Orchestrator(TickingClock()).run(
        run_dir, stub_registry(), manifest_fields=manifest_fields()
    )
    assert result.state == "COMPLETED"
    manifest = Manifest.verify_seal(run_dir)  # sealed, tamper-evident
    assert manifest.state == "COMPLETED"
    assert [record.stage for record in manifest.stages] == list(PIPELINE)
    assert all(record.state == "PASSED" for record in manifest.stages)
    report = json.loads((run_dir / RUN_REPORT_FILENAME).read_text(encoding="utf-8"))
    assert report["state"] == "COMPLETED"  # every terminal state writes its report
    assert (run_dir / "ingest.txt").exists() and (run_dir / "package.txt").exists()


def test_unregistered_stage_is_impossible(run_dir: Path) -> None:  # AT-M04-1 (typed)
    registry = stub_registry()
    del registry["prep"]
    with pytest.raises(IntegrityHalt) as excinfo:
        Orchestrator(TickingClock()).run(run_dir, registry, manifest_fields=manifest_fields())
    assert "prep" in str(excinfo.value.to_report()["details"])


def test_unknown_extra_stage_is_impossible(run_dir: Path) -> None:  # AT-M04-1 (typed)
    registry = stub_registry()
    registry["telemetry"] = StubStage("telemetry")
    with pytest.raises(IntegrityHalt):
        Orchestrator(TickingClock()).run(run_dir, registry, manifest_fields=manifest_fields())


def _failing(exc_factory):  # noqa: ANN001, ANN202 — test helper
    def action(ctx: StageContext) -> None:
        halt(exc_factory())

    return action


@pytest.mark.parametrize(
    ("exc_factory", "expected_state"),
    [
        (lambda: IntegrityHalt("invariant fail", report={"which": "range"}), "HALTED_INTEGRITY"),
        (
            lambda: VerificationHalt("parity breach", report={"scope": "prep"}),
            "HALTED_VERIFICATION",
        ),
        (lambda: GateExhausted("gate 1 exhausted", report={"retries": 2}), "HALTED_GATE"),
    ],
)
def test_injected_faults_map_to_their_halt_class(
    run_dir: Path, exc_factory, expected_state: str
) -> None:  # AT-M04-3
    registry = stub_registry({"prep": StubStage("prep", _failing(exc_factory))})
    result = Orchestrator(TickingClock()).run(run_dir, registry, manifest_fields=manifest_fields())
    assert result.state == expected_state
    manifest = Manifest.verify_seal(run_dir)
    assert manifest.state == expected_state
    states = {record.stage: record.state for record in manifest.stages}
    assert states["prep"] == "FAILED"
    assert states["ingest"] == "PASSED"
    # partial artifacts preserved and marked non-final (NFR-202)
    assert (run_dir / "ingest.txt").exists()
    assert (run_dir / NON_FINAL_MARKER).exists()
    report = json.loads((run_dir / RUN_REPORT_FILENAME).read_text(encoding="utf-8"))
    assert report["state"] == expected_state
    assert report["failed_stage"] == "prep"
    assert report["halt"]["halt_class"]


def test_advisory_completes_to_boundary(run_dir: Path) -> None:  # AT-M04-3
    def advisory(ctx: StageContext) -> None:
        halt(AdvisoryStop("power shortfall", report={"n_q": 1.6}))

    registry = stub_registry({"power": StubStage("power", advisory)})
    result = Orchestrator(TickingClock()).run(run_dir, registry, manifest_fields=manifest_fields())
    assert result.state == "COMPLETED_TO_BOUNDARY"
    manifest = Manifest.verify_seal(run_dir)
    assert manifest.state == "COMPLETED_TO_BOUNDARY"
    states = {record.stage: record.state for record in manifest.stages}
    assert states["power"] == "FAILED"
    assert states["prep"] == "SKIPPED_BOUNDARY"
    assert states["package"] == "SKIPPED_BOUNDARY"
    assert not (run_dir / NON_FINAL_MARKER).exists()  # boundary is a completion


def test_stage_seeds_are_derived_per_stage(run_dir: Path) -> None:  # NFR-101
    Orchestrator(TickingClock()).run(run_dir, stub_registry(), manifest_fields=manifest_fields())
    ingest = (run_dir / "ingest.txt").read_text(encoding="utf-8")
    prep = (run_dir / "prep.txt").read_text(encoding="utf-8")
    assert "seed=" in ingest and ingest != prep  # distinct derived seeds


def test_unclassifiable_exception_becomes_integrity_halt(run_dir: Path) -> None:  # NFR-201
    def explode(ctx: StageContext) -> None:
        raise RuntimeError("stray bug")

    registry = stub_registry({"effects": StubStage("effects", explode)})
    result = Orchestrator(TickingClock()).run(run_dir, registry, manifest_fields=manifest_fields())
    assert result.state == "HALTED_INTEGRITY"
    report = json.loads((run_dir / RUN_REPORT_FILENAME).read_text(encoding="utf-8"))
    assert "RuntimeError" in str(report["halt"]["details"])


def test_full_stub_pipeline_runs_with_stdin_closed(tmp_path: Path) -> None:  # AT-M04-2
    driver = tmp_path / "driver.py"
    driver.write_text(
        f"""
import sys
sys.path.insert(0, {str(REPO / "src")!r})
sys.path.insert(0, {str(REPO / "tests" / "unit" / "orchestrator")!r})
from orch_util import TickingClock, manifest_fields, stub_registry
from burhan.core.orchestrator import Orchestrator
from pathlib import Path

result = Orchestrator(TickingClock()).run(
    Path({str(tmp_path / "run")!r}), stub_registry(), manifest_fields=manifest_fields()
)
print(result.state)
""",
        encoding="utf-8",
    )
    completed = subprocess.run(  # noqa: S603 — fixed argv, test-controlled
        [sys.executable, str(driver)],
        stdin=subprocess.DEVNULL,  # no interactive input available (FR-306)
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().endswith("COMPLETED")
