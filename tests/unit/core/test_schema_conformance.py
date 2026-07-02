"""Schema-keyword conformance harness (AT-M01-1 support; PLAN v2 Fix 4b).

For every assertive-keyword instance in the six machine contracts, a
violating mutant must be rejected by the governed schema AND the pydantic
model must return the same verdict; boundary variants must also agree.
``format`` sites assert the expected asymmetry (Hypothesis H2: annotation-only
under the locked jsonschema install; the models enforce real datetimes).

Coverage is self-policing: a keyword occurring in a schema without a
generated mutant — or a keyword outside the handled/structural/annotation
sets — fails the meta-test rather than going silently untested. Schema
``default`` declarations are enumerated mechanically and each is asserted to
match the model's materialized default.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from artifact_instances import valid_instance
from conformance_util import (
    ANNOTATION_KEYWORDS,
    HANDLED_KEYWORDS,
    STRUCTURAL_KEYWORDS,
    assertive_keyword_occurrences,
    declared_defaults,
    generate_cases,
)
from pydantic import ValidationError

from burhan.core.artifacts.loader import MODEL_FOR_SCHEMA
from burhan.core.artifacts.schemas import (
    GOVERNED_SCHEMA_FILES,
    is_valid,
    load_schema,
    schemas_dir,
)

SCHEMA_NAMES = sorted(GOVERNED_SCHEMA_FILES)


def _augmented_study_config() -> dict[str, Any]:
    """The governed worked example, enriched (in-memory only) so every
    optional subtree carrying keywords is reachable by the walker."""
    base = yaml.safe_load((schemas_dir() / "study_config.example.yaml").read_text(encoding="utf-8"))
    assert isinstance(base, dict)
    base["crosswalk"] = {"mode": "provided", "provided_map": {"Q4_1": "RS1"}}
    base["model"]["moderators"] = [{"variable": "sector", "on_path": "ENB->INT"}]
    base["instrument"]["items"][0]["scale"]["labels"] = ["Strongly disagree", "Strongly agree"]
    return base


def _base(name: str) -> Any:
    if name == "study_config":
        return _augmented_study_config()
    return valid_instance(name)


def _model_accepts(name: str, instance: Any) -> bool:
    try:
        MODEL_FOR_SCHEMA[name].model_validate(instance)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_base_instances_accepted_by_both_validators(name: str) -> None:
    base = _base(name)
    assert is_valid(name, base), f"base instance for {name} rejected by governed schema"
    assert _model_accepts(name, base), f"base instance for {name} rejected by model"


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_mutants_rejected_and_verdicts_agree(name: str) -> None:
    cases = [
        case
        for case in generate_cases(name, load_schema(name), _base(name))
        if case.kind == "mutant"
    ]
    assert cases, f"no mutants generated for {name}"
    failures: list[str] = []
    for case in cases:
        schema_verdict = is_valid(name, case.instance)
        model_verdict = _model_accepts(name, case.instance)
        if schema_verdict:
            failures.append(f"vacuous mutant [{case.keyword}] at {case.path}")
        if model_verdict != schema_verdict:
            failures.append(
                f"verdict disagreement [{case.keyword}] at {case.path}: "
                f"schema={schema_verdict} model={model_verdict}"
            )
    assert not failures, f"{len(failures)} failures, first 20: {failures[:20]}"


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_boundary_variants_verdicts_agree(name: str) -> None:
    cases = [
        case
        for case in generate_cases(name, load_schema(name), _base(name))
        if case.kind == "variant"
    ]
    assert cases, f"no variants generated for {name}"
    failures: list[str] = []
    valid_count = 0
    for case in cases:
        schema_verdict = is_valid(name, case.instance)
        model_verdict = _model_accepts(name, case.instance)
        valid_count += int(schema_verdict)
        if model_verdict != schema_verdict:
            failures.append(
                f"verdict disagreement [{case.keyword}] at {case.path}: "
                f"schema={schema_verdict} model={model_verdict}"
            )
    assert not failures, f"{len(failures)} failures, first 20: {failures[:20]}"
    assert valid_count > 0, "no boundary variant was schema-valid; generator broken"


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_format_sites_show_expected_h2_asymmetry(name: str) -> None:
    probes = [
        case
        for case in generate_cases(name, load_schema(name), _base(name))
        if case.kind == "format_probe"
    ]
    if name in {"results_store_entry", "provenance_entry", "decision_entry", "run_manifest"}:
        assert probes, f"expected format sites in {name}"
    for case in probes:
        # H2: base jsonschema treats format as annotation -> accepts garbage;
        # the models (real datetime/date types) must reject it.
        assert is_valid(name, case.instance), f"H2 falsified at {case.path} — revisit plan"
        assert not _model_accepts(name, case.instance), f"model accepted garbage at {case.path}"


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_keyword_occurrence_coverage_is_closed(name: str) -> None:  # REJECT fix 3
    """Every (schema pointer, keyword) occurrence must receive ≥1 mutant.

    Coverage is tracked per keyword OCCURRENCE (its location in the schema
    document), not per keyword name — an optional branch left unreachable by
    the base instance, or a new keyword, fails here instead of hiding.
    """
    schema = load_schema(name)
    occurrences = assertive_keyword_occurrences(schema)
    assert occurrences, f"no assertive occurrences found in {name}?"
    unknown = {keyword for _, keyword in occurrences} - HANDLED_KEYWORDS
    assert not unknown, (
        f"{name} uses assertive keywords the harness does not handle: {sorted(unknown)}"
    )
    generated = {
        (case.schema_pointer, case.keyword)
        for case in generate_cases(name, schema, _base(name))
        if case.kind == "mutant"
    }
    missing = occurrences - generated
    assert not missing, (
        f"{name}: {len(missing)} keyword occurrences never mutation-tested "
        f"(unreachable in the base instance?): {sorted(missing)[:15]}"
    )
    phantom = generated - occurrences
    assert not phantom, (
        f"{name}: walker produced mutants for pointers the schema does not "
        f"declare (pointer-grammar drift): {sorted(phantom)[:15]}"
    )


def test_handled_structural_annotation_sets_are_disjoint() -> None:
    assert not HANDLED_KEYWORDS & STRUCTURAL_KEYWORDS
    assert not HANDLED_KEYWORDS & ANNOTATION_KEYWORDS
    assert not STRUCTURAL_KEYWORDS & ANNOTATION_KEYWORDS


def test_schema_defaults_are_exactly_the_known_four() -> None:
    found = {
        (name, pointer): value
        for name in SCHEMA_NAMES
        for pointer, value in declared_defaults(load_schema(name)).items()
    }
    assert found == {
        ("decision_entry", "$.properties.protected.default"): False,
        ("run_manifest", "$.properties.advisory.default"): False,
        (
            "reference_comparison",
            "$.properties.comparisons.items.properties.classification.default",
        ): "unresolved",
        (
            "study_config",
            "$.properties.protected_overrides.properties.item_deletion_preauthorized.default",
        ): False,
    }


def test_model_defaults_match_schema_defaults() -> None:
    decision = valid_instance("decision_entry")
    del decision["protected"]
    assert MODEL_FOR_SCHEMA["decision_entry"].model_validate(decision).protected is False  # type: ignore[attr-defined]

    manifest = valid_instance("run_manifest")
    del manifest["advisory"]
    assert MODEL_FOR_SCHEMA["run_manifest"].model_validate(manifest).advisory is False  # type: ignore[attr-defined]

    report = valid_instance("reference_comparison")
    assert "classification" not in report["comparisons"][1]
    built = MODEL_FOR_SCHEMA["reference_comparison"].model_validate(report)
    assert built.comparisons[1].classification == "unresolved"  # type: ignore[attr-defined]

    config = _augmented_study_config()
    del config["protected_overrides"]["item_deletion_preauthorized"]
    built_config = MODEL_FOR_SCHEMA["study_config"].model_validate(config)
    assert built_config.protected_overrides.item_deletion_preauthorized is False  # type: ignore[attr-defined]
