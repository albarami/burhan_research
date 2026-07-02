"""Verdict schema strictness (FR-303; AT-M07-5 foundation).

The verdict contract is closed: ``verdict: approve|reject`` plus ``fixes``
(exact fixes, non-empty iff reject). Anything else is a schema-invalid
verdict — a pseudo-reject consuming a retry cycle, never a crash.
"""

from __future__ import annotations

import pytest
from review_util import approve_yaml, reject_yaml

from burhan.review.node_c import Verdict, parse_verdict


def test_valid_approve_parses() -> None:
    verdict = parse_verdict(approve_yaml())
    assert verdict == Verdict(verdict="approve", fixes=(), schema_invalid=False)


def test_valid_reject_parses_with_exact_fixes() -> None:
    verdict = parse_verdict(reject_yaml("fix A", "fix B"))
    assert verdict.verdict == "reject"
    assert verdict.fixes == ("fix A", "fix B")
    assert verdict.schema_invalid is False


@pytest.mark.parametrize(
    "response",
    [
        "Sure! Here's my verdict: {unbalanced: [",  # not YAML
        "- approve\n- reject\n",  # not a mapping
        "verdict: maybe\nfixes: []\n",  # unknown verdict value
        "verdict: approve\nfixes: []\nconfidence: high\n",  # extra key
        "verdict: approve\n",  # missing fixes key
        "fixes: []\n",  # missing verdict key
        "verdict: reject\nfixes: not-a-list\n",  # fixes not a list
        "verdict: reject\nfixes: [3]\n",  # fix not a string
        "verdict: reject\nfixes: ['']\n",  # empty fix string
        "verdict: approve\nfixes: ['tighten X']\n",  # approve carrying fixes
        "verdict: reject\nfixes: []\n",  # reject without exact fixes
    ],
)
def test_schema_invalid_verdicts_become_pseudo_rejects(response: str) -> None:  # AT-M07-5
    verdict = parse_verdict(response)
    assert verdict.schema_invalid is True
    assert verdict.verdict == "reject"
    assert len(verdict.fixes) == 1
    assert "verdict schema violation" in verdict.fixes[0]
