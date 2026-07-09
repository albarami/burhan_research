"""R worker harness tests (AT-M04-5; AD-02; architecture §6).

The Python side is proven against a controllable fake Rscript executable:
nonzero exit, schema-invalid output, and renv drift each produce
IntegrityHalt with the captured stderr; the worker receives the derived
seed and payload by file. The real-R integration test runs whenever
Rscript is on PATH (E-R1 bootstrap) and is skipped — declared, not hidden
— until then.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
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
) -> None:  # AT-M04-5 / AT-M19-3 (NFR-102)
    monkeypatch.setenv("FAKE_MODE", "drift")
    with pytest.raises(IntegrityHalt) as excinfo:
        worker.call("echo_worker", {}, call_id="c003", run_dir=run_dir, seed=1)
    assert excinfo.value.message == "renv drift detected at worker startup (NFR-102)"
    details = excinfo.value.to_report()["details"]
    assert "RENV_DRIFT" in details["stderr"]
    assert details["exit_code"] == 3


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


# ---------------------------------------------------------------------------
# TC-19 — the R worker must run in the workers/r project context so renv
# activates (via .Rprofile -> activate.R) before harness.R's NFR-102 check.
# RED tests first (fail against the pre-fix no-cwd invocation).
# ---------------------------------------------------------------------------


def test_call_runs_subprocess_in_workers_dir_cwd(
    worker: RWorker, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M19-1
    """subprocess.run is invoked with cwd == the workers/r project dir, and every
    Rscript path argument is absolute (so the cwd cannot misresolve them)."""
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["cwd"] = kwargs.get("cwd")
        envelope = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
        Path(argv[4]).write_text(
            json.dumps({"call_id": envelope["call_id"], "status": "ok", "result": {}}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("burhan.core.rworker.subprocess.run", fake_run)
    worker.call("echo_worker", {}, call_id="c101", run_dir=run_dir, seed=1)

    assert captured["cwd"] == worker._workers_dir
    cwd = captured["cwd"]
    assert isinstance(cwd, Path) and cwd.is_absolute()
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert all(Path(a).is_absolute() for a in argv[1:])


def test_workers_dir_absolute_for_injected_relative() -> None:  # AT-M19-4
    """A caller-injected relative workers_dir is normalized to an absolute path."""
    w = RWorker(workers_dir=Path("workers/r"))
    assert w._workers_dir.is_absolute()
    assert w._workers_dir == (Path.cwd() / "workers" / "r").resolve()


def _isolate_from_conftest_r_libs(monkeypatch: pytest.MonkeyPatch, empty_lib: Path) -> None:
    """Undo the suite-wide R_LIBS injection (tests/conftest.py) and point the user
    library at an empty dir, so the workers/r project library is reachable ONLY via
    renv activation — i.e. the DBA-run context in which the false drift occurred."""
    monkeypatch.delenv("R_LIBS", raising=False)
    monkeypatch.setenv("R_LIBS_USER", str(empty_lib))


def _renv_only_library(tmp_path: Path) -> Path:
    """A library dir exposing ONLY renv, symlinked from wherever it is installed (the
    project library on CI, a site library locally). Pointed to by R_LIBS it lets
    renv::status load and run while the workers/r project packages stay off the library
    path — the deterministic precondition for the false not-synchronized drift. No
    install/restore/snapshot; workers/r is untouched."""
    renv_pkg = subprocess.run(  # noqa: S603
        ["Rscript", "-e", 'cat(find.package("renv"))'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    lib = tmp_path / "renv_only_lib"
    lib.mkdir()
    (lib / "renv").symlink_to(renv_pkg, target_is_directory=True)
    return lib


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R not installed (E-R1)")
def test_renv_drift_clears_with_project_cwd(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M19-2
    """With the project library off the ambient library path, running the worker in
    the workers/r project context activates renv and clears the false RENV_DRIFT:
    the echo worker reaches computation and returns."""
    empty_lib = tmp_path / "empty_userlib"
    empty_lib.mkdir()
    _isolate_from_conftest_r_libs(monkeypatch, empty_lib)
    real = RWorker(rscript="Rscript", workers_dir=REPO / "workers" / "r")
    result = real.call(
        "echo_worker", {"greeting": "burhan"}, call_id="c201", run_dir=run_dir, seed=424242
    )
    assert result["echo"] == {"greeting": "burhan"}
    assert 0.0 <= float(result["draw"]) <= 1.0


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R not installed (E-R1)")
def test_false_renv_drift_reproduces_without_project_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M19-2
    """Invoking harness.R as the pre-fix worker did — no project cwd, renv itself
    loadable but the workers/r project library NOT activated — makes renv::status run
    and correctly report the false not-synchronized drift: RENV_DRIFT, exit 3. The
    cwd=workers/r fix activates the project and clears it."""
    renv_lib = _renv_only_library(tmp_path)
    empty_lib = tmp_path / "empty_userlib"
    empty_lib.mkdir()
    monkeypatch.setenv("R_LIBS", str(renv_lib))
    monkeypatch.setenv("R_LIBS_USER", str(empty_lib))
    envelope = {"call_id": "d1", "module": "echo_worker", "seed": 1, "payload": {}}
    in_path = tmp_path / "in.json"
    out_path = tmp_path / "out.json"
    in_path.write_text(json.dumps(envelope), encoding="utf-8")
    argv = [
        "Rscript",
        str(REPO / "workers" / "r" / "harness.R"),
        str(REPO / "workers" / "r" / "echo_worker.R"),
        str(in_path),
        str(out_path),
    ]
    completed = subprocess.run(  # noqa: S603
        argv, cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 3
    assert "RENV_DRIFT" in completed.stderr


def test_workers_dir_absolute_for_default() -> None:  # AT-M19-4
    """The default workers_dir is absolute."""
    assert RWorker()._workers_dir.is_absolute()


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R not installed (E-R1)")
def test_real_renv_drift_still_halts_with_cwd(tmp_path: Path, run_dir: Path) -> None:  # AT-M19-3
    """A genuinely unsynchronized renv project still maps to IntegrityHalt even with
    the cwd fix active (the guard is not weakened). Uses a throwaway project — a
    read-only copy of harness.R + a synthetic unsatisfiable lockfile; the governed
    workers/r files are never touched."""
    tmp_workers = tmp_path / "workers_r"
    tmp_workers.mkdir()
    (tmp_workers / "harness.R").write_text(
        (REPO / "workers" / "r" / "harness.R").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_workers / "echo_worker.R").write_text(
        "run_worker <- function(payload) list(ok = TRUE)\n", encoding="utf-8"
    )
    (tmp_workers / "renv.lock").write_text(
        json.dumps(
            {
                "R": {
                    "Version": "4.5.2",
                    "Repositories": [{"Name": "CRAN", "URL": "https://cloud.r-project.org"}],
                },
                "Packages": {
                    "burhanBogusPkg": {
                        "Package": "burhanBogusPkg",
                        "Version": "9.9.9",
                        "Source": "Repository",
                        "Repository": "CRAN",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    real = RWorker(rscript="Rscript", workers_dir=tmp_workers)
    with pytest.raises(IntegrityHalt) as excinfo:
        real.call("echo_worker", {}, call_id="rd1", run_dir=run_dir, seed=1)
    assert excinfo.value.message == "renv drift detected at worker startup (NFR-102)"
    assert "RENV_DRIFT" in excinfo.value.to_report()["details"]["stderr"]


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R not installed (E-R1)")
def test_real_r_call_leaves_renv_lock_unchanged(run_dir: Path) -> None:  # AT-M19-5
    """A real worker call reads renv state but never mutates workers/r/renv.lock."""
    lock = REPO / "workers" / "r" / "renv.lock"
    before = hashlib.sha256(lock.read_bytes()).hexdigest()
    real = RWorker(rscript="Rscript", workers_dir=REPO / "workers" / "r")
    real.call("echo_worker", {"greeting": "x"}, call_id="c501", run_dir=run_dir, seed=7)
    after = hashlib.sha256(lock.read_bytes()).hexdigest()
    assert before == after


# ---------------------------------------------------------------------------
# TC-19 REJECT remediation — run_dir path safety. With cwd=workers/r, a caller
# supplied RELATIVE run_dir must still produce ABSOLUTE input/output argv paths;
# otherwise the R process resolves them under workers/r, not the caller cwd.
# ---------------------------------------------------------------------------


def test_relative_run_dir_yields_absolute_io_paths(
    worker: RWorker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M19-4
    """A caller-supplied relative run_dir yields absolute input/output argv paths
    that still point at the intended run directory, once cwd=workers/r is set."""
    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["cwd"] = kwargs.get("cwd")
        envelope = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
        Path(argv[4]).write_text(
            json.dumps({"call_id": envelope["call_id"], "status": "ok", "result": {}}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("burhan.core.rworker.subprocess.run", fake_run)
    worker.call("echo_worker", {}, call_id="c301", run_dir=Path("relrun"), seed=1)

    run_abs = (tmp_path / "relrun").resolve()
    argv = captured["argv"]
    assert isinstance(argv, list)
    in_arg, out_arg = Path(argv[3]), Path(argv[4])
    assert in_arg.is_absolute() and out_arg.is_absolute()
    assert in_arg == run_abs / "stats" / "call_c301.input.json"
    assert out_arg == run_abs / "stats" / "call_c301.output.json"
    assert captured["cwd"] == worker._workers_dir


def test_all_argv_paths_absolute_with_relative_workers_dir_and_run_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AT-M19-4
    """Both a relative workers_dir and a relative run_dir yield four absolute Rscript
    path args (harness, worker, input, output), so cwd=workers/r cannot misresolve
    any of them."""
    (tmp_path / "wr").mkdir()
    (tmp_path / "wr" / "harness.R").write_text("", encoding="utf-8")
    (tmp_path / "wr" / "echo_worker.R").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["cwd"] = kwargs.get("cwd")
        envelope = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
        Path(argv[4]).write_text(
            json.dumps({"call_id": envelope["call_id"], "status": "ok", "result": {}}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("burhan.core.rworker.subprocess.run", fake_run)
    worker = RWorker(rscript="Rscript", workers_dir=Path("wr"))
    worker.call("echo_worker", {}, call_id="c401", run_dir=Path("relrun"), seed=1)

    argv = captured["argv"]
    assert isinstance(argv, list)
    assert all(Path(a).is_absolute() for a in argv[1:])
    cwd = captured["cwd"]
    assert isinstance(cwd, Path) and cwd.is_absolute()
    assert cwd == (tmp_path / "wr").resolve()
