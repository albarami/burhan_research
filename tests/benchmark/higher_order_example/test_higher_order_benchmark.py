"""AT-M10-1: the published higher-order worked example (FR-701/702/1502).

Anchor: Mplus User's Guide ex5.6 (see PROVENANCE.md) — data committed
verbatim, reference values quoted from the publisher-hosted output. The
repeated-indicator fit must reproduce every printed value to printed
precision; the two-stage approach must produce both-level reporting on
the same data; a report missing either level halts typed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy
from burhan.core.rworker import RWorker
from burhan.stats.measurement import run_measurement

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

# Printed Mplus reference values (PROVENANCE.md; statmodel.com ex5.6 output)
PUBLISHED_FIRST_ORDER = {
    ("F1", "y2"): 0.760,
    ("F1", "y3"): 0.669,
    ("F2", "y5"): 0.718,
    ("F2", "y6"): 0.703,
    ("F3", "y8"): 0.702,
    ("F3", "y9"): 0.691,
    ("F4", "y11"): 0.742,
    ("F4", "y12"): 0.669,
}
PUBLISHED_SECOND_ORDER = {("F5", "F2"): 0.944, ("F5", "F3"): 1.168, ("F5", "F4"): 0.854}
PUBLISHED_CHISQ = 46.743
PUBLISHED_DF = 50

# Reliability reference values (PROVENANCE.md): renv-locked semTools 0.5-8 /
# lavaan 0.6-21 on the same fits the worker computes — compRelSEM (CR),
# compRelSEM(tau.eq = TRUE) (alpha) and AVE on the correlated first-order
# CFA; reliabilityL2 omegaL1/omegaL2 on the second-order fit. Captured
# 2026-07-03; tolerance 1e-4 (matches the AT-M10-2 parity tolerance).
SEMTOOLS_FIRST_ORDER_RELIABILITY = {
    "F1": {"alpha": 0.885217, "cr": 0.898142, "ave": 0.752108},
    "F2": {"alpha": 0.885369, "cr": 0.898198, "ave": 0.751544},
    "F3": {"alpha": 0.903026, "cr": 0.917772, "ave": 0.793400},
    "F4": {"alpha": 0.890386, "cr": 0.904605, "ave": 0.764981},
}
SEMTOOLS_SECOND_ORDER_RELIABILITY = {"omega_l1": 0.604452, "cr_l2": 0.637787}
RELIABILITY_TOLERANCE = 1e-4


def _frame() -> pd.DataFrame:
    frame = pd.read_csv(
        HERE / "ex5.6.dat", sep=r"\s+", header=None, names=[f"y{i}" for i in range(1, 13)]
    )
    frame.index = pd.Index([f"R_{i:04d}" for i in range(1, len(frame) + 1)], name="case")
    return frame


def _config(approach: str) -> StudyConfig:
    items = [
        {
            "code": f"y{i}",
            "text": f"y{i} indicator.",
            "construct_ref": f"F{(i - 1) // 3 + 1}",
            "scale": {"type": "numeric", "min": -10, "max": 10},
            "reverse_coded": False,
            "column_hint": f"Q_y{i}",
        }
        for i in range(1, 13)
    ]
    constructs: list[dict[str, Any]] = [
        {
            "code": f"F{k}",
            "name": f"Factor {k}",
            "level": "first_order",
            "measurement": "reflective",
            "indicators": [f"y{(k - 1) * 3 + j}" for j in (1, 2, 3)],
        }
        for k in (1, 2, 3, 4)
    ]
    constructs.append(
        {
            "code": "F5",
            "name": "General factor",
            "level": "second_order",
            "measurement": "reflective",
            "components": ["F1", "F2", "F3", "F4"],
        }
    )
    data = {
        "schema_version": 1,
        "meta": {
            "study_id": "mplus-ex56-benchmark",
            "title": "Mplus UG ex5.6 second-order benchmark",
            "source_documents": [
                {"role": "study_document", "path": "inputs/ex56.docx", "sha256": "e" * 64}
            ],
        },
        "methodology": {
            "declared": "CB_SEM",
            "playbook_id": "CB_SEM_PLAYBOOK",
            "playbook_version": "1.0",
            "design": "cross_sectional",
        },
        "instrument": {"items": items},
        "constructs": constructs,
        "higher_order": {"approach": approach, "structural_carry": "full_hierarchy"},
        "model": {"exogenous": ["F5"], "endogenous": ["F1"]},
        "hypotheses": [
            {"id": "H1", "effect": "direct", "from": "F1", "to": "F2", "sign": "positive"}
        ],
        "data": {"file": "inputs/ex56.csv", "format": "csv"},
    }
    return validate_and_build(StudyConfig, data)


def _run(approach: str, tmp_path: Path, call_id: str) -> dict[str, Any]:
    return run_measurement(
        _frame(),
        _config(approach),
        policy=Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification"),
        playbook=Playbook.load(
            REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification"
        ),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id=call_id,
    )


def test_repeated_indicator_reproduces_published_anchors(tmp_path: Path) -> None:  # AT-M10-1
    report = _run("repeated_indicator", tmp_path, "bench-ri")
    assert report["approach"] == "repeated_indicator"
    first = {
        (entry["construct"], entry["item"]): entry["est"]
        for entry in report["first_order"]["loadings"]
    }
    for key, published in PUBLISHED_FIRST_ORDER.items():
        assert round(first[key], 3) == published, key
    second = {
        (entry["construct"], entry["component"]): entry["est"]
        for entry in report["second_order"]["loadings"]
    }
    for key, published in PUBLISHED_SECOND_ORDER.items():
        assert round(second[key], 3) == published, key
    assert round(report["fit"]["chisq"], 3) == PUBLISHED_CHISQ
    assert report["fit"]["df"] == PUBLISHED_DF


def test_repeated_indicator_reports_reliability_at_both_levels(tmp_path: Path) -> None:
    # AT-M10-1: both-level reporting (FR-702), every value pinned to the
    # renv-locked semTools reference implementation within tolerance
    # (constants above; capture record in PROVENANCE.md).
    report = _run("repeated_indicator", tmp_path, "bench-ri-rel")
    first = {entry["construct"]: entry for entry in report["first_order"]["reliability"]}
    assert set(first) == set(SEMTOOLS_FIRST_ORDER_RELIABILITY)
    for construct, expected in SEMTOOLS_FIRST_ORDER_RELIABILITY.items():
        for key, reference in expected.items():
            assert first[construct][key] == pytest.approx(reference, abs=RELIABILITY_TOLERANCE), (
                construct,
                key,
            )
    second = report["second_order"]["reliability"]
    assert second["construct"] == "F5"
    assert second["cr_l2"] == pytest.approx(
        SEMTOOLS_SECOND_ORDER_RELIABILITY["cr_l2"], abs=RELIABILITY_TOLERANCE
    )
    assert second["omega_l1"] == pytest.approx(
        SEMTOOLS_SECOND_ORDER_RELIABILITY["omega_l1"], abs=RELIABILITY_TOLERANCE
    )


def test_two_stage_reports_both_levels_on_the_same_data(tmp_path: Path) -> None:  # AT-M10-1
    report = _run("two_stage", tmp_path, "bench-ts")
    assert report["approach"] == "two_stage"
    # stage 1 is the correlated first-order CFA: full loading set present
    first = report["first_order"]["loadings"]
    assert {(e["construct"], e["item"]) for e in first} == {
        (f"F{(i - 1) // 3 + 1}", f"y{i}") for i in range(1, 13)
    }
    # stage 2 regresses the second-order factor on stage-1 factor scores
    second = report["second_order"]["loadings"]
    assert {(e["construct"], e["component"]) for e in second} == {
        ("F5", "F1"),
        ("F5", "F2"),
        ("F5", "F3"),
        ("F5", "F4"),
    }
    assert all(entry["est"] > 0 for entry in second)
    assert report["second_order"]["stage"] == 2


def test_missing_second_order_level_halts_typed(tmp_path: Path) -> None:  # AT-M10-1
    class HollowWorker:
        @staticmethod
        def call(*args: object, **kwargs: object) -> dict[str, object]:
            return {"first_order": {"loadings": [], "reliability": []}, "fit": {}}

    with pytest.raises(IntegrityHalt) as excinfo:
        run_measurement(
            _frame(),
            _config("repeated_indicator"),
            policy=Policy.load(
                REPO / "policy" / "decision_policy.template.yaml", mode="certification"
            ),
            playbook=Playbook.load(
                REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification"
            ),
            rworker=HollowWorker(),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="bench-hollow",
        )
    assert "second_order" in excinfo.value.message


def test_missing_first_order_level_halts_typed(tmp_path: Path) -> None:  # AT-M10-1
    class HollowWorker:
        @staticmethod
        def call(*args: object, **kwargs: object) -> dict[str, object]:
            return {"second_order": {"loadings": [], "reliability": {}}, "fit": {}}

    with pytest.raises(IntegrityHalt) as excinfo:
        run_measurement(
            _frame(),
            _config("repeated_indicator"),
            policy=Policy.load(
                REPO / "policy" / "decision_policy.template.yaml", mode="certification"
            ),
            playbook=Playbook.load(
                REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification"
            ),
            rworker=HollowWorker(),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="bench-hollow-2",
        )
    assert "first_order" in excinfo.value.message
