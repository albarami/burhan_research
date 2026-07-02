"""Results store tests (AT-M01-4; FR-1001; AD-05).

Duplicate IDs rejected; IDs violating the grammar rejected — including the
stage-binding rule: the ID's first segment IS the entry's stage
(03_ARCHITECTURE.md §8 grammar ``<stage>.<family>...``; schemas/00_README.md
``id := stage "." family``; PLAN v2 Fix 6). Prefixes resolve on segment
boundaries; the store file is append-only (no mutating API; external
mutation is detected on reopen).
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from burhan.core.artifacts.canonical import sha256_canonical
from burhan.core.errors import HALT_REPORT_FILENAME, IntegrityHalt
from burhan.results.store import ResultsStore

FIXED_NOW = dt.datetime(2026, 7, 2, 9, 0, 0, tzinfo=dt.UTC)


class FixedClock:
    def __init__(self, at: dt.datetime = FIXED_NOW) -> None:
        self._at = at

    def now(self) -> dt.datetime:
        return self._at


def _entry(stat_id: str = "structural.fit.rmsea", **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": stat_id,
        "value": 0.058,
        "stage": stat_id.split(".")[0],
        "engine": "r_lavaan",
        "playbook_step": "structural.fit_evaluation",
    }
    fields.update(overrides)
    return fields


@pytest.fixture
def store(tmp_path: Path) -> ResultsStore:
    return ResultsStore(tmp_path / "results", FixedClock())


def test_write_appends_canonical_lines_and_resolve_returns_entry(
    store: ResultsStore, tmp_path: Path
) -> None:
    store.write(_entry("structural.fit.rmsea", value=0.058))
    store.write(_entry("structural.fit.cfi", value=0.951))
    resolved = store.resolve("structural.fit.cfi")
    assert resolved.value == 0.951
    lines = (tmp_path / "results" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert parsed["schema_version"] == 1
    assert (tmp_path / "results" / "index.json").exists()


def test_created_is_stamped_from_injected_clock(store: ResultsStore) -> None:
    entry = store.write(_entry())
    assert entry.created == FIXED_NOW


def test_hash_covers_all_fields_except_hash(store: ResultsStore) -> None:
    entry = store.write(_entry())
    dumped = entry.model_dump(mode="json", by_alias=True, exclude_unset=True)
    expected = dumped.pop("hash")
    assert entry.hash == expected == sha256_canonical(dumped)


def test_duplicate_id_rejected_and_halt_report_colocated(
    store: ResultsStore, tmp_path: Path
) -> None:  # AT-M01-4
    store.write(_entry())
    with pytest.raises(IntegrityHalt):
        store.write(_entry())
    report = json.loads((tmp_path / "results" / HALT_REPORT_FILENAME).read_text(encoding="utf-8"))
    assert report["halt_class"] == "IntegrityHalt"
    lines = (tmp_path / "results" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


@pytest.mark.parametrize(
    "bad_id",
    [
        "narrate.fit.rmsea",  # narrate is not a statistical stage
        "Structural.fit.rmsea",  # uppercase stage
        "structural..path",  # empty family segment
        "prep",  # missing family
        "prep.",  # trailing dot
    ],
)
def test_ids_violating_grammar_rejected(store: ResultsStore, bad_id: str) -> None:  # AT-M01-4
    with pytest.raises(IntegrityHalt):
        store.write(_entry(bad_id, stage=bad_id.split(".")[0]))


def test_stage_binding_is_grammar_enforcement(store: ResultsStore) -> None:  # Fix 6
    # id's first segment IS the stage nonterminal (03_ARCHITECTURE.md §8).
    with pytest.raises(IntegrityHalt) as excinfo:
        store.write(_entry("prep.n_chain.final_n", stage="measurement"))
    assert "stage" in excinfo.value.message
    with pytest.raises(IntegrityHalt):
        store.resolve("prep.n_chain.final_n")  # nothing was written


def test_schema_invalid_entry_rejected(store: ResultsStore) -> None:
    with pytest.raises(IntegrityHalt):
        store.write(_entry(engine="spss"))


def test_store_owned_fields_cannot_be_supplied(store: ResultsStore) -> None:
    for owned, value in (
        ("created", "2026-07-02T09:00:00Z"),
        ("hash", "a" * 64),
        ("schema_version", 1),
    ):
        with pytest.raises(IntegrityHalt):
            store.write(_entry(**{owned: value}))


def test_iter_resolves_prefixes_on_segment_boundaries(store: ResultsStore) -> None:  # AT-M01-4
    store.write(_entry("structural.fit.rmsea"))
    store.write(_entry("structural.fitness.x"))
    store.write(_entry("structural.fit.cfi"))
    matched = [entry.id for entry in store.iter("structural.fit")]
    assert matched == ["structural.fit.rmsea", "structural.fit.cfi"]
    assert [entry.id for entry in store.iter("structural.fit.rmsea")] == ["structural.fit.rmsea"]
    everything = [entry.id for entry in store.iter()]
    assert everything == ["structural.fit.rmsea", "structural.fitness.x", "structural.fit.cfi"]


def test_iteration_order_is_insertion_order(store: ResultsStore) -> None:
    for stat_id in ("prep.n_chain.raw", "prep.n_chain.final_n", "prep.descriptives.mean"):
        store.write(_entry(stat_id, stage="prep"))
    assert [entry.id for entry in store.iter("prep")] == [
        "prep.n_chain.raw",
        "prep.n_chain.final_n",
        "prep.descriptives.mean",
    ]


def test_resolve_unknown_id_halts(store: ResultsStore) -> None:
    with pytest.raises(IntegrityHalt):
        store.resolve("structural.fit.rmsea")


def test_no_mutating_api_exists(store: ResultsStore) -> None:  # AT-M01-4 append-only
    public = {
        name for name in dir(store) if not name.startswith("_") and callable(getattr(store, name))
    }
    assert public == {"write", "resolve", "iter"}


def test_reopen_replays_and_continues(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    first = ResultsStore(directory, FixedClock())
    first.write(_entry("prep.n_chain.raw", stage="prep"))
    first.write(_entry("prep.n_chain.final_n", stage="prep"))
    reopened = ResultsStore(directory, FixedClock())
    assert reopened.resolve("prep.n_chain.raw").stage == "prep"
    with pytest.raises(IntegrityHalt):
        reopened.write(_entry("prep.n_chain.raw", stage="prep"))  # still duplicate
    reopened.write(_entry("prep.n_chain.recovered", stage="prep"))
    assert len(list(reopened.iter("prep"))) == 3


def test_reopen_detects_tampered_line(tmp_path: Path) -> None:  # AT-M01-4 append-only
    directory = tmp_path / "results"
    store = ResultsStore(directory, FixedClock())
    store.write(_entry())
    path = directory / "results.jsonl"
    tampered = path.read_text(encoding="utf-8").replace("0.058", "0.999")
    path.write_text(tampered, encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        ResultsStore(directory, FixedClock())


def test_reopen_detects_truncation_against_index(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    store = ResultsStore(directory, FixedClock())
    store.write(_entry("structural.fit.rmsea"))
    store.write(_entry("structural.fit.cfi"))
    path = directory / "results.jsonl"
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    path.write_text(first_line + "\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        ResultsStore(directory, FixedClock())


def test_reopen_detects_hand_appended_duplicate(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    store = ResultsStore(directory, FixedClock())
    store.write(_entry())
    path = directory / "results.jsonl"
    line = path.read_text(encoding="utf-8")
    path.write_text(line + line, encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        ResultsStore(directory, FixedClock())


def test_reopen_rejects_malformed_line(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    store = ResultsStore(directory, FixedClock())
    store.write(_entry())
    path = directory / "results.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        ResultsStore(directory, FixedClock())


def test_missing_index_is_rebuilt_but_orphan_index_halts(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    store = ResultsStore(directory, FixedClock())
    store.write(_entry())
    (directory / "index.json").unlink()
    reopened = ResultsStore(directory, FixedClock())  # index is derived: rebuilt
    assert (directory / "index.json").exists()
    assert reopened.resolve("structural.fit.rmsea").value == 0.058

    orphan_dir = tmp_path / "orphan"
    orphan_dir.mkdir()
    (orphan_dir / "index.json").write_text("{}", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        ResultsStore(orphan_dir, FixedClock())


def test_corrupt_index_json_halts(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    store = ResultsStore(directory, FixedClock())
    store.write(_entry())
    (directory / "index.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        ResultsStore(directory, FixedClock())


def test_stale_index_content_halts(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    store = ResultsStore(directory, FixedClock())
    store.write(_entry())
    (directory / "index.json").write_text('{"prep.fake.id":"' + "0" * 64 + '"}', encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        ResultsStore(directory, FixedClock())


def test_non_utc_clock_is_refused(tmp_path: Path) -> None:
    class SkewedClock:
        def now(self) -> dt.datetime:
            return dt.datetime(2026, 7, 2, 9, 0, 0, 500000, tzinfo=dt.UTC)

    store = ResultsStore(tmp_path / "results", SkewedClock())
    with pytest.raises(IntegrityHalt):
        store.write(_entry())


def test_write_accepts_mapping_and_returns_typed_entry(store: ResultsStore) -> None:
    fields: Mapping[str, Any] = _entry(
        "effects.indirect.READINESS->INT.boot_ci",
        stage="effects",
        value=0.12,
        ci_low=0.05,
        ci_high=0.21,
        ci_level=0.95,
        params={"resamples": 5000},
    )
    entry = store.write(fields)
    assert entry.id == "effects.indirect.READINESS->INT.boot_ci"
    assert entry.ci_low == 0.05
    assert entry.params == {"resamples": 5000}
