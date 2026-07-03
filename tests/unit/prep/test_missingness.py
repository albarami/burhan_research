"""Missingness mechanism and treatment selection (AT-M08-7; FR-503/504).

Little's MCAR test and the pattern map are computed before any treatment
choice; treatment comes from policy, never from code. The MNAR-engineered
fixture rejects MCAR and flags with the policy's sensitivity note; MCAR
cannot be *confirmed* — only not rejected.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from generator import build_missingness_fixture

from burhan.core.policy import Policy
from burhan.prep.py_impl.missingness import littles_mcar, missingness_report

REPO = Path(__file__).resolve().parents[3]
_ITEM_CODES = [
    "RS1",
    "RS2",
    "RS3",
    "RS4",
    "CU1",
    "CU2",
    "CU3",
    "CU4",
    "IN1",
    "IN2",
    "IN3",
    "IN4",
]


def _policy() -> Policy:
    template = REPO / "policy" / "decision_policy.template.yaml"
    return Policy.load(template, mode="certification")


def _frame(kind: str, seed: int = 7) -> pd.DataFrame:
    fixture = build_missingness_fixture(kind, seed)  # type: ignore[arg-type]
    data = fixture.rows[3:]
    values = [
        [float(row[column]) if row[column] != "" else np.nan for column in range(2, 14)]
        for row in data
    ]
    index = pd.Index([row[0] for row in data], name="case")
    return pd.DataFrame(values, index=index, columns=_ITEM_CODES)


def test_littles_test_on_complete_data_is_degenerate_pass() -> None:
    frame = _frame("mcar").dropna()
    d2, df, p = littles_mcar(frame)
    assert d2 == 0.0
    assert df == 0
    assert p == 1.0


def test_mcar_fixture_is_not_rejected_and_selects_fiml() -> None:  # AT-M08-7
    report = missingness_report(_frame("mcar"), _policy())
    assert report["little_mcar"]["p"] > 0.05
    assert report["mechanism_verdict"] == "mcar_not_rejected"
    assert report["treatment"]["method"] == "fiml"
    assert report["treatment"]["mnar_flag"] is False
    assert "sensitivity_note" not in report["treatment"]


def test_policy_alternative_selects_multiple_imputation() -> None:  # AT-M08-7
    # The governed schema pins primary=fiml and alternative=multiple_imputation
    # (FR-504); selecting the alternative reads its method and parameters from
    # policy paths — nothing is hard-coded in the pipeline.
    report = missingness_report(_frame("mcar"), _policy(), select="alternative")
    assert report["treatment"]["method"] == "multiple_imputation"
    assert report["treatment"]["params"] == {"imputations": 20, "pooling": "rubin_rules"}


def test_mnar_fixture_rejects_mcar_and_flags_with_sensitivity_note() -> None:  # AT-M08-7
    report = missingness_report(_frame("mnar"), _policy())
    assert report["little_mcar"]["p"] < 0.05
    assert report["mechanism_verdict"] == "mcar_rejected"
    assert report["treatment"]["method"] == "fiml"  # MAR-appropriate primary stands
    assert report["treatment"]["mnar_flag"] is True
    assert "MNAR cannot be excluded" in report["treatment"]["sensitivity_note"]


def test_pattern_map_precedes_treatment_and_counts_every_case() -> None:  # FR-503
    frame = _frame("mcar")
    report = missingness_report(frame, _policy())
    patterns = report["pattern_map"]
    assert sum(entry["n"] for entry in patterns) == len(frame)
    complete = next(entry for entry in patterns if entry["missing_items"] == [])
    assert complete["n"] == int(frame.notna().all(axis=1).sum())
    # mechanism evidence precedes the treatment key in the artifact itself
    keys = list(report)
    assert keys.index("little_mcar") < keys.index("treatment")
    assert keys.index("pattern_map") < keys.index("treatment")


def test_report_is_deterministic_and_value_free() -> None:
    frame = _frame("mcar")
    policy = _policy()
    a = missingness_report(frame, policy)
    assert a == missingness_report(frame, policy)
    text = str(a)
    for stored_value in ("4.0", "5.0", "3.0"):
        assert f"'{stored_value}'" not in text  # counts and ids only


def test_unknown_primary_treatment_halts() -> None:
    from burhan.core.errors import IntegrityHalt

    frame = _frame("mcar")

    class FakePolicy:
        @staticmethod
        def rule(path: str) -> object:
            return {"prep.missing_treatment.primary": "mean_substitution"}.get(path, "x")

    # Even a doctored policy object cannot smuggle mean substitution through
    # the treatment selector (FR-505 defense in depth).
    with pytest.raises(IntegrityHalt) as excinfo:
        missingness_report(frame, FakePolicy())  # type: ignore[arg-type]
    assert "treatment" in excinfo.value.message
