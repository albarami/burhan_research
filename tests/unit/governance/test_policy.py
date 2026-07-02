"""Decision policy engine tests (AT-M02-1, AT-M02-2/D2, AT-M02-6; FR-1201).

The governed template is loaded from mutated tmp copies; the real file is
never modified. D1: draft blocks production loads. D2: every playbook
policy_ref resolves. D3: preauthorized_rules only when preauthorized.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from gov_util import (
    PLAYBOOK,
    POLICY_TEMPLATE,
    FixedClock,
    load_yaml,
    playbook_copy,
    policy_copy,
)

from burhan.core.errors import IntegrityHalt
from burhan.core.policy import DecisionLog, Policy, render_decision_log

FIXED_TS = "2026-07-02T09:00:00Z"


@pytest.fixture
def policy(tmp_path: Path) -> Policy:
    return Policy.load(policy_copy(tmp_path), mode="certification")


@pytest.fixture
def log(tmp_path: Path) -> DecisionLog:
    return DecisionLog(tmp_path / "decisions.jsonl", FixedClock())


def _leaf_paths(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.extend(_leaf_paths(value, path))
            out.append((path, value))
        else:
            out.append((path, value))
    return out


# -- AT-M02-1 ------------------------------------------------------------------


def test_template_validates_and_draft_blocks_production_load(tmp_path: Path) -> None:
    Policy.load(POLICY_TEMPLATE, mode="certification")  # draft loads here
    with pytest.raises(IntegrityHalt) as excinfo:
        Policy.load(POLICY_TEMPLATE, mode="production")  # D1
    assert "D1" in excinfo.value.message
    approved = policy_copy(tmp_path, status="approved")
    loaded = Policy.load(approved, mode="production")
    assert loaded.status == "approved"
    assert loaded.version == "1.0"


def test_every_leaf_path_is_addressable_via_rule(policy: Policy) -> None:  # AT-M02-1
    template = load_yaml(POLICY_TEMPLATE)
    paths = _leaf_paths(template)
    assert len(paths) > 40  # the whole rulebook, leaves and subtrees
    for path, expected in paths:
        assert policy.rule(path) == expected, path


def test_unknown_rule_path_halts_naming_it(policy: Policy) -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        policy.rule("prep.no_such_rule")
    assert excinfo.value.to_report()["details"]["path"] == "prep.no_such_rule"


def test_rule_returns_copies_not_references(policy: Policy) -> None:
    subtree = policy.rule("prep.outliers")
    assert isinstance(subtree, dict)
    subtree["univariate_z"] = 99.0
    assert policy.rule("prep.outliers.univariate_z") == 3.29  # template value intact


def test_schema_violation_halts_with_path(tmp_path: Path) -> None:
    def corrupt(data: dict[str, Any]) -> None:
        data["gates"]["max_retries"] = 0  # below schema minimum 1

    with pytest.raises(IntegrityHalt) as excinfo:
        Policy.load(policy_copy(tmp_path, mutate=corrupt), mode="certification")
    assert "max_retries" in excinfo.value.to_report()["details"]["path"]


def test_d3_rules_without_preauthorization_halt(tmp_path: Path) -> None:  # D3
    def smuggle_rules(data: dict[str, Any]) -> None:
        data["measurement"]["item_deletion"]["preauthorized_rules"] = ["reliability_gain"]
        # preauthorized stays false

    with pytest.raises(IntegrityHalt) as excinfo:
        Policy.load(policy_copy(tmp_path, mutate=smuggle_rules), mode="certification")
    assert "D3" in excinfo.value.message


def test_malformed_policy_file_halts(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{unbalanced: [", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Policy.load(bad, mode="certification")
    with pytest.raises(IntegrityHalt):
        Policy.load(tmp_path / "absent.yaml", mode="certification")


# -- AT-M02-2 (D2): playbook refs ----------------------------------------------


def test_all_playbook_policy_refs_resolve(policy: Policy) -> None:  # AT-M02-2
    refs = policy.verify_playbook_refs(PLAYBOOK)
    assert len(refs) == 11  # 10 criteria policy_refs + 1 preauthorization ref
    assert refs.count("measurement.item_deletion.preauthorized") == 2  # PB-13 + governance


def test_unresolvable_playbook_ref_halts_naming_missing_path(
    policy: Policy, tmp_path: Path
) -> None:  # AT-M02-2
    def bogus(data: dict[str, Any]) -> None:
        data["steps"][0]["criteria"][0]["policy_ref"] = "power.no_such.knob"

    broken = playbook_copy(tmp_path, mutate=bogus)
    with pytest.raises(IntegrityHalt) as excinfo:
        policy.verify_playbook_refs(broken)
    details = excinfo.value.to_report()["details"]
    assert details["path"] == "power.no_such.knob"
    assert details["step"]  # the offending playbook step is named


# -- AT-M02-6: decide() + DECISION_LOG.md rendering ------------------------------


def _decide(policy: Policy, log: DecisionLog) -> None:
    policy.decide(
        log=log,
        stage="assumptions",
        decision_point="estimator_determination",
        rule_id="estimator.robust_trigger.on_mardia_violation",
        inputs={"mardia_p": 0.0004, "skew_max": 2.4},
        decision="MLR",
        rationale="Multivariate non-normality; robust ML within method (PB-07).",
        alternatives_considered=["ML", "WLSMV"],
    )
    policy.decide(
        log=log,
        stage="prep",
        decision_point="inclusion_threshold",
        rule_id="prep.inclusion_threshold.min_completion_pct",
        inputs={"partials_profiled": 37, "recovered": 21},
        decision="recover >= 90% completions",
        rationale="Policy inclusion threshold applied to model items (FR-502).",
    )


def test_decide_writes_entries_citing_rule_and_version(
    policy: Policy, log: DecisionLog, tmp_path: Path
) -> None:  # AT-M02-6
    _decide(policy, log)
    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        raw = json.loads(line)
        assert raw["rule_version"] == policy.version == "1.0"
        assert policy.rule(raw["rule_id"]) is not None  # cited rule resolves
        assert raw["ts"] == FIXED_TS
    assert [json.loads(line)["seq"] for line in lines] == [1, 2]


def test_decide_with_unresolvable_rule_id_halts(policy: Policy, log: DecisionLog) -> None:
    with pytest.raises(IntegrityHalt):
        policy.decide(
            log=log,
            stage="prep",
            decision_point="other",
            rule_id="not.a.rule",
            inputs={},
            decision="x",
            rationale="y",
        )


def test_invalid_decision_point_writes_nothing_and_no_seq_gap(
    policy: Policy, log: DecisionLog, tmp_path: Path
) -> None:
    with pytest.raises(IntegrityHalt):
        policy.decide(
            log=log,
            stage="prep",
            decision_point="not_a_decision_point",
            rule_id="prep.inclusion_threshold.min_completion_pct",
            inputs={},
            decision="x",
            rationale="y",
        )
    assert not (tmp_path / "decisions.jsonl").exists()
    _decide(policy, log)
    first = json.loads((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["seq"] == 1  # failed attempt consumed no seq


def test_rendered_decision_log_contains_nothing_absent_from_jsonl(
    policy: Policy, log: DecisionLog, tmp_path: Path
) -> None:  # AT-M02-6 (schema promise, decision_log.schema.json:5)
    _decide(policy, log)
    jsonl_path = tmp_path / "decisions.jsonl"
    rendered = render_decision_log(jsonl_path)

    # Deterministic pure function of the JSONL.
    assert rendered == render_decision_log(jsonl_path)

    # Every decision is present...
    assert "estimator_determination" in rendered
    assert "MLR" in rendered
    assert "estimator.robust_trigger.on_mardia_violation" in rendered

    # ...and nothing numeric exists in the render that the JSONL lacks.
    jsonl_text = jsonl_path.read_text(encoding="utf-8")
    import re

    for number in re.findall(r"\d+(?:\.\d+)?", rendered):
        assert number in jsonl_text, f"render invented number {number}"


def test_render_reflects_jsonl_tampering(policy: Policy, log: DecisionLog, tmp_path: Path) -> None:
    _decide(policy, log)
    jsonl_path = tmp_path / "decisions.jsonl"
    before = render_decision_log(jsonl_path)
    tampered = jsonl_path.read_text(encoding="utf-8").replace('"MLR"', '"WLSMV"')
    jsonl_path.write_text(tampered, encoding="utf-8")
    assert render_decision_log(jsonl_path) != before


def test_render_validates_entries(tmp_path: Path) -> None:
    bad = tmp_path / "decisions.jsonl"
    bad.write_text('{"schema_version": 1, "seq": 0}\n', encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        render_decision_log(bad)


# -- coverage of defensive branches (100%-module mandate, standards §3) ----------


def test_non_mapping_policy_document_halts(tmp_path: Path) -> None:
    listy = tmp_path / "list.yaml"
    listy.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        Policy.load(listy, mode="certification")


def test_policy_exposes_content_hash_for_manifest(policy: Policy, tmp_path: Path) -> None:
    assert len(policy.sha256) == 64  # NFR-102 wiring surface
    assert int(policy.sha256, 16) >= 0


def test_verify_playbook_refs_unreadable_playbook_halts(policy: Policy, tmp_path: Path) -> None:
    with pytest.raises(IntegrityHalt):
        policy.verify_playbook_refs(tmp_path / "absent_playbook.yaml")


def test_decide_records_flags(policy: Policy, log: DecisionLog, tmp_path: Path) -> None:
    policy.decide(
        log=log,
        stage="prep",
        decision_point="outlier_treatment",
        rule_id="prep.outliers.treatment",
        inputs={"outliers": 3},
        decision="retain_with_sensitivity",
        rationale="Policy outlier treatment applied (PB-04).",
        flags=["FLAG-002"],
    )
    raw = json.loads((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert raw["flags"] == ["FLAG-002"]
    rendered = render_decision_log(log.path)
    assert "FLAG-002" in rendered


def test_log_owned_fields_cannot_be_supplied(log: DecisionLog) -> None:
    for owned, value in (("seq", 9), ("ts", FIXED_TS), ("schema_version", 1)):
        with pytest.raises(IntegrityHalt):
            log.append(
                {
                    "stage": "prep",
                    "decision_point": "other",
                    "rule_id": "prep.inclusion_threshold.min_completion_pct",
                    "rule_version": "1.0",
                    "inputs": {},
                    "decision": "x",
                    "rationale": "y",
                    owned: value,
                }
            )


def test_non_utc_clock_is_refused(tmp_path: Path) -> None:
    import datetime as dt

    class NaiveClock:
        def now(self) -> dt.datetime:
            return dt.datetime(2026, 7, 2, 9, 0, 0)  # noqa: DTZ001 — deliberate bad clock

    log = DecisionLog(tmp_path / "decisions.jsonl", NaiveClock())
    with pytest.raises(IntegrityHalt):
        log.append(
            {
                "stage": "prep",
                "decision_point": "other",
                "rule_id": "x",
                "rule_version": "1.0",
                "inputs": {},
                "decision": "d",
                "rationale": "r",
            }
        )


def test_replay_rejects_malformed_line_and_seq_gap(
    policy: Policy, log: DecisionLog, tmp_path: Path
) -> None:
    _decide(policy, log)
    jsonl = tmp_path / "decisions.jsonl"
    with_gap = jsonl.read_text(encoding="utf-8").splitlines()
    forged = json.loads(with_gap[1])
    forged["seq"] = 9
    jsonl.write_text(with_gap[0] + "\n" + json.dumps(forged) + "\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        render_decision_log(jsonl)
    jsonl.write_text(with_gap[0] + "\nnot json\n", encoding="utf-8")
    with pytest.raises(IntegrityHalt):
        render_decision_log(jsonl)


def test_render_marks_human_protected_entries(tmp_path: Path) -> None:
    # M10's pre-authorized execution records the HUMAN decision with
    # protected=true (decision_log.schema.json); the renderer surfaces it.
    log = DecisionLog(tmp_path / "decisions.jsonl", FixedClock())
    log.append(
        {
            "stage": "measurement",
            "decision_point": "item_deletion_executed",
            "rule_id": "measurement.item_deletion.preauthorized",
            "rule_version": "1.0",
            "inputs": {"item": "RS3"},
            "decision": "deleted RS3 under permit token",
            "rationale": "Pre-authorized by the method owner via policy delegation.",
            "protected": True,
        }
    )
    rendered = render_decision_log(log.path)
    assert "protected: true (human decision on record)" in rendered
