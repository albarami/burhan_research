"""Node A extraction tests (AT-M06-3/4/5; FR-201–206).

The provider is a deterministic stub keyed by a marker in each fixture
document — no network, ever. The faithful document (the worked example
rendered to prose) extracts and passes V1–V7; seven mutated documents each
trip exactly their validator; ambiguity is a hard stop; the dictionary is
authoritative for what it declares.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from contract_util import EXPORTS, example_dict
from ingest_fixture_config import base_dict

from burhan.contract.llm_base import LlmSettings, NodeSettings
from burhan.contract.node_a import NodeA
from burhan.core.errors import IntegrityHalt

REPO = Path(__file__).resolve().parents[3]


def _settings() -> LlmSettings:
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


def _document(variant: str, *, reversed_items: tuple[str, ...] = ("RS3", "CU3")) -> str:
    lines = [
        f"STUDY-VARIANT: {variant}",
        "Organizational Enablers of Tool Adoption — methodology chapter.",
        "The declared methodology is covariance-based SEM (CB-SEM),",
        "cross-sectional design, executed under the approved playbook.",
        "Constructs: Resources (RES: RS1, RS2, RS3), Culture (CUL: CU1, CU2,",
        "CU3), Enablement (ENB) as a second-order construct over RES and CUL",
        "using the repeated-indicator approach with full-hierarchy carry,",
        "Perceived Usefulness (PU: PU1, PU2, PU3), Attitude (ATT: AT1, AT2,",
        "AT3), and Intention (INT: IN1, IN2, IN3).",
    ]
    for code in reversed_items:
        lines.append(f"Item {code} is reverse-coded in the instrument.")
    lines += [
        "Hypotheses: H1 ENB->PU, H2 PU->ATT, H3 ATT->INT, H4a ENB->INT,",
        "and H4b ENB->INT indirectly via PU and ATT (all positive).",
        "Data: Qualtrics export (3 header rows), ResponseId ids, Q3 consent,",
        "attention check Q9_4 expecting 5, firm size and sector demographics.",
    ]
    return "\n".join(lines)


def _faithful_yaml() -> str:
    return yaml.safe_dump(example_dict(), sort_keys=False)


def _mutated_yaml(mutate: Any) -> str:
    data = example_dict()
    mutate(data)
    return yaml.safe_dump(data, sort_keys=False)


class StubProvider:
    """Deterministic document→yaml mapping keyed by the STUDY-VARIANT marker."""

    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        for key, response in self._responses.items():
            if f"STUDY-VARIANT: {key}" in prompt:
                return response
        raise AssertionError("no stub response matched the prompt")


def _node(responses: dict[str, str]) -> NodeA:
    return NodeA(_settings(), provider_call=StubProvider(responses))


# -- AT-M06-3: faithful document passes; seven mutants trip exactly their validator


def test_faithful_document_extracts_and_validates() -> None:  # AT-M06-3
    node = _node({"faithful": _faithful_yaml()})
    config = node.extract(study_document=_document("faithful"), min_designed_items=3)
    assert config.meta.study_id == "example-adoption-2026"
    assert {c.code for c in config.constructs} == {"RES", "CUL", "ENB", "PU", "ATT", "INT"}


@pytest.mark.parametrize(
    ("validator", "mutate_yaml"),
    [
        ("V1", lambda d: d["instrument"]["items"][0].__setitem__("construct_ref", "GHOST")),
        ("V2", lambda d: d["constructs"][0].__setitem__("indicators", ["RS1", "RS2", "GHOST9"])),
        ("V3", lambda d: d.pop("higher_order")),
        ("V4", lambda d: d["model"].__setitem__("exogenous", ["GHOST"])),
        ("V5", lambda d: d["hypotheses"][1].__setitem__("id", "H1")),
    ],
)
def test_mutated_documents_trip_exactly_their_validator(
    validator: str, mutate_yaml: Any
) -> None:  # AT-M06-3 (V1–V5)
    key = f"mutant-{validator}"
    node = _node({key: _mutated_yaml(mutate_yaml)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document(key), min_designed_items=3)
    assert excinfo.value.message.startswith(validator)


def test_v6_mutant_trips_column_accounting() -> None:  # AT-M06-3 (V6)
    data = base_dict()
    data["data"]["metadata_columns"] = []  # StartDate orphaned
    node = _node({"mutant-V6": yaml.safe_dump(data, sort_keys=False)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(
            study_document=_document("mutant-V6", reversed_items=()),
            export_path=EXPORTS / "adoption_3header.csv",
        )
    assert excinfo.value.message.startswith("V6")


def test_v7_mutant_trips_reverse_coding_source_rule() -> None:  # AT-M06-3 (V7)
    def invent_reversal(data: dict[str, Any]) -> None:
        for item in data["instrument"]["items"]:
            if item["code"] == "PU1":
                item["reverse_coded"] = True  # nothing in the sources says so

    node = _node({"mutant-V7": _mutated_yaml(invent_reversal)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("mutant-V7"), min_designed_items=3)
    assert excinfo.value.message.startswith("V7")
    assert "PU1" in str(excinfo.value.to_report()["details"])


# -- AT-M06-4: the dictionary is authoritative ---------------------------------------


def test_dictionary_conflict_is_hard_failure_citing_it() -> None:  # AT-M06-4
    def rs3_not_reversed(data: dict[str, Any]) -> None:
        for item in data["instrument"]["items"]:
            if item["code"] == "RS3":
                item["reverse_coded"] = False

    # Document silent about RS3; dictionary declares it reverse-coded.
    node = _node({"dict-conflict": _mutated_yaml(rs3_not_reversed)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(
            study_document=_document("dict-conflict", reversed_items=("CU3",)),
            data_dictionary="RS3 | reverse-coded\nCU3 | reverse-coded\n",
            min_designed_items=3,
        )
    assert "FR-204" in excinfo.value.message
    assert "RS3" in str(excinfo.value.to_report()["details"])


def test_dictionary_consistent_extraction_passes() -> None:
    node = _node({"faithful": _faithful_yaml()})
    config = node.extract(
        study_document=_document("faithful"),
        data_dictionary="RS3 | reverse-coded\nCU3 | reverse-coded\n",
        min_designed_items=3,
    )
    assert config.meta.study_id == "example-adoption-2026"


def test_consistent_negative_declaration_passes_end_to_end() -> None:
    # REJECT-TC06 fix 2 corollary: an accepted negative declaration must not
    # poison V7's evidence scan (a 'not reverse-coded' line is not positive
    # evidence of reversal).
    node = _node({"faithful": _faithful_yaml()})
    config = node.extract(
        study_document=_document("faithful"),
        data_dictionary=("RS1 | not reverse-coded\nRS3 | reverse-coded\nCU3 | reverse-coded\n"),
        min_designed_items=3,
    )
    assert config.meta.study_id == "example-adoption-2026"


# -- FR-205: ambiguity is a hard stop --------------------------------------------------


def test_ambiguity_marker_is_hard_failure_never_a_guess() -> None:  # FR-205
    node = _node({"ambiguous": "AMBIGUOUS: item AT9 has no construct assignment in §3.2"})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("ambiguous"))
    assert "FR-205" in excinfo.value.message
    assert "AT9" in str(excinfo.value.to_report()["details"])


def test_non_yaml_model_output_halts() -> None:
    node = _node({"garbage": "Sure! Here's the config: {unbalanced: ["})
    with pytest.raises(IntegrityHalt):
        node.extract(study_document=_document("garbage"))


def test_non_mapping_yaml_halts() -> None:
    node = _node({"listy": "- a\n- b\n"})
    with pytest.raises(IntegrityHalt):
        node.extract(study_document=_document("listy"))


def test_schema_invalid_extraction_halts_with_path() -> None:  # FR-203
    def wreck(data: dict[str, Any]) -> None:
        data["hypotheses"][0]["id"] = "X1"

    node = _node({"schema-bad": _mutated_yaml(wreck)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("schema-bad"))
    assert excinfo.value.to_report()["details"]["path"] == "$.hypotheses[0].id"


# -- AT-M06-5: no field can encode a retained subset -----------------------------------


def test_no_contract_field_can_encode_a_retained_subset() -> None:  # AT-M06-5
    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.artifacts.schemas import load_schema

    banned = ("retained", "subset", "kept", "selected", "final", "dropped")

    names: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    names.extend(value.keys())
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(load_schema("study_config"))
    assert names, "walker found no properties?"
    offenders = [name for name in names if any(token in name.lower() for token in banned)]
    assert offenders == []
    # And the model cannot grow such a field silently: extras are forbidden.
    assert StudyConfig.model_config.get("extra") == "forbid"


def test_ignored_item_columns_cannot_hide_modeled_items() -> None:  # FR-202 corollary
    # Declaring a MODELED item's column as ignored collides in the role
    # accounting — exactly one role per column (V6) — so the escape hatch
    # cannot encode a retained-subset choice.
    data = base_dict()
    data["data"]["ignored_item_columns"] = ["Q4_2"]  # RS2's column
    node = _node({"hide-item": yaml.safe_dump(data, sort_keys=False)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(
            study_document=_document("hide-item", reversed_items=()),
            export_path=EXPORTS / "adoption_3header.csv",
        )
    assert "Q4_2" in str(excinfo.value.to_report()["details"])


# -- prompt wiring ----------------------------------------------------------------------


def test_prompt_carries_document_and_dictionary() -> None:
    provider = StubProvider({"faithful": _faithful_yaml()})
    node = NodeA(_settings(), provider_call=provider)
    node.extract(
        study_document=_document("faithful"),
        data_dictionary="RS3 | reverse-coded\nCU3 | reverse-coded\n",
        min_designed_items=3,
    )
    prompt = provider.prompts[0]
    assert "STUDY-VARIANT: faithful" in prompt
    assert "RS3 | reverse-coded" in prompt
    assert "Ambiguity is a hard stop" in prompt  # the versioned template text


def test_node_a_prompt_manifest_entry() -> None:  # AT-M06-6 at node level
    node = _node({"faithful": _faithful_yaml()})
    entry = node.prompt_manifest()
    assert entry["version"] == "v1"
    assert len(entry["sha256"]) == 64
