"""Append-only provenance (sanad) log appender (NFR-301; architecture §3).

One appender instance is the single writer of a run's ``PROVENANCE.jsonl``
(single orchestrator process, AD-06); a ``threading.Lock`` serializes
seq-assignment and writes, so ``seq`` is strictly increasing and gap-free
under concurrent stage writes (AT-M01-5). Every entry is validated against
the governed schema BEFORE anything is written; a failed append consumes no
sequence number.

Content tamper-evidence for the log file itself is the manifest seal
(architecture §9/§11) — the provenance schema defines no per-entry hash.
Structural tampering (gaps, reordering, malformed lines) halts on reopen.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.loader import dump_canonical, validate_and_build
from burhan.core.artifacts.models import ProvenanceEntry, format_utc_seconds
from burhan.core.errors import BurhanHalt, IntegrityHalt, halt_with_file, write_halt_report

PROVENANCE_FILENAME = "PROVENANCE.jsonl"

_APPENDER_OWNED_FIELDS = ("schema_version", "seq", "ts")


class Provenance:
    """Sequenced, schema-validated appender for one run's sanad log."""

    def __init__(self, path: Path, clock: Clock) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._next_seq = self._replay() + 1

    def append(self, fields: Mapping[str, object]) -> ProvenanceEntry:
        """Validate and append one provenance entry, assigning ``seq``/``ts``.

        The appender owns ``schema_version``, ``seq``, and ``ts`` (injected
        clock); supplying any of them is a defect. Nothing is written unless
        the full entry validates.
        """
        payload: dict[str, Any] = dict(fields)
        for owned in _APPENDER_OWNED_FIELDS:
            if owned in payload:
                self._halt(
                    IntegrityHalt(
                        "appender-owned field supplied by caller",
                        report={"field": owned},
                    )
                )
        with self._lock:
            payload["schema_version"] = 1
            payload["seq"] = self._next_seq
            payload["ts"] = self._stamp()
            entry = self._build(payload)
            line = dump_canonical(entry)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._next_seq += 1
        return entry

    # -- internals -----------------------------------------------------------

    def _halt(self, exc: IntegrityHalt) -> NoReturn:
        halt_with_file(exc, self._path.parent)

    def _build(self, payload: dict[str, Any]) -> ProvenanceEntry:
        try:
            return validate_and_build(ProvenanceEntry, payload)
        except BurhanHalt as exc:
            write_halt_report(exc, self._path.parent)  # already sink-emitted
            raise

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

    def _replay(self) -> int:
        if not self._path.exists():
            return 0
        count = 0
        for line_number, line in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                self._halt(
                    IntegrityHalt(
                        "provenance line is not valid JSON (external mutation?)",
                        report={"line": line_number, "error": str(exc)},
                    )
                )
            entry = self._build(raw)
            count += 1
            if entry.seq != count:
                self._halt(
                    IntegrityHalt(
                        "provenance seq is not gap-free strictly increasing (external mutation?)",
                        report={"line": line_number, "expected": count, "found": entry.seq},
                    )
                )
        return count
