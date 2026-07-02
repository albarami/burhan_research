"""Append-only results store (FR-1001; AD-05; architecture §8).

JSONL of canonical-JSON statistic entries plus a derived ``index.json``
(regenerable; the JSONL is the truth). Single writer per stage window;
consumers resolve statistic IDs, never values.

Grammar enforcement includes the stage binding: the ID's first segment IS
the ``stage`` nonterminal of the grammar (03_ARCHITECTURE.md §8
``<stage>.<family>...``; schemas/00_README.md ``id := stage "." family``),
so an entry whose ``id`` opens with a different stage than its ``stage``
field violates the grammar and is rejected.

Append-only is API-level (no mutating method exists) and tamper-evident:
reopening replays every line, re-verifies every entry hash, and cross-checks
the index; any mismatch halts. Failures co-locate ``halt_report.json`` with
the store (standards §4; PLAN v2 Fix 5).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, NoReturn

from burhan.core.artifacts.canonical import dumps, sha256_canonical
from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.loader import dump_canonical, validate_and_build
from burhan.core.artifacts.models import ResultsStoreEntry, format_utc_seconds
from burhan.core.errors import BurhanHalt, IntegrityHalt, halt_with_file, write_halt_report

RESULTS_FILENAME = "results.jsonl"
INDEX_FILENAME = "index.json"

_PLACEHOLDER_HASH = "0" * 64
_STORE_OWNED_FIELDS = ("schema_version", "created", "hash")


class ResultsStore:
    """Append-only statistic store bound to one run's ``results/`` directory."""

    def __init__(self, directory: Path, clock: Clock) -> None:
        self._directory = directory
        self._clock = clock
        self._path = directory / RESULTS_FILENAME
        self._index_path = directory / INDEX_FILENAME
        self._entries: dict[str, ResultsStoreEntry] = {}
        self._order: list[str] = []
        directory.mkdir(parents=True, exist_ok=True)
        self._replay()

    # -- public API (write / resolve / iter — nothing mutates) --------------

    def write(self, fields: Mapping[str, object]) -> ResultsStoreEntry:
        """Validate, hash, and append one statistic entry.

        The store owns ``schema_version``, ``created`` (injected clock), and
        ``hash`` (SHA-256 over canonical JSON of all fields except ``hash``);
        supplying any of them is a defect.
        """
        payload: dict[str, Any] = dict(fields)
        for owned in _STORE_OWNED_FIELDS:
            if owned in payload:
                self._halt(
                    IntegrityHalt(
                        "store-owned field supplied by caller",
                        report={"field": owned},
                    )
                )
        payload["schema_version"] = 1
        payload["created"] = self._stamp()

        stat_id = payload.get("id")
        stage = payload.get("stage")
        if isinstance(stat_id, str) and isinstance(stage, str):
            if stat_id.split(".", 1)[0] != stage:
                self._halt(
                    IntegrityHalt(
                        "id grammar violation: first segment must be the entry's stage "
                        "(03_ARCHITECTURE.md §8)",
                        report={"id": stat_id, "stage": stage},
                    )
                )
        if isinstance(stat_id, str) and stat_id in self._entries:
            self._halt(
                IntegrityHalt(
                    "duplicate statistic id: the store is append-only per run",
                    report={"id": stat_id},
                )
            )

        payload["hash"] = _PLACEHOLDER_HASH
        draft = self._build(payload)
        body = draft.model_dump(mode="json", by_alias=True, exclude_unset=True)
        del body["hash"]
        payload["hash"] = sha256_canonical(body)
        entry = self._build(payload)

        line = dump_canonical(entry)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._entries[entry.id] = entry
        self._order.append(entry.id)
        self._write_index()
        return entry

    def resolve(self, stat_id: str) -> ResultsStoreEntry:
        """Return the entry for ``stat_id``; an unknown ID is an integrity defect."""
        entry = self._entries.get(stat_id)
        if entry is None:
            self._halt(
                IntegrityHalt(
                    "unknown statistic id referenced",
                    report={"id": stat_id},
                )
            )
        return entry

    def iter(self, prefix: str = "") -> Iterator[ResultsStoreEntry]:
        """Yield entries in insertion order whose ID matches ``prefix``.

        Matching is on whole dot-segments: ``structural.fit`` matches
        ``structural.fit`` and ``structural.fit.rmsea``, never
        ``structural.fitness.x``. An empty prefix yields everything.
        """
        for stat_id in self._order:
            if not prefix or stat_id == prefix or stat_id.startswith(prefix + "."):
                yield self._entries[stat_id]

    # -- internals -----------------------------------------------------------

    def _halt(self, exc: IntegrityHalt) -> NoReturn:
        halt_with_file(exc, self._directory)

    def _build(self, payload: dict[str, Any]) -> ResultsStoreEntry:
        try:
            return validate_and_build(ResultsStoreEntry, payload)
        except BurhanHalt as exc:
            write_halt_report(exc, self._directory)  # already sink-emitted by halt()
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

    def _replay(self) -> None:
        if not self._path.exists():
            if self._index_path.exists():
                self._halt(
                    IntegrityHalt(
                        "index.json present without results.jsonl",
                        report={"index": str(self._index_path)},
                    )
                )
            self._write_index()
            return
        for line_number, line in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                self._halt(
                    IntegrityHalt(
                        "results store line is not valid JSON (external mutation?)",
                        report={"line": line_number, "error": str(exc)},
                    )
                )
            entry = self._build(raw)
            if entry.id in self._entries:
                self._halt(
                    IntegrityHalt(
                        "duplicate statistic id in store file (external mutation?)",
                        report={"id": entry.id, "line": line_number},
                    )
                )
            body = entry.model_dump(mode="json", by_alias=True, exclude_unset=True)
            recorded = body.pop("hash")
            recomputed = sha256_canonical(body)
            if recorded != recomputed:
                self._halt(
                    IntegrityHalt(
                        "entry hash mismatch (external mutation?)",
                        report={
                            "id": entry.id,
                            "line": line_number,
                            "recorded": recorded,
                            "recomputed": recomputed,
                        },
                    )
                )
            self._entries[entry.id] = entry
            self._order.append(entry.id)
        if self._index_path.exists():
            derived = {stat_id: self._entries[stat_id].hash for stat_id in self._order}
            try:
                recorded_index = json.loads(self._index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                self._halt(
                    IntegrityHalt(
                        "index.json is not valid JSON (external mutation?)",
                        report={"error": str(exc)},
                    )
                )
            if recorded_index != derived:
                self._halt(
                    IntegrityHalt(
                        "index.json disagrees with results.jsonl (external mutation?)",
                        report={
                            "index_ids": sorted(recorded_index)[:10],
                            "derived_ids": sorted(derived)[:10],
                        },
                    )
                )
        else:
            self._write_index()

    def _write_index(self) -> None:
        derived = {stat_id: self._entries[stat_id].hash for stat_id in self._order}
        tmp = self._index_path.with_suffix(".json.tmp")
        tmp.write_text(dumps(derived) + "\n", encoding="utf-8")
        os.replace(tmp, self._index_path)
