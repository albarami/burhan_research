"""Deterministic stub LLM providers for the TC-15 integration harness.

The engine's only network egress is an adapter's ``provider_call``
(``contract/llm_base.py``); every adapter takes it by injection. These
stubs replace it with a canned, schema-valid response so a golden study
drives the pipeline end-to-end with **no** provider call — the same
mechanism the TC-06 contract/review unit tests use. Node A yields a
fixed study contract; Node C always approves. No raw respondent data
ever reaches these callables (the adapter allowlist still screens
inputs upstream, NFR-401).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import yaml

from burhan.contract.llm_base import LlmSettings, NodeSettings


def stub_settings() -> LlmSettings:
    """Pinned, schema-valid settings for constructing stubbed nodes.

    Mirrors the TC-06 test settings: temperature 0 and distinct Node A vs
    Node C lineages (both hard constraints enforced at settings load).
    """
    node = {
        "provider": "anthropic",
        "model": "claude-pinned",
        "lineage": "anthropic.claude",
        "temperature": 0.0,
        "api_key_env": "ANTHROPIC_API_KEY",
        "max_retries": 2,
    }
    node_c = dict(node, provider="openai", lineage="openai.gpt")
    return LlmSettings(
        nodes={
            "node_a": NodeSettings(**node),
            "node_b": NodeSettings(**node),
            "node_c": NodeSettings(**node_c),
        },
        source_sha256="0" * 64,
    )


def node_a_provider(config: Mapping[str, Any]) -> Callable[[str], str]:
    """A Node A provider that yields ``config`` as YAML for any prompt.

    Deterministic (sorted keys, no clock/RNG); the response is a schema-valid
    ``study_config`` mapping that ``NodeA.extract`` parses and validates.
    """
    payload = yaml.safe_dump(dict(config), sort_keys=True)

    def _call(_prompt: str) -> str:
        return payload

    return _call


def node_c_approve_provider() -> Callable[[str], str]:
    """A Node C provider that always approves with no fixes (closed schema)."""
    payload = yaml.safe_dump({"verdict": "approve", "fixes": []}, sort_keys=True)

    def _call(_prompt: str) -> str:
        return payload

    return _call
