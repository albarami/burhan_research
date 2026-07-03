"""Pipeline guards, tripwires, and secondary paths (FR-501/505/506/507).

Small hand-built exports exercise every guard the golden run cannot
reach: missing declarations, unsupported policy values (halting loud
rather than screening wrong), unparseable cells, zero-variance items, the
multivariate outlier criterion, and the two case-level tripwires.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.core.policy import Policy
from burhan.prep import invariants
from burhan.prep.n_chain import NChainAccountant
from burhan.prep.py_impl.missingness import littles_mcar, missingness_report
from burhan.prep.py_impl.pipeline import run_prep

REPO = Path(__file__).resolve().parents[3]
_ITEMS = ("XA1", "XA2", "XA3", "XB1", "XB2", "XB3")


def _mini_config(**overrides: Any) -> dict[str, Any]:
    data_block: dict[str, Any] = {
        "file": "inputs/mini.csv",
        "format": "csv",
        "export_dialect": "generic",
        "header_rows": 3,
        "id_column": "ResponseId",
        "consent_column": "Q3",
        "attention_checks": [{"column": "A1", "expected": "5"}],
    }
    data_block.update(overrides.pop("data", {}))
    data_block = {key: value for key, value in data_block.items() if value is not None}
    config: dict[str, Any] = {
        "schema_version": 1,
        "meta": {
            "study_id": "mini-2026",
            "title": "Mini pipeline fixture",
            "source_documents": [
                {"role": "study_document", "path": "inputs/mini.docx", "sha256": "e" * 64}
            ],
        },
        "methodology": {
            "declared": "CB_SEM",
            "playbook_id": "CB_SEM_PLAYBOOK",
            "playbook_version": "1.0",
            "design": "cross_sectional",
        },
        "instrument": {
            "items": [
                {
                    "code": code,
                    "text": f"{code} statement.",
                    "construct_ref": "XA" if code.startswith("XA") else "XB",
                    "scale": {"type": "likert", "min": 1, "max": 7},
                    "reverse_coded": False,
                    "column_hint": f"Q{index + 10}",
                }
                for index, code in enumerate(_ITEMS)
            ]
        },
        "constructs": [
            {
                "code": "XA",
                "name": "XA",
                "level": "first_order",
                "measurement": "reflective",
                "indicators": ["XA1", "XA2", "XA3"],
            },
            {
                "code": "XB",
                "name": "XB",
                "level": "first_order",
                "measurement": "reflective",
                "indicators": ["XB1", "XB2", "XB3"],
            },
        ],
        "model": {"exogenous": ["XA"], "endogenous": ["XB"]},
        "hypotheses": [
            {"id": "H1", "effect": "direct", "from": "XA", "to": "XB", "sign": "positive"}
        ],
        "data": data_block,
    }
    config.update(overrides)
    return config


def _columns(config: dict[str, Any]) -> list[str]:
    data = config["data"]
    columns = []
    if data.get("id_column"):
        columns.append(data["id_column"])
    if data.get("consent_column"):
        columns.append(data["consent_column"])
    columns += [item["column_hint"] for item in config["instrument"]["items"]]
    columns += [check["column"] for check in data.get("attention_checks") or []]
    return columns


def _write(
    tmp_path: Path, config: dict[str, Any], cases: list[dict[str, str]]
) -> tuple[Path, StudyConfig]:
    columns = _columns(config)
    hint_to_code = {i["column_hint"]: i["code"] for i in config["instrument"]["items"]}
    texts = [f"{hint_to_code[c]} - statement." if c in hint_to_code else c for c in columns]
    rows = [columns, texts, [f"import:{c}" for c in columns]]
    for case in cases:
        rows.append([case.get(column, "") for column in columns])
    path = tmp_path / "mini.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
    return path, validate_and_build(StudyConfig, config)


def _case(case_id: str, values: dict[str, str] | None = None, **extra: str) -> dict[str, str]:
    base = {"ResponseId": case_id, "Q3": "1", "A1": "5"}
    ordinal = int(case_id.split("_")[1])
    for index in range(len(_ITEMS)):
        # ordinal encoded in binary across items: every default vector is
        # unique (ordinals < 64), so vector-dedup never eats a fixture case
        base[f"Q{index + 10}"] = str(3 + ((ordinal >> index) & 1))
    base.update(values or {})
    base.update(extra)
    return base


def _policy(tmp_path: Path | None = None, mutate: Any = None) -> Policy:
    template = REPO / "policy" / "decision_policy.template.yaml"
    if mutate is None:
        return Policy.load(template, mode="certification")
    assert tmp_path is not None
    data = yaml.safe_load(template.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "edge_policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return Policy.load(path, mode="certification")


class _DoctoredPolicy:
    """A policy double for unsupported-value guards (schema forbids these
    values in real policies; the pipeline must halt, not improvise)."""

    def __init__(self, **rules: object) -> None:
        self._rules = rules
        self._template = Policy.load(
            REPO / "policy" / "decision_policy.template.yaml", mode="certification"
        )

    def rule(self, path: str) -> object:
        if path in self._rules:
            return self._rules[path]
        return self._template.rule(path)


def test_missing_id_column_declaration_halts(tmp_path: Path) -> None:
    config = _mini_config(data={"id_column": None})
    cases = [_case(f"R_{i:03d}") for i in range(1, 5)]
    for case in cases:
        del case["ResponseId"]
    path, built = _write(tmp_path, config, cases)
    with pytest.raises(IntegrityHalt) as excinfo:
        run_prep(path, built, _policy())
    assert "id column" in excinfo.value.message


def test_absent_consent_column_is_a_zero_drop_link(tmp_path: Path) -> None:
    config = _mini_config(data={"consent_column": None})
    cases = [_case(f"R_{i:03d}") for i in range(1, 7)]
    for case in cases:
        del case["Q3"]
    path, built = _write(tmp_path, config, cases)
    result = run_prep(path, built, _policy())
    consent = next(link for link in result.n_chain.links if link.name == "consent")
    assert consent.dropped_n == 0


def test_case_failing_two_attention_checks_drops_once(tmp_path: Path) -> None:
    config = _mini_config(
        data={
            "attention_checks": [
                {"column": "A1", "expected": "5"},
                {"column": "A2", "expected": "1"},
            ]
        }
    )
    cases = [_case(f"R_{i:03d}", A2="1") for i in range(1, 7)]
    cases.append(_case("R_007", A1="2", A2="9"))  # fails both checks
    path, built = _write(tmp_path, config, cases)
    result = run_prep(path, built, _policy())
    link = next(link for link in result.n_chain.links if link.name == "attention_checks")
    assert link.dropped_cases == ("R_007",)
    assert [e["case"] for e in result.screening["attention_fails"]] == ["R_007"]


def test_unparseable_cell_is_out_of_range_metadata(tmp_path: Path) -> None:
    config = _mini_config()
    cases = [_case(f"R_{i:03d}") for i in range(1, 7)]
    cases[2]["Q12"] = "abc"  # XA3, non-numeric
    path, built = _write(tmp_path, config, cases)
    result = run_prep(path, built, _policy())
    assert {"case": "R_003", "item": "XA3"} in result.screening["out_of_range"]
    assert np.isnan(result.frame.loc["R_003", "XA3"])


def test_item_missing_beyond_policy_pct_is_flagged(tmp_path: Path) -> None:
    config = _mini_config()
    cases = [_case(f"R_{i:03d}") for i in range(1, 9)]
    for case in cases[:3]:  # XB3 missing in 3 of 8 profiled cases (37.5% > 20%)
        case["Q15"] = ""
    path, built = _write(tmp_path, config, cases)
    result = run_prep(path, built, _policy())
    flagged_items = [e["item"] for e in result.screening["items_missing_over_policy_pct"]]
    assert flagged_items == ["XB3"]


def test_zero_variance_item_skips_univariate_scoring(tmp_path: Path) -> None:
    config = _mini_config()
    cases = [_case(f"R_{i:03d}", {"Q14": "4"}) for i in range(1, 8)]  # XB2 constant
    path, built = _write(tmp_path, config, cases)
    result = run_prep(path, built, _policy())
    assert all("XB2" not in c for e in result.outliers["flagged"] for c in e["criteria"])


def test_mahalanobis_criterion_flags_pattern_breaking_case(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    config = _mini_config()
    cases = []
    for i in range(1, 31):  # one shared latent: XA and XB move together
        latent = rng.normal(0.0, 0.8)
        values = {
            f"Q{index + 10}": str(int(np.clip(round(4 + latent + rng.normal(0, 0.3)), 2, 6)))
            for index in range(6)
        }
        cases.append(_case(f"R_{i:03d}", values))
    # in-range on every item, impossible as a combination: XA high, XB low
    cases.append(
        _case("R_031", {"Q10": "6", "Q11": "6", "Q12": "6", "Q13": "2", "Q14": "2", "Q15": "2"})
    )
    path, built = _write(tmp_path, config, cases)

    def widen_univariate(data: dict[str, Any]) -> None:
        data["prep"]["outliers"]["univariate_z"] = 4.0
        data["prep"]["outliers"]["mahalanobis_p"] = 0.01

    result = run_prep(path, built, _policy(tmp_path, widen_univariate))
    flagged = {e["case"]: e["criteria"] for e in result.outliers["flagged"]}
    assert "R_031" in flagged
    assert "mahalanobis" in flagged["R_031"]


def test_unsupported_straightliner_method_halts(tmp_path: Path) -> None:
    config = _mini_config()
    path, built = _write(tmp_path, config, [_case(f"R_{i:03d}") for i in range(1, 5)])
    policy = _DoctoredPolicy(**{"prep.straightliner.method": "longstring"})
    with pytest.raises(IntegrityHalt) as excinfo:
        run_prep(path, built, policy)  # type: ignore[arg-type]
    assert "straight-liner" in excinfo.value.message


def test_unsupported_completion_basis_halts(tmp_path: Path) -> None:
    config = _mini_config()
    path, built = _write(tmp_path, config, [_case(f"R_{i:03d}") for i in range(1, 5)])
    policy = _DoctoredPolicy(**{"prep.inclusion_threshold.basis": "all_items"})
    with pytest.raises(IntegrityHalt) as excinfo:
        run_prep(path, built, policy)  # type: ignore[arg-type]
    assert "basis" in excinfo.value.message


def test_unsupported_outlier_treatment_halts(tmp_path: Path) -> None:
    config = _mini_config()
    path, built = _write(tmp_path, config, [_case(f"R_{i:03d}") for i in range(1, 5)])
    policy = _DoctoredPolicy(**{"prep.outliers.treatment": "winsorize"})
    with pytest.raises(IntegrityHalt) as excinfo:
        run_prep(path, built, policy)  # type: ignore[arg-type]
    assert "outlier treatment" in excinfo.value.message


def test_sign_flip_screening_skips_item_without_prepared_siblings(tmp_path: Path) -> None:
    # Schema-valid but V2-defective contract: XB's indicator list names ghost
    # items, and XB3 is declared reverse-coded. The screening pass has no
    # prepared siblings to verify against and must skip, not crash — the
    # invariant gate (I2) is where unverifiable reversal refuses to pass.
    config = _mini_config()
    config["constructs"][1]["indicators"] = ["GH1", "GH2"]
    config["instrument"]["items"][5]["reverse_coded"] = True  # XB3
    path, built = _write(tmp_path, config, [_case(f"R_{i:03d}") for i in range(1, 7)])
    result = run_prep(path, built, _policy())
    assert result.screening["reverse_coding_violations"] == []
    with pytest.raises(IntegrityHalt) as excinfo:
        invariants.i2_reverse_sign_flip(result.frame, built)
    assert "no siblings" in str(excinfo.value.to_report()["details"])


def test_n_chain_reconciliation_tripwire_fires_on_tampering() -> None:
    accountant = NChainAccountant(("R_001", "R_002", "R_003"))
    accountant.apply("duplicates", dropped=("R_002",))
    accountant._current = ("R_001",)  # tamper: bypass the ledger
    with pytest.raises(IntegrityHalt) as excinfo:
        accountant.finalize()
    assert "reconciliation" in excinfo.value.message


def test_frame_chain_disagreement_tripwire(tmp_path: Path, monkeypatch: Any) -> None:
    from burhan.prep import n_chain as n_chain_module

    config = _mini_config()
    path, built = _write(tmp_path, config, [_case(f"R_{i:03d}") for i in range(1, 6)])
    original = n_chain_module.NChainAccountant.finalize

    def lying_finalize(self: Any) -> Any:
        chain = original(self)
        return type(chain)(
            raw_n=chain.raw_n,
            final_n=chain.final_n - 1,
            links=chain.links,
            final_cases=chain.final_cases[:-1],
        )

    monkeypatch.setattr(n_chain_module.NChainAccountant, "finalize", lying_finalize)
    with pytest.raises(IntegrityHalt) as excinfo:
        run_prep(path, built, _policy())
    assert "disagree" in excinfo.value.message


def test_littles_skips_an_entirely_missing_case_row() -> None:
    rng = np.random.default_rng(4)
    frame = pd.DataFrame(
        rng.normal(4, 1, size=(30, 4)),
        columns=["XA1", "XA2", "XB1", "XB2"],
        index=pd.Index([f"R_{i:03d}" for i in range(1, 31)], name="case"),
    )
    frame.iloc[0] = np.nan  # a fully-empty row contributes nothing
    frame.iloc[5, 0] = np.nan
    d2, df, p = littles_mcar(frame)
    assert df > 0 and 0.0 <= p <= 1.0


def test_unknown_treatment_selector_halts() -> None:
    frame = pd.DataFrame({"XA1": [4.0, 5.0, np.nan], "XA2": [4.0, 4.0, 5.0]})
    with pytest.raises(IntegrityHalt) as excinfo:
        missingness_report(frame, _policy(), select="both")
    assert "selector" in excinfo.value.message


def test_i5_resolves_second_order_through_components() -> None:
    from generator import build_golden

    data = build_golden(11).config
    data["constructs"].append(
        {
            "code": "ENB",
            "name": "Enablement",
            "level": "second_order",
            "measurement": "reflective",
            "components": ["RES", "CUL"],
        }
    )
    data["higher_order"] = {
        "approach": "repeated_indicator",
        "structural_carry": "full_hierarchy",
    }
    data["model"]["exogenous"] = ["ENB"]
    data["hypotheses"].append(
        {"id": "H3", "effect": "direct", "from": "ENB", "to": "INT", "sign": "positive"}
    )
    config = validate_and_build(StudyConfig, data)
    columns = {i.code: [4.0, 5.0, 4.0, 3.0, 5.0] for i in config.instrument.items}
    frame = pd.DataFrame(columns, index=pd.Index([f"R_{i}" for i in range(5)], name="case"))
    invariants.i5_paths_resolvable(frame, config)  # ENB measured via components


def test_i7_higher_order_block_without_second_order_trips() -> None:
    from generator import build_golden

    data = build_golden(11).config
    data["higher_order"] = {
        "approach": "repeated_indicator",
        "structural_carry": "full_hierarchy",
    }
    config = validate_and_build(StudyConfig, data)
    frame = pd.DataFrame(
        {i.code: [4.0, 5.0] for i in config.instrument.items},
        index=pd.Index(["R_1", "R_2"], name="case"),
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        invariants.i7_higher_order(frame, config)
    assert "without second-order" in str(excinfo.value.to_report()["details"])


def test_i7_component_without_prepared_items_trips() -> None:
    from generator import build_golden

    data = build_golden(11).config
    data["constructs"].append(
        {
            "code": "XGH",
            "name": "Ghost-measured",
            "level": "first_order",
            "measurement": "reflective",
            "indicators": ["GH1", "GH2"],
        }
    )
    data["constructs"].append(
        {
            "code": "ENB",
            "name": "Enablement",
            "level": "second_order",
            "measurement": "reflective",
            "components": ["RES", "XGH"],
        }
    )
    data["higher_order"] = {
        "approach": "repeated_indicator",
        "structural_carry": "full_hierarchy",
    }
    config = validate_and_build(StudyConfig, data)
    frame = pd.DataFrame(
        {i.code: [4.0, 5.0] for i in config.instrument.items},
        index=pd.Index(["R_1", "R_2"], name="case"),
    )
    with pytest.raises(IntegrityHalt) as excinfo:
        invariants.i7_higher_order(frame, config)
    assert "XGH" in str(excinfo.value.to_report()["details"])
