"""Doctor tests (AT-M04-6; 04_ENVIRONMENT_AND_STACK §9).

Every check is injectable so each violation is simulated exactly; doctor
passes only on the reference setup, and manifest environment fields carry
``doctor_passed: true`` only from a passing report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from burhan.cli.doctor import DoctorInputs, doctor_environment_fields, run_doctor
from burhan.core.errors import IntegrityHalt

REPO = Path(__file__).resolve().parents[3]


def _llm_config() -> dict[str, Any]:
    return {
        "nodes": {
            "node_a": {
                "provider": "anthropic",
                "model": "claude-pinned",
                "lineage": "anthropic.claude",
                "temperature": 0,
                "max_retries": 2,
            },
            "node_b": {
                "provider": "anthropic",
                "model": "claude-pinned",
                "lineage": "anthropic.claude",
                "temperature": 0,
            },
            "node_c": {
                "provider": "openai",
                "model": "gpt-pinned",
                "lineage": "openai.gpt",
                "temperature": 0,
                "max_retries": 2,
            },
        },
        "providers": {
            "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
            "openai": {"api_key_env": "OPENAI_API_KEY"},
        },
    }


def _reference_inputs(tmp_path: Path, **overrides: Any) -> DoctorInputs:
    studies = tmp_path / "studies"
    studies.mkdir(parents=True, exist_ok=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    llm = overrides.pop("llm_config", _llm_config())
    (config_dir / "llm.yaml").write_text(yaml.safe_dump(llm), encoding="utf-8")
    env = {
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "PYTHONHASHSEED": "0",
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
        "BURHAN_STUDIES_DIR": str(studies),
        "ANTHROPIC_API_KEY": "k1",
        "OPENAI_API_KEY": "k2",
    }
    env.update(overrides.pop("env", {}))
    commands = {
        "r_version": (0, "R version 4.4.1 (2024-06-14)"),
        "renv_status": (0, "No issues found -- the project is in a consistent state."),
        "git_status": (0, ""),
        "git_commit": (0, "abcdef1234567"),
    }
    commands.update(overrides.pop("commands", {}))
    defaults: dict[str, Any] = {
        "repo_dir": REPO,
        "config_dir": config_dir,
        "env": env,
        "python_version": "3.12.13",
        "run_command": lambda name: commands[name],
        "rscript_available": True,
        "find_library": lambda name: f"lib{name}.so.3",
    }
    defaults.update(overrides)
    return DoctorInputs(**defaults)


def test_reference_setup_passes(tmp_path: Path) -> None:  # AT-M04-6
    report = run_doctor(_reference_inputs(tmp_path))
    assert report.passed, [c.name for c in report.checks if c.status == "fail"]
    names = {check.name for check in report.checks}
    assert {
        "repo_on_ext4",
        "python_and_lock",
        "r_and_renv",
        "blas_and_env_pinning",
        "llm_config",
        "provider_connectivity",
        "studies_dir_writable",
        "git_state",
    } <= names
    connectivity = next(c for c in report.checks if c.name == "provider_connectivity")
    assert connectivity.status == "skip"  # adapters land in TC-06; no network here


@pytest.mark.parametrize(
    ("violation", "failing_check"),
    [
        ({"env": {"OPENBLAS_NUM_THREADS": "8"}}, "blas_and_env_pinning"),  # wrong BLAS
        ({"env": {"ANTHROPIC_API_KEY": ""}}, "llm_config"),  # missing key
        (
            {
                "llm_config": {
                    **_llm_config(),
                    "nodes": {
                        **_llm_config()["nodes"],
                        "node_c": {
                            "provider": "anthropic",
                            "model": "claude-pinned",
                            "lineage": "anthropic.claude",
                            "temperature": 0,
                        },
                    },
                }
            },
            "llm_config",  # lineage(A) == lineage(C)
        ),
        (
            {"commands": {"renv_status": (0, "The project is out-of-sync -- use renv::status()")}},
            "r_and_renv",  # dirty renv
        ),
        ({"rscript_available": False}, "r_and_renv"),  # R missing entirely
        ({"env": {"BURHAN_STUDIES_DIR": ""}}, "studies_dir_writable"),
        ({"commands": {"git_status": (0, " M src/x.py")}}, "git_state"),
    ],
)
def test_each_simulated_violation_fails_its_check(
    tmp_path: Path, violation: dict[str, Any], failing_check: str
) -> None:  # AT-M04-6
    report = run_doctor(_reference_inputs(tmp_path, **violation))
    assert not report.passed
    failed = {check.name for check in report.checks if check.status == "fail"}
    assert failing_check in failed


def test_environment_fields_only_from_passing_report(tmp_path: Path) -> None:  # AT-M04-6
    passing = run_doctor(_reference_inputs(tmp_path))
    fields = doctor_environment_fields(passing)
    assert fields["doctor_passed"] is True
    assert fields["python"] == "3.12.13"
    assert fields["r"].startswith("R version 4.4.1")
    assert fields["blas_threads"] == 1
    assert len(fields["doctor_report_sha256"]) == 64

    failing = run_doctor(_reference_inputs(tmp_path, env={"OPENBLAS_NUM_THREADS": "8"}))
    with pytest.raises(IntegrityHalt):
        doctor_environment_fields(failing)  # a failing doctor cannot enter a manifest


def test_report_render_lists_every_check(tmp_path: Path) -> None:
    report = run_doctor(_reference_inputs(tmp_path))
    rendered = report.render()
    for check in report.checks:
        assert check.name in rendered
    assert "PASS" in rendered


def test_certified_workstation_marker_pass_when_set(tmp_path: Path) -> None:  # TC-15 P3
    report = run_doctor(_reference_inputs(tmp_path, env={"BURHAN_CERTIFIED_WORKSTATION": "1"}))
    marker = next(c for c in report.checks if c.name == "certified_workstation")
    assert marker.status == "pass"
    assert "BURHAN_CERTIFIED_WORKSTATION" in marker.detail
    assert report.passed


def test_certified_workstation_marker_skips_when_unset(tmp_path: Path) -> None:  # TC-15 P3
    report = run_doctor(_reference_inputs(tmp_path))
    marker = next(c for c in report.checks if c.name == "certified_workstation")
    assert marker.status == "skip"  # absent marker is declared, never a failure
    assert "BURHAN_CERTIFIED_WORKSTATION" in marker.detail
    assert report.passed


def test_certified_workstation_marker_never_fails_doctor(tmp_path: Path) -> None:  # TC-15 P3
    # Any non-"1" value is a declared skip, not a fail: doctor greenness must
    # not depend on the marker (it is diagnostic output, not gate logic).
    report = run_doctor(_reference_inputs(tmp_path, env={"BURHAN_CERTIFIED_WORKSTATION": "0"}))
    marker = next(c for c in report.checks if c.name == "certified_workstation")
    assert marker.status == "skip"
    assert report.passed
