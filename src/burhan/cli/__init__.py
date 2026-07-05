"""Burhān CLI (FR-1401): ``run``, ``rerun``, ``certify``, ``doctor``.

One command starts a run; no interactive input is required after Gate 1
(FR-306 — the orchestrator exposes no input channel at all). ``run``/``rerun``
execute the full 13-stage DAG under ``--certification`` (offline canned, D2)
or ``--live`` (TC-16 real-provider path: ``--live`` extracts the contract for
the researcher glance, ``--live --confirm`` runs the DAG, ``rerun --live``
replays the archives). Without a mode flag they refuse cleanly; the engine
never improvises a pipeline (FR-1302 doctrine). Exit codes map terminal
states: 0 = COMPLETED / COMPLETED_TO_BOUNDARY · 10 = HALTED_INTEGRITY ·
11 = HALTED_VERIFICATION · 12 = HALTED_GATE · 1 = doctor not green.
"""

from __future__ import annotations

from pathlib import Path

import typer

from burhan.cli.doctor import production_inputs, run_doctor
from burhan.core.errors import BurhanHalt

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)

EXIT_BY_STATE = {
    "COMPLETED": 0,
    "COMPLETED_TO_BOUNDARY": 0,
    "HALTED_INTEGRITY": 10,
    "HALTED_VERIFICATION": 11,
    "HALTED_GATE": 12,
}


@app.command()
def run(
    study_dir: Path,
    certification: bool = typer.Option(
        False, "--certification", help="offline certified-workstation dry run (TC-15/M5, D2)"
    ),
    live: bool = typer.Option(
        False, "--live", help="live-provider run (TC-16): extract, then --confirm after the glance"
    ),
    confirm: bool = typer.Option(
        False, "--confirm", help="confirm a --live extraction and run the full DAG (TC-16)"
    ),
) -> None:
    """Execute a full study run from a study directory (headless after Gate 1)."""
    if live:
        from burhan.cli.live import live_confirm, live_extract

        try:
            if confirm:
                result = live_confirm(study_dir)
                typer.echo(f"run terminal state: {result.state} ({result.run_dir})")
                raise typer.Exit(
                    code=EXIT_BY_STATE.get(result.state, EXIT_BY_STATE["HALTED_INTEGRITY"])
                )
            extract = live_extract(study_dir)
            typer.echo(
                f"extracted contract -> {extract.config_path}\n"
                "glance it, then re-run with --live --confirm to run Gate 1 + Stage-1A."
            )
            raise typer.Exit(code=0)
        except BurhanHalt as exc:
            typer.echo(f"live run halted: {exc.message}")
            raise typer.Exit(code=EXIT_BY_STATE.get(exc.run_state, 10)) from exc
    if confirm:
        typer.echo("no run: --confirm requires --live (TC-16).")
        raise typer.Exit(code=EXIT_BY_STATE["HALTED_INTEGRITY"])
    if not certification:
        typer.echo(
            "no run: pass --live for a real-provider run (TC-16) or --certification for "
            "the offline certified-workstation dry run (D2)."
        )
        raise typer.Exit(code=EXIT_BY_STATE["HALTED_INTEGRITY"])
    from burhan.cli.certification import certification_run

    result = certification_run(study_dir)
    typer.echo(f"run terminal state: {result.state} ({result.run_dir})")
    raise typer.Exit(code=EXIT_BY_STATE.get(result.state, EXIT_BY_STATE["HALTED_INTEGRITY"]))


@app.command()
def rerun(
    run_dir: Path,
    certification: bool = typer.Option(
        False, "--certification", help="re-execute a sealed certification run (TC-15/M5, D2)"
    ),
    live: bool = typer.Option(
        False, "--live", help="re-execute a sealed live run by replaying archives (TC-16, NFR-101)"
    ),
) -> None:
    """Re-execute a sealed run from its manifest and assert byte-identity."""
    if live:
        from burhan.cli.live import live_rerun

        try:
            result = live_rerun(run_dir)
            typer.echo(f"rerun terminal state: {result.state} ({result.run_dir})")
            raise typer.Exit(
                code=EXIT_BY_STATE.get(result.state, EXIT_BY_STATE["HALTED_INTEGRITY"])
            )
        except BurhanHalt as exc:
            typer.echo(f"live rerun halted: {exc.message}")
            raise typer.Exit(code=EXIT_BY_STATE.get(exc.run_state, 10)) from exc
    if not certification:
        typer.echo(
            "no rerun: pass --live to replay a sealed live run (TC-16) or --certification "
            "for a sealed certification run (D2)."
        )
        raise typer.Exit(code=EXIT_BY_STATE["HALTED_INTEGRITY"])
    from burhan.cli.certification import certification_rerun

    result = certification_rerun(run_dir)
    typer.echo(f"rerun terminal state: {result.state} ({result.run_dir})")
    raise typer.Exit(code=EXIT_BY_STATE.get(result.state, EXIT_BY_STATE["HALTED_INTEGRITY"]))


@app.command()
def certify() -> None:
    """Validate the governed machine contracts in certification mode."""
    from burhan.core.artifacts.schemas import GOVERNED_SCHEMA_FILES, load_schema
    from burhan.core.playbook import Playbook, playbooks_dir
    from burhan.core.policy import Policy, governance_dir
    from burhan.core.registry import Registry

    try:
        policy = Policy.load(
            governance_dir() / "decision_policy.template.yaml",
            mode="certification",
            playbook_path=playbooks_dir() / "CB_SEM_PLAYBOOK_v1.0.yaml",
        )
        typer.echo("decision policy: OK (D1-D3; playbook refs resolve)")
        Registry.load(
            governance_dir() / "protected_decisions.registry.yaml",
            mode="certification",
            policy=policy,
        )
        typer.echo("protected registry: OK (R1-R2; D3 pointer)")
        Playbook.load(
            playbooks_dir() / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification", policy=policy
        )
        typer.echo("playbook: OK (P1-P5)")
        for name in sorted(GOVERNED_SCHEMA_FILES):
            load_schema(name)
        typer.echo(f"schemas: OK ({len(GOVERNED_SCHEMA_FILES)} machine contracts load)")
    except BurhanHalt as exc:
        typer.echo(f"certification validation halted: {exc.message}")
        raise typer.Exit(code=EXIT_BY_STATE.get(exc.run_state, 10)) from exc


@app.command()
def doctor() -> None:
    """Verify the environment per 04_ENVIRONMENT_AND_STACK §9."""
    report = run_doctor(production_inputs())
    typer.echo(report.render())
    raise typer.Exit(code=0 if report.passed else 1)
