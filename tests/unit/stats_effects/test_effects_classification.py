"""AT-M11-3: Zhao–Lynch–Chen classification (PB-17).

Five canned fixtures — complementary, competitive, indirect-only,
direct-only, no-effect — each classified correctly by the pure
classifier; every hypothesized indirect effect receives a
classification entry; one live end-to-end run proves the pipeline on
real bootstrap output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from effects_util import (
    effect_block,
    mediation_config,
    mediation_frame,
    playbook,
    policy_with,
)

from burhan.core.rworker import RWorker
from burhan.stats.effects import classify_effect, run_effects


@pytest.mark.parametrize(
    ("direct", "indirect", "expected"),
    [
        (effect_block(0.30, 0.15, 0.45), effect_block(0.35, 0.20, 0.50), "complementary"),
        (effect_block(-0.30, -0.45, -0.15), effect_block(0.35, 0.20, 0.50), "competitive"),
        (effect_block(0.05, -0.10, 0.20), effect_block(0.35, 0.20, 0.50), "indirect_only"),
        (effect_block(0.40, 0.20, 0.60), effect_block(0.01, -0.05, 0.08), "direct_only"),
        (effect_block(0.02, -0.10, 0.15), effect_block(0.01, -0.05, 0.08), "no_effect"),
    ],
    ids=["complementary", "competitive", "indirect_only", "direct_only", "no_effect"],
)
def test_five_way_classification(
    direct: dict[str, Any], indirect: dict[str, Any], expected: str
) -> None:
    assert classify_effect(direct, indirect) == expected


class _CannedWorker:
    def __init__(self, result: object) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def call(self, *args: object, **kwargs: object) -> object:
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        assert isinstance(payload, dict)
        self.calls.append(payload)
        return self._result


def _canned_result(resamples: int) -> dict[str, Any]:
    return {
        "bootstrap": {
            "resamples": resamples,
            "completed": resamples,
            "ci_level": 0.95,
            "ci_type": "bias_corrected",
        },
        "paths": [],
        "effects": [
            {
                "id": "H2",
                "direct": effect_block(0.30, 0.15, 0.45),
                "indirect": effect_block(0.35, 0.20, 0.50),
                "total": effect_block(0.65, 0.45, 0.85),
            }
        ],
        "sums": [],
    }


def test_every_hypothesized_indirect_receives_classification(tmp_path: Path) -> None:
    policy = policy_with(tmp_path, resamples=1000)
    report = run_effects(
        mediation_frame(),
        mediation_config(),
        policy=policy,
        playbook=playbook(),
        rworker=_CannedWorker(_canned_result(1000)),  # type: ignore[arg-type]
        run_dir=tmp_path,
        call_id="cls-canned",
    )
    (entry,) = report["effects"]
    assert entry["hypothesis"] == "H2"
    assert entry["classification"] == "complementary"
    assert entry["via"] == ["M"]


def test_live_complementary_end_to_end(tmp_path: Path) -> None:
    # Real bootstrap through the R worker on data generated with a
    # complementary population (a=.6, b=.6, c=.5).
    policy = policy_with(tmp_path, resamples=1000)
    report = run_effects(
        mediation_frame(),
        mediation_config(),
        policy=policy,
        playbook=playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id="cls-live",
    )
    (entry,) = report["effects"]
    assert entry["classification"] == "complementary"
    assert entry["direct"]["ci_low"] > 0
    assert entry["indirect"]["ci_low"] > 0
    assert report["bootstrap"]["resamples"] == 1000
    assert report["bootstrap"]["completed"] == 1000
