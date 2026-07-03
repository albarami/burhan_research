"""AT-M11-5: structural_carrier demonstrably changes the model (FR-803).

Both carriers run live against the same data and contract shape; the
fitted models must be distinguishable (different syntax, different
degrees of freedom, different fit), and each report records the
declared carrier with its rationale and citation.
"""

from __future__ import annotations

from pathlib import Path

from structural_util import carry_config, carry_frame, playbook

from burhan.core.rworker import RWorker
from burhan.stats.structural import run_structural


def _run(carry: str, tmp_path: Path) -> dict:
    return run_structural(
        carry_frame(),
        carry_config(carry),
        playbook=playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id=f"carry-{carry}",
    )


def test_carriers_produce_distinguishable_fitted_models(tmp_path: Path) -> None:
    full = _run("full_hierarchy", tmp_path)
    scores = _run("latent_scores", tmp_path)
    # different model structure ...
    assert full["model"]["syntax"] != scores["model"]["syntax"]
    assert "F5 =~" in full["model"]["syntax"]
    assert "F5 =~" not in scores["model"]["syntax"]
    assert full["fit"]["df"] != scores["fit"]["df"]
    assert full["model"]["nfree"] != scores["model"]["nfree"]
    # ... and different estimates on the same data
    assert full["fit"]["chisq"] != scores["fit"]["chisq"]
    (full_path,) = full["paths"]
    (scores_path,) = scores["paths"]
    assert (full_path["lhs"], full_path["rhs"]) == ("OUT", "F5")
    assert (scores_path["lhs"], scores_path["rhs"]) == ("OUT", "F5")
    assert full_path["est"] != scores_path["est"]


def test_carrier_recorded_with_rationale(tmp_path: Path) -> None:
    for carry in ("full_hierarchy", "latent_scores"):
        carrier = _run(carry, tmp_path)["carrier"]
        assert carrier["value"] == carry
        assert carrier["approach"] == "repeated_indicator"
        assert "structural_carry" in carrier["rationale"]
        assert carry in carrier["rationale"]
        assert carrier["citation"] == "Sarstedt et al. (2019)"


def test_worker_echoes_the_requested_carrier(tmp_path: Path) -> None:
    # The engine validates the worker fitted the carrier it was asked to
    # fit — the report's carrier and the fitted model must correspond.
    scores = _run("latent_scores", tmp_path)
    assert scores["carrier"]["value"] == "latent_scores"
    # score-space path model: OUT regressed on the F5 score column
    assert "OUT ~ F5" in scores["model"]["syntax"]
