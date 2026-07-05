"""Archive/replay wrappers over ``provider_call`` (TC-16; underpins AT-M16-5).

A live run records each LLM prompt+response into a write-once archive; a rerun
replays the archive and makes **no** provider call. Replay verifies the incoming
prompt against the archived prompt (tamper-evident) and can mirror the archive
into the target run dir so the regenerated tree is byte-identical (NFR-101).
Archives carry prompt+response text only — never secrets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from burhan.contract.archive import recording_provider_call, replay_provider_call
from burhan.core.errors import BurhanHalt


def test_recording_writes_archive_and_returns_response(tmp_path: Path) -> None:
    calls: list[str] = []

    def inner(prompt: str) -> str:
        calls.append(prompt)
        return "RESPONSE-A"

    call = recording_provider_call(inner, tmp_path, "node_a")
    out = call("PROMPT-A")

    assert out == "RESPONSE-A"
    assert calls == ["PROMPT-A"]  # the real provider was invoked exactly once
    archive = tmp_path / "node_a.0.json"
    assert archive.is_file()
    payload = json.loads(archive.read_text(encoding="utf-8"))
    assert payload["prompt"] == "PROMPT-A"
    assert payload["response"] == "RESPONSE-A"


def test_recording_seq_increments_per_call(tmp_path: Path) -> None:
    call = recording_provider_call(lambda p: f"r:{p}", tmp_path, "node_c")
    call("p0")
    call("p1")
    assert (tmp_path / "node_c.0.json").is_file()
    assert (tmp_path / "node_c.1.json").is_file()


def test_replay_returns_archived_response_without_any_provider(tmp_path: Path) -> None:
    recording_provider_call(lambda p: "ARCHIVED", tmp_path, "node_a")("THE-PROMPT")

    replay = replay_provider_call(tmp_path, "node_a")
    out = replay("THE-PROMPT")
    assert out == "ARCHIVED"


def test_replay_mirrors_archive_byte_identical(tmp_path: Path) -> None:
    source = tmp_path / "src"
    target = tmp_path / "dst"
    source.mkdir()
    recording_provider_call(lambda p: "ARCHIVED", source, "node_a")("THE-PROMPT")

    replay = replay_provider_call(source, "node_a", mirror_dir=target)
    replay("THE-PROMPT")
    assert (target / "node_a.0.json").read_bytes() == (source / "node_a.0.json").read_bytes()


def test_replay_halts_on_prompt_mismatch(tmp_path: Path) -> None:
    recording_provider_call(lambda p: "ARCHIVED", tmp_path, "node_a")("ORIGINAL-PROMPT")
    replay = replay_provider_call(tmp_path, "node_a")
    with pytest.raises(BurhanHalt):
        replay("TAMPERED-PROMPT")


def test_replay_halts_on_missing_archive(tmp_path: Path) -> None:
    replay = replay_provider_call(tmp_path, "node_a")
    with pytest.raises(BurhanHalt):
        replay("any prompt")
