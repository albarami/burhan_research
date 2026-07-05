"""Archive & replay of LLM provider calls for the live run (TC-16; NFR-101).

A live run is non-deterministic at the LLM boundary. To keep ``burhan rerun``
byte-identical, every live prompt+response is recorded write-once into the run
directory; a rerun replays the archive and makes **no** provider call. Replay is
tamper-evident (it verifies the incoming prompt against the archived prompt) and
can mirror the archive into the target run dir so the regenerated tree matches
the source bit-for-bit. Archives hold prompt+response **text only** — never keys.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from burhan.core.artifacts.canonical import dumps
from burhan.core.errors import IntegrityHalt, VerificationHalt, halt


def _archive_path(directory: Path, node: str, seq: int) -> Path:
    return directory / f"{node}.{seq}.json"


def recording_provider_call(
    inner: Callable[[str], str], archive_dir: Path, node: str
) -> Callable[[str], str]:
    """Wrap a real provider call, archiving each prompt+response write-once."""
    seq = 0

    def call(prompt: str) -> str:
        nonlocal seq
        response = inner(prompt)
        path = _archive_path(archive_dir, node, seq)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            halt(
                IntegrityHalt(
                    "llm archive already exists; run artifacts are written once (AD-06)",
                    report={"path": str(path)},
                )
            )
        payload = {"node": node, "seq": seq, "prompt": prompt, "response": response}
        path.write_text(dumps(payload) + "\n", encoding="utf-8")
        seq += 1
        return response

    return call


def replay_provider_call(
    source_dir: Path, node: str, *, mirror_dir: Path | None = None
) -> Callable[[str], str]:
    """Return archived responses in order; make no provider call (NFR-101).

    Verifies the incoming prompt against the archived prompt (tamper-evident) and,
    when ``mirror_dir`` is given, writes the archive bytes there unchanged so the
    replayed run's tree is byte-identical to the source.
    """
    seq = 0

    def call(prompt: str) -> str:
        nonlocal seq
        path = _archive_path(source_dir, node, seq)
        if not path.is_file():
            halt(
                IntegrityHalt(
                    "llm archive missing on replay (NFR-101)",
                    report={"path": str(path), "node": node, "seq": seq},
                )
            )
        data = path.read_bytes()
        payload = json.loads(data.decode("utf-8"))
        if payload.get("prompt") != prompt:
            halt(
                VerificationHalt(
                    "replay prompt does not match the archived prompt (NFR-101)",
                    report={"node": node, "seq": seq},
                )
            )
        if mirror_dir is not None:
            target = _archive_path(mirror_dir, node, seq)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        seq += 1
        return str(payload["response"])

    return call
