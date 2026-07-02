"""Typed stage orchestrator over the fixed pipeline DAG (AD-01; arch §4/§7).

Control flow is static: the DAG is the 13-stage tuple below, a stage
registry must cover it exactly (missing or unknown stages are typed
defects raised before any artifact exists), and the only dynamism is the
failure taxonomy. The orchestrator is the one layer that CATCHES halts —
it maps them to terminal run states (arch §7), records every stage
transition with timings in the manifest (NFR-502), writes the terminal
run report (machine- and human-readable, NFR-201), preserves partial
artifacts marked non-final (NFR-202), and seals the run directory.

The orchestrator exposes no input channel: nothing here reads stdin, ever
(FR-306/FR-1401 — proven by the closed-stdin acceptance test).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from burhan.core.artifacts import seeds
from burhan.core.artifacts.canonical import dumps
from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.models import format_utc_seconds
from burhan.core.errors import (
    AdvisoryStop,
    BurhanHalt,
    IntegrityHalt,
    VerificationHalt,
    get_halt_sink,
    write_halt_report,
)
from burhan.core.manifest import Manifest
from burhan.core.provenance import Provenance
from burhan.results.store import ResultsStore

# The fixed DAG (architecture §4). Order is the contract; nothing reorders it.
PIPELINE = (
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

RUN_REPORT_FILENAME = "run_report.json"
RUN_REPORT_MD_FILENAME = "RUN_REPORT.md"
NON_FINAL_MARKER = "PARTIAL_NON_FINAL.txt"


def _artifact_bytes(run_dir: Path) -> dict[str, bytes]:
    """Every run-dir file's bytes by relative path, manifest.json excluded."""
    return {
        path.relative_to(run_dir).as_posix(): path.read_bytes()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path.relative_to(run_dir).as_posix() != "manifest.json"
    }


@dataclass(frozen=True)
class StageContext:
    """Everything a stage may touch; handed to ``Stage.execute``."""

    run_dir: Path
    stage: str
    stage_seed: int
    master_seed: int
    clock: Clock
    manifest: Manifest
    provenance: Provenance
    store: ResultsStore


class Stage(Protocol):
    """One pipeline stage (AD-01): consumes/produces artifacts, executes once."""

    name: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]

    def execute(self, ctx: StageContext) -> None:
        """Run the stage; raise a taxonomy halt on failure."""
        ...


@dataclass(frozen=True)
class RunResult:
    """Terminal outcome of one orchestrated run."""

    state: str
    run_dir: Path
    report_path: Path


