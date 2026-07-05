"""REJECT fix 4: PB-12 (CMB) and PB-14 (respecification) are data-conditioned.

The measurement adapter must CALL the certified CMB / respecification entry
points when the study supports them — a method marker is declared (CMB) / the
model fit is inadequate (respecification) — serialize ``measurement.cmb`` /
``measurement.respecification`` evidence, and mark the step ``completed``. It
flags only the genuine not-applicable case (no marker / adequate fit), and it
never *calls-then-catches*: the certified module is invoked only when the data
supports it, so no ``IntegrityHalt`` is swallowed. Workers are canned spies
(the module fits are already certified in their own suites).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deletion_util import (
    SequenceWorker,
    decision_log,
    frame_for,
    policy_with,
    study_config,
    worker_result,
)
from deletion_util import playbook as del_playbook
from stages_util import stage_context

from burhan.core.compliance import Compliance
from burhan.core.orchestrator import StageContext
from burhan.stages import context
from burhan.stages.stage_1a import assess_cmb, assess_respecification

_ITEMS = {"FA": ["A1", "A2", "A3", "A4"], "FB": ["B1", "B2", "B3", "B4"]}
_ADEQUATE = {"cfi": 0.99, "tli": 0.98, "rmsea": 0.02, "srmr": 0.03, "chisq": 20.0, "df": 24}
_INADEQUATE = {"cfi": 0.70, "tli": 0.66, "rmsea": 0.20, "srmr": 0.15, "chisq": 300.0, "df": 24}


def _codes() -> list[str]:
    return [code for items in _ITEMS.values() for code in items]


def _cmb_result() -> dict[str, Any]:
    return {
        "harman": {"single_factor_share": 0.30},
        "clf": {"method_variance_share": 0.15, "loading_distortions": []},
    }


def _mi_result(fit_chisq: float, mi: list[dict[str, Any]]) -> dict[str, Any]:
    result = worker_result(_ITEMS, fit_chisq=fit_chisq)
    result["mi"] = mi
    return result


def _ctx_tracker(run_dir: Path) -> tuple[StageContext, Compliance]:
    ctx = stage_context(run_dir, stage="measurement")
    return ctx, context.compliance(ctx, del_playbook())


# -- PB-12 (CMB) -------------------------------------------------------------


def test_cmb_completes_with_serialized_evidence_when_markers_declared(tmp_path: Path) -> None:
    ctx, tracker = _ctx_tracker(tmp_path / "run")
    worker = SequenceWorker([_cmb_result()])
    row = assess_cmb(
        ctx,
        tracker,
        frame=frame_for([*_codes(), "M1"]),
        config=study_config(_ITEMS),
        policy=policy_with(False, tmp_path),
        playbook=del_playbook(),
        rworker=worker,  # type: ignore[arg-type]
        marker_items=["M1"],
    )
    assert row["status"] == "completed"
    assert list(ctx.store.iter("measurement.cmb"))
    assert worker.calls  # the certified CMB module WAS called


def test_cmb_flags_without_calling_when_no_marker_declared(tmp_path: Path) -> None:
    ctx, tracker = _ctx_tracker(tmp_path / "run")
    worker = SequenceWorker([])
    row = assess_cmb(
        ctx,
        tracker,
        frame=frame_for(_codes()),
        config=study_config(_ITEMS),
        policy=policy_with(False, tmp_path),
        playbook=del_playbook(),
        rworker=worker,  # type: ignore[arg-type]
        marker_items=[],
    )
    assert row["status"] == "flagged"
    assert not list(ctx.store.iter("measurement.cmb"))
    assert worker.calls == []  # genuine not-applicable: never called, nothing caught


# -- PB-14 (respecification) -------------------------------------------------


def test_respecification_completes_with_evidence_when_fit_inadequate(tmp_path: Path) -> None:
    ctx, tracker = _ctx_tracker(tmp_path / "run")
    worker = SequenceWorker(
        [
            _mi_result(300.0, [{"lhs": "A1", "rhs": "A2", "mi": 40.0, "epc": 0.10}]),
            _mi_result(120.0, []),
        ]
    )
    row = assess_respecification(
        ctx,
        tracker,
        frame=frame_for(_codes()),
        config=study_config(_ITEMS),
        policy=policy_with(False, tmp_path),
        playbook=del_playbook(),
        log=decision_log(tmp_path),
        rworker=worker,  # type: ignore[arg-type]
        fit=_INADEQUATE,
    )
    assert row["status"] == "completed"
    assert list(ctx.store.iter("measurement.respecification"))
    assert worker.calls  # the certified respecification module WAS called


def test_respecification_flags_without_calling_when_fit_adequate(tmp_path: Path) -> None:
    ctx, tracker = _ctx_tracker(tmp_path / "run")
    worker = SequenceWorker([])
    row = assess_respecification(
        ctx,
        tracker,
        frame=frame_for(_codes()),
        config=study_config(_ITEMS),
        policy=policy_with(False, tmp_path),
        playbook=del_playbook(),
        log=decision_log(tmp_path),
        rworker=worker,  # type: ignore[arg-type]
        fit=_ADEQUATE,
    )
    assert row["status"] == "flagged"
    assert not list(ctx.store.iter("measurement.respecification"))
    assert worker.calls == []  # adequate fit: no modification indicated, never called
