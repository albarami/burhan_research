"""R worker harness tests (AT-M04-5; AD-02; architecture §6).

The Python side is proven against a controllable fake Rscript executable:
nonzero exit, schema-invalid output, and renv drift each produce
IntegrityHalt with the captured stderr; the worker receives the derived
seed and payload by file. The real-R integration test runs whenever
Rscript is on PATH (E-R1 bootstrap) and is skipped — declared, not hidden
— until then.
"""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path

import pytest

from burhan.core.errors import IntegrityHalt
from burhan.core.rworker import RWorker

REPO = Path(__file__).resolve().parents[3]

_FAKE_RSCRIPT = '''#!/usr/bin/env python3
"""Fake Rscript: behavior selected by FAKE_MODE (test-controlled)."""
import json, os, sys

mode = os.environ.get("FAKE_MODE", "ok")
# argv: harness.R worker.R input.json output.json
_, harness, worker, input_path, output_path = sys.argv
envelope = json.load(open(input_path))

if mode == "nonzero":
    # String literal only — mimics R's stderr wording; nothing is eval'd here.
    sys.stderr.write("Error in eval(): object not found\\n")
    sys.exit(1)
if mode == "drift":
    sys.stderr.write("RENV_DRIFT: renv status not synchronized\\n")
    sys.exit(3)
if mode == "invalid_output":
    open(output_path, "w").write(json.dumps({"unexpected": True}))
    sys.exit(0)
if mode == "no_output":
    sys.exit(0)

json.dump(
    {"call_id": envelope["call_id"], "status": "ok",
     "result": {"echo": envelope["payload"], "seed_seen": envelope["seed"]}},
    open(output_path, "w"),
)
'''


@pytest.fixture
def fake_rscript(tmp_path: Path) -> Path:
    path = tmp_path / "fake_rscript"
    path.write_text(_FAKE_RSCRIPT, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture
def worker(fake_rscript: Path, tmp_path: Path) -> RWorker:
    return RWorker(rscript=str(fake_rscript), workers_dir=REPO / "workers" / "r")


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "run"
    directory.mkdir()
    return directory


def test_worker_receives_seed_and_payload_by_file(
    worker: RWorker, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M04-5
    monkeypatch.setenv("FAKE_MODE", "ok")
    result = worker.call(
        "echo_worker", {"x": [1, 2, 3]}, call_id="c001", run_dir=run_dir, seed=781967108
    )
    assert result == {"echo": {"x": [1, 2, 3]}, "seed_seen": 781967108}
    input_file = run_dir / "stats" / "call_c001.input.json"
    envelope = json.loads(input_file.read_text(encoding="utf-8"))
    assert envelope["seed"] == 781967108
    assert envelope["payload"] == {"x": [1, 2, 3]}
    assert (run_dir / "stats" / "call_c001.output.json").exists()


def test_nonzero_exit_halts_with_captured_stderr(
    worker: RWorker, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M04-5
    monkeypatch.setenv("FAKE_MODE", "nonzero")
    with pytest.raises(IntegrityHalt) as excinfo:
        worker.call("echo_worker", {}, call_id="c002", run_dir=run_dir, seed=1)
    details = excinfo.value.to_report()["details"]
    assert "object not found" in details["stderr"]
    assert details["exit_code"] == 1


def test_renv_drift_halts_named(
    worker: RWorker, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M04-5 (NFR-102)
    monkeypatch.setenv("FAKE_MODE", "drift")
    with pytest.raises(IntegrityHalt) as excinfo:
        worker.call("echo_worker", {}, call_id="c003", run_dir=run_dir, seed=1)
    assert "renv" in excinfo.value.message.lower()
    assert "RENV_DRIFT" in excinfo.value.to_report()["details"]["stderr"]


def test_schema_invalid_output_halts(
    worker: RWorker, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M04-5
    monkeypatch.setenv("FAKE_MODE", "invalid_output")
    with pytest.raises(IntegrityHalt) as excinfo:
        worker.call("echo_worker", {}, call_id="c004", run_dir=run_dir, seed=1)
    assert "envelope" in excinfo.value.message


def test_missing_output_halts(
    worker: RWorker, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "no_output")
    with pytest.raises(IntegrityHalt):
        worker.call("echo_worker", {}, call_id="c005", run_dir=run_dir, seed=1)


def test_unknown_worker_module_halts(worker: RWorker, run_dir: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        worker.call("no_such_worker", {}, call_id="c006", run_dir=run_dir, seed=1)
    assert "no_such_worker" in str(excinfo.value.to_report()["details"])


def test_call_files_are_write_once(
    worker: RWorker, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AD-06
    monkeypatch.setenv("FAKE_MODE", "ok")
    worker.call("echo_worker", {}, call_id="c007", run_dir=run_dir, seed=1)
    with pytest.raises(IntegrityHalt):
        worker.call("echo_worker", {}, call_id="c007", run_dir=run_dir, seed=1)


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R not installed (E-R1 pending)")
def test_real_r_echo_worker_round_trip(run_dir: Path) -> None:  # AT-M04-5 (real R)
    real = RWorker(rscript="Rscript", workers_dir=REPO / "workers" / "r")
    result = real.call(
        "echo_worker", {"greeting": "burhan"}, call_id="r001", run_dir=run_dir, seed=424242
    )
    assert result["echo"] == {"greeting": "burhan"}
    assert 0.0 <= float(result["draw"]) <= 1.0
    # Determinism through the injected seed: same call, fresh dir, same draw.
    rerun_dir = run_dir.parent / "run2"
    rerun_dir.mkdir()
    again = real.call(
        "echo_worker", {"greeting": "burhan"}, call_id="r001", run_dir=rerun_dir, seed=424242
    )
    assert again["draw"] == result["draw"]
