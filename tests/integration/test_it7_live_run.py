"""IT-7 (TC-16): the live-provider run path, end to end.

Covers AT-M16-1 (live path real), -3 (pause un-bypassable), -5 (rerun replays
archives, no provider call), -6 (write-back + manifest hashing, no secrets). The
provider is a **recording** stub (records calls, returns fixed valid Node A /
Node C responses) so the test proves the live wiring — not the canned echo — and
touches no network.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from docx import Document  # type: ignore[import-untyped]
from integration_study import build_integration_study, integration_config, study_document
from it_util import fast_policy
from stub_nodes import node_a_provider, node_c_approve_provider

from burhan.cli.live import live_confirm, live_extract, live_rerun
from burhan.contract.llm_base import LlmSettings
from burhan.core.errors import BurhanHalt


class RecordingFactory:
    """A ``provider_factory`` that records calls and returns canned responses.

    Non-canned in the AT-M16-1 sense: each call is recorded (proving the live
    path invoked the provider), and it is distinct from ``certification_run``'s
    injected lambdas. No network.
    """

    def __init__(self) -> None:
        self.calls: dict[str, int] = {"node_a": 0, "node_c": 0}
        self._node_a = node_a_provider(integration_config())
        self._node_c = node_c_approve_provider()

    def __call__(self, settings: LlmSettings, node: str) -> Callable[[str], str]:
        inner = {"node_a": self._node_a, "node_c": self._node_c}[node]

        def call(prompt: str) -> str:
            self.calls[node] += 1
            return inner(prompt)

        return call


def _llm_yaml() -> str:
    anthropic = {
        "provider": "anthropic",
        "model": "claude-live-test",
        "lineage": "anthropic.claude",
        "temperature": 0,
        "max_retries": 2,
    }
    openai = dict(anthropic, provider="openai", model="gpt-live-test", lineage="openai.gpt")
    return yaml.safe_dump(
        {
            "nodes": {"node_a": anthropic, "node_b": anthropic, "node_c": openai},
            "providers": {
                "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
                "openai": {"api_key_env": "OPENAI_API_KEY"},
            },
        },
        sort_keys=True,
    )


def _build_live_bundle(tmp_path: Path) -> Path:
    """A live study bundle: study/instrument DOCX, the CSV, and llm.yaml."""
    study_dir = tmp_path / "study"
    (study_dir / "inputs").mkdir(parents=True)
    (study_dir / "config").mkdir(parents=True)

    doc = Document()
    for line in study_document().splitlines():
        doc.add_paragraph(line)
    doc.save(str(study_dir / "inputs" / "study_document.docx"))

    instrument = Document()
    instrument.add_paragraph("Survey instrument: 7-point Likert items for RES, CUL, INT.")
    instrument.save(str(study_dir / "inputs" / "data_dictionary.docx"))

    build_integration_study(20260705, n=300).write(study_dir / "inputs")
    (study_dir / "config" / "llm.yaml").write_text(_llm_yaml(), encoding="utf-8")
    return study_dir


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_live_extract_then_confirm_reaches_completed(tmp_path: Path) -> None:
    study_dir = _build_live_bundle(tmp_path)
    factory = RecordingFactory()

    extract = live_extract(study_dir, provider_factory=factory)
    # AT-M16-1: the live provider was invoked for Node A (not a canned echo).
    assert factory.calls["node_a"] == 1
    config_path = study_dir / "config" / "study_config.yaml"
    assert config_path.is_file()  # write-back
    assert (study_dir / "extract" / "node_a.0.json").is_file()  # archived
    assert (study_dir / "extract" / "GLANCE_TOKEN.json").is_file()  # pending token
    assert extract.study_id == "integration-adoption-2026"

    result = live_confirm(study_dir, provider_factory=factory, policy=fast_policy(tmp_path))
    assert result.state == "COMPLETED"
    # Node A was NOT re-called (it replays the archive); Node C ran live once.
    assert factory.calls["node_a"] == 1
    assert factory.calls["node_c"] >= 1
    # The archives are inside the sealed run dir.
    assert (result.run_dir / "llm" / "node_a.0.json").is_file()
    assert (result.run_dir / "llm" / "node_c.0.json").is_file()


def test_confirm_without_token_halts_before_gate1(tmp_path: Path) -> None:
    study_dir = _build_live_bundle(tmp_path)
    factory = RecordingFactory()
    live_extract(study_dir, provider_factory=factory)
    (study_dir / "extract" / "GLANCE_TOKEN.json").unlink()  # no confirmation token

    with pytest.raises(BurhanHalt):
        live_confirm(study_dir, provider_factory=factory, policy=fast_policy(tmp_path))
    assert factory.calls["node_c"] == 0  # no Gate 1 / no Stage-1A work
    assert not (study_dir / "runs").exists()


def test_confirm_with_tampered_config_halts(tmp_path: Path) -> None:
    study_dir = _build_live_bundle(tmp_path)
    factory = RecordingFactory()
    live_extract(study_dir, provider_factory=factory)
    config_path = study_dir / "config" / "study_config.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8"
    )

    with pytest.raises(BurhanHalt):
        live_confirm(study_dir, provider_factory=factory, policy=fast_policy(tmp_path))
    assert factory.calls["node_c"] == 0


def test_writeback_and_manifest_hashes_no_secrets(tmp_path: Path) -> None:
    study_dir = _build_live_bundle(tmp_path)
    factory = RecordingFactory()
    live_extract(study_dir, provider_factory=factory)
    result = live_confirm(study_dir, provider_factory=factory, policy=fast_policy(tmp_path))

    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    config_path = study_dir / "config" / "study_config.yaml"
    # AT-M16-6: config bytes hashed; real llm.yaml model IDs recorded.
    assert manifest["hashes"]["study_config"] == _sha(config_path)
    assert manifest["llm_nodes"]["node_a"]["model"] == "claude-live-test"
    assert manifest["llm_nodes"]["node_c"]["model"] == "gpt-live-test"
    # archives are covered by the seal hash-tree.
    assert manifest["seal"]["hash_tree_root"]
    # no secrets anywhere in the manifest.
    blob = json.dumps(manifest)
    assert "ANTHROPIC_API_KEY" not in blob and "OPENAI_API_KEY" not in blob
    assert "sk-" not in blob


def test_rerun_replays_archives_byte_identical(tmp_path: Path) -> None:
    study_dir = _build_live_bundle(tmp_path)
    factory = RecordingFactory()
    live_extract(study_dir, provider_factory=factory)
    run = live_confirm(study_dir, provider_factory=factory, policy=fast_policy(tmp_path))

    # AT-M16-5: rerun replays archives, calls NO provider, byte-identical.
    rerun = live_rerun(run.run_dir, policy=fast_policy(tmp_path))
    assert rerun.state == "COMPLETED"


def test_planted_archive_mismatch_is_caught(tmp_path: Path) -> None:
    study_dir = _build_live_bundle(tmp_path)
    factory = RecordingFactory()
    live_extract(study_dir, provider_factory=factory)
    run = live_confirm(study_dir, provider_factory=factory, policy=fast_policy(tmp_path))

    archive = run.run_dir / "llm" / "node_c.0.json"
    payload = json.loads(archive.read_text(encoding="utf-8"))
    payload["response"] = yaml.safe_dump(
        {"verdict": "reject", "fixes": ["planted"]}, sort_keys=True
    )
    archive.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BurhanHalt):
        live_rerun(run.run_dir, policy=fast_policy(tmp_path))


def test_extract_missing_study_document_halts(tmp_path: Path) -> None:
    # AT-M16-7 ingestion guard: no study_document.docx -> typed halt before any
    # provider call (never a silent empty prompt).
    (tmp_path / "study" / "inputs").mkdir(parents=True)
    factory = RecordingFactory()
    with pytest.raises(BurhanHalt):
        live_extract(tmp_path / "study", provider_factory=factory)
    assert factory.calls["node_a"] == 0


def test_extract_missing_csv_halts(tmp_path: Path) -> None:
    # A live run needs the CSV export as pipeline data; its absence halts typed.
    study_dir = _build_live_bundle(tmp_path)
    for csv in (study_dir / "inputs").glob("*.csv"):
        csv.unlink()
    factory = RecordingFactory()
    with pytest.raises(BurhanHalt):
        live_extract(study_dir, provider_factory=factory)
    assert factory.calls["node_a"] == 0


def test_confirm_with_tampered_archive_halts(tmp_path: Path) -> None:
    # AT-M16-3: the glance binds the Node A archive too — mutating it after the
    # glance halts before Gate 1 (the archive-sha branch of the pause).
    study_dir = _build_live_bundle(tmp_path)
    factory = RecordingFactory()
    live_extract(study_dir, provider_factory=factory)
    archive = study_dir / "extract" / "node_a.0.json"
    archive.write_text(archive.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(BurhanHalt):
        live_confirm(study_dir, provider_factory=factory, policy=fast_policy(tmp_path))
    assert factory.calls["node_c"] == 0
    assert not (study_dir / "runs").exists()


def test_confirm_with_missing_config_halts(tmp_path: Path) -> None:
    # AT-M16-3: a token present but a vanished config is an incomplete pending
    # state — halt, never run against a config the glance never saw.
    study_dir = _build_live_bundle(tmp_path)
    factory = RecordingFactory()
    live_extract(study_dir, provider_factory=factory)
    (study_dir / "config" / "study_config.yaml").unlink()

    with pytest.raises(BurhanHalt):
        live_confirm(study_dir, provider_factory=factory, policy=fast_policy(tmp_path))
    assert factory.calls["node_c"] == 0
    assert not (study_dir / "runs").exists()
