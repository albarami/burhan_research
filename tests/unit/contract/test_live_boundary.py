"""AT-M16-4: raw survey data never reaches an LLM adapter on the live path.

The adapter allowlist admits only document/dictionary TEXT; a CSV — as a
data-file path string, raw bytes, or a dataframe — is rejected at the boundary
**before** any provider call (NFR-401). Proven with a real ``NodeA`` wired to a
recording provider whose ``inner`` fails the test if it is ever invoked. (The
end-to-end wiring guarantee — that the live run hands the CSV to
``validate_contract`` and never to an adapter — is asserted in the IT-7 suite.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from burhan.cli.certification import certification_settings
from burhan.contract.archive import recording_provider_call
from burhan.contract.node_a import NodeA
from burhan.core.errors import IntegrityHalt


def _node_a_provider_must_not_fire(tmp_path: Path) -> NodeA:
    def inner(_prompt: str) -> str:
        raise AssertionError("provider called: raw data reached the adapter (NFR-401 breach)")

    call = recording_provider_call(inner, tmp_path, "node_a")
    return NodeA(certification_settings(), provider_call=call)


def test_node_a_allowlist_excludes_any_raw_data_slot() -> None:
    assert NodeA.ALLOWED_INPUTS == ("study_document", "data_dictionary")


def test_csv_path_string_rejected_before_provider(tmp_path: Path) -> None:
    node = _node_a_provider_must_not_fire(tmp_path)
    with pytest.raises(IntegrityHalt):
        node.complete(study_document="/studies/dba/inputs/survey.csv")


def test_dataframe_rejected_before_provider(tmp_path: Path) -> None:
    import pandas as pd  # type: ignore[import-untyped]

    node = _node_a_provider_must_not_fire(tmp_path)
    with pytest.raises(IntegrityHalt):
        node.complete(study_document=pd.DataFrame({"score": [1, 2, 3]}))


def test_raw_bytes_rejected_before_provider(tmp_path: Path) -> None:
    node = _node_a_provider_must_not_fire(tmp_path)
    with pytest.raises(IntegrityHalt):
        node.complete(study_document=b"respondent,score\n1,5\n")
