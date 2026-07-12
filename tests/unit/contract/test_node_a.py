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


def test_fenced_yaml_response_parses() -> None:  # §7 fix: models wrap YAML in ```yaml fences
    # A response the model wrapped in a ```yaml … ``` markdown code fence must
    # still parse: the fence is stripped before schema validation (FR-203).
    node = _node({"fenced": f"```yaml\n{_faithful_yaml()}```\n"})
    config = node.extract(study_document=_document("fenced"), min_designed_items=3)
    assert config.meta.study_id == "example-adoption-2026"


def test_fenced_yaml_without_closing_fence_parses() -> None:  # §7 fix (truncation-robust)
    # A leading ```yaml with no closing fence (e.g. the model omits it) still
    # parses: only the opening fence line is stripped, the body is untouched.
    node = _node({"fenced-open": f"```yaml\n{_faithful_yaml()}"})
    config = node.extract(study_document=_document("fenced-open"), min_designed_items=3)
    assert config.meta.study_id == "example-adoption-2026"


def test_fenced_ambiguous_still_halts_fr205() -> None:  # §7 fix: FR-205 after fence normalization
    # A fenced AMBIGUOUS: response must still halt FR-205 — the ambiguity check
    # runs on the de-fenced body, not only on the raw response.
    node = _node({"amb-fenced": "```\nAMBIGUOUS: item AT9 has no construct in §3.2\n```"})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("amb-fenced"))
    assert "FR-205" in excinfo.value.message
    assert "AT9" in str(excinfo.value.to_report()["details"])


def test_non_yaml_fence_is_not_stripped() -> None:  # §7 fix: only yaml/yml/bare fences unwrap
    # A non-YAML fence (```json) is left in place and fails FR-203 — the strip is
    # scoped to YAML fences, not any fenced content.
    node = _node({"json-fenced": f"```json\n{_faithful_yaml()}```\n"})
    with pytest.raises(IntegrityHalt):
        node.extract(study_document=_document("json-fenced"))


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


# -- §7 correction (Node A schema-contract) -------------------------------------------
# Live DBA run halted "non-string dict key in canonical payload". Root cause: v1.md
# deferred the entire output shape to a schema the model never sees, so Node A
# invented `instrument.scale_range.anchors: {1:.., 7:..}` (numeric keys → canonical
# halt), top-level `out_of_model` / `reference_comparison`, and `study` in place of
# meta/methodology/model. The prompt/input-contract must carry the schema's shape;
# the engine already rejects each drifted shape (pinned below).


def _rendered_node_a_prompt() -> str:
    """The prompt Node A actually sends — the schema contract must live here."""
    provider = StubProvider({"faithful": _faithful_yaml()})
    node = NodeA(_settings(), provider_call=provider)
    node.extract(study_document=_document("faithful"), min_designed_items=3)
    return provider.prompts[0]


def _prompt_prohibitions() -> str:
    """Rendered prompt, whitespace-collapsed and lowercased so exact-phrase
    prohibition assertions are robust to markdown line wrapping."""
    return " ".join(_rendered_node_a_prompt().split()).lower()


def test_prompt_declares_exact_schema_top_level_keys() -> None:  # §7 (b)
    # Every allowed study_config top-level key must be named, tied to the real model
    # so the shape cannot be hallucinated (the incident used `study`, `out_of_model`,
    # `reference_comparison` and omitted meta/methodology/model).
    from burhan.core.artifacts.models import StudyConfig

    prompt = _rendered_node_a_prompt()
    for key in StudyConfig.model_fields:  # the 11 governed top-level keys
        assert key in prompt, f"prompt must name allowed top-level key {key!r}"


def test_prompt_requires_model_mediators_for_indirect_hypotheses() -> None:
    # AT-M6-MC-5 (s7): _prompt_prohibitions() lowercases and collapses
    # whitespace (test_node_a.py:350-353).
    prompt = _prompt_prohibitions()
    trigger = "whenever any hypothesis has `effect: indirect`"
    coverage = (
        "`model.mediators` must list every construct used in any indirect hypothesis's `via` chain"
    )
    order = "each such construct exactly once, in the order it is declared in `constructs`"
    optional = "when no hypothesis has `effect: indirect`, `model.mediators` remains optional"
    assert trigger in prompt
    assert coverage in prompt
    assert order in prompt
    assert optional in prompt


