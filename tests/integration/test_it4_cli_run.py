"""AT-M15-4: ``burhan run`` reaches COMPLETED (the certification run pathway).

An independent probe: a well-formed study bundle (config + inputs) runs through
``certification_run`` — the exact pathway ``burhan run --certification`` drives —
to terminal ``COMPLETED``, so the CLI no longer refuses (exit 10) with the DAG
wired. A certification-speed policy keeps the probe fast.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from integration_study import build_integration_study, integration_config, study_document
from it_util import fast_policy
from orch_util import TickingClock

from burhan.cli.certification import certification_run


def _write_study_bundle(tmp_path: Path, *, n: int = 300) -> Path:
    study_dir = tmp_path / "study"
    (study_dir / "config").mkdir(parents=True)
    (study_dir / "inputs").mkdir()
    study = build_integration_study(20260705, n=n)
    (study_dir / "config" / "study_config.yaml").write_text(
        yaml.safe_dump(integration_config(), sort_keys=True), encoding="utf-8"
    )
    study.write(study_dir / "inputs")  # study/inputs/golden.csv
    (study_dir / "inputs" / "study_document.txt").write_text(study_document(), encoding="utf-8")
    return study_dir


def test_certification_run_reaches_completed(tmp_path: Path) -> None:
    study_dir = _write_study_bundle(tmp_path)
    result = certification_run(study_dir, clock=TickingClock(), policy=fast_policy(tmp_path))
    assert result.state == "COMPLETED"
    assert result.run_dir.parent == study_dir / "runs"
    assert (result.run_dir / "METHOD_COMPLIANCE_CHECKLIST.md").exists()
