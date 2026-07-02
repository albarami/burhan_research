"""Canonical JSON serialization and hashing (NFR-101; standards §1).

One byte representation per value: sorted keys, compact separators, UTF-8,
shortest-round-trip float repr with ``-0.0`` normalized to ``0.0``. The input
domain is closed — ``dict[str, ...]``, ``list``, ``str``, ``int``, ``float``,
``bool``, ``None``. Anything else (including datetimes, which artifact models
serialize to strings first) raises :class:`IntegrityHalt`; there is no
``default=`` hook and no coercion (NFR-201).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from burhan.core.errors import IntegrityHalt, halt

_FILE_CHUNK_BYTES = 1 << 20


def _normalize(value: object, path: str) -> object:
    """Validate ``value`` against the closed domain; normalize floats."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):  # checked before int: bool subclasses int
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            halt(
                IntegrityHalt(
                    "non-finite float in canonical payload",
                    report={"path": path, "value": repr(value)},
                )
            )
        return 0.0 if value == 0.0 else value
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                halt(
                    IntegrityHalt(
                        "non-string dict key in canonical payload",
                        report={"path": path, "key": repr(key)},
                    )
                )
            normalized[key] = _normalize(item, f"{path}.{key}")
        return normalized
    if isinstance(value, list):
        return [_normalize(item, f"{path}[{index}]") for index, item in enumerate(value)]
    halt(
        IntegrityHalt(
            "unsupported type in canonical payload",
            report={"path": path, "type": type(value).__name__},
        )
    )


def dumps(obj: object) -> str:
    """Serialize ``obj`` to the canonical JSON string."""
    return json.dumps(
        _normalize(obj, "$"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def dumps_bytes(obj: object) -> bytes:
    """Serialize ``obj`` to canonical JSON UTF-8 bytes."""
    return dumps(obj).encode("utf-8")


def sha256_canonical(obj: object) -> str:
    """Return the SHA-256 hex digest of the canonical bytes of ``obj``."""
    return hashlib.sha256(dumps_bytes(obj)).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's exact bytes (streamed)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_FILE_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()
