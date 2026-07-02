"""Shared Node C test fixtures: settings, stub provider, artifact texts.

The provider is the TC-06 StubProvider pattern — deterministic responses
keyed by a ``STUDY-VARIANT:`` marker carried in the audited artifacts'
source document; no network, ever.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from burhan.contract.llm_base import LlmSettings, NodeSettings

REPO = Path(__file__).resolve().parents[3]
CORRUPTIONS = REPO / "tests" / "fixtures" / "corruptions"
FAITHFUL_CONTRACT = REPO / "schemas" / "study_config.example.yaml"


def settings() -> LlmSettings:
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


class StubProvider:
    """Deterministic prompt→response mapping keyed by the STUDY-VARIANT marker."""

    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        for key, response in self._responses.items():
            if f"STUDY-VARIANT: {key}" in prompt:
                return response
        raise AssertionError("no stub response matched the prompt")


def document(variant: str) -> str:
    """The worked-example methodology chapter as prose (the Gate-1 source)."""
    return "\n".join(
        [
            f"STUDY-VARIANT: {variant}",
            "Organizational Enablers of Tool Adoption — methodology chapter.",
            "The declared methodology is covariance-based SEM (CB-SEM),",
            "cross-sectional design, executed under the approved playbook.",
            "Constructs: Resources (RES: RS1, RS2, RS3), Culture (CUL: CU1, CU2,",
            "CU3), Enablement (ENB) second-order over RES and CUL, Perceived",
            "Usefulness (PU: PU1, PU2, PU3), Attitude (ATT: AT1, AT2, AT3),",
            "and Intention (INT: IN1, IN2, IN3).",
            "Item RS3 is reverse-coded in the instrument.",
            "Item CU3 is reverse-coded in the instrument.",
            "Hypotheses: H1 ENB->PU, H2 PU->ATT, H3 ATT->INT, H4a ENB->INT,",
            "and H4b ENB->INT indirectly via PU and ATT (all positive).",
        ]
    )


def approve_yaml() -> str:
    return yaml.safe_dump({"verdict": "approve", "fixes": []}, sort_keys=False)


def reject_yaml(*fixes: str) -> str:
    return yaml.safe_dump({"verdict": "reject", "fixes": list(fixes)}, sort_keys=False)


# -- Gate-2 artifact texts (rows conform to schemas/results_store.schema.json) --


def results_store_text() -> str:
    """Fixture results store: H1 supported; H4a NOT supported (p=.41)."""
    rows = [
        {
            "schema_version": "1.0",
            "id": "structural.path.H1",
            "value": 0.412,
            "se": 0.071,
            "p": 0.003,
            "stage": "structural",
            "engine": "lavaan",
            "playbook_step": "S7",
            "created": "2026-07-01T00:00:00Z",
            "hash": "a" * 64,
        },
        {
            "schema_version": "1.0",
            "id": "structural.path.H4a",
            "value": 0.062,
            "se": 0.075,
            "p": 0.41,
            "stage": "structural",
            "engine": "lavaan",
            "playbook_step": "S7",
            "created": "2026-07-01T00:00:00Z",
            "hash": "b" * 64,
        },
    ]
    import json

    return "\n".join(json.dumps(row, sort_keys=True) for row in rows)


def decision_log_text() -> str:
    return "\n".join(
        [
            "# DECISION_LOG",
            "| ts | rule | effect |",
            "|---|---|---|",
            "| 2026-07-01T00:00:00Z | estimator.default | MLR selected |",
        ]
    )


def bad_draft(variant: str) -> str:
    """Unsupported claim (H4a called supported) + omitted hypothesis (H4b)."""
    return "\n".join(
        [
            f"STUDY-VARIANT: {variant}",
            "Findings. H1 was supported (structural.path.H1).",
            "H4a was supported, confirming a direct enablement effect",
            "(structural.path.H4a).",
        ]
    )


def good_draft(variant: str) -> str:
    """Every hypothesis reported, including the unsupported one."""
    return "\n".join(
        [
            f"STUDY-VARIANT: {variant}",
            "Findings. H1 was supported (structural.path.H1).",
            "H4a was not supported (structural.path.H4a).",
            "H4b is reported per the mediation results in the store.",
        ]
    )