def test_prompt_binds_scale_labels_and_forbids_numeric_anchors() -> None:  # §7 (a)
    # Prohibition, not vocabulary: the prompt must FORBID a numeric-keyed anchors map and
    # a nested shared scale_range, and route anchors to scale.labels. A prompt that told
    # the model to emit those structures would fail these assertions.
    prompt = _prompt_prohibitions()
    assert "labels` array of strings" in prompt  # anchors home = scale.labels string array
    assert "never use a numeric-keyed `anchors` map" in prompt
    assert "never nest a shared `instrument.scale_range`" in prompt
    assert "must parse as a string" in prompt  # not the contradictory "must be quoted"


def test_prompt_routes_out_of_model_to_ignored_item_columns() -> None:  # §7 (c: out-of-model)
    # Prohibition + correct target: out-of-model -> data.ignored_item_columns, and the
    # prompt must forbid a top-level out_of_model key.
    prompt = _prompt_prohibitions()
    assert "ignored_item_columns" in prompt
    assert "never create a top-level `out_of_model` key" in prompt


def test_prompt_forbids_reference_and_retained_subset_material() -> None:  # §7 (c)
    # Prohibition: the prompt must forbid a reference_comparison block and any retained
    # subset (FR-202). Fails if the prompt instructed the model to emit that material.
    prompt = _prompt_prohibitions()
    assert "never emit a `reference_comparison` block" in prompt
    assert "never emit a retained subset of items" in prompt
    assert "fr-202" in prompt


