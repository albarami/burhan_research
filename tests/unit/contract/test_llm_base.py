"""LLM adapter base tests (AT-M06-1/2/6; AD-04; FR-206/304; NFR-401/402).

The allowlist is closed and enumerable; raw data cannot cross the boundary
in any form (path, frame, bytes); lineage(A) == lineage(C) fails startup;
deterministic settings are enforced; prompt templates are versioned and
hashed for the manifest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from burhan.contract.llm_base import (
    AdapterBase,
    LlmSettings,
    load_llm_settings,
    prompt_manifest_entry,
)
from burhan.core.errors import IntegrityHalt

REPO = Path(__file__).resolve().parents[3]
PROMPT_V1 = REPO / "prompts" / "node_a" / "v1.md"


def _config(node_c_lineage: str = "openai.gpt", temperature: float = 0) -> dict[str, Any]:
    return {
        "nodes": {
            "node_a": {
                "provider": "anthropic",
                "model": "claude-pinned",
                "lineage": "anthropic.claude",
                "temperature": temperature,
                "max_retries": 2,
            },
            "node_b": {
                "provider": "anthropic",
                "model": "claude-pinned",
                "lineage": "anthropic.claude",
                "temperature": 0,
            },
            "node_c": {
                "provider": "openai",
                "model": "gpt-pinned",
                "lineage": node_c_lineage,
                "temperature": 0,
                "max_retries": 2,
            },
        },
        "providers": {
            "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
            "openai": {"api_key_env": "OPENAI_API_KEY"},
        },
    }


def _settings_file(tmp_path: Path, config: dict[str, Any]) -> Path:
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


class EchoAdapter(AdapterBase):
    """Minimal adapter fixture: two text slots, canned completion."""

    node = "node_a"
    ALLOWED_INPUTS = ("study_document", "data_dictionary")

    def __init__(self, settings: LlmSettings) -> None:
        super().__init__(settings, provider_call=lambda prompt: f"echo:{len(prompt)}")


# -- AT-M06-2: lineage validation at startup -------------------------------------


def test_lineage_a_equals_c_fails_startup(tmp_path: Path) -> None:  # AT-M06-2
    path = _settings_file(tmp_path, _config(node_c_lineage="anthropic.claude"))
    with pytest.raises(IntegrityHalt) as excinfo:
        load_llm_settings(path)
    assert "lineage" in excinfo.value.message
    assert "FR-304" in excinfo.value.message


def test_valid_settings_load(tmp_path: Path) -> None:
    settings = load_llm_settings(_settings_file(tmp_path, _config()))
    assert settings.node("node_a").lineage == "anthropic.claude"
    assert settings.node("node_c").lineage == "openai.gpt"


def test_nondeterministic_temperature_fails_startup(tmp_path: Path) -> None:  # AD-04
    path = _settings_file(tmp_path, _config(temperature=0.7))
    with pytest.raises(IntegrityHalt) as excinfo:
        load_llm_settings(path)
    assert "temperature" in excinfo.value.message


@pytest.mark.parametrize(
    ("shape", "named"),
    [
        ({"nodes": ["node_a", "node_b"], "providers": {}}, "nodes"),  # list, not mapping
        ({"nodes": {}, "providers": ["anthropic"]}, "providers"),  # list, not mapping
    ],
)
def test_wrongly_typed_blocks_halt_typed(
    tmp_path: Path, shape: dict[str, Any], named: str
) -> None:  # REJECT-TC06 fix 1 (raw AttributeError probe)
    with pytest.raises(IntegrityHalt) as excinfo:  # typed, never AttributeError
        load_llm_settings(_settings_file(tmp_path, shape))
    assert named in excinfo.value.message


def test_non_numeric_temperature_halts_typed(tmp_path: Path) -> None:
    # REJECT-TC06 fix 1 (raw ValueError probe: temperature: hot)
    config = _config()
    config["nodes"]["node_a"]["temperature"] = "hot"
    with pytest.raises(IntegrityHalt) as excinfo:  # typed, never ValueError
        load_llm_settings(_settings_file(tmp_path, config))
    assert "temperature" in excinfo.value.message
    assert "node_a" in str(excinfo.value.to_report()["details"])


def test_non_integer_max_retries_halts_typed(tmp_path: Path) -> None:  # REJECT-TC06 fix 1
    config = _config()
    config["nodes"]["node_c"]["max_retries"] = "twice"
    with pytest.raises(IntegrityHalt) as excinfo:
        load_llm_settings(_settings_file(tmp_path, config))
    assert "max_retries" in excinfo.value.message


def test_malformed_settings_halt(tmp_path: Path) -> None:
    bad = tmp_path / "llm.yaml"
    bad.write_text("{unbalanced: [", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        load_llm_settings(bad)
    with pytest.raises(IntegrityHalt):
        load_llm_settings(tmp_path / "absent.yaml")

    incomplete = {"nodes": {"node_a": {"provider": "anthropic"}}, "providers": {}}
    with pytest.raises(IntegrityHalt):
        load_llm_settings(_settings_file(tmp_path, incomplete))


# -- AT-M06-1: the allowlist is closed and raw data cannot cross ------------------


@pytest.fixture
def adapter(tmp_path: Path) -> EchoAdapter:
    return EchoAdapter(load_llm_settings(_settings_file(tmp_path, _config())))


def test_allowlist_is_closed_and_enumerable(adapter: EchoAdapter) -> None:  # AT-M06-1
    assert adapter.ALLOWED_INPUTS == ("study_document", "data_dictionary")
    with pytest.raises(IntegrityHalt) as excinfo:
        adapter.complete(study_document="text", smuggled_frame="x")
    assert "allowlist" in excinfo.value.message
    assert "smuggled_frame" in str(excinfo.value.to_report()["details"])


@pytest.mark.parametrize(
    "raw_value",
    [
        Path("/home/x/studies/export.csv"),  # a Path object
        "studies/dba/inputs/export.xlsx",  # a string path to a data file
        "/data/responses.sav",  # SPSS raw data
        b"ResponseId,Q3\nR_001,5",  # raw bytes
    ],
)
def test_raw_data_paths_and_bytes_rejected_at_boundary(
    adapter: EchoAdapter, raw_value: Any
) -> None:  # AT-M06-1 / NFR-401
    with pytest.raises(IntegrityHalt) as excinfo:
        adapter.complete(study_document=raw_value)
    assert "boundary" in excinfo.value.message


def test_dataframe_like_objects_rejected_at_boundary(adapter: EchoAdapter) -> None:  # AT-M06-1
    class FrameLike:
        columns = ["Q4_1", "Q4_2"]
        iloc = object()

    with pytest.raises(IntegrityHalt) as excinfo:
        adapter.complete(study_document=FrameLike())
    assert "boundary" in excinfo.value.message


def test_text_inputs_pass_and_reach_the_provider(adapter: EchoAdapter) -> None:
    result = adapter.complete(study_document="A study document.", data_dictionary=None)
    assert result.startswith("echo:")


def test_no_bypass_attribute_exists(adapter: EchoAdapter) -> None:  # AT-M06-1 absence
    public = {
        name
        for name in dir(adapter)
        if not name.startswith("_") and callable(getattr(adapter, name))
    }
    assert public == {"complete"}  # one door, allowlisted


# -- AT-M06-6: prompt version + hash for the manifest ------------------------------


def test_prompt_template_versioned_and_hashed() -> None:  # AT-M06-6
    entry = prompt_manifest_entry(PROMPT_V1)
    assert entry["version"] == "v1"
    assert len(entry["sha256"]) == 64


def test_changing_the_template_changes_the_hash(tmp_path: Path) -> None:  # AT-M06-6
    original = PROMPT_V1.read_text(encoding="utf-8")
    variant = tmp_path / "v1.md"
    variant.write_text(original + "\nEXTRA LINE\n", encoding="utf-8")
    assert prompt_manifest_entry(variant)["sha256"] != prompt_manifest_entry(PROMPT_V1)["sha256"]
    assert prompt_manifest_entry(variant)["version"] == "v1"


def test_missing_template_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt):
        prompt_manifest_entry(tmp_path / "v9.md")
