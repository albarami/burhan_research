"""AT-M10-4: the deletion protected path (FR-705–708; PB-13).

Candidate deletions surface as a Recommendation unless PD-05 is
pre-authorized; under a PermitToken the protocol runs one item at a
time with full re-estimation between deletions (call sequence
asserted), enforces the dual trigger, the three-item floor and the
two-item deletion-lock, emits a before/after audit, and prominently
flags validated-instrument deviations.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from deletion_util import (
    SequenceWorker,
    decision_log,
    frame_for,
    playbook,
    policy_with,
    registry,
    study_config,
    worker_result,
)

from burhan.core.errors import IntegrityHalt
from burhan.core.registry import PermitToken, Recommendation
from burhan.stats.deletion import deletion_candidates, deletion_floor, run_deletion_protocol

_FIVE_FOUR = {"FA": ["A1", "A2", "A3", "A4", "A5"], "FB": ["B1", "B2", "B3", "B4"]}


def _run(
    tmp_path: Path,
    *,
    constructs: dict[str, list[str]],
    preauthorized: bool,
    results: list[dict],
    content_validity: dict[str, str],
    sources: dict[str, str] | None = None,
    item_sources: dict[str, str] | None = None,
    rules: list[str] | None = None,
) -> tuple[dict, SequenceWorker]:
    policy = policy_with(preauthorized, tmp_path, rules=rules)
    worker = SequenceWorker(results)
    outcome = run_deletion_protocol(
        frame_for([code for items in constructs.values() for code in items]),
        study_config(constructs, sources=sources, item_sources=item_sources),
        policy=policy,
        playbook=playbook(),
        registry=registry(policy),
        log=decision_log(tmp_path),
        rworker=worker,  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="del",
        content_validity=content_validity,
    )
    return outcome, worker


def test_candidate_yields_recommendation_only(tmp_path: Path) -> None:
    # Protected default (FR-705): a weak loading surfaces a Recommendation;
    # nothing is deleted and no re-estimation happens (single baseline call).
    outcome, worker = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=False,
        results=[worker_result(_FIVE_FOUR, {"A5": 0.55})],
        content_validity={"A5": "domain intact without A5"},
    )
    assert outcome["mode"] == "recommendation"
    assert isinstance(outcome["recommendation"], Recommendation)
    assert outcome["deletions"] == []
    assert [c["item"] for c in outcome["candidates"]] == ["A5"]
    assert len(worker.calls) == 1


def test_permit_executes_one_at_a_time_with_reestimation(tmp_path: Path) -> None:
    # FR-706: one item per step, full re-estimation between deletions.
    # The call sequence proves it: every re-fit payload drops exactly the
    # single item deleted so far, worst signal first.
    after_a5 = {"FA": ["A1", "A2", "A3", "A4"], "FB": ["B1", "B2", "B3", "B4"]}
    after_a4 = {"FA": ["A1", "A2", "A3"], "FB": ["B1", "B2", "B3", "B4"]}
    outcome, worker = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=True,
        results=[
            worker_result(_FIVE_FOUR, {"A5": 0.55, "A4": 0.62}, fit_chisq=140.0),
            worker_result(after_a5, {"A4": 0.62}, fit_chisq=120.0),
            worker_result(after_a4, fit_chisq=100.0),
        ],
        content_validity={"A5": "redundant with A1", "A4": "redundant with A2"},
    )
    assert outcome["mode"] == "executed"
    assert isinstance(outcome["token"], PermitToken)
    assert [d["item"] for d in outcome["deletions"]] == ["A5", "A4"]
    assert len(worker.calls) == 3
    assert worker.calls[0]["columns"] == ["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4"]
    assert worker.calls[1]["columns"] == ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4"]
    assert worker.calls[2]["columns"] == ["A1", "A2", "A3", "B1", "B2", "B3", "B4"]
    # each audit captures the model on both sides of its deletion
    first, second = outcome["deletions"]
    assert first["before"]["fit"]["chisq"] == 140.0
    assert first["after"]["fit"]["chisq"] == 120.0
    assert second["before"]["fit"]["chisq"] == 120.0
    assert second["after"]["fit"]["chisq"] == 100.0


def test_statistical_signal_alone_is_insufficient(tmp_path: Path) -> None:
    # FR-707 dual trigger: a weak loading without a content-validity
    # attestation must not delete — even under a valid PermitToken.
    outcome, worker = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=True,
        results=[worker_result(_FIVE_FOUR, {"A5": 0.55})],
        content_validity={},
    )
    assert outcome["mode"] == "executed"
    assert outcome["deletions"] == []
    assert len(worker.calls) == 1
    assert [(s["item"], s["reason"]) for s in outcome["skipped"]] == [
        ("A5", "content_validity_missing")
    ]


def test_three_item_floor_enforced(tmp_path: Path) -> None:
    # FR-707: never below three items per reflective construct. With two
    # attested weak items in a four-item construct, only one deletion runs.
    constructs = {"FA": ["A1", "A2", "A3"], "FB": ["B1", "B2", "B3", "B4"]}
    after_b4 = {"FA": ["A1", "A2", "A3"], "FB": ["B1", "B2", "B3"]}
    outcome, worker = _run(
        tmp_path,
        constructs=constructs,
        preauthorized=True,
        results=[
            worker_result(constructs, {"B4": 0.55, "B3": 0.60}),
            worker_result(after_b4, {"B3": 0.60}),
        ],
        content_validity={"B4": "redundant", "B3": "redundant"},
    )
    assert [d["item"] for d in outcome["deletions"]] == ["B4"]
    assert len(worker.calls) == 2
    assert ("B3", "three_item_floor") in [(s["item"], s["reason"]) for s in outcome["skipped"]]


def test_two_item_construct_is_deletion_locked(tmp_path: Path) -> None:
    # PB-13: constructs designed with fewer than three items are
    # deletion-locked outright, before any floor arithmetic.
    constructs = {"FA": ["A1", "A2", "A3", "A4"], "FC": ["C1", "C2"]}
    outcome, worker = _run(
        tmp_path,
        constructs=constructs,
        preauthorized=True,
        results=[worker_result(constructs, {"C2": 0.40})],
        content_validity={"C2": "attested"},
    )
    assert outcome["deletions"] == []
    assert len(worker.calls) == 1
    assert [(s["item"], s["reason"]) for s in outcome["skipped"]] == [("C2", "deletion_locked")]


def test_validated_instrument_deviation_flagged(tmp_path: Path) -> None:
    # FR-708: deleting from a construct with a published source is a
    # validated-instrument deviation and must be prominently flagged.
    after = {"FA": ["A1", "A2", "A3", "A4"], "FB": ["B1", "B2", "B3", "B4"]}
    outcome, _ = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=True,
        results=[
            worker_result(_FIVE_FOUR, {"A5": 0.55}),
            worker_result(after),
        ],
        content_validity={"A5": "redundant"},
        sources={"FA": "Validated Scale (Author, 2001)"},
    )
    (deletion,) = outcome["deletions"]
    assert deletion["validated_instrument_deviation"] is True


def test_unvalidated_construct_not_flagged(tmp_path: Path) -> None:
    after = {"FA": ["A1", "A2", "A3", "A4"], "FB": ["B1", "B2", "B3", "B4"]}
    outcome, _ = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=True,
        results=[
            worker_result(_FIVE_FOUR, {"A5": 0.55}),
            worker_result(after),
        ],
        content_validity={"A5": "redundant"},
    )
    (deletion,) = outcome["deletions"]
    assert deletion["validated_instrument_deviation"] is False


def test_audit_carries_reliability_validity_and_fit_both_sides(tmp_path: Path) -> None:
    # FR-708: a complete before/after audit on every deletion.
    after = {"FA": ["A1", "A2", "A3", "A4"], "FB": ["B1", "B2", "B3", "B4"]}
    outcome, _ = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=True,
        results=[
            worker_result(_FIVE_FOUR, {"A5": 0.55}),
            worker_result(after),
        ],
        content_validity={"A5": "redundant"},
    )
    (deletion,) = outcome["deletions"]
    for side in ("before", "after"):
        assert set(deletion[side]) == {"reliability", "validity", "fit"}
        assert deletion[side]["fit"]["chisq"] > 0


def test_deletion_decisions_are_logged(tmp_path: Path) -> None:
    # FR-1201: the permit consultation and each executed deletion land in
    # the decision log with the delegation rule cited.
    policy = policy_with(True, tmp_path)
    log = decision_log(tmp_path)
    after = {"FA": ["A1", "A2", "A3", "A4"], "FB": ["B1", "B2", "B3", "B4"]}
    run_deletion_protocol(
        frame_for([code for items in _FIVE_FOUR.values() for code in items]),
        study_config(_FIVE_FOUR),
        policy=policy,
        playbook=playbook(),
        registry=registry(policy),
        log=log,
        rworker=SequenceWorker(  # type: ignore[arg-type]
            [worker_result(_FIVE_FOUR, {"A5": 0.55}), worker_result(after)]
        ),
        run_dir=tmp_path,
        call_id="del-log",
        content_validity={"A5": "redundant"},
    )
    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # token issuance + one executed deletion
    assert '"item_deletion_executed"' in lines[1]
    assert '"A5"' in lines[1]


def test_weak_loading_without_permit_never_reaches_the_worker_twice(tmp_path: Path) -> None:
    # Absence-of-execution under the protected default even when the dual
    # trigger would otherwise be satisfied.
    outcome, worker = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=False,
        results=[worker_result(_FIVE_FOUR, {"A5": 0.30, "A4": 0.35})],
        content_validity={"A5": "attested", "A4": "attested"},
    )
    assert outcome["mode"] == "recommendation"
    assert len(worker.calls) == 1


def test_candidates_are_derived_from_playbook_bound() -> None:
    # The deletion-candidate signal comes from PB-09's rule text, not a
    # hard-coded constant: .69 is a candidate, .71 is not.
    report_like = {
        "first_order": {
            "loadings": [
                {"construct": "FA", "item": "A1", "est": 0.69, "std": 0.69},
                {"construct": "FA", "item": "A2", "est": 0.71, "std": 0.71},
            ]
        }
    }
    candidates = deletion_candidates(report_like, playbook=playbook())
    assert [c["item"] for c in candidates] == ["A1"]
    assert candidates[0]["signal"] == "loading_below_playbook_target"


def test_doctored_playbook_without_candidate_rule_halts() -> None:
    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, object]]:
            if step_id == "PB-09":
                return [
                    {"name": "other_rule", "value": 0.1, "rule": "ignore"},
                    {"name": "loading_target", "value": 0.708, "rule": "be strict"},
                ]
            return []

    with pytest.raises(IntegrityHalt) as excinfo:
        deletion_candidates(
            {"first_order": {"loadings": []}},
            playbook=DoctoredPlaybook(),  # type: ignore[arg-type]
        )
    assert "deletion-candidate" in excinfo.value.message


@pytest.mark.parametrize(
    "criteria",
    [
        [{"name": "unrelated", "value": 3}],
        [{"name": "three_item_floor", "value": 2.5}],
        [{"name": "three_item_floor", "value": "three"}],
    ],
    ids=["missing", "fractional", "nonnumeric"],
)
def test_doctored_playbook_floor_halts(criteria: list[dict[str, object]]) -> None:
    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, object]]:
            if step_id == "PB-13":
                return criteria
            return playbook().criteria(step_id)

    with pytest.raises(IntegrityHalt) as excinfo:
        deletion_floor(DoctoredPlaybook())  # type: ignore[arg-type]
    assert "three-item floor" in excinfo.value.message


def test_nonnumeric_std_in_candidate_scan_halts() -> None:
    report_like = {
        "first_order": {"loadings": [{"construct": "FA", "item": "A1", "est": 0.5, "std": "low"}]}
    }
    with pytest.raises(IntegrityHalt) as excinfo:
        deletion_candidates(report_like, playbook=playbook())
    assert "nonnumeric std" in excinfo.value.message


def test_signal_outside_granted_rules_is_not_executed(tmp_path: Path) -> None:
    # PB-13 governance: the token's granted rules bound what the permit
    # covers; a loading signal is skipped when only discriminant_violation
    # was pre-authorized.
    outcome, worker = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=True,
        results=[worker_result(_FIVE_FOUR, {"A5": 0.55})],
        content_validity={"A5": "attested"},
        rules=["discriminant_violation"],
    )
    assert outcome["deletions"] == []
    assert len(worker.calls) == 1
    assert [(s["item"], s["reason"]) for s in outcome["skipped"]] == [("A5", "signal_not_granted")]


def test_item_level_source_flags_deviation(tmp_path: Path) -> None:
    # FR-708 also binds when the validated provenance sits on the item.
    after = {"FA": ["A1", "A2", "A3", "A4"], "FB": ["B1", "B2", "B3", "B4"]}
    outcome, _ = _run(
        tmp_path,
        constructs=_FIVE_FOUR,
        preauthorized=True,
        results=[
            worker_result(_FIVE_FOUR, {"A5": 0.55}),
            worker_result(after),
        ],
        content_validity={"A5": "redundant"},
        item_sources={"A5": "Item bank (Author, 1999)"},
    )
    (deletion,) = outcome["deletions"]
    assert deletion["validated_instrument_deviation"] is True
