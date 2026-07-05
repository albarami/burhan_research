"""REJECT fixes 5 & 2: the Typer CLI commands, exercised end to end.

Fix 5 — ``burhan run --certification <study>`` reaches ``COMPLETED`` through the
real Typer command (CliRunner against ``app``), not a direct ``certification_run``
call, proving the wired 13-stage registry drives the CLI and the old
empty-registry exit-10 path is gone.

Fix 2 — ``burhan rerun --certification <run>`` re-executes the sealed run and
exits 0, which the orchestrator grants only when every regenerated artifact is
byte-identical (NFR-101). This is the actual CLI path, whose default clock is no
longer an ambient wall clock: the rerun replays the source run's sealed base, so
provenance / results-store / compliance timestamps reproduce exactly.

A certification-speed policy (monkeypatched onto the CLI's default policy loader)
keeps both probes fast without exposing a policy flag on the command.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from integration_study import build_integration_study, integration_config, study_document
from it_util import fast_policy
from typer.testing import CliRunner

from burhan.cli import app

runner = CliRunner()

_ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_study_bundle(tmp_path: Path, *, n: int = 300) -> Path:
    study_dir = tmp_path / "study"
    (study_dir / "config").mkdir(parents=True)
    (study_dir / "inputs").mkdir()
    study = build_integration_study(20260705, n=n)
    (study_dir / "config" / "study_config.yaml").write_text(
        yaml.safe_dump(integration_config(), sort_keys=True), encoding="utf-8"
    )
    study.write(study_dir / "inputs")
    (study_dir / "inputs" / "study_document.txt").write_text(study_document(), encoding="utf-8")
    return study_dir


@pytest.fixture(autouse=True)
def _fast_default_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The CLI exposes no policy flag; certification uses ``_load_policy`` by
    # default. Point it at the schema-floor certification policy so the probes
    # run at IT speed. run and rerun both read it → identical policy values.
    monkeypatch.setattr("burhan.cli.certification._load_policy", lambda: fast_policy(tmp_path))


def test_run_command_reaches_completed_via_cli(tmp_path: Path) -> None:
    study_dir = _write_study_bundle(tmp_path)
    result = runner.invoke(app, ["run", "--certification", str(study_dir)])
    assert result.exit_code == 0, result.output
    assert "COMPLETED" in result.output
    # NFR-102: the manifest records the ACTUAL sources this run consumed — the
    # study's own config bytes and the loaded (monkeypatched fast) policy hash —
    # not the governed template that an injected policy would never match.
    run_dir = next(iter(sorted((study_dir / "runs").glob("*"))))
    hashes = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["hashes"]
    assert hashes["study_config"] == _sha(study_dir / "config" / "study_config.yaml")
    assert hashes["decision_policy"] == fast_policy(tmp_path).sha256
    assert hashes["decision_policy"] != _sha(_ROOT / "policy" / "decision_policy.template.yaml")


def test_rerun_command_is_byte_identical_via_cli(tmp_path: Path) -> None:
    study_dir = _write_study_bundle(tmp_path)
    run_result = runner.invoke(app, ["run", "--certification", str(study_dir)])
    assert run_result.exit_code == 0, run_result.output
    run_dir = next(iter(sorted((study_dir / "runs").glob("*"))))
    rerun_result = runner.invoke(app, ["rerun", "--certification", str(run_dir)])
    # exit 0 == COMPLETED == every regenerated artifact byte-identical (NFR-101);
    # a VerificationHalt on any drift would surface as a nonzero exit here.
    assert rerun_result.exit_code == 0, rerun_result.output
    assert "COMPLETED" in rerun_result.output
