"""Playbook engine tests (AT-M03-1/2/3; FR-1301–1303; P1–P5).

P1–P5 reproduce the Wave-2 validation script as production code (TC-03
Delivery Notes); each violation is named specifically. P3 binds at load —
production loads require the decision policy (the AT-M02-2 'resolve at
load' rule applied here from the start).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pb_util import PLAYBOOK, load_yaml, playbook_copy, policy_copy

from burhan.core.errors import IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy

ALL_STEP_IDS = [f"PB-{n:02d}" for n in range(1, 22)]


@pytest.fixture
def playbook() -> Playbook:
    return Playbook.load(PLAYBOOK, mode="certification")


@pytest.fixture
def policy(tmp_path: Path) -> Policy:
    return Policy.load(policy_copy(tmp_path), mode="certification")


# -- AT-M03-1: governed playbook loads; P1–P4 violations named -------------------


def test_governed_playbook_loads_with_all_steps(playbook: Playbook) -> None:  # AT-M03-1
    assert playbook.step_ids == ALL_STEP_IDS
    assert playbook.id == "CB_SEM_PLAYBOOK"
    assert playbook.version == "1.0"
    assert playbook.methodology == "CB_SEM"
    assert len(playbook.sha256) == 64


def test_p1_duplicate_step_id_named(tmp_path: Path) -> None:  # AT-M03-1 (P1)
    def duplicate(data: dict[str, Any]) -> None:
        data["steps"][1]["id"] = "PB-01"

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=duplicate), mode="certification")
    assert "P1" in excinfo.value.message and "duplicate" in excinfo.value.message


def test_p1_step_id_order_named(tmp_path: Path) -> None:  # AT-M03-1 (P1)
    def disorder(data: dict[str, Any]) -> None:
        data["steps"][0]["id"] = "PB-99"

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=disorder), mode="certification")
    assert "P1" in excinfo.value.message and "order" in excinfo.value.message


def test_p1_stage_order_named(tmp_path: Path) -> None:  # AT-M03-1 (P1)
    def disorder(data: dict[str, Any]) -> None:
        data["steps"][0]["stage"] = "structural"

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=disorder), mode="certification")
    assert "P1" in excinfo.value.message and "stage" in excinfo.value.message


def test_p2_registered_but_unused_citation_named(tmp_path: Path) -> None:  # AT-M03-1 (P2)
    def orphan(data: dict[str, Any]) -> None:
        data["citations"]["ghost2024"] = "Ghost, A. (2024). Unused reference."

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=orphan), mode="certification")
    assert "P2" in excinfo.value.message
    assert "ghost2024" in str(excinfo.value.to_report()["details"])


def test_p2_used_but_unregistered_citation_named(tmp_path: Path) -> None:  # AT-M03-1 (P2)
    def phantom(data: dict[str, Any]) -> None:
        data["steps"][0]["citations"][0] = "phantom1999"

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=phantom), mode="certification")
    assert "P2" in excinfo.value.message
    assert "phantom1999" in str(excinfo.value.to_report()["details"])


@pytest.mark.parametrize("bad_prefix", ["narrate.free_text", "Power.mc", "structural.fit.rmsea"])
def test_p4_output_prefix_grammar_named(tmp_path: Path, bad_prefix: str) -> None:  # AT-M03-1 (P4)
    def corrupt(data: dict[str, Any]) -> None:
        data["steps"][0]["outputs"][0] = bad_prefix

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=corrupt), mode="certification")
    assert "P4" in excinfo.value.message
    details = excinfo.value.to_report()["details"]
    assert details["prefix"] == bad_prefix
    assert details["step"] == "PB-01"


def test_p3_bogus_criteria_policy_ref_named(tmp_path: Path, policy: Policy) -> None:  # AT-M03-1
    def bogus(data: dict[str, Any]) -> None:
        data["steps"][0]["criteria"][2]["policy_ref"] = "power.no_such.knob"

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=bogus), mode="certification", policy=policy)
    assert "P3" in excinfo.value.message
    details = excinfo.value.to_report()["details"]
    assert details["path"] == "power.no_such.knob"
    assert details["step"] == "PB-01"


def test_p3_bogus_governance_ref_named(tmp_path: Path, policy: Policy) -> None:  # AT-M03-1 (P3)
    def bogus(data: dict[str, Any]) -> None:
        data["steps"][12]["governance"]["preauthorization_policy_ref"] = "measurement.nope"

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=bogus), mode="certification", policy=policy)
    assert "P3" in excinfo.value.message
    assert excinfo.value.to_report()["details"]["step"] == "PB-13"


def test_p3_resolves_with_policy_at_load(tmp_path: Path, policy: Policy) -> None:
    loaded = Playbook.load(playbook_copy(tmp_path), mode="certification", policy=policy)
    assert loaded.step_ids == ALL_STEP_IDS


def test_missing_and_malformed_playbook_files_halt(tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt):
        Playbook.load(tmp_path / "absent.yaml", mode="certification")
    bad = tmp_path / "bad.yaml"
    bad.write_text("{unbalanced: [", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Playbook.load(bad, mode="certification")


def test_schema_violation_halts_with_path(tmp_path: Path) -> None:
    def corrupt(data: dict[str, Any]) -> None:
        data["steps"][0]["failure_action"] = "explode"

    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path, mutate=corrupt), mode="certification")
    assert "failure_action" in excinfo.value.to_report()["details"]["path"]


# -- AT-M03-2: P5 status gate ----------------------------------------------------


def test_draft_blocks_production_and_certification_loads_draft(
    tmp_path: Path, policy: Policy
) -> None:  # AT-M03-2
    Playbook.load(PLAYBOOK, mode="certification")  # governed file is draft
    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(playbook_copy(tmp_path), mode="production", policy=policy)
    assert "P5" in excinfo.value.message
    approved = playbook_copy(tmp_path, status="approved")
    loaded = Playbook.load(approved, mode="production", policy=policy)
    assert loaded.status == "approved"


def test_production_load_requires_policy_for_p3(tmp_path: Path) -> None:
    approved = playbook_copy(tmp_path, status="approved")
    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.load(approved, mode="production")
    assert "P3" in excinfo.value.message


# -- AT-M03-3: no playbook, no run (FR-1302/1303) ---------------------------------


def test_unknown_methodology_is_clean_refusal_with_report(tmp_path: Path) -> None:  # AT-M03-3
    would_be_run_dir = tmp_path / "runs" / "20260702T090000Z"
    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.for_methodology(
            "PLS_SEM",
            "PLS_SEM_PLAYBOOK",
            "1.0",
            mode="certification",
            playbooks_dir=tmp_path / "playbooks",
        )
    details = excinfo.value.to_report()["details"]
    assert details["methodology"] == "PLS_SEM"
    assert "PLS_SEM_PLAYBOOK_v1.0.yaml" in details["expected_file"]
    # clean refusal: no partial run artifacts anywhere
    assert not would_be_run_dir.exists()
    assert list(tmp_path.rglob("*")) == []  # not even a halt report file


def test_binding_mismatch_is_refused(tmp_path: Path) -> None:  # FR-1303
    def wrong_version(data: dict[str, Any]) -> None:
        data["meta"]["version"] = "1.1"

    directory = tmp_path / "playbooks"
    playbook_copy(directory, name="CB_SEM_PLAYBOOK_v1.0.yaml", mutate=wrong_version)
    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.for_methodology(
            "CB_SEM", "CB_SEM_PLAYBOOK", "1.0", mode="certification", playbooks_dir=directory
        )
    assert "FR-1303" in excinfo.value.message


def test_for_methodology_loads_exactly_the_declared_playbook() -> None:  # FR-1303
    loaded = Playbook.for_methodology("CB_SEM", "CB_SEM_PLAYBOOK", "1.0", mode="certification")
    assert loaded.id == "CB_SEM_PLAYBOOK"
    assert loaded.version == "1.0"


def test_methodology_mismatch_against_file_is_refused(tmp_path: Path) -> None:  # FR-1303
    directory = tmp_path / "playbooks"
    playbook_copy(directory, name="CB_SEM_PLAYBOOK_v1.0.yaml")
    with pytest.raises(IntegrityHalt) as excinfo:
        Playbook.for_methodology(
            "PLS_SEM", "CB_SEM_PLAYBOOK", "1.0", mode="certification", playbooks_dir=directory
        )
    assert "FR-1303" in excinfo.value.message


# -- accessors --------------------------------------------------------------------


def test_step_and_criteria_accessors(playbook: Playbook) -> None:
    step = playbook.step("PB-13")
    assert step["title"] == "Item deletion protocol (protected by default)"
    assert step["governance"]["protected_default"] is True
    assert [c["name"] for c in playbook.criteria("PB-10")] == [
        "alpha_floor",
        "cr_floor",
        "ave_floor",
    ]
    assert playbook.outputs("PB-20") == []
    assert playbook.outputs("PB-17") == [
        "effects.direct",
        "effects.indirect",
        "effects.total",
        "effects.classification",
    ]
    assert "Kline" in playbook.citation("kline2016")
    assert len(playbook.chapter_structure) == 9


def test_accessors_halt_on_unknown_ids(playbook: Playbook) -> None:
    with pytest.raises(IntegrityHalt):
        playbook.step("PB-99")
    with pytest.raises(IntegrityHalt):
        playbook.criteria("PB-99")
    with pytest.raises(IntegrityHalt):
        playbook.citation("nobody2020")


def test_accessors_return_copies(playbook: Playbook) -> None:
    playbook.step("PB-01")["title"] = "tampered"
    assert playbook.step("PB-01")["title"] != "tampered"
    playbook.criteria("PB-01")[0]["rule"] = "tampered"
    assert playbook.criteria("PB-01")[0]["rule"] != "tampered"


def test_loaded_playbook_matches_governed_file(playbook: Playbook) -> None:
    governed = load_yaml(PLAYBOOK)
    assert len(governed["steps"]) == 21
    assert playbook.step("PB-01")["stage"] == governed["steps"][0]["stage"]
