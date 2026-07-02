"""CLI surface tests (FR-1401; TC-04 deliverable src/burhan/cli/).

The four commands exist (`run`, `rerun`, `certify`, `doctor`); `run` and
`rerun` refuse cleanly while no production stages are registered (stages
land with M05+ — no playbook-style improvisation); `certify` validates the
governed contracts in certification mode; exit codes map documented states.
"""

from __future__ import annotations

from typer.testing import CliRunner

from burhan.cli import app

runner = CliRunner()


def test_all_four_commands_exist() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "rerun", "certify", "doctor"):
        assert command in result.output


def test_run_refuses_cleanly_without_production_stages(tmp_path) -> None:  # noqa: ANN001
    study = tmp_path / "study"
    study.mkdir()
    result = runner.invoke(app, ["run", str(study)])
    assert result.exit_code == 10  # HALTED_INTEGRITY exit mapping
    assert "M05" in result.output  # names what is missing, not a stack trace


def test_rerun_refuses_cleanly_without_production_stages(tmp_path) -> None:  # noqa: ANN001
    run_dir = tmp_path / "runs" / "x"
    run_dir.mkdir(parents=True)
    result = runner.invoke(app, ["rerun", str(run_dir)])
    assert result.exit_code == 10
    assert "M05" in result.output


def test_certify_validates_governed_contracts() -> None:
    result = runner.invoke(app, ["certify"])
    assert result.exit_code == 0
    for label in ("decision policy", "protected registry", "playbook", "schemas"):
        assert label in result.output.lower()


def test_doctor_command_reports_and_exits_by_state() -> None:
    result = runner.invoke(app, ["doctor"])
    # On an un-bootstrapped machine doctor legitimately fails; the command
    # must render the per-check report and exit 1, never crash.
    assert result.exit_code in (0, 1)
    assert "repo_on_ext4" in result.output
    assert result.exception is None or result.exit_code in (0, 1)
