"""Method compliance tracker (FR-1106; PLAYBOOK_SCHEMA.md compliance rules).

One append-only row per playbook step — completed / failed / flagged — with
``completed`` permitted only when every one of the step's ``outputs``
prefixes actually landed in the results store. The rendered
``METHOD_COMPLIANCE_CHECKLIST.md`` is derived evidence, not a hand-written
claim: it is generated purely from recorded rows, in playbook step order,
every step exactly once, and it refuses to render an unevidenced sequence.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, NoReturn

from burhan.core.artifacts.canonical import dumps
from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.models import format_utc_seconds
from burhan.core.errors import IntegrityHalt, halt_with_file
from burhan.core.playbook import Playbook
from burhan.results.store import ResultsStore

COMPLIANCE_STATUSES = ("completed", "failed", "flagged")

_ROW_FIELDS = ("step_id", "status", "evidence", "ts")


class Compliance:
    """Append-only compliance rows for one run, bound to playbook + store."""

    def __init__(self, playbook: Playbook, store: ResultsStore, path: Path, clock: Clock) -> None:
        self._playbook = playbook
        self._store = store
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._rows: dict[str, dict[str, Any]] = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        self._replay()

    def mark(self, step_id: str, status: str, evidence: str) -> dict[str, Any]:
        """Record one step's outcome (completed / failed / flagged).

        ``completed`` requires every ``outputs`` prefix of the step to be
        present in the results store (FR-1106); a step is markable exactly
        once — re-marking is mutation and halts.
        """
        step_outputs = self._playbook.outputs(step_id)  # halts on unknown step
        if status not in COMPLIANCE_STATUSES:
            self._halt(
                IntegrityHalt(
                    "compliance status must be completed, failed, or flagged",
                    report={"step": step_id, "status": status},
                )
            )
        if not evidence:
            self._halt(
                IntegrityHalt(
                    "compliance rows are recorded evidence; evidence must be non-empty",
                    report={"step": step_id},
                )
            )
        with self._lock:
            if step_id in self._rows:
                self._halt(
                    IntegrityHalt(
                        "compliance rows are append-only: step already recorded",
                        report={"step": step_id, "existing": self._rows[step_id]["status"]},
                    )
                )
            if status == "completed":
                for prefix in step_outputs:
                    if not any(True for _ in self._store.iter(prefix)):
                        self._halt(
                            IntegrityHalt(
                                "step cannot be marked completed: required outputs "
                                "prefix absent from the results store (FR-1106)",
                                report={"step": step_id, "missing_prefix": prefix},
                            )
                        )
            row: dict[str, Any] = {
                "step_id": step_id,
                "status": status,
                "evidence": evidence,
                "ts": self._stamp(),
            }
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(dumps(row) + "\n")
            self._rows[step_id] = row
        return dict(row)

    def render(self) -> str:
        """Render METHOD_COMPLIANCE_CHECKLIST.md from recorded rows only.

        Every playbook step appears exactly once, in playbook order; an
        unrecorded step means the approved sequence is not evidenced in
        full, and the render refuses (FR-1106).
        """
        missing = [step_id for step_id in self._playbook.step_ids if step_id not in self._rows]
        if missing:
            self._halt(
                IntegrityHalt(
                    "compliance render refused: the approved sequence is not "
                    "evidenced in full (FR-1106)",
                    report={"unrecorded_steps": missing},
                )
            )
        lines = [
            "# METHOD_COMPLIANCE_CHECKLIST",
            "",
            f"Playbook: {self._playbook.id} v{self._playbook.version} "
            f"(sha256 {self._playbook.sha256})",
            "",
            "| Step | Stage | Title | Status | Evidence | Recorded |",
            "|---|---|---|---|---|---|",
        ]
        for step_id in self._playbook.step_ids:
            step = self._playbook.step(step_id)
            row = self._rows[step_id]
            lines.append(
                f"| {step_id} | {step['stage']} | {step['title']} "
                f"| {row['status']} | {row['evidence']} | {row['ts']} |"
            )
        lines.append("")
        return "\n".join(lines)

    # -- internals ---------------------------------------------------------------

    def _halt(self, exc: IntegrityHalt) -> NoReturn:
        halt_with_file(exc, self._path.parent)

    def _stamp(self) -> str:
        try:
            return format_utc_seconds(self._clock.now())
        except ValueError as exc:
            self._halt(
                IntegrityHalt(
                    "injected clock produced a non-canonical timestamp",
                    report={"error": str(exc)},
                )
            )

    def _replay(self) -> None:
        if not self._path.exists():
            return
        for line_number, line in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                self._halt(
                    IntegrityHalt(
                        "compliance row is not valid JSON (external mutation?)",
                        report={"line": line_number, "error": str(exc)},
                    )
                )
            if not isinstance(raw, dict) or sorted(raw) != sorted(_ROW_FIELDS):
                self._halt(
                    IntegrityHalt(
                        "compliance row shape invalid (external mutation?)",
                        report={"line": line_number},
                    )
                )
            step_id = str(raw["step_id"])
            if step_id not in self._playbook.step_ids:
                self._halt(
                    IntegrityHalt(
                        "compliance row references a step outside the playbook",
                        report={"line": line_number, "step": step_id},
                    )
                )
            if str(raw["status"]) not in COMPLIANCE_STATUSES:
                self._halt(
                    IntegrityHalt(
                        "compliance row carries an invalid status",
                        report={"line": line_number, "status": str(raw["status"])},
                    )
                )
            if step_id in self._rows:
                self._halt(
                    IntegrityHalt(
                        "duplicate compliance row for step (external mutation?)",
                        report={"line": line_number, "step": step_id},
                    )
                )
            self._rows[step_id] = raw
