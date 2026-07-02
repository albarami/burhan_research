"""Provider-factory coverage (the engine's single network-capable path).

The real SDK calls are exercised against fake modules injected into
sys.modules — the mapping logic is covered without any network.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest
import yaml

from burhan.contract.llm_base import load_llm_settings, resolve_provider_call
from burhan.core.errors import IntegrityHalt


def _settings_path(tmp_path: Path, *, node_a_provider: str = "anthropic") -> Path:
    config: dict[str, Any] = {
        "nodes": {
            "node_a": {
                "provider": node_a_provider,
                "model": "pinned-model",
                "lineage": "anthropic.claude" if node_a_provider == "anthropic" else "x.y",
                "temperature": 0,
            },
            "node_b": {
                "provider": "openai",
                "model": "pinned-b",
                "lineage": "openai.gpt",
                "temperature": 0,
            },
            "node_c": {
                "provider": "openai",
                "model": "pinned-c",
                "lineage": "openai.gpt",
                "temperature": 0,
            },
        },
        "providers": {
            "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
            "openai": {"api_key_env": "OPENAI_API_KEY"},
            "local_lmstudio": {"api_key_env": "LMSTUDIO_API_KEY"},
        },
    }
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_anthropic_call_maps_text_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class TextBlock:
        def __init__(self, text: str) -> None:
            self.text = text

    class OtherBlock:
        pass

    captured: dict[str, Any] = {}

    class FakeAnthropic:
        def __init__(self) -> None:
            self.messages = self

        def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            response = types.SimpleNamespace()
            response.content = [OtherBlock(), TextBlock("part1 "), TextBlock("part2")]
            return response

    fake = types.ModuleType("anthropic")
    fake.Anthropic = FakeAnthropic  # type: ignore[attr-defined]
    fake_types = types.ModuleType("anthropic.types")
    fake_types.TextBlock = TextBlock  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setitem(sys.modules, "anthropic.types", fake_types)

    settings = load_llm_settings(_settings_path(tmp_path))
    call = resolve_provider_call(settings, "node_a")
    assert call("PROMPT") == "part1 part2"
    assert captured["model"] == "pinned-model"
    assert captured["temperature"] == 0
    assert captured["messages"] == [{"role": "user", "content": "PROMPT"}]


def test_openai_call_maps_choice_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeOpenAI:
        def __init__(self) -> None:
            self.chat = self
            self.completions = self

        def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            message = types.SimpleNamespace(content="the completion")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    fake = types.ModuleType("openai")
    fake.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake)

    settings = load_llm_settings(_settings_path(tmp_path))
    call = resolve_provider_call(settings, "node_c")
    assert call("PROMPT") == "the completion"
    assert captured["model"] == "pinned-c"
    assert captured["temperature"] == 0


def test_unknown_provider_halts(tmp_path: Path) -> None:
    settings = load_llm_settings(_settings_path(tmp_path, node_a_provider="local_lmstudio"))
    with pytest.raises(IntegrityHalt) as excinfo:
        resolve_provider_call(settings, "node_a")
    assert "provider" in excinfo.value.message


def test_unknown_node_halts(tmp_path: Path) -> None:
    settings = load_llm_settings(_settings_path(tmp_path))
    with pytest.raises(IntegrityHalt):
        settings.node("node_z")


def test_missing_providers_block_and_unresolvable_key_halt(tmp_path: Path) -> None:
    no_providers = tmp_path / "a.yaml"
    no_providers.write_text(yaml.safe_dump({"nodes": {}}), encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        load_llm_settings(no_providers)

    config = yaml.safe_load(_settings_path(tmp_path).read_text(encoding="utf-8"))
    del config["providers"]["anthropic"]
    orphan_provider = tmp_path / "b.yaml"
    orphan_provider.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(IntegrityHalt) as excinfo:
        load_llm_settings(orphan_provider)
    assert "api_key_env" in excinfo.value.message
