"""AT-M10-2: α/CR/AVE, Fornell–Larcker, HTMT with PB bands (FR-703).

Reference values captured from the renv-locked semTools (2026-07-03) on
the deterministic fixtures in measurement_util (seeds pinned there):

- validity fixture: alpha FA=.840661 FB=.839848 · CR FA=.839933
  FB=.842417 · AVE FA=.568825 FB=.574735 · HTMT=.572821 ·
  latent corr=.580910
- trap fixture: AVE FA=.860654 FB=.842825 · latent corr=.878294
  (r² = .771 < both AVEs → Fornell–Larcker passes) · HTMT=.878476 →
  inside the governed PB-11 flag band (.85–.90) exactly.

Bands come from the playbook criteria (PB-09/10/11), never literals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from burhan.stats.measurement import measurement_bands, run_measurement
from measurement_util import trap_frame, two_construct_config, validity_frame

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy
from burhan.core.rworker import RWorker

REPO = Path(__file__).resolve().parents[3]

SEMTOOLS_VALIDITY = {
    "alpha": {"FA": 0.840661, "FB": 0.839848},
    "cr": {"FA": 0.839933, "FB": 0.842417},
    "ave": {"FA": 0.568825, "FB": 0.574735},
    "htmt": 0.572821,
}
SEMTOOLS_TRAP = {
    "ave": {"FA": 0.860654, "FB": 0.842825},
    "latent_corr": 0.878294,
    "htmt": 0.878476,
}


def _playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


def _config() -> StudyConfig:
    return validate_and_build(StudyConfig, two_construct_config())


def _run(frame: Any, tmp_path: Path, call_id: str) -> dict[str, Any]:
    return run_measurement(
        frame,
        _config(),
        policy=_policy(),
        playbook=_playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id=call_id,
    )


def test_bands_come_from_the_playbook() -> None:
    bands = measurement_bands(_playbook())
    assert bands["loading_target"] == 0.708
    assert bands["alpha_floor"] == 0.70
    assert bands["cr_floor"] == 0.70
    assert bands["ave_floor"] == 0.50
    assert bands["htmt_flag"] == 0.85
    assert bands["htmt_fail"] == 0.90
    assert bands["harman_share"] == 0.50


def test_validity_battery_matches_semtools_references(tmp_path: Path) -> None:  # AT-M10-2
    report = _run(validity_frame(), tmp_path, "val-battery")
    reliability = {e["construct"]: e for e in report["first_order"]["reliability"]}
    for construct in ("FA", "FB"):
        assert reliability[construct]["alpha"] == pytest.approx(
            SEMTOOLS_VALIDITY["alpha"][construct], abs=1e-4
        )
        assert reliability[construct]["cr"] == pytest.approx(
            SEMTOOLS_VALIDITY["cr"][construct], abs=1e-4
        )
        assert reliability[construct]["ave"] == pytest.approx(
            SEMTOOLS_VALIDITY["ave"][construct], abs=1e-4
        )
    htmt = report["validity"]["htmt"]["pairs"][0]
    assert htmt["value"] == pytest.approx(SEMTOOLS_VALIDITY["htmt"], abs=1e-4)
    assert htmt["band"] == "pass"
    assert report["validity"]["fornell_larcker"]["pass"] is True


def test_trap_passes_fornell_larcker_but_trips_htmt_flag(tmp_path: Path) -> None:
    # AT-M10-2: the engineered near-redundant pair (r² ≈ .77–.80).
    report = _run(trap_frame(), tmp_path, "val-trap")
    fl = report["validity"]["fornell_larcker"]
    assert fl["pass"] is True  # AVEs .861/.843 > r² .771
    pair = report["validity"]["htmt"]["pairs"][0]
    assert pair["value"] == pytest.approx(SEMTOOLS_TRAP["htmt"], abs=1e-4)
    assert pair["band"] == "flag"  # .85 < .8785 <= .90, exactly per PB-11
    assert "flag" in report["validity"]["htmt"]["verdict"]


def test_htmt_band_edges_follow_pb11_exactly() -> None:
    from burhan.stats.measurement import htmt_band

    bands = measurement_bands(_playbook())
    assert htmt_band(0.8499, bands=bands) == "pass"
    assert htmt_band(0.85, bands=bands) == "pass"  # rule: HTMT < 0.85 passes
    assert htmt_band(0.8501, bands=bands) == "flag"
    assert htmt_band(0.90, bands=bands) == "flag"  # 0.85–0.90 flagged
    assert htmt_band(0.9001, bands=bands) == "fail"  # > 0.90 fails


def test_loading_band_evaluation_per_pb09(tmp_path: Path) -> None:
    report = _run(validity_frame(), tmp_path, "val-loadings")
    for entry in report["first_order"]["loadings"]:
        assert "std" in entry and "p" in entry
        assert entry["band"] in {"target", "borderline", "deletion_candidate"}
    # fixture loadings ≈ .75 standardized: all at target
    assert all(e["band"] == "target" for e in report["first_order"]["loadings"])


def test_malformed_reliability_block_halts_typed(tmp_path: Path) -> None:
    class HollowWorker:
        @staticmethod
        def call(*args: object, **kwargs: object) -> dict[str, object]:
            return {
                "first_order": {"loadings": [], "reliability": "high"},
                "second_order": None,
                "fit": {"chisq": 1.0, "df": 1},
                "validity": {},
            }

    with pytest.raises(IntegrityHalt) as excinfo:
        run_measurement(
            validity_frame(),
            _config(),
            policy=_policy(),
            playbook=_playbook(),
            rworker=HollowWorker(),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="val-hollow",
        )
    assert "reliability" in excinfo.value.message
