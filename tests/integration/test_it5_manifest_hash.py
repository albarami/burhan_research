"""REJECT fix 3: the run manifest must hash the study config, not the policy.

``_manifest_fields`` previously set ``hashes.study_config`` to the decision-policy
file hash — so mutating the study config never moved ``hashes.study_config``.
It must hash the actual ``study_config.yaml`` bytes used for the run, and remain
independent of the decision-policy hash.
"""

from __future__ import annotations

from integration_study import integration_config

from burhan.cli.certification import _manifest_fields
from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig


def test_manifest_study_config_hash_is_the_study_config_not_the_policy() -> None:
    config = validate_and_build(StudyConfig, integration_config())
    run_id = "20260705T000000Z"
    fields_a = _manifest_fields(config, run_id, study_config_sha="a" * 64)
    fields_b = _manifest_fields(config, run_id, study_config_sha="b" * 64)
    # study_config tracks the study-config bytes handed in (mutating it moves the hash) ...
    assert fields_a["hashes"]["study_config"] == "a" * 64
    assert fields_b["hashes"]["study_config"] == "b" * 64
    # ... while decision_policy is a different governing file, independent of it.
    assert fields_a["hashes"]["decision_policy"] == fields_b["hashes"]["decision_policy"]
    assert fields_a["hashes"]["study_config"] != fields_a["hashes"]["decision_policy"]
