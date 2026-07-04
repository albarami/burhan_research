"""AT-M12-2/3: parity semantics (FR-902/903).

Within tolerance passes; beyond tolerance but below the halt multiplier
flags with the scope named; beyond the halt multiplier raises
VerificationHalt (HALTED_VERIFICATION) with a per-estimate diff.
Scopes outside validated parity are declared in flags, never compared;
an undeclared scope is a configuration defect and halts typed.
"""

from __future__ import annotations

from typing import Any

import pytest
from verify_util import pair, parity_map_data, policy

from burhan.core.errors import IntegrityHalt, VerificationHalt
from burhan.verify.parity import load_parity_map, parity_check, verification_settings


def _settings() -> dict[str, Any]:
    return verification_settings(policy())


def _map() -> dict[str, Any]:
    return load_parity_map(parity_map_data())


def test_verification_settings_come_from_policy() -> None:
    settings = _settings()
    assert settings == {
        "prep_cell_tolerance": 0.0,
        "estimate_abs_tolerance": 0.001,
        "halt_multiplier": 10.0,
    }


def test_within_tolerance_passes() -> None:
    outcome = parity_check(
        [pair("structural.paths", "structural.path.F3->F1", 0.563, 0.5634)],
        parity_map=_map(),
        settings=_settings(),
    )
    (result,) = outcome["results"]
    assert result["status"] == "pass"
    assert outcome["flags"] == []


def test_beyond_tolerance_below_halt_flags_with_scope_named() -> None:
    # delta 0.005: above the 0.001 scope tolerance, below 10x.
    outcome = parity_check(
        [pair("structural.paths", "structural.path.F3->F1", 0.563, 0.568)],
        parity_map=_map(),
        settings=_settings(),
    )
    (result,) = outcome["results"]
    assert result["status"] == "flagged"
    (flag,) = outcome["flags"]
    assert "structural.paths" in flag
    assert "structural.path.F3->F1" in flag


def test_beyond_halt_multiplier_raises_verification_halt() -> None:
    # delta 0.02 = 20x tolerance.
    with pytest.raises(VerificationHalt) as excinfo:
        parity_check(
            [
                pair("structural.paths", "structural.path.F3->F1", 0.563, 0.583),
                pair("structural.paths", "structural.path.F4->F3", 0.473, 0.4731),
            ],
            parity_map=_map(),
            settings=_settings(),
        )
    assert excinfo.value.run_state == "HALTED_VERIFICATION"
    (diff,) = excinfo.value.details["diffs"]
    assert diff["id"] == "structural.path.F3->F1"
    assert diff["scope"] == "structural.paths"
    assert diff["engine_value"] == 0.563
    assert diff["independent_value"] == 0.583
    assert diff["tolerance"] == 0.001
    assert round(diff["delta"], 6) == 0.02


def test_out_of_parity_scope_is_declared_never_compared() -> None:
    # AT-M12-3: a wildly divergent value in a declared non-parity scope
    # (WLSMV) produces the declaration path, not a comparison.
    outcome = parity_check(
        [pair("estimator.wlsmv", "structural.path.F3->F1", 0.5, 9.9)],
        parity_map=_map(),
        settings=_settings(),
    )
    (result,) = outcome["results"]
    assert result["status"] == "declared_out_of_parity"
    assert "delta" not in result
    (flag,) = outcome["flags"]
    assert "estimator.wlsmv" in flag
    assert "not compared" in flag


def test_out_of_parity_declaration_is_deduplicated_per_scope() -> None:
    outcome = parity_check(
        [
            pair("estimator.wlsmv", "a.b.c", 0.1, 0.9),
            pair("estimator.wlsmv", "a.b.d", 0.2, 0.8),
        ],
        parity_map=_map(),
        settings=_settings(),
    )
    assert len(outcome["flags"]) == 1


