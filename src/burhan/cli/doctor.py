"""``burhan doctor`` — environment verification (04_ENVIRONMENT_AND_STACK §9).

Every check is a named pass/fail/skip with detail; the report is
machine-hashable and renders per line. All inputs are injectable so the
acceptance tests simulate each violation exactly (AT-M04-6); production
inputs read the real machine. A failing report can never enter a run
manifest: :func:`doctor_environment_fields` halts unless the report passed
(the manifest schema then pins ``doctor_passed: const true``).

The provider connectivity probe is SKIPPED until the LLM adapters land
(TC-06/M06): outside the adapters no Burhān code may touch the network.
"""

from __future__ import annotations

import ctypes.util
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Untyped third-party edge (no stubs in the locked dependency set).
import yaml  # type: ignore[import-untyped]

from burhan.core.artifacts.canonical import sha256_canonical, sha256_file
from burhan.core.errors import IntegrityHalt, halt

_PINNED_ENV = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "PYTHONHASHSEED": "0",
    "TZ": "UTC",
    "LC_ALL": "C.UTF-8",
}


@dataclass(frozen=True)
class DoctorCheck:
    """One named verification with its outcome."""

    name: str
    status: str  # pass | fail | skip
    detail: str


@dataclass(frozen=True)
class DoctorInputs:
    """Everything doctor examines; injectable for exact simulation."""

    repo_dir: Path
    config_dir: Path
    env: Mapping[str, str]
    python_version: str
    run_command: Callable[[str], tuple[int, str]]
    rscript_available: bool
    find_library: Callable[[str], str | None] = field(default=lambda name: f"lib{name}.so")
    os_label: str = "linux"


@dataclass(frozen=True)
class DoctorReport:
    """The full check battery plus the context a manifest needs."""

    checks: tuple[DoctorCheck, ...]
    python_version: str
    r_version: str
    os_label: str

    @property
    def passed(self) -> bool:
        """Green means zero failing checks (skips are declared, not hidden)."""
        return all(check.status != "fail" for check in self.checks)

    def to_payload(self) -> dict[str, Any]:
        """Canonical-serializable report content."""
        return {
            "passed": self.passed,
            "python": self.python_version,
            "r": self.r_version,
            "os": self.os_label,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail} for c in self.checks
            ],
        }

    def render(self) -> str:
        """Human-readable per-line report."""
        lines = ["burhan doctor (04_ENVIRONMENT_AND_STACK §9)", ""]
        for check in self.checks:
            lines.append(f"[{check.status.upper():4}] {check.name}: {check.detail}")
        lines.append("")
        lines.append("PASS" if self.passed else "FAIL")
        return "\n".join(lines)


def run_doctor(inputs: DoctorInputs) -> DoctorReport:
    """Run the full §9 check battery over the injected inputs."""
    checks: list[DoctorCheck] = []
    r_version = "unavailable"

    if str(inputs.repo_dir).startswith("/mnt/"):
        checks.append(
            DoctorCheck(
                "repo_on_ext4",
                "fail",
                f"repository under Windows mount {inputs.repo_dir} (04 §1 filesystem rule)",
            )
        )
    else:
        checks.append(DoctorCheck("repo_on_ext4", "pass", str(inputs.repo_dir)))

    uv_lock = inputs.repo_dir / "uv.lock"
    if not inputs.python_version.startswith("3.12"):
        checks.append(
            DoctorCheck(
                "python_and_lock", "fail", f"CPython 3.12 required, {inputs.python_version} found"
            )
        )
    elif not uv_lock.is_file():
        checks.append(DoctorCheck("python_and_lock", "fail", "uv.lock missing"))
    else:
        checks.append(
            DoctorCheck(
                "python_and_lock",
                "pass",
                f"python {inputs.python_version}; uv.lock sha256 {sha256_file(uv_lock)[:12]}…",
            )
        )

    if not inputs.rscript_available:
        checks.append(
            DoctorCheck("r_and_renv", "fail", "Rscript not on PATH (bootstrap 04 §8 step 2)")
        )
    else:
        version_rc, version_out = inputs.run_command("r_version")
        status_rc, status_out = inputs.run_command("renv_status")
        if version_rc != 0:
            checks.append(
                DoctorCheck("r_and_renv", "fail", f"R version probe failed: {version_out}")
            )
        elif status_rc != 0 or "consistent state" not in status_out:
            checks.append(
                DoctorCheck("r_and_renv", "fail", f"renv not clean: {status_out.strip()}")
            )
        else:
            r_version = version_out.strip()
            checks.append(DoctorCheck("r_and_renv", "pass", f"{r_version}; renv consistent"))

    missing_libs = [name for name in ("blas", "lapack") if inputs.find_library(name) is None]
    if missing_libs:
        checks.append(
            DoctorCheck("system_libraries", "fail", f"missing shared libraries: {missing_libs}")
        )
    else:
        checks.append(DoctorCheck("system_libraries", "pass", "blas/lapack resolvable"))

    wrong_env = {
        key: inputs.env.get(key, "<unset>")
        for key, expected in _PINNED_ENV.items()
        if inputs.env.get(key) != expected
    }
    if wrong_env:
        checks.append(
            DoctorCheck(
                "blas_and_env_pinning",
                "fail",
                f"determinism pins violated (04 §2): {wrong_env}",
            )
        )
    else:
        checks.append(DoctorCheck("blas_and_env_pinning", "pass", "single-threaded BLAS; pins set"))

    checks.append(_check_llm_config(inputs))
    checks.append(
        DoctorCheck(
            "provider_connectivity",
            "skip",
            "deferred until LLM adapters land (TC-06/M06); no network outside adapters",
        )
    )

    studies = inputs.env.get("BURHAN_STUDIES_DIR", "")
    if not studies:
        checks.append(DoctorCheck("studies_dir_writable", "fail", "BURHAN_STUDIES_DIR unset"))
    else:
        studies_path = Path(studies)
        if not studies_path.is_dir():
            checks.append(
                DoctorCheck("studies_dir_writable", "fail", f"{studies_path} does not exist")
            )
        else:
            probe = studies_path / ".doctor_write_probe"
            try:
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
                checks.append(DoctorCheck("studies_dir_writable", "pass", str(studies_path)))
            except OSError as exc:
                checks.append(DoctorCheck("studies_dir_writable", "fail", str(exc)))

    status_rc, status_out = inputs.run_command("git_status")
    commit_rc, commit_out = inputs.run_command("git_commit")
    if status_rc != 0 or commit_rc != 0:
        checks.append(DoctorCheck("git_state", "fail", "git probes failed"))
    elif status_out.strip():
        checks.append(
            DoctorCheck("git_state", "fail", f"working tree dirty: {status_out.strip()[:80]}")
        )
    else:
        checks.append(DoctorCheck("git_state", "pass", f"clean at {commit_out.strip()[:12]}"))

    return DoctorReport(
        checks=tuple(checks),
        python_version=inputs.python_version,
        r_version=r_version,
        os_label=inputs.os_label,
    )


