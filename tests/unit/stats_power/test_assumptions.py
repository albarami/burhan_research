"""Distributional and collinearity diagnostics (AT-M09-3; FR-601; PB-05/06).

Known-answer anchor, with provenance: Mardia's test on the iris setosa
subset (n=50, four variables) — published in Korkmaz, Göksülük & Zararsız
(2014), "MVN: An R Package for Assessing Multivariate Normality", The R
Journal 6(2):151–162: skewness b1p = 3.0797 (p = 0.1772), kurtosis
b2p = 26.5377 (p = 0.1953). The fixture at
tests/fixtures/known_answers/iris_setosa.csv is R's datasets::iris setosa
block written verbatim. Univariate bands come from the governed playbook
criterion (PB-05: "2 / 7"), never from code literals.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from burhan.core.errors import IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy
from burhan.stats.assumptions import (
    assumptions_store_rows,
    mahalanobis_feed,
    mardia,
    univariate_moments,
    vif_composites,
)

REPO = Path(__file__).resolve().parents[3]
SETOSA = REPO / "tests" / "fixtures" / "known_answers" / "iris_setosa.csv"


def _setosa() -> pd.DataFrame:
    return pd.read_csv(SETOSA)


def _playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


# -- AT-M09-3: Mardia against the published MVN reference ------------------------------


def test_mardia_reproduces_published_setosa_values() -> None:  # AT-M09-3
    result = mardia(_setosa())
    assert result["b1p"] == pytest.approx(3.0797, abs=5e-5)
    assert result["skew_statistic"] == pytest.approx(25.6643, abs=5e-4)
    assert result["skew_p"] == pytest.approx(0.1772, abs=5e-5)
    assert result["b2p"] == pytest.approx(26.5377, abs=5e-5)
    assert result["kurtosis_z"] == pytest.approx(1.2950, abs=5e-5)
    assert result["kurtosis_p"] == pytest.approx(0.1953, abs=5e-5)
    assert result["n"] == 50
    assert result["p"] == 4


def test_mardia_guards_halt_typed() -> None:
    tiny = _setosa().head(3)  # n <= p: covariance singular by construction
    with pytest.raises(IntegrityHalt):
        mardia(tiny)
    with pytest.raises(IntegrityHalt):
        mardia(_setosa().head(0))


def test_univariate_moments_match_hand_computation() -> None:
    frame = pd.DataFrame({"x": [1.0, 2.0, 2.0, 3.0, 7.0]})
    moments = univariate_moments(frame, playbook=_playbook())
    x = np.array([1.0, 2.0, 2.0, 3.0, 7.0])
    c = x - x.mean()
    m2 = float((c**2).mean())
    expected_skew = float((c**3).mean()) / m2**1.5
    expected_kurt = float((c**4).mean()) / m2**2 - 3.0
    entry = moments["items"][0]
    assert entry["item"] == "x"
    assert entry["skewness"] == pytest.approx(expected_skew, abs=1e-12)
    assert entry["kurtosis"] == pytest.approx(expected_kurt, abs=1e-12)
    assert moments["skew_limit"] == 2.0  # PB-05 "2 / 7" — from the playbook
    assert moments["kurtosis_limit"] == 7.0


def test_univariate_bands_flag_violations_per_playbook() -> None:
    rng = np.random.default_rng(4)
    frame = pd.DataFrame(
        {
            "ok": rng.normal(4, 1, 300),
            "skewed": np.exp(rng.normal(0, 1.2, 300)),  # |skew| >> 2
        }
    )
    moments = univariate_moments(frame, playbook=_playbook())
    by_item = {e["item"]: e for e in moments["items"]}
    assert by_item["ok"]["within_bands"] is True
    assert by_item["skewed"]["within_bands"] is False


# -- PB-06: collinearity ---------------------------------------------------------------


def test_vif_matches_the_exact_two_predictor_identity() -> None:
    rng = np.random.default_rng(9)
    a = rng.normal(0, 1, 4000)
    b = 0.8 * a + rng.normal(0, np.sqrt(1 - 0.64), 4000)
    frame = pd.DataFrame({"A": a, "B": b})
    result = vif_composites(frame)
    r_squared = float(np.corrcoef(a, b)[0, 1] ** 2)
    expected = 1.0 / (1.0 - r_squared)
    by_name = {e["composite"]: e["vif"] for e in result["composites"]}
    assert by_name["A"] == pytest.approx(expected, rel=1e-9)
    assert by_name["B"] == pytest.approx(expected, rel=1e-9)


def test_vif_requires_at_least_two_composites() -> None:
    with pytest.raises(IntegrityHalt):
        vif_composites(pd.DataFrame({"only": [1.0, 2.0, 3.0]}))


# -- FR-601: Mahalanobis feed at the policy criterion ----------------------------------


def test_mahalanobis_feed_flags_at_policy_criterion() -> None:
    rng = np.random.default_rng(6)
    base = rng.normal(0, 1, (60, 3))
    base[0] = [9.0, -9.0, 9.0]  # far outside the cloud
    frame = pd.DataFrame(base, columns=["a", "b", "c"])
    frame.index = pd.Index([f"R_{i:03d}" for i in range(1, 61)], name="case")
    feed = mahalanobis_feed(frame, policy=_policy())
    assert feed["criterion_p"] == 0.001  # policy prep.outliers.mahalanobis_p
    assert "R_001" in feed["flagged_cases"]
    assert len(feed["d2"]) == 60
    assert all(not math.isnan(v) for v in feed["d2"].values())


# -- store rows under assumptions.* ------------------------------------------------------


def test_assumptions_store_rows_land_under_assumptions_ids() -> None:  # AT-M09-3
    from jsonschema import Draft202012Validator

    schema = json.loads((REPO / "schemas" / "results_store.schema.json").read_text())
    validator = Draft202012Validator(schema)
    rows = assumptions_store_rows(_setosa(), playbook=_playbook(), created="2026-07-03T09:00:00Z")
    ids = [row["id"] for row in rows]
    assert "assumptions.normality.mardia_skew_p" in ids
    assert "assumptions.normality.mardia_kurtosis_p" in ids
    for row in rows:
        validator.validate(row)
        assert row["id"].startswith("assumptions.")
        assert row["stage"] == "assumptions"
        assert row["engine"] == "py_pandas"
