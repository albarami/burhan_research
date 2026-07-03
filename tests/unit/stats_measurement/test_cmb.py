"""AT-M10-3: common method bias — screen plus substantive test (FR-704).

Harman's single-factor share is a SCREEN only: a passing Harman alone can
never mark PB-12 complete; the CLF/marker comparison is the substantive
test. The injected-method fixture (method loadings ≈ .75 dominating
construct loadings ≈ .45) must be flagged by the CLF comparison; the
clean twin must not. The step's single governed quantitative bound (0.50,
PB-12 harman_screen, Podsakoff 2003) is the share line for both the
screen and the substantive common-variance share; loading distortions
are reported as evidence (PB-12 defines no distortion bound).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from measurement_util import cmb_frame, two_construct_config

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy
from burhan.core.rworker import RWorker
from burhan.stats.measurement import evaluate_cmb, run_cmb

REPO = Path(__file__).resolve().parents[3]


def _playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


def _config() -> StudyConfig:
    return validate_and_build(StudyConfig, two_construct_config())


def _run_cmb(with_method: bool, tmp_path: Path, call_id: str) -> dict[str, Any]:
    return run_cmb(
        cmb_frame(with_method=with_method),
        _config(),
        policy=_policy(),
        playbook=_playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id=call_id,
        marker_items=["M1", "M2"],  # method-only markers anchor the CLF
    )


def test_injected_method_variance_is_flagged_by_clf(tmp_path: Path) -> None:  # AT-M10-3
    report = _run_cmb(True, tmp_path, "cmb-injected")
    assert report["clf"]["method_variance_share"] > report["bands"]["harman_share"]
    assert report["flagged"] is True
    assert report["complete"] is True  # both criteria evaluated — with a flag
    assert "clf" in report["evidence_basis"]


def test_clean_twin_is_not_flagged(tmp_path: Path) -> None:  # AT-M10-3
    report = _run_cmb(False, tmp_path, "cmb-clean")
    assert report["clf"]["method_variance_share"] < report["bands"]["harman_share"]
    assert report["flagged"] is False
    assert report["complete"] is True


def test_harman_alone_never_marks_pb12_complete() -> None:  # AT-M10-3
    # Structural rule, independent of any dataset: an evaluation carrying
    # only the Harman screen — however clean — is incomplete (PB-12 has a
    # substantive criterion; the screen cannot satisfy it).
    evaluation = evaluate_cmb(
        {"harman": {"single_factor_share": 0.31}},
        playbook=_playbook(),
    )
    assert evaluation["complete"] is False
    assert evaluation["harman"]["passes_screen"] is True
    assert "substantive" in evaluation["incomplete_reason"]


def test_harman_failure_is_screen_information_not_completion(tmp_path: Path) -> None:
    evaluation = evaluate_cmb(
        {"harman": {"single_factor_share": 0.62}},
        playbook=_playbook(),
    )
    assert evaluation["complete"] is False
    assert evaluation["harman"]["passes_screen"] is False


def test_malformed_cmb_block_halts_typed() -> None:  # AT-M10-3
    with pytest.raises(IntegrityHalt) as excinfo:
        evaluate_cmb({"harman": {"single_factor_share": "most"}}, playbook=_playbook())
    assert "harman" in excinfo.value.message
    with pytest.raises(IntegrityHalt) as excinfo:
        evaluate_cmb({}, playbook=_playbook())
    assert "harman" in excinfo.value.message
    with pytest.raises(IntegrityHalt) as excinfo:
        evaluate_cmb(
            {"harman": {"single_factor_share": 0.4}, "clf": {"method_variance_share": None}},
            playbook=_playbook(),
        )
    assert "clf" in excinfo.value.message


def test_missing_worker_cmb_block_halts_typed(tmp_path: Path) -> None:  # AT-M10-3
    class HollowWorker:
        @staticmethod
        def call(*args: object, **kwargs: object) -> dict[str, object]:
            return {"harman": {"single_factor_share": 0.3}}  # no clf block

    with pytest.raises(IntegrityHalt) as excinfo:
        run_cmb(
            cmb_frame(with_method=False),
            _config(),
            policy=_policy(),
            playbook=_playbook(),
            rworker=HollowWorker(),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="cmb-hollow",
            marker_items=["M1", "M2"],
        )
    assert "clf" in excinfo.value.message


def test_missing_marker_columns_halt_typed(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        run_cmb(
            cmb_frame(with_method=False),
            _config(),
            policy=_policy(),
            playbook=_playbook(),
            rworker=RWorker(),
            run_dir=tmp_path,
            call_id="cmb-nomarker",
            marker_items=["GHOST_MARKER"],
        )
    assert "marker" in excinfo.value.message