def test_undeclared_scope_halts_typed() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        parity_check(
            [pair("mystery.scope", "a.b.c", 0.1, 0.1)],
            parity_map=_map(),
            settings=_settings(),
        )
    assert "parity map" in excinfo.value.message


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.pop("certified"),
        lambda m: m["certified"].update({"structural.paths": {"tolerance": "tight"}}),
        lambda m: m["certified"].update({"structural.paths": {"tolerance": -0.001}}),
        lambda m: m.update(non_parity="wlsmv"),
    ],
    ids=["missing_certified", "nonnumeric_tolerance", "negative_tolerance", "nonlist_non_parity"],
)
def test_malformed_parity_map_halts(mutate: Any) -> None:
    data = parity_map_data()
    mutate(data)
    with pytest.raises(IntegrityHalt):
        load_parity_map(data)


@pytest.mark.parametrize(
    ("rule", "value"),
    [
        ("verification.estimate_abs_tolerance", "tight"),
        ("verification.estimate_abs_tolerance", -0.1),
        ("verification.halt_multiplier", 0.5),
        ("verification.halt_multiplier", "big"),
        ("verification.prep_cell_tolerance", None),
    ],
)
def test_doctored_verification_policy_halts(rule: str, value: Any) -> None:
    good = {
        "verification.prep_cell_tolerance": 0,
        "verification.estimate_abs_tolerance": 0.001,
        "verification.halt_multiplier": 10,
    }

    class DoctoredPolicy:
        version = "0.0-test"

        @staticmethod
        def rule(ref: str) -> object:
            return value if ref == rule else good[ref]

    with pytest.raises(IntegrityHalt):
        verification_settings(DoctoredPolicy())  # type: ignore[arg-type]


def test_nonfinite_pair_value_halts() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        parity_check(
            [pair("structural.paths", "a.b.c", float("nan"), 0.1)],
            parity_map=_map(),
            settings=_settings(),
        )
    assert "engine_value" in excinfo.value.message


def test_nonmapping_pair_halts_typed() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        parity_check(
            [("structural.paths", "a.b.c", 0.1, 0.1)],  # type: ignore[list-item]
            parity_map=_map(),
            settings=_settings(),
        )
    assert "not a mapping" in excinfo.value.message
    assert excinfo.value.details["index"] == 0


@pytest.mark.parametrize(
    ("mutate", "field"),
    [
        (lambda p: p.pop("scope"), "scope"),
        (lambda p: p.pop("id"), "id"),
        (lambda p: p.pop("engine_value"), "engine_value"),
        (lambda p: p.pop("independent_value"), "independent_value"),
        (lambda p: p.update(scope=""), "scope"),
        (lambda p: p.update(scope=7), "scope"),
        (lambda p: p.update(id=""), "id"),
        (lambda p: p.update(id=["a", "b"]), "id"),
        (lambda p: p.update(engine_value="x"), "engine_value"),
        (lambda p: p.update(engine_value=True), "engine_value"),
        (lambda p: p.update(engine_value=float("nan")), "engine_value"),
        (lambda p: p.update(engine_value=float("inf")), "engine_value"),
        (lambda p: p.update(independent_value=None), "independent_value"),
        (lambda p: p.update(independent_value=float("-inf")), "independent_value"),
    ],
    ids=[
        "missing_scope",
        "missing_id",
        "missing_engine_value",
        "missing_independent_value",
        "blank_scope",
        "nonstring_scope",
        "blank_id",
        "nonstring_id",
        "nonnumeric_engine_value",
        "bool_engine_value",
        "nan_engine_value",
        "inf_engine_value",
        "none_independent_value",
        "neginf_independent_value",
    ],
)
def test_malformed_pair_halts_typed(mutate: Any, field: str) -> None:
    entry = pair("structural.paths", "structural.path.F3->F1", 0.563, 0.5634)
    mutate(entry)
    with pytest.raises(IntegrityHalt) as excinfo:
        parity_check([entry], parity_map=_map(), settings=_settings())
    assert excinfo.value.details["field"] == field
    assert excinfo.value.details["index"] == 0


def test_malformed_pair_in_non_parity_scope_still_halts() -> None:
    # Shape validation precedes the declaration branch: a nonfinite value
    # in a declared non-parity scope is a defect, not a declaration.
    with pytest.raises(IntegrityHalt) as excinfo:
        parity_check(
            [pair("estimator.wlsmv", "a.b.c", float("nan"), 0.1)],
            parity_map=_map(),
            settings=_settings(),
        )
    assert excinfo.value.details["field"] == "engine_value"
