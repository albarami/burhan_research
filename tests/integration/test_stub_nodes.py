"""TC-15 Task 2: the deterministic stub Node A / Node C providers.

Proves the stubs drive the *real* nodes: Node A's provider yields a config
the real ``validate_and_build`` accepts, and Node C's provider drives the
real ``NodeC.gate1`` to an ``approve`` verdict — no provider call, no
network. End-to-end exercise through ``NodeA.extract`` lives in IT-1.
"""

from __future__ import annotations

import yaml
from generator import build_golden
from stub_nodes import node_a_provider, node_c_approve_provider, stub_settings

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.review.node_c import NodeC


def test_node_a_provider_yields_a_valid_study_config() -> None:
    config = build_golden(11).config
    provider = node_a_provider(config)
    rebuilt = validate_and_build(StudyConfig, yaml.safe_load(provider("ignored prompt")))
    assert rebuilt.meta.study_id == config["meta"]["study_id"]
    # deterministic: the same fixture yields byte-identical responses
    assert provider("a") == provider("b")


def test_node_c_approve_provider_drives_real_gate1_to_approve() -> None:
    node_c = NodeC(stub_settings(), provider_call=node_c_approve_provider())
    verdict = node_c.gate1(study_contract="contract-text", study_document="document-text")
    assert verdict.verdict == "approve"
    assert verdict.fixes == ()
    assert verdict.schema_invalid is False
