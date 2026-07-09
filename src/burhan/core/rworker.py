"""File-based Rscript worker harness, Python side (AD-02; architecture §6).

Every statistical call is: write ``call_<id>.input.json`` → spawn
``Rscript workers/r/harness.R <worker.R> <input> <output>`` → read and
envelope-check ``call_<id>.output.json``. Workers are stateless; the
harness asserts renv is clean and sets the injected seed before any
computation (NFR-102). Worker stderr is captured; a nonzero exit,
schema-invalid output envelope, or renv drift each produce
``IntegrityHalt`` with the captured report (AT-M04-5, NFR-201). Call
files are written once (AD-06).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from burhan.core.artifacts.canonical import dumps
from burhan.core.errors import IntegrityHalt, halt_with_file

HARNESS_FILENAME = "harness.R"
CALLS_SUBDIR = "stats"

_RENV_DRIFT_MARKER = "RENV_DRIFT"


def workers_dir() -> Path:
    """Location of the R workers (repo ``workers/r``)."""
    return Path(__file__).resolve().parents[3] / "workers" / "r"


_default_workers_dir = workers_dir


class RWorker:
    """Spawns stateless R workers through the file-based call contract."""

    def __init__(
        self,
        *,
        rscript: str = "Rscript",
        workers_dir: Path | None = None,
        timeout_seconds: int = 600,
    ) -> None:
        self._rscript = rscript
        self._workers_dir = (
            workers_dir if workers_dir is not None else _default_workers_dir()
        ).resolve()
        self._timeout = timeout_seconds

    def call(
        self,
        module: str,
        payload: Mapping[str, Any],
        *,
        call_id: str,
        run_dir: Path,
        seed: int,
    ) -> dict[str, Any]:
        """Execute one worker call; return its ``result`` payload.

        Args:
            module: Worker module name (``<module>.R`` under workers/r).
            payload: JSON-canonical call payload, passed by file.
            call_id: Unique id for this call's input/output pair.
            run_dir: Run directory owning the ``stats/`` call files.
            seed: Derived seed the worker must set before computing.
        """
        # Absolute run_dir so the input/output argv paths stay valid when the R
        # subprocess runs with cwd=self._workers_dir (TC-19 path safety).
        run_dir = run_dir.resolve()
        worker_path = self._workers_dir / f"{module}.R"
        calls_dir = run_dir / CALLS_SUBDIR
        calls_dir.mkdir(parents=True, exist_ok=True)
        if not worker_path.is_file():
            self._halt(
                calls_dir,
                IntegrityHalt(
                    "unknown R worker module",
                    report={"module": module, "expected_file": str(worker_path)},
                ),
            )
        input_path = calls_dir / f"call_{call_id}.input.json"
        output_path = calls_dir / f"call_{call_id}.output.json"
        if input_path.exists() or output_path.exists():
            self._halt(
                calls_dir,
                IntegrityHalt(
                    "call files are written once per call id (AD-06)",
                    report={"call_id": call_id},
                ),
            )
        envelope = {
            "call_id": call_id,
            "module": module,
            "seed": seed,
            "payload": dict(payload),
        }
        input_path.write_text(dumps(envelope) + "\n", encoding="utf-8")

        argv = [
            self._rscript,
            str(self._workers_dir / HARNESS_FILENAME),
            str(worker_path),
            str(input_path),
            str(output_path),
        ]
        try:
            completed = subprocess.run(  # noqa: S603 — argv fixed above; no shell
                argv,
                cwd=self._workers_dir,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._halt(
                calls_dir,
                IntegrityHalt(
                    "R worker process could not be executed",
                    report={"call_id": call_id, "error": str(exc)},
                ),
            )
        stderr = completed.stderr
        if completed.returncode != 0:
            reason = (
                "renv drift detected at worker startup (NFR-102)"
                if _RENV_DRIFT_MARKER in stderr
                else "R worker exited nonzero"
            )
            self._halt(
                calls_dir,
                IntegrityHalt(
                    reason,
                    report={
                        "call_id": call_id,
                        "module": module,
                        "exit_code": completed.returncode,
                        "stderr": stderr.strip(),
                    },
                ),
            )
        if not output_path.is_file():
            self._halt(
                calls_dir,
                IntegrityHalt(
                    "R worker exited cleanly but wrote no output file",
                    report={"call_id": call_id, "stderr": stderr.strip()},
                ),
            )
        try:
            raw = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self._halt(
                calls_dir,
                IntegrityHalt(
                    "R worker output is not valid JSON",
                    report={"call_id": call_id, "error": str(exc), "stderr": stderr.strip()},
                ),
            )
        if (
            not isinstance(raw, dict)
            or raw.get("call_id") != call_id
            or raw.get("status") != "ok"
            or "result" not in raw
        ):
            self._halt(
                calls_dir,
                IntegrityHalt(
                    "R worker output envelope is schema-invalid "
                    "(expected {call_id, status: ok, result})",
                    report={
                        "call_id": call_id,
                        "keys": sorted(raw) if isinstance(raw, dict) else str(type(raw)),
                        "stderr": stderr.strip(),
                    },
                ),
            )
        result: dict[str, Any] = raw["result"]
        return result

    @staticmethod
    def _halt(calls_dir: Path, exc: IntegrityHalt) -> NoReturn:
        halt_with_file(exc, calls_dir)
