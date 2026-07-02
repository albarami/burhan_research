"""Run-manifest tests (AT-M01-6; NFR-102).

``seal`` computes a hash-tree root over the run directory (manifest.json
itself excluded — it carries the seal); ``verify_seal`` detects any
post-seal modification, addition, or deletion. Live-manifest failures
co-locate halt reports; verify failures never write into a sealed run
directory (immutability, architecture §11).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from artifact_instances import valid_instance

from burhan.core.artifacts.schemas import check_instance
from burhan.core.errors import HALT_REPORT_FILENAME, IntegrityHalt
from burhan.core.manifest import Manifest

FIXED_NOW = dt.datetime(2026, 7, 2, 9, 0, 0, tzinfo=dt.UTC)


class FixedClock:
    def now(self) -> dt.datetime:
        return FIXED_NOW


def _open_fields() -> dict[str, Any]:
    base = valid_instance("run_manifest")
    return {
        "run_id": base["run_id"],
        "study_id": base["study_id"],
        "master_seed": base["master_seed"],
        "engine": base["engine"],
        "hashes": base["hashes"],
        "environment": base["environment"],
        "llm_nodes": base["llm_nodes"],
    }


def _stage_fields(stage: str = "ingest") -> dict[str, Any]:
    return {
        "stage": stage,
        "state": "PASSED",
        "started": "2026-07-02T09:00:00Z",
        "finished": "2026-07-02T09:01:00Z",
    }


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "runs" / "20260702T090000Z"
    (directory / "results").mkdir(parents=True)
    (directory / "results" / "results.jsonl").write_text('{"x":1}\n', encoding="utf-8")
    (directory / "logs").mkdir()
    (directory / "logs" / "run.log").write_text("started\n", encoding="utf-8")
    (directory / "PROVENANCE.jsonl").write_text('{"seq":1}\n', encoding="utf-8")
    return directory


def test_open_writes_schema_valid_manifest(run_dir: Path) -> None:
    Manifest.open(run_dir, FixedClock(), _open_fields())
    raw = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    check_instance("run_manifest", raw)  # raises on violation
    assert raw["state"] == "PENDING"
    assert raw["started"] == "2026-07-02T09:00:00Z"
    assert raw["stages"] == []


def test_open_rejects_manifest_owned_fields(run_dir: Path) -> None:
    for owned, value in (
        ("schema_version", 1),
        ("started", "2026-07-02T09:00:00Z"),
        ("state", "RUNNING"),
        ("stages", []),
        ("finished", "2026-07-02T10:00:00Z"),
        ("seal", {"hash_tree_root": "5" * 64, "sealed_at": "2026-07-02T10:00:00Z"}),
    ):
        fields = _open_fields()
        fields[owned] = value
        with pytest.raises(IntegrityHalt):
            Manifest.open(run_dir, FixedClock(), fields)


def test_record_stage_appends_and_persists(run_dir: Path) -> None:
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    manifest.record_stage(_stage_fields("ingest"))
    manifest.record_stage(_stage_fields("contract"))
    raw = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert [record["stage"] for record in raw["stages"]] == ["ingest", "contract"]
    check_instance("run_manifest", raw)


def test_record_stage_validates_and_writes_halt_report(run_dir: Path) -> None:
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    with pytest.raises(IntegrityHalt):
        manifest.record_stage(_stage_fields("not_a_stage"))
    raw = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert raw["stages"] == []  # nothing persisted
    assert (run_dir / HALT_REPORT_FILENAME).exists()


def test_seal_requires_terminal_state(run_dir: Path) -> None:
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    for non_terminal in ("PENDING", "RUNNING", "nonsense"):
        with pytest.raises(IntegrityHalt):
            manifest.seal(non_terminal)


def test_seal_then_verify_passes_and_manifest_is_excluded(run_dir: Path) -> None:  # AT-M01-6
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    manifest.record_stage(_stage_fields("ingest"))
    manifest.seal("COMPLETED")
    raw = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    check_instance("run_manifest", raw)
    assert raw["state"] == "COMPLETED"
    assert raw["finished"] == "2026-07-02T09:00:00Z"
    assert len(raw["seal"]["hash_tree_root"]) == 64
    # The root was computed BEFORE the seal was written into manifest.json;
    # verify recomputes AFTER. Passing proves manifest.json is excluded.
    Manifest.verify_seal(run_dir)


def test_verify_detects_modified_file(run_dir: Path) -> None:  # AT-M01-6
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    manifest.seal("COMPLETED")
    target = run_dir / "results" / "results.jsonl"
    target.write_text(target.read_text(encoding="utf-8").replace("1", "2"), encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Manifest.verify_seal(run_dir)
    assert not (run_dir / HALT_REPORT_FILENAME).exists()  # sealed dir: no writes


def test_verify_detects_added_file(run_dir: Path) -> None:  # AT-M01-6
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    manifest.seal("HALTED_INTEGRITY")
    (run_dir / "smuggled.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Manifest.verify_seal(run_dir)


def test_verify_detects_deleted_file(run_dir: Path) -> None:  # AT-M01-6
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    manifest.seal("COMPLETED")
    (run_dir / "logs" / "run.log").unlink()
    with pytest.raises(IntegrityHalt):
        Manifest.verify_seal(run_dir)


def test_verify_unsealed_manifest_halts(run_dir: Path) -> None:
    Manifest.open(run_dir, FixedClock(), _open_fields())
    with pytest.raises(IntegrityHalt):
        Manifest.verify_seal(run_dir)


def test_verify_missing_manifest_halts(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt):
        Manifest.verify_seal(tmp_path)


def test_verify_malformed_manifest_halts(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Manifest.verify_seal(tmp_path)


def test_non_utc_clock_is_refused(run_dir: Path) -> None:
    class NaiveClock:
        def now(self) -> dt.datetime:
            return dt.datetime(2026, 7, 2, 9, 0, 0)  # noqa: DTZ001 — deliberate bad clock

    with pytest.raises(IntegrityHalt):
        Manifest.open(run_dir, NaiveClock(), _open_fields())
    assert (run_dir / HALT_REPORT_FILENAME).exists()


def test_double_seal_halts(run_dir: Path) -> None:
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    manifest.seal("COMPLETED")
    with pytest.raises(IntegrityHalt):
        manifest.seal("COMPLETED")
    with pytest.raises(IntegrityHalt):
        manifest.record_stage(_stage_fields("package"))  # sealed = closed


def test_symlink_in_run_dir_is_refused(run_dir: Path) -> None:
    (run_dir / "link.log").symlink_to(run_dir / "logs" / "run.log")
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    with pytest.raises(IntegrityHalt):
        manifest.seal("COMPLETED")


def test_public_api_surface(run_dir: Path) -> None:
    manifest = Manifest.open(run_dir, FixedClock(), _open_fields())
    public = {
        name
        for name in dir(manifest)
        if not name.startswith("_") and callable(getattr(manifest, name))
    }
    assert public == {"open", "record_stage", "seal", "verify_seal"}