def test_numeric_anchor_keys_reproduce_the_canonical_halt() -> None:  # §7 (a) incident repro
    # The exact live incident: instrument.scale_range.anchors with unquoted integer
    # keys → YAML int keys → canonical front door halts before schema validation.
    def inject_numeric_anchors(data: dict[str, Any]) -> None:
        data["instrument"]["scale_range"] = {
            "min": 1,
            "max": 7,
            "anchors": {1: "Strongly Disagree", 7: "Strongly Agree"},
        }

    node = _node({"numeric-anchors": _mutated_yaml(inject_numeric_anchors)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("numeric-anchors"), min_designed_items=3)
    assert excinfo.value.message == "non-string dict key in canonical payload"


def test_extra_top_level_out_of_model_key_rejected() -> None:  # §7 (b/c) incident repro
    def add_out_of_model(data: dict[str, Any]) -> None:
        data["out_of_model"] = [{"section": "Financial Resources", "items": ["R1", "R2"]}]

    node = _node({"oom": _mutated_yaml(add_out_of_model)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("oom"), min_designed_items=3)
    assert excinfo.value.to_report()["details"]["path"] == "$"


def test_extra_top_level_reference_comparison_key_rejected() -> None:  # §7 (c) incident repro
    def add_reference(data: dict[str, Any]) -> None:
        data["reference_comparison"] = {"paper_retained_items": {"R_TI": ["R9", "R10"]}}

    node = _node({"ref": _mutated_yaml(add_reference)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("ref"), min_designed_items=3)
    assert excinfo.value.to_report()["details"]["path"] == "$"


def test_extra_top_level_study_key_rejected() -> None:  # §7 (b) incident repro
    # The observed top-level drift: a `study` key in place of meta/methodology.
    def add_study(data: dict[str, Any]) -> None:
        data["study"] = {"title": "AI readiness", "methodology": "CB_SEM"}

    node = _node({"study-toplevel": _mutated_yaml(add_study)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("study-toplevel"), min_designed_items=3)
    assert excinfo.value.to_report()["details"]["path"] == "$"


# -- §7 follow-up (Node A full-schema contract) ----------------------------------------
# The live `$.model.paths` halt was only jsonschema's best-match: the SAME response
# carried 255 violations, because the prompt under-specified EVERY block and Node A
# hallucinated a plausible key for each — `construct` for `construct_ref`, `direction`
# for `sign`, `label`/`parent` on constructs, `approach`/`estimation` on methodology,
# `higher_order` as a list, `source_documents` as title strings, `study_id` with
# underscores. Fixing only `model.paths` would have surfaced the next block's halt.
# The prompt now enumerates every block; the prompt-contract tests below pin that
# enumeration (each RED on the pre-edit prompt), and the per-block locks pin that the
# engine already rejects each observed drift at its exact JSON path.


def test_prompt_enumerates_model_roles_and_forbids_edge_lists() -> None:  # directive (1)
    # Prohibition, not vocabulary: the five role sub-keys are enumerated AND a from/to
    # edge list under `model` is forbidden — a prompt that told the model to emit
    # `model.paths` would fail this.
    prompt = _prompt_prohibitions()
    for role in ("exogenous", "endogenous", "mediators", "moderators", "controls"):
        assert role in prompt, f"model role {role!r} must be enumerated"
    assert "never emit `model.paths`, `model.edges`, `model.relationships`" in prompt
    assert "classifies constructs by role" in prompt
    assert "does not encode path edges" in prompt


def test_prompt_routes_structural_edges_to_hypotheses_not_model() -> None:  # directive (2)
    prompt = _prompt_prohibitions()
    assert "structural path edges are expressed" in prompt
    assert "never under `model`" in prompt
    assert "key is `sign`, not `direction`" in prompt


# -- §7 correction (Node A mediation via semantics) ------------------------------------
# The live DBA run reached V5 (schema + V1-V4 passed) and halted: Node A serialized two
# PARALLEL mediators (A_PEOU, A_PU) into one indirect `via` [A_PEOU, A_PU, A_ATT],
# inventing a phantom A_PEOU->A_PU direct edge no hypothesis declared. v1.md described
# `via` only as "an array of mediator construct codes" — silent on the V5 rule that a
# via is ONE reachable chain whose consecutive links must all be declared direct
# hypotheses, and that parallel siblings must be split into separate indirect paths.


def test_prompt_defines_via_as_single_reachable_chain_and_forbids_parallel_serialization() -> None:
    # Prohibition + rule: `via` is one structurally reachable path whose consecutive links
    # are each a declared effect:direct hypothesis; parallel sibling mediators must never be
    # serialized into one via, and route to separate indirect hypotheses instead. A prompt
    # that still called via "an array of mediator construct codes" fails these.
    prompt = _prompt_prohibitions()
    assert "structurally reachable indirect path" in prompt
    assert "each consecutive link in the chain" in prompt
    assert "must also appear as a declared `effect: direct` hypothesis" in prompt
    assert "never serialize parallel sibling mediators into one `via` list" in prompt
    assert "separate indirect hypotheses, one per reachable path" in prompt


# -- §7 exhaustive pass (close EVERY schema/validator gap in one correction) ------------
# Seventh sequential live-halt = hypothesis-id grammar (`H6b_via_PU`). The standing
# meta-test (test_prompt_schema_coverage) mechanically enumerates all constraints; the
# per-gap prompt-contract tests below pin each of the six gaps that pass found, each RED
# on the pre-edit prompt.


def test_prompt_binds_hypothesis_id_grammar_and_split_naming() -> (
    None
):  # gap: hypotheses[].id + V5-unique
    # Live halt: Node A named split indirect hypotheses `H6b_via_PU` (violates ^H[0-9]+[a-z]?$).
    # The prompt must state the grammar, forbid descriptive suffixes, give conforming split ids,
    # and require uniqueness. The prior "of the form H1, H2, H4a" examples fail these.
    prompt = _prompt_prohibitions()
    assert "an `h` followed by one or more digits and an optional single lowercase letter" in prompt
    assert "never a descriptive suffix" in prompt
    assert "appending the next unused lowercase letter" in prompt  # how to name split paths
    assert "each hypothesis `id` is unique" in prompt


def test_prompt_omits_created_timestamp() -> None:  # gap: meta.created UtcSeconds trap
    # `created` is optional but strictly UTC whole-second (models.UtcSeconds); an LLM date
    # trips it. The prompt must tell Node A to omit it (the engine records timestamps).
    assert "do not emit `created`" in _prompt_prohibitions()


def test_prompt_requires_nonempty_structural_roles() -> (
    None
):  # gap: model.exogenous/endogenous minItems
    assert "at least one exogenous" in _prompt_prohibitions()


def test_prompt_requires_higher_order_when_any_second_order() -> None:  # gap: V3 biconditional
    # V3 halts if a second_order construct exists without a higher_order block. The prompt
    # stated only "present only if second-order"; it must also state the required direction.
    assert "required if any construct is second-order" in _prompt_prohibitions()


def test_prompt_declares_data_dictionary_authoritative() -> None:  # gap: FR-204
    assert "the data dictionary is authoritative" in _prompt_prohibitions()


def test_descriptive_hypothesis_id_reproduces_the_schema_halt() -> None:  # §7 (id) incident repro
    # The exact seventh live halt: a hypothesis id with a descriptive suffix violates the
    # schema pattern ^H[0-9]+[a-z]?$ and halts before any cross-field validator.
    def descriptive_id(data: dict[str, Any]) -> None:
        data["hypotheses"][0]["id"] = "H1_via_PU"

    node = _node({"desc-id": _mutated_yaml(descriptive_id)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("desc-id"), min_designed_items=3)
    details = excinfo.value.to_report()["details"]
    assert "hypotheses" in details["path"] and details["path"].endswith(".id")


def test_prompt_binds_meta_and_forbids_fabricated_provenance() -> None:
    # study_id is a slug (the incident used `dba_validation_qatar_ai`); source_documents
    # is engine-supplied provenance the LLM must never fabricate (it cannot hash files).
    prompt = _prompt_prohibitions()
    assert "no underscores" in prompt
    assert "do not emit `source_documents`" in prompt
    assert "never fabricate" in prompt


def test_prompt_binds_methodology_and_forbids_invented_fields() -> None:
    prompt = _prompt_prohibitions()
    assert "cb_sem" in prompt
    assert "cross_sectional" in prompt
    assert "playbook_id" in prompt and "playbook_version" in prompt
    assert "never emit an `estimator`, `estimation`, `approach`" in prompt


def test_prompt_binds_instrument_item_construct_ref() -> None:
    prompt = _prompt_prohibitions()
    assert "the key is `construct_ref`, not `construct`" in prompt


def test_prompt_binds_construct_fields_and_forbids_extras() -> None:
    prompt = _prompt_prohibitions()
    for key in ("code", "name", "level", "measurement", "indicators", "components"):
        assert key in prompt
    assert "first_order" in prompt and "second_order" in prompt
    assert "never `label`, `order`, `parent`, or `deletion_locked`" in prompt


def test_prompt_binds_higher_order_as_object_not_list() -> None:
    prompt = _prompt_prohibitions()
    assert "an object (never a list)" in prompt
    assert "repeated_indicator" in prompt and "structural_carry" in prompt


def test_prompt_binds_data_fields_and_forbids_extras() -> None:
    prompt = _prompt_prohibitions()
    assert "never `target_population`" in prompt
    assert "entry has exactly `code`, `column_hint`, and `type`" in prompt


def test_prompt_binds_crosswalk_and_protected_overrides() -> None:
    prompt = _prompt_prohibitions()
    assert "provided_map" in prompt
    assert "item_deletion_preauthorized" in prompt
    assert "researcher-owned safety decision" in prompt


def test_model_paths_edge_list_reproduces_the_model_halt() -> None:  # directive (3)
    # The exact second live incident: a from/to edge list under `model` trips the
    # schema's additionalProperties:false at $.model (only best-match of the 255).
    def add_paths(data: dict[str, Any]) -> None:
        data["model"]["paths"] = [{"from": "ENB", "to": "PU"}, {"from": "PU", "to": "ATT"}]

    node = _node({"model-paths": _mutated_yaml(add_paths)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("model-paths"), min_designed_items=3)
    assert excinfo.value.to_report()["details"]["path"] == "$.model"


def _set_nested(data: dict[str, Any], keys: list[Any], value: Any) -> None:
    target: Any = data
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value


@pytest.mark.parametrize(
    ("keys", "value", "path"),
    [
        (["constructs", 0, "parent"], "ENB", "$.constructs[0]"),
        (["hypotheses", 0, "direction"], "up", "$.hypotheses[0]"),
        (["instrument", "items", 0, "construct"], "RES", "$.instrument.items[0]"),
        (["methodology", "approach"], "pls", "$.methodology"),
        (["data", "target_population"], "SMEs", "$.data"),
        (["higher_order"], [{"name": "ENB"}], "$.higher_order"),
        (["meta", "study_id"], "dba_validation_qatar_ai", "$.meta.study_id"),
    ],
)
def test_underspecified_block_drift_halts_at_its_path(
    keys: list[Any], value: Any, path: str
) -> None:
    # One observed drift per previously under-specified block: the engine rejects each
    # at its exact JSON path, so no single-block halt is left latent behind model.paths.
    node = _node({path: _mutated_yaml(lambda data: _set_nested(data, keys, value))})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document(path), min_designed_items=3)
    assert excinfo.value.to_report()["details"]["path"] == path


# -- §7 combined follow-up: engine-injected authoritative provenance/governance --------
# The prompt tells Node A to OMIT meta.source_documents (file hashes) and
# methodology.playbook_id/version (governance) — an LLM cannot derive them and must not
# fabricate a hash. The engine injects the authoritative values into the raw contract
# BEFORE schema validation, so a compliant Node A response completes into a schema-valid
# StudyConfig. These tests pin the injection API and the no-injection halt.


def _drop_engine_fields(data: dict[str, Any]) -> None:
    del data["meta"]["source_documents"]
    del data["methodology"]["playbook_id"]
    del data["methodology"]["playbook_version"]


def test_extract_injects_authoritative_provenance_before_validation() -> None:
    # A response omitting the engine fields WOULD fail schema; with provenance it becomes
    # valid — proving the injection lands before validate_and_build.
    from burhan.contract.node_a import ContractProvenance, SourceDocumentRef

    prov = ContractProvenance(
        source_documents=(
            SourceDocumentRef("study_document", "inputs/study_document.docx", "a" * 64),
            SourceDocumentRef("data_dictionary", "inputs/data_dictionary.docx", "b" * 64),
        ),
        playbook_id="CB_SEM_PLAYBOOK",
        playbook_version="1.0",
    )
    node = _node({"inject": _mutated_yaml(_drop_engine_fields)})
    config = node.extract(study_document=_document("inject"), min_designed_items=3, provenance=prov)
    assert [(s.role, s.path, s.sha256) for s in config.meta.source_documents] == [
        ("study_document", "inputs/study_document.docx", "a" * 64),
        ("data_dictionary", "inputs/data_dictionary.docx", "b" * 64),
    ]
    assert config.methodology.playbook_id == "CB_SEM_PLAYBOOK"
    assert config.methodology.playbook_version == "1.0"


def test_extract_provenance_overwrites_any_llm_supplied_fields() -> None:
    # If the model defies the prompt and emits these anyway, the engine's authoritative
    # values win — a model-emitted file hash is never trusted.
    from burhan.contract.node_a import ContractProvenance, SourceDocumentRef

    def fake_provenance(data: dict[str, Any]) -> None:
        data["meta"]["source_documents"] = [
            {"role": "study_document", "path": "x", "sha256": "c" * 64}
        ]
        data["methodology"]["playbook_id"] = "FAKE_PLAYBOOK"

    prov = ContractProvenance(
        source_documents=(
            SourceDocumentRef("study_document", "inputs/study_document.docx", "a" * 64),
        ),
        playbook_id="CB_SEM_PLAYBOOK",
        playbook_version="1.0",
    )
    node = _node({"overwrite": _mutated_yaml(fake_provenance)})
    config = node.extract(
        study_document=_document("overwrite"), min_designed_items=3, provenance=prov
    )
    assert config.meta.source_documents[0].sha256 == "a" * 64  # authoritative, not the LLM's "c…"
    assert config.methodology.playbook_id == "CB_SEM_PLAYBOOK"  # not "FAKE_PLAYBOOK"


def test_omitted_provenance_without_injection_halts_typed() -> None:
    # Negative: the corrected prompt omits engine fields; WITHOUT the injection path the
    # omission is a typed halt on a required field, never a silent pass.
    node = _node({"omit": _mutated_yaml(_drop_engine_fields)})
    with pytest.raises(IntegrityHalt) as excinfo:
        node.extract(study_document=_document("omit"), min_designed_items=3)  # no provenance
    details = str(excinfo.value.to_report()["details"])
    assert "source_documents" in details or "playbook" in details
