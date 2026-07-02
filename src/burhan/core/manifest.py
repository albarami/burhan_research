"""Run manifest lifecycle: open, record stages, seal, verify (NFR-100/102).

The manifest is the one rewrite-permitted file in a run directory — the
governed schema says "written incrementally; sealed at terminal state"
(run_manifest.schema.json). Every rewrite is atomic (tmp + rename) and
re-validated against the governed schema.

``seal`` computes the hash-tree root over the run directory: relative POSIX
paths sorted bytewise, each leaf ``[path, sha256(file)]``, root = SHA-256
over the canonical JSON of the leaf list. The manifest participates through
a **normalized leaf** — its own content with only the self-referential
``seal.hash_tree_root`` field excluded — so post-seal edits to any manifest
field, including ``seal.sealed_at``, change the recomputed root (REJECT
fix 1); an edit to the stored root itself trivially mismatches the
recomputation. ``verify_seal`` additionally requires the manifest file bytes
to be the canonical serialization of their content, so formatting-only
edits are detected too. Symlinks do not belong in a run directory and halt.
``verify_seal`` never writes into the sealed directory (architecture §11).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from burhan.core.artifacts.canonical import sha256_canonical, sha256_file
from burhan.core.artifacts.clock import Clock
from burhan.core.artifacts.loader import dump_canonical, validate_and_build
from burhan.core.artifacts.models import RunManifest, format_utc_seconds
from burhan.core.errors import BurhanHalt, IntegrityHalt, halt, halt_with_file, write_halt_report

MANIFEST_FILENAME = "manifest.json"

TERMINAL_STATES = frozenset(
    {
        "COMPLETED",
        "COMPLETED_TO_BOUNDARY",
        "HALTED_INTEGRITY",
        "HALTED_VERIFICATION",
        "HALTED_GATE",
    }
)

_MANIFEST_OWNED_FIELDS = ("schema_version", "started", "state", "stages", "finished", "seal")


def _normalized_manifest_hash(payload: dict[str, Any]) -> str:
    """Hash of the manifest content with only ``seal.hash_tree_root`` removed."""
    normalized = dict(payload)
    seal = normalized.get("seal")
    if isinstance(seal, dict):
        normalized["seal"] = {key: value for key, value in seal.items() if key != "hash_tree_root"}
    return sha256_canonical(normalized)


def _hash_tree_root(run_dir: Path, manifest_payload: dict[str, Any]) -> str:
    """Root hash over every run-dir file plus the normalized manifest leaf.

    The physical ``manifest.json`` is skipped (it will contain the root);
    the manifest's CONTENT enters the tree as the normalized leaf, so no
    manifest field escapes the seal except the root itself.
    """
    leaves: list[list[str]] = [[MANIFEST_FILENAME, _normalized_manifest_hash(manifest_payload)]]
    for path in run_dir.rglob("*"):
        if path.is_symlink():
            halt(
                IntegrityHalt(
                    "symlink in run directory; run artifacts must be regular files",
                    report={"path": str(path)},
                )
            )
        if not path.is_file():
            continue
        relative = path.relative_to(run_dir).as_posix()
        if relative == MANIFEST_FILENAME:
            continue
        leaves.append([relative, sha256_file(path)])
    leaves.sort(key=lambda leaf: leaf[0])
    return sha256_canonical(leaves)


class Manifest:
    """Lifecycle handle for one run's ``manifest.json``."""

    def __init__(self, run_dir: Path, clock: Clock, model: RunManifest) -> None:
        self._run_dir = run_dir
        self._clock = clock
        self._model = model

    @classmethod
    def open(cls, run_dir: Path, clock: Clock, fields: Mapping[str, object]) -> Manifest:
        """Create ``manifest.json`` (state PENDING, empty stage list).

        The manifest owns ``schema_version``, ``started`` (injected clock),
        ``state``, ``stages``, ``finished``, and ``seal``; supplying any of
        them is a defect.
        """
        payload: dict[str, Any] = dict(fields)
        run_dir.mkdir(parents=True, exist_ok=True)
        for owned in _MANIFEST_OWNED_FIELDS:
            if owned in payload:
                halt_with_file(
                    IntegrityHalt(
                        "manifest-owned field supplied by caller",
                        report={"field": owned},
                    ),
                    run_dir,
                )
        payload["schema_version"] = 1
        payload["started"] = _stamp(clock, run_dir)
        payload["state"] = "PENDING"
        payload["stages"] = []
        model = _build(payload, run_dir)
        manifest = cls(run_dir, clock, model)
        manifest._write()
        return manifest

    def record_stage(self, fields: Mapping[str, object]) -> None:
        """Append one stage record and atomically rewrite the manifest."""
        if self._model.seal is not None:
            self._halt(IntegrityHalt("manifest already sealed; run directory is closed"))
        payload = self._model.model_dump(mode="json", by_alias=True, exclude_unset=True)
        payload["stages"] = [*payload["stages"], dict(fields)]
        self._model = _build(payload, self._run_dir)
        self._write()

    def seal(self, state: str) -> None:
        """Set the terminal state, compute the hash-tree root, and seal."""
        if self._model.seal is not None:
            self._halt(IntegrityHalt("manifest already sealed"))
        if state not in TERMINAL_STATES:
            self._halt(
                IntegrityHalt(
                    "seal requires a terminal run state",
                    report={"state": state, "terminal": sorted(TERMINAL_STATES)},
                )
            )
        stamp = _stamp(self._clock, self._run_dir)
        payload = self._model.model_dump(mode="json", by_alias=True, exclude_unset=True)
        payload["state"] = state
        payload["finished"] = stamp
        payload["seal"] = {"sealed_at": stamp}  # root joins after the tree is computed
        root = _hash_tree_root(self._run_dir, payload)
        payload["seal"] = {"hash_tree_root": root, "sealed_at": stamp}
        self._model = _build(payload, self._run_dir)
        self._write()

    @staticmethod
    def verify_seal(run_dir: Path) -> RunManifest:
        """Recompute the hash tree and compare with the sealed root.

        Never writes into ``run_dir`` (sealed directories are immutable);
        reports go through the halt sink only.
        """
        manifest_path = run_dir / MANIFEST_FILENAME
        try:
            raw_text = manifest_path.read_text(encoding="utf-8")
            raw = json.loads(raw_text)
        except OSError as exc:
            halt(
                IntegrityHalt(
                    "manifest.json unreadable",
                    report={"path": str(manifest_path), "error": str(exc)},
                )
            )
        except json.JSONDecodeError as exc:
            halt(
                IntegrityHalt(
                    "manifest.json is not valid JSON",
                    report={"path": str(manifest_path), "error": str(exc)},
                )
            )
        model = validate_and_build(RunManifest, raw)
        if raw_text != dump_canonical(model) + "\n":
            halt(
                IntegrityHalt(
                    "manifest.json bytes are not the canonical serialization of "
                    "its content (external mutation?)",
                    report={"path": str(manifest_path)},
                )
            )
        if model.seal is None:
            halt(
                IntegrityHalt(
                    "manifest is not sealed; nothing to verify",
                    report={"path": str(manifest_path)},
                )
            )
        recomputed = _hash_tree_root(run_dir, raw)
        if recomputed != model.seal.hash_tree_root:
            halt(
                IntegrityHalt(
                    "hash-tree root mismatch: run directory changed after seal",
                    report={
                        "sealed_root": model.seal.hash_tree_root,
                        "recomputed_root": recomputed,
                    },
                )
            )
        return model

    # -- internals -----------------------------------------------------------

    def _halt(self, exc: IntegrityHalt) -> NoReturn:
        halt_with_file(exc, self._run_dir)

    def _write(self) -> None:
        tmp = self._run_dir / (MANIFEST_FILENAME + ".tmp")
        tmp.write_text(dump_canonical(self._model) + "\n", encoding="utf-8")
        os.replace(tmp, self._run_dir / MANIFEST_FILENAME)


def _stamp(clock: Clock, run_dir: Path) -> str:
    try:
        return format_utc_seconds(clock.now())
    except ValueError as exc:
        halt_with_file(
            IntegrityHalt(
                "injected clock produced a non-canonical timestamp",
                report={"error": str(exc)},
            ),
            run_dir,
        )


def _build(payload: dict[str, Any], run_dir: Path) -> RunManifest:
    try:
        return validate_and_build(RunManifest, payload)
    except BurhanHalt as exc:
        write_halt_report(exc, run_dir)  # already sink-emitted by halt()
        raise
