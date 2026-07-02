"""Defensive-branch coverage for the TC-04 modules (lane standard: 100%).

Each test here exercises a real failure path — none is decorative.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_doctor import _reference_inputs
from typer.testing import CliRunner

from burhan.cli import app
from burhan.cli.doctor import production_inputs, run_doctor
from burhan.core.errors import IntegrityHalt
from burhan.core.rworker import RWorker, workers_dir

REPO = Path(__file__).resolve().parents[3]
runner = CliRunner()


def _failing_names(report: Any) -> set[str]:
    return {check.name for check in report.checks if check.status == "fail"}


def test_repo_under_windows_mount_fails(tmp_path: Path) -> None:
    report = run_doctor(_reference_inputs(tmp_path, repo_dir=Path("/mnt/c/dev/burhan")))
    assert "repo_on_ext4" in _failing_names(report)


def test_wrong_python_and_missing_lock_fail(tmp_path: Path) -> None:
    report = run_doctor(_reference_inputs(tmp_path, python_version="3.11.9"))
    assert "python_and_lock" in _failing_names(report)
    report = run_doctor(_reference_inputs(tmp_path, repo_dir=tmp_path))  # no uv.lock here
    assert "python_and_lock" in _failing_names(report)


def test_r_version_probe_failure_fails(tmp_path: Path) -> None:
    report = run_doctor(
        _reference_inputs(tmp_path, commands={"r_version": (1, "Rscript exploded")})
    )
    assert "r_and_renv" in _failing_names(report)


def test_missing_system_libraries_fail(tmp_path: Path) -> None:
    report = run_doctor(_reference_inputs(tmp_path, find_library=lambda name: None))
    assert "system_libraries" in _failing_names(report)


def test_git_probe_failure_fails(tmp_path: Path) -> None:
    report = run_doctor(_reference_inputs(tmp_path, commands={"git_status": (128, "boom")}))
    assert "git_state" in _failing_names(report)


def test_studies_dir_missing_and_unwritable_fail(tmp_path: Path) -> None:
    report = run_doctor(
        _reference_inputs(tmp_path, env={"BURHAN_STUDIES_DIR": str(tmp_path / "absent")})
    )
    assert "studies_dir_writable" in _failing_names(report)
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read-only directory
    try:
        report = run_doctor(_reference_inputs(tmp_path, env={"BURHAN_STUDIES_DIR": str(locked)}))
        assert "studies_dir_writable" in _failing_names(report)
    finally:
        locked.chmod(stat.S_IRWXU)


def test_llm_config_missing_and_malformed_fail(tmp_path: Path) -> None:
    inputs = _reference_inputs(tmp_path)
    (inputs.config_dir / "llm.yaml").unlink()
    assert "llm_config" in _failing_names(run_doctor(inputs))

    inputs = _reference_inputs(tmp_path)
    (inputs.config_dir / "llm.yaml").write_text("{unbalanced: [", encoding="utf-8")
    assert "llm_config" in _failing_names(run_doctor(inputs))

    inputs = _reference_inputs(tmp_path)
    (inputs.config_dir / "llm.yaml").write_text(yaml.safe_dump({"nodes": {}}), encoding="utf-8")
    assert "llm_config" in _failing_names(run_doctor(inputs))

    incomplete = {
        "nodes": {"node_a": {"provider": "anthropic"}, "node_b": {}, "node_c": {}},
        "providers": {"anthropic": {"api_key_env": "ANTHROPIC_API_KEY"}},
    }
    inputs = _reference_inputs(tmp_path)
    (inputs.config_dir / "llm.yaml").write_text(yaml.safe_dump(incomplete), encoding="utf-8")
    assert "llm_config" in _failing_names(run_doctor(inputs))


def test_production_inputs_read_the_real_machine() -> None:
    inputs = production_inputs()
    assert inputs.repo_dir == REPO
    rc, out = inputs.run_command("git_commit")  # read-only probe
    assert rc == 0 and out.strip()
    # r_version degrades to a failure tuple when Rscript is absent (E-R1).
    rc, _ = inputs.run_command("r_version")
    assert isinstance(rc, int)


def test_certify_reports_halts_via_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    import burhan.core.policy as policy_module

    def broken_load(*args: Any, **kwargs: Any) -> Any:
        raise IntegrityHalt("simulated governance defect", report={})

    monkeypatch.setattr(policy_module.Policy, "load", broken_load)
    result = runner.invoke(app, ["certify"])
    assert result.exit_code == 10
    assert "halted" in result.output


def test_rworker_unspawnable_rscript_halts(tmp_path: Path) -> None:
    worker = RWorker(rscript=str(tmp_path / "no_such_binary"), workers_dir=REPO / "workers" / "r")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(IntegrityHalt) as excinfo:
        worker.call("echo_worker", {}, call_id="x1", run_dir=run_dir, seed=1)
    assert "could not be executed" in excinfo.value.message


def test_rworker_garbage_output_halts(tmp_path: Path) -> None:
    fake = tmp_path / "fake_rscript"
    fake.write_text(
        "#!/usr/bin/env python3\nimport sys\nopen(sys.argv[4], 'w').write('not json')\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    worker = RWorker(rscript=str(fake), workers_dir=REPO / "workers" / "r")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(IntegrityHalt) as excinfo:
        worker.call("echo_worker", {}, call_id="x2", run_dir=run_dir, seed=1)
    assert "not valid JSON" in excinfo.value.message


def test_workers_dir_points_into_repo() -> None:
    assert workers_dir() == REPO / "workers" / "r"
    assert (workers_dir() / "harness.R").is_file()


def test_run_report_md_written_on_completion(tmp_path: Path) -> None:
    from orch_util import TickingClock, manifest_fields, stub_registry

    from burhan.core.orchestrator import RUN_REPORT_MD_FILENAME, Orchestrator

    run_dir = tmp_path / "run"
    Orchestrator(TickingClock()).run(run_dir, stub_registry(), manifest_fields=manifest_fields())
    rendered = (run_dir / RUN_REPORT_MD_FILENAME).read_text(encoding="utf-8")
    assert "terminal state: COMPLETED" in rendered


def test_fake_output_envelope_call_id_mismatch_halts(tmp_path: Path) -> None:
    fake = tmp_path / "fake_rscript"
    fake.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        "json.dump({'call_id': 'WRONG', 'status': 'ok', 'result': {}}, open(sys.argv[4], 'w'))\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    worker = RWorker(rscript=str(fake), workers_dir=REPO / "workers" / "r")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(IntegrityHalt) as excinfo:
        worker.call("echo_worker", {}, call_id="x3", run_dir=run_dir, seed=1)
    assert "envelope" in excinfo.value.message
    report = json.loads((run_dir / "stats" / "halt_report.json").read_text(encoding="utf-8"))
    assert report["halt_class"] == "IntegrityHalt"