class Orchestrator:
    """Advances a run through the fixed DAG and owns terminal-state handling."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def run(
        self,
        run_dir: Path,
        registry: Mapping[str, Stage],
        *,
        manifest_fields: Mapping[str, Any],
    ) -> RunResult:
        """Execute the pipeline; return the terminal state (never raises halts).

        The registry must cover the fixed DAG exactly; a missing or unknown
        stage is a typed defect raised BEFORE any run artifact exists.
        """
        self._check_registry(registry)
        manifest = Manifest.open(run_dir, self._clock, manifest_fields)
        provenance = Provenance(run_dir / "PROVENANCE.jsonl", self._clock)
        store = ResultsStore(run_dir / "results", self._clock)
        master_seed = int(manifest_fields["master_seed"])  # schema-validated by open()

        executed: list[str] = []
        for index, stage_name in enumerate(PIPELINE):
            stage = registry[stage_name]
            started = format_utc_seconds(self._clock.now())
            ctx = StageContext(
                run_dir=run_dir,
                stage=stage_name,
                stage_seed=seeds.derive(master_seed, stage_name, 0),
                master_seed=master_seed,
                clock=self._clock,
                manifest=manifest,
                provenance=provenance,
                store=store,
            )
            try:
                stage.execute(ctx)
            except BurhanHalt as exc:
                return self._terminate(
                    run_dir,
                    manifest,
                    provenance,
                    stage_name,
                    started,
                    exc,
                    remaining=PIPELINE[index + 1 :],
                    executed=executed,
                )
            except Exception as exc:  # noqa: BLE001 — unclassifiable => IntegrityHalt (NFR-201)
                wrapped = IntegrityHalt(
                    "unclassifiable stage failure re-raised as integrity halt (NFR-201)",
                    report={"stage": stage_name, "type": type(exc).__name__, "error": str(exc)},
                )
                get_halt_sink().emit(wrapped.to_report())
                write_halt_report(wrapped, run_dir)
                return self._terminate(
                    run_dir,
                    manifest,
                    provenance,
                    stage_name,
                    started,
                    wrapped,
                    remaining=PIPELINE[index + 1 :],
                    executed=executed,
                )
            finished = format_utc_seconds(self._clock.now())
            manifest.record_stage(
                {"stage": stage_name, "state": "PASSED", "started": started, "finished": finished}
            )
            provenance.append(
                {
                    "stage": stage_name,
                    "actor": "orchestrator",
                    "event_type": "stage_complete",
                    "trigger": "stage executed",
                    "effect": f"{stage_name} PASSED",
                }
            )
            executed.append(stage_name)

        report_path = self._write_report(
            run_dir, manifest_fields, state="COMPLETED", executed=executed
        )
        manifest.seal("COMPLETED")
        return RunResult(state="COMPLETED", run_dir=run_dir, report_path=report_path)

    def rerun(
        self,
        source_run_dir: Path,
        registry: Mapping[str, Stage],
        *,
        target_run_dir: Path,
    ) -> RunResult:
        """Re-execute a sealed run from its manifest; assert byte-identity.

        Full re-execution, never partial resume (AD-03). Every regenerated
        artifact must be byte-identical to the source (manifest.json
        excluded — it carries the seal); any difference, addition, or
        omission raises :class:`VerificationHalt` naming the files
        (AT-M04-4, NFR-101).
        """
        source_manifest = Manifest.verify_seal(source_run_dir)  # sealed + untampered
        if target_run_dir.exists():
            raise IntegrityHalt(
                "rerun target already exists; run directories are written once (AD-06)",
                report={"target": str(target_run_dir)},
            )
        fields = source_manifest.model_dump(mode="json", by_alias=True, exclude_unset=True)
        # Manifest.open owns lifecycle + schema_version; everything else carries over.
        for owned_key in ("schema_version", "started", "finished", "state", "stages", "seal"):
            fields.pop(owned_key, None)
        result = self.run(target_run_dir, registry, manifest_fields=fields)

        source_map = _artifact_bytes(source_run_dir)
        target_map = _artifact_bytes(target_run_dir)
        missing = sorted(source_map.keys() - target_map.keys())
        added = sorted(target_map.keys() - source_map.keys())
        differing = sorted(
            name
            for name in source_map.keys() & target_map.keys()
            if source_map[name] != target_map[name]
        )
        if missing or added or differing:
            raise VerificationHalt(
                "rerun identity assertion failed: regenerated artifacts are not "
                "byte-identical (NFR-101)",
                report={"missing": missing, "added": added, "differing": differing},
            )
        return result

    # -- internals ---------------------------------------------------------------

    @staticmethod
    def _check_registry(registry: Mapping[str, Stage]) -> None:
        missing = [name for name in PIPELINE if name not in registry]
        unknown = [name for name in registry if name not in PIPELINE]
        if missing or unknown:
            raise IntegrityHalt(
                "stage registry must cover the fixed DAG exactly (AD-01)",
                report={"missing": missing, "unknown": unknown},
            )

    def _terminate(
        self,
        run_dir: Path,
        manifest: Manifest,
        provenance: Provenance,
        failed_stage: str,
        started: str,
        exc: BurhanHalt,
        *,
        remaining: tuple[str, ...],
        executed: list[str],
    ) -> RunResult:
        finished = format_utc_seconds(self._clock.now())
        manifest.record_stage(
            {"stage": failed_stage, "state": "FAILED", "started": started, "finished": finished}
        )
        provenance.append(
            {
                "stage": failed_stage,
                "actor": "orchestrator",
                "event_type": "halt" if exc.run_state.startswith("HALTED") else "advisory_issued",
                "trigger": exc.message,
                "effect": f"run moves to {exc.run_state}",
            }
        )
        boundary = isinstance(exc, AdvisoryStop)
        if boundary:
            skip_stamp = format_utc_seconds(self._clock.now())
            for skipped in remaining:
                manifest.record_stage(
                    {"stage": skipped, "state": "SKIPPED_BOUNDARY", "started": skip_stamp}
                )
        else:
            (run_dir / NON_FINAL_MARKER).write_text(
                "Partial results preserved at a hard failure; NON-FINAL (NFR-202).\n"
                f"Terminal state: {exc.run_state}; failed stage: {failed_stage}.\n",
                encoding="utf-8",
            )
        report_path = self._write_report(
            run_dir,
            {},
            state=exc.run_state,
            executed=executed,
            failed_stage=failed_stage,
            halt=exc,
        )
        manifest.seal(exc.run_state)
        return RunResult(state=exc.run_state, run_dir=run_dir, report_path=report_path)

    def _write_report(
        self,
        run_dir: Path,
        manifest_fields: Mapping[str, Any],
        *,
        state: str,
        executed: list[str],
        failed_stage: str | None = None,
        halt: BurhanHalt | None = None,
    ) -> Path:
        report: dict[str, Any] = {
            "state": state,
            "completed_stages": list(executed),
        }
        if failed_stage is not None:
            report["failed_stage"] = failed_stage
        if halt is not None:
            report["halt"] = halt.to_report()
        report_path = run_dir / RUN_REPORT_FILENAME
        report_path.write_text(dumps(report) + "\n", encoding="utf-8")
        lines = [
            "# RUN REPORT",
            "",
            f"- terminal state: {state}",
            f"- stages completed: {', '.join(executed) if executed else 'none'}",
        ]
        if failed_stage is not None:
            report_lines_halt = halt.message if halt is not None else ""
            lines.append(f"- failed stage: {failed_stage}")
            lines.append(f"- condition: {report_lines_halt}")
        lines.append("")
        (run_dir / RUN_REPORT_MD_FILENAME).write_text("\n".join(lines), encoding="utf-8")
        return report_path
