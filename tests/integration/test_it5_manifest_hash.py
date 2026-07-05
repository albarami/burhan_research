"""REJECT (2nd) fix 3 / NFR-102: manifest hashes track their own source.

``hashes.study_config`` must be the sha256 of the study's own
``study_config.yaml`` bytes, and ``hashes.decision_policy`` must be the sha256 of
the ACTUAL ``Policy`` loaded for the run (``Policy.sha256``) — never the governed
template on disk, which an injected/monkeypatched policy would not match. Mutating
one source must move only its hash (02_REQUIREMENTS.md NFR-102). Real files and
real ``Policy`` objects throughout — no injected dummy hash strings.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from integration_study import integration_config
from it_util import fast_policy

from burhan.cli.certification import _manifest_fields
from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig

_RUN_ID = "20260705T000000Z"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_hashes_track_their_own_source_files(tmp_path: Path) -> None:
    cfg_text = yaml.safe_dump(integration_config(), sort_keys=True)
    cfg_path = tmp_path / "study_config.yaml"
    cfg_path.write_text(cfg_text, encoding="utf-8")
    config = validate_and_build(StudyConfig, yaml.safe_load(cfg_text))

    policy_a = fast_policy(tmp_path, replications=500)  # a real policy file
    base = _manifest_fields(
        config, _RUN_ID, study_config_sha=_sha(cfg_path), decision_policy_sha=policy_a.sha256
    )
    assert base["hashes"]["study_config"] == _sha(cfg_path)
    assert base["hashes"]["decision_policy"] == policy_a.sha256

    # (1) mutate ONLY the study config file -> only study_config moves
    cfg_path.write_text(cfg_text + "\n# one byte changed\n", encoding="utf-8")
    after_cfg = _manifest_fields(
        config, _RUN_ID, study_config_sha=_sha(cfg_path), decision_policy_sha=policy_a.sha256
    )
    assert after_cfg["hashes"]["study_config"] != base["hashes"]["study_config"]
    assert after_cfg["hashes"]["decision_policy"] == base["hashes"]["decision_policy"]

    # (2) mutate ONLY the policy (a different real policy file) -> only decision_policy moves
    policy_b = fast_policy(tmp_path, replications=700)  # different bytes -> different sha256
    assert policy_b.sha256 != policy_a.sha256
    after_pol = _manifest_fields(
        config, _RUN_ID, study_config_sha=_sha(cfg_path), decision_policy_sha=policy_b.sha256
    )
    assert after_pol["hashes"]["decision_policy"] != after_cfg["hashes"]["decision_policy"]
    assert after_pol["hashes"]["study_config"] == after_cfg["hashes"]["study_config"]