def _check_llm_config(inputs: DoctorInputs) -> DoctorCheck:
    llm_path = inputs.config_dir / "llm.yaml"
    if not llm_path.is_file():
        return DoctorCheck("llm_config", "fail", f"{llm_path} missing (bootstrap 04 §8 step 4)")
    try:
        config = yaml.safe_load(llm_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return DoctorCheck("llm_config", "fail", f"llm.yaml unparseable: {exc}")
    if not isinstance(config, dict) or "nodes" not in config or "providers" not in config:
        return DoctorCheck("llm_config", "fail", "llm.yaml lacks nodes/providers blocks")
    nodes = config["nodes"]
    for node in ("node_a", "node_b", "node_c"):
        spec = nodes.get(node)
        if not isinstance(spec, dict) or not {"provider", "model", "lineage"} <= spec.keys():
            return DoctorCheck("llm_config", "fail", f"{node} incomplete in llm.yaml")
        provider = spec["provider"]
        provider_spec = config["providers"].get(provider, {})
        key_env = provider_spec.get("api_key_env")
        if not key_env or not inputs.env.get(str(key_env)):
            return DoctorCheck(
                "llm_config", "fail", f"{node}: api key env for provider '{provider}' unresolved"
            )
    if nodes["node_a"]["lineage"] == nodes["node_c"]["lineage"]:
        return DoctorCheck(
            "llm_config",
            "fail",
            "lineage(node_a) == lineage(node_c) violates FR-304 (Sanad independence)",
        )
    return DoctorCheck(
        "llm_config", "pass", "schema-valid; keys resolvable; lineage(A) != lineage(C)"
    )


def doctor_environment_fields(report: DoctorReport) -> dict[str, Any]:
    """Manifest ``environment`` fields — obtainable ONLY from a passing report."""
    if not report.passed:
        halt(
            IntegrityHalt(
                "doctor did not pass; a run manifest cannot record doctor_passed",
                report={"failed": [c.name for c in report.checks if c.status == "fail"]},
            )
        )
    return {
        "python": report.python_version,
        "r": report.r_version,
        "os": report.os_label,
        "blas_threads": 1,
        "doctor_passed": True,
        "doctor_report_sha256": sha256_canonical(report.to_payload()),
    }


def production_inputs() -> DoctorInputs:
    """Doctor inputs read from the real machine (CLI entry)."""
    import os

    repo = Path(__file__).resolve().parents[3]

    def run_command(name: str) -> tuple[int, str]:
        argv = {
            "r_version": ["Rscript", "-e", "cat(R.version.string)"],
            "renv_status": [
                "Rscript",
                "-e",
                f'setwd("{repo / "workers" / "r"}"); renv::status()',
            ],
            "git_status": ["git", "-C", str(repo), "status", "--porcelain"],
            "git_commit": ["git", "-C", str(repo), "rev-parse", "HEAD"],
        }[name]
        try:
            completed = subprocess.run(  # noqa: S603 — fixed argv table above
                argv, capture_output=True, text=True, timeout=120, check=False
            )
        except OSError as exc:
            return 1, str(exc)
        return completed.returncode, completed.stdout + completed.stderr

    return DoctorInputs(
        repo_dir=repo,
        config_dir=Path(os.environ.get("BURHAN_CONFIG_DIR", str(Path.home() / ".config/burhan"))),
        env=dict(os.environ),
        python_version=platform.python_version(),
        run_command=run_command,
        rscript_available=shutil.which("Rscript") is not None,
        find_library=ctypes.util.find_library,
        os_label=(
            f"{platform.system()} {platform.release()} "
            f"python={sys.version_info.major}.{sys.version_info.minor}"
        ),
    )
