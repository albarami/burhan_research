"""Standing meta-test (§7 exhaustive pass): the Node A prompt must cover every
study_config schema + validator constraint.

Seven sequential live-extraction halts (YAML fence, numeric keys, top-level
shape, model.paths, provenance fields, mediation via, hypothesis-id grammar)
were each a prompt gap found by spending a token. This meta-test enumerates the
constraints mechanically (``prompt_coverage``) and fails if any is:

* UNMAPPED — a schema/validator constraint no one paired with prompt language
  (e.g. a future schema change adds a pattern/enum/required key); or
* GAP — the prompt stopped guaranteeing a mapped constraint (a prompt regression).

Either failure blocks merge, so the sequential-halt class cannot silently reopen.

The enumeration is exhaustive on three axes, each with its own guard here:

* every schema ``type`` is enumerated and either justified-excluded (string /
  object / array carry no prompt obligation) or mapped to a phrase
  (integer / boolean / number gate extraction) — ``test_excluded_type_classes*``;
* every pydantic Field constraint (pattern / min_length / ge / le) mirrors a
  schema row at the same path — ``test_pydantic_model_field_constraints*``;
* removing any one context-specific required phrase reopens EXACTLY its row and
  no other — ``test_removing_a_required_phrase*`` (proves the mapping is
  specific, not a reused cross-field phrase that would mask a deletion).
"""

from __future__ import annotations

import prompt_coverage
import pytest
from prompt_coverage import (
    GAP,
    TYPE_PROBES,
    TYPE_STRUCTURAL,
    TYPE_TRIVIAL,
    UNMAPPED,
    coverage_rows,
    model_divergences,
    model_only_constraints,
    schema_constraints,
)


def test_no_unmapped_schema_or_validator_constraints() -> None:
    unmapped = [key for key, status, _ in coverage_rows() if status == UNMAPPED]
    assert not unmapped, (
        "constraints with no prompt-coverage mapping — add them to "
        f"prompt_coverage.py AND cover them in prompts/node_a/v1.md: {unmapped}"
    )


def test_prompt_covers_every_schema_and_validator_constraint() -> None:
    gaps = {key: missing for key, status, missing in coverage_rows() if status == GAP}
    assert not gaps, (
        "Node A prompt no longer guarantees these constraints — add the missing "
        f"phrase(s) to prompts/node_a/v1.md: {gaps}"
    )


def test_pydantic_model_mirrors_schema() -> None:
    # StudyConfig and the JSON schema both validate at runtime (loader); enumerating the
    # schema is only complete if the model adds no property/enum constraint of its own.
    # Model-only strictness (UtcSeconds) is enumerated separately and covered via omit.
    divergences = model_divergences()
    assert not divergences, (
        "StudyConfig pydantic model diverged from study_config.schema.yaml "
        f"(a model-only constraint the schema walk would miss): {divergences}"
    )


def test_pydantic_model_field_constraints_mirror_schema() -> None:
    # Fix 1b: every pydantic Field constraint (pattern/min_length/ge/le) must be
    # represented by a schema row at the same path, else the schema walk under-counts
    # and a model-only rule could halt a schema-passing response uncaught. Empty proves
    # introspecting the model surfaces no constraint the schema enumeration already lacks.
    model_only = model_only_constraints()
    assert not model_only, (
        "pydantic Field constraints not mirrored by a schema row at the same path — "
        f"enumerate them in the schema walk or give each a model-strict row: {model_only}"
    )


def test_excluded_type_classes_are_only_trivial_or_structural() -> None:
    # Fix 1a: every schema `type` is enumerated. A type is legitimately excluded only if
    # it is trivial (string: any YAML scalar satisfies it) or structural (object/array:
    # covered by no-extra/required/minItems). Any other type (integer/boolean/number)
    # gates extraction and MUST map to a prompt phrase — never a silent exclusion.
    justified = TYPE_TRIVIAL | TYPE_STRUCTURAL
    for kind, path, detail in schema_constraints():
        if kind != "type":
            continue
        key = f"type:{path}"
        assert detail in justified or key in TYPE_PROBES, (
            f"type constraint {key}={detail!r} is neither a justified exclusion "
            "(string/object/array) nor mapped to a prompt phrase in TYPE_PROBES"
        )


# (constraint row key, the exact prompt phrase that guarantees it). Removing the phrase
# must reopen EXACTLY that row — proving the mapping is context-specific, so no reused
# cross-field phrase can leave a deleted rule silently COVERED (the REJECT's core defect).
REOPENINGS = [
    ("minItems:$.model.endogenous", "at least one endogenous"),
    ("minItems:$.model.controls[].on", "every control targets at least one construct"),
    ("validator:V2-playbook-minimum", "the designed pool must meet the playbook's minimum"),
    ("validator:V4-resolvable", "must be one of the declared `constructs`"),
    ("validator:V6-one-role", "every export column resolves to exactly one role"),
    ("validator:V6-zero-orphan", "an unaccounted column is an orphan"),
]


@pytest.mark.parametrize("key, phrase", REOPENINGS, ids=[k for k, _ in REOPENINGS])
def test_removing_a_required_phrase_reopens_exactly_that_row(
    monkeypatch: pytest.MonkeyPatch, key: str, phrase: str
) -> None:
    full = prompt_coverage.rendered_prompt()
    assert phrase in full, f"probe phrase not present in the live prompt: {phrase!r}"
    monkeypatch.setattr(prompt_coverage, "rendered_prompt", lambda: full.replace(phrase, ""))
    reopened = {k for k, status, _ in coverage_rows() if status == GAP}
    assert reopened == {key}, (
        f"removing {phrase!r} should reopen EXACTLY {key}; reopened {sorted(reopened)} "
        "(a shared phrase would reopen several rows or none — mapping must be specific)"
    )
