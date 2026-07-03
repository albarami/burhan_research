"""AT-M10-6: the respecification controller (FR-709; PB-14).

Cross-construct MI suggestions are filtered out; within-construct error
covariances apply one at a time in MI order with re-estimation; the
policy cap stops the loop at 3; each modification is logged with its
MI, EPC, and justification rule. Workers are canned sequences — the
recorded payloads prove cumulative one-at-a-time application.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from deletion_util import (
    SequenceWorker,
    decision_log,
    frame_for,
    playbook,
    policy_with,
    study_config,
    worker_result,
)

from burhan.core.errors import IntegrityHalt
from burhan.stats.respecification import mi_floor, run_respecification

_TWO_FOUR = {"FA": ["A1", "A2", "A3", "A4"], "FB": ["B1", "B2", "B3", "B4"]}


def _mi(lhs: str, rhs: str, mi: float, epc: float = 0.10) -> dict[str, Any]:
    return {"lhs": lhs, "rhs": rhs, "mi": mi, "epc": epc}


def _result(mi_entries: list[dict[str, Any]], *, fit_chisq: float = 150.0) -> dict[str, Any]:
    result = worker_result(_TWO_FOUR, fit_chisq=fit_chisq)
    result["mi"] = mi_entries
    return result


def _run(
    tmp_path: Path,
    results: list[dict[str, Any]],
    *,
    cap: int | None = None,
) -> tuple[dict[str, Any], SequenceWorker]:
    policy = policy_with(False, tmp_path, cap=cap)
    worker = SequenceWorker(results)
    outcome = run_respecification(
        frame_for([code for items in _TWO_FOUR.values() for code in items]),
        study_config(_TWO_FOUR),
        policy=policy,
        playbook=playbook(),
        log=decision_log(tmp_path),
        rworker=worker,  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="respec",
    )
    return outcome, worker


def test_cross_construct_and_latent_suggestions_filtered_out(tmp_path: Path) -> None:
    # PB-14 within_construct_only: cross-construct error covariances and
    # anything touching a latent are impermissible regardless of MI size.
    outcome, worker = _run(
        tmp_path,
        [
            _result(
                [
                    _mi("A1", "B1", 40.0),  # cross-construct
                    _mi("A1", "FA", 35.0),  # error-to-latent
                    _mi("FA", "FB", 30.0),  # latent-to-latent
                ]
            )
        ],
    )
    assert outcome["modifications"] == []
    assert len(worker.calls) == 1
    assert {(f["lhs"], f["rhs"]) for f in outcome["filtered"]} == {
        ("A1", "B1"),
        ("A1", "FA"),
        ("FA", "FB"),
    }
    assert all(f["reason"] == "not_within_construct" for f in outcome["filtered"])


def test_within_construct_applied_one_at_a_time_in_mi_order(tmp_path: Path) -> None:
    # Highest MI first, one covariance per re-estimation, cumulatively.
    outcome, worker = _run(
        tmp_path,
        [
            _result([_mi("A1", "A2", 12.0), _mi("B1", "B2", 20.0)], fit_chisq=150.0),
            _result([_mi("A1", "A2", 11.0)], fit_chisq=130.0),
            _result([], fit_chisq=118.0),
        ],
    )
    assert [m["pair"] for m in outcome["modifications"]] == [["B1", "B2"], ["A1", "A2"]]
    assert len(worker.calls) == 3
    assert "error_covariances" not in worker.calls[0]
    assert worker.calls[1]["error_covariances"] == [["B1", "B2"]]
    assert worker.calls[2]["error_covariances"] == [["B1", "B2"], ["A1", "A2"]]
    assert outcome["stopped"] == "no_eligible_suggestion"
    assert outcome["baseline_fit"]["chisq"] == 150.0
    assert outcome["final_fit"]["chisq"] == 118.0


def test_cap_from_policy_stops_at_three(tmp_path: Path) -> None:
    # PB-14 hard_cap via measurement.respecification.max_modifications:
    # a fourth eligible suggestion must not be applied.
    outcome, worker = _run(
        tmp_path,
        [
            _result([_mi("A1", "A2", 30.0)]),
            _result([_mi("A3", "A4", 25.0)]),
            _result([_mi("B1", "B2", 20.0)]),
            _result([_mi("B3", "B4", 15.0)]),  # still eligible — cap stops here
        ],
    )
    assert len(outcome["modifications"]) == 3
    assert len(worker.calls) == 4
    assert outcome["stopped"] == "policy_cap"
    assert worker.calls[3]["error_covariances"] == [["A1", "A2"], ["A3", "A4"], ["B1", "B2"]]


def test_lowered_policy_cap_is_honored(tmp_path: Path) -> None:
    # The cap is read from policy, not hard-coded: cap=1 stops after one.
    outcome, worker = _run(
        tmp_path,
        [
            _result([_mi("A1", "A2", 30.0)]),
            _result([_mi("A3", "A4", 25.0)]),
        ],
        cap=1,
    )
    assert len(outcome["modifications"]) == 1
    assert len(worker.calls) == 2
    assert outcome["stopped"] == "policy_cap"


def test_mi_floor_from_playbook_excludes_small_indices(tmp_path: Path) -> None:
    # PB-14 mi_floor 3.84: a within-construct suggestion below it is not
    # applied (and is reported as filtered with the floor as reason).
    outcome, worker = _run(
        tmp_path,
        [_result([_mi("A1", "A2", 3.5)])],
    )
    assert outcome["modifications"] == []
    assert len(worker.calls) == 1
    assert [(f["lhs"], f["rhs"], f["reason"]) for f in outcome["filtered"]] == [
        ("A1", "A2", "below_mi_floor")
    ]


def test_each_modification_logged_with_mi_epc_and_rule(tmp_path: Path) -> None:
    policy = policy_with(False, tmp_path)
    log = decision_log(tmp_path)
    worker = SequenceWorker(
        [
            _result([_mi("A1", "A2", 12.5, epc=0.21)]),
            _result([]),
        ]
    )
    run_respecification(
        frame_for([code for items in _TWO_FOUR.values() for code in items]),
        study_config(_TWO_FOUR),
        policy=policy,
        playbook=playbook(),
        log=log,
        rworker=worker,  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="respec-log",
    )
    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["decision_point"] == "respecification"
    assert entry["rule_id"] == "measurement.respecification.max_modifications"
    assert entry["inputs"]["mi"] == 12.5
    assert entry["inputs"]["epc"] == 0.21
    assert entry["inputs"]["pair"] == ["A1", "A2"]


def test_mi_block_missing_halts(tmp_path: Path) -> None:
    result = worker_result(_TWO_FOUR)
    with pytest.raises(IntegrityHalt) as excinfo:
        _run(tmp_path, [result])
    assert "mi" in excinfo.value.message


@pytest.mark.parametrize(
    "entry",
    [
        {"lhs": "A1", "rhs": "A2", "mi": "big", "epc": 0.1},
        {"lhs": "A1", "rhs": "A2", "mi": 5.0, "epc": None},
        {"lhs": "A1", "rhs": "A2", "mi": True, "epc": 0.1},
        {"lhs": "A1", "mi": 5.0, "epc": 0.1},
        "not-a-mapping",
    ],
    ids=["nonnumeric_mi", "null_epc", "boolean_mi", "missing_rhs", "nonmapping"],
)
def test_malformed_mi_entries_halt(tmp_path: Path, entry: Any) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        _run(tmp_path, [_result([entry])])
    assert "mi" in excinfo.value.message.lower()


@pytest.mark.parametrize(
    "criteria",
    [
        [{"name": "unrelated", "value": 1.0}],
        [{"name": "mi_floor", "value": "large"}],
        [{"name": "other", "value": 2.0}, {"name": "mi_floor", "value": True}],
    ],
    ids=["missing", "nonnumeric", "boolean_after_other"],
)
def test_doctored_playbook_mi_floor_halts(criteria: list[dict[str, Any]]) -> None:
    class DoctoredPlaybook:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, Any]]:
            if step_id == "PB-14":
                return criteria
            return []

    with pytest.raises(IntegrityHalt) as excinfo:
        mi_floor(DoctoredPlaybook())  # type: ignore[arg-type]
    assert "MI floor" in excinfo.value.message


def test_doctored_policy_cap_halts(tmp_path: Path) -> None:
    class DoctoredPolicy:
        version = "0.0-test"

        @staticmethod
        def rule(ref: str) -> object:
            assert ref == "measurement.respecification.max_modifications"
            return "three"

    with pytest.raises(IntegrityHalt) as excinfo:
        run_respecification(
            frame_for([code for items in _TWO_FOUR.values() for code in items]),
            study_config(_TWO_FOUR),
            policy=DoctoredPolicy(),  # type: ignore[arg-type]
            playbook=playbook(),
            log=decision_log(tmp_path),
            rworker=SequenceWorker([]),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="respec-cap",
        )
    assert "cap" in excinfo.value.message


def test_nonmapping_worker_result_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        _run(tmp_path, [["not", "a", "mapping"]])  # type: ignore[list-item]
    assert "not a mapping" in excinfo.value.message


def test_missing_fit_block_halts(tmp_path: Path) -> None:
    result = worker_result(_TWO_FOUR)
    result["fit"] = {"df": 24}
    result["mi"] = []
    with pytest.raises(IntegrityHalt) as excinfo:
        _run(tmp_path, [result])
    assert "fit" in excinfo.value.message
