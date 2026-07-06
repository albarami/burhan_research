"""CLI routing for the TC-16 live path (AT-M16-1 surface; fast, no DAG).

Monkeypatches the ``live_*`` functions so routing and exit-code mapping are
proven without running the real pipeline (that is IT-7's job). The ``--live``
extraction exits 0 with a glance hint; ``--live --confirm`` runs and maps the
terminal state; ``--confirm`` without ``--live`` refuses; a live halt maps to
its exit code; ``rerun --live`` routes to the replay path.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from typer.testing import CliRunner

from burhan.cli import app
from burhan.core.errors import IntegrityHalt, halt
from burhan.core.orchestrator import RunResult

runner = CliRunner()


def test_run_live_extract_routes_and_exits_zero(tmp_path: Path, monkeypatch: Any) -> None:
    seen: dict[str, Path] = {}

    def fake_extract(study_dir: Path) -> SimpleNamespace:
        seen["study_dir"] = study_dir
        return SimpleNamespace(config_path=study_dir / "config" / "study_config.yaml")

    monkeypatch.setattr("burhan.cli.live.live_extract", fake_extract)
    result = runner.invoke(app, ["run", str(tmp_path), "--live"])
    assert result.exit_code == 0
    assert seen["study_dir"] == tmp_path
    assert "glance" in result.output.lower()


def test_run_live_confirm_routes_and_maps_state(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "burhan.cli.live.live_confirm",
        lambda study_dir, reference_path=None: RunResult(
            state="COMPLETED", run_dir=tmp_path / "runs" / "x", report_path=tmp_path / "r"
        ),
    )
    result = runner.invoke(app, ["run", str(tmp_path), "--live", "--confirm"])
    assert result.exit_code == 0
    assert "COMPLETED" in result.output


def test_run_live_confirm_forwards_reference_path(tmp_path: Path, monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake(study_dir: Path, reference_path: Path | None = None) -> RunResult:
        seen["reference_path"] = reference_path
        return RunResult(state="COMPLETED", run_dir=tmp_path, report_path=tmp_path / "r")

    monkeypatch.setattr("burhan.cli.live.live_confirm", fake)
    reference = tmp_path / "reference_set.yaml"
    reference.write_text("study_id: s\n", encoding="utf-8")
    result = runner.invoke(
        app, ["run", str(tmp_path), "--live", "--confirm", "--reference", str(reference)]
    )
    assert result.exit_code == 0
    assert seen["reference_path"] == reference  # --reference reaches live_confirm (item 10)


def test_run_confirm_without_live_refuses(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(tmp_path), "--confirm"])
    assert result.exit_code == 10
    assert "--live" in result.output


def test_run_live_halt_maps_to_exit_ten(tmp_path: Path, monkeypatch: Any) -> None:
    def boom(study_dir: Path, reference_path: Path | None = None) -> RunResult:
        halt(IntegrityHalt("no pending-glance token", report={}))

    monkeypatch.setattr("burhan.cli.live.live_confirm", boom)
    result = runner.invoke(app, ["run", str(tmp_path), "--live", "--confirm"])
    assert result.exit_code == 10
    assert "halted" in result.output.lower()


def test_rerun_live_routes_and_maps_state(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "burhan.cli.live.live_rerun",
        lambda run_dir: RunResult(state="COMPLETED", run_dir=run_dir, report_path=run_dir / "r"),
    )
    result = runner.invoke(app, ["rerun", str(tmp_path / "runs" / "x"), "--live"])
    assert result.exit_code == 0
