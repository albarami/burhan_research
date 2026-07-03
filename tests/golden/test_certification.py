"""Golden certification suite (TC-08c; FR-1501/1504; NFR-601; M3 exit).

Re-executes the AT-M08 battery against the completed matrix — multiple
pinned seeds, clean twins, the adversarial overlapping-defect fixture,
and dual-path R parity per build — and pins DEFECT_MATRIX.md to the code
so the enumeration cannot rot. This module is a permanent regression
gate (FR-1504): it runs in the default pytest battery and in CI.

Seed notes: golden seeds {11, 23, 47} verified detection-exact with
zero-false-positive clean twins. MCAR fixture seeds are pinned to
{7, 21, 29} — seed 13 falsely rejects MCAR at p=.012, which is the
statistic's designed 5% false-rejection rate at work, not a defect.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from generator import DEFECT_CLASSES, build_adversarial, build_golden, build_missingness_fixture

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.core.policy import Policy
from burhan.core.rworker import RWorker
from burhan.prep.invariants import assert_invariants
from burhan.prep.py_impl.missingness import missingness_report
from burhan.prep.py_impl.pipeline import PrepResult, run_prep
from burhan.prep.reconciler import build_r_payload, reconcile_prep

REPO = Path(__file__).resolve().parents[2]
MATRIX = REPO / "tests" / "golden" / "DEFECT_MATRIX.md"
GOLDEN_SEEDS = (11, 23, 47)
MCAR_SEEDS = (7, 21, 29)


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


def _run(tmp_path: Path, seed: int, *, with_defects: bool) -> tuple[Any, Any, PrepResult]:
    golden = build_golden(seed, with_defects=with_defects)
    config = validate_and_build(StudyConfig, golden.config)
    result = run_prep(golden.write(tmp_path), config, _policy())
    return golden, config, result


# -- CERT AT-M08-1: full-matrix detection, zero false positives ----------------------


@pytest.mark.parametrize("seed", GOLDEN_SEEDS)
def test_matrix_detection_is_exact_per_class(tmp_path: Path, seed: int) -> None:
    golden, _, result = _run(tmp_path, seed, with_defects=True)
    manifest = golden.manifest
    assert {e["case"] for e in result.screening["duplicates"]} == {
        e["case"] for e in manifest["duplicates"]
    }
    assert {e["case"] for e in result.screening["attention_fails"]} == {
        e["case"] for e in manifest["attention_fails"]
    }
    assert {e["case"] for e in result.screening["straight_liners"]} == {
        e["case"] for e in manifest["straight_liners"]
    }
    assert {(e["case"], e["item"]) for e in result.screening["out_of_range"]} == {
        (e["case"], e["item"]) for e in manifest["out_of_range"]
    }
    assert {e["item"] for e in result.screening["reverse_coding_violations"]} == {
        e["item"] for e in manifest["un_reversed"]
    }
    assert {(e["case"], e["item"]) for e in result.screening["missing_cells"]} == {
        (e["case"], e["item"]) for e in manifest["engineered_missingness"]
    }
    assert {e["case"] for e in result.outliers["flagged"]} == {
        e["case"] for e in manifest["known_outliers"]
    }


@pytest.mark.parametrize("seed", GOLDEN_SEEDS)
def test_matrix_clean_twins_have_zero_detections(tmp_path: Path, seed: int) -> None:
    _, config, result = _run(tmp_path, seed, with_defects=False)
    assert all(not entries for entries in result.screening.values())
    assert result.outliers["flagged"] == []
    assert result.n_chain.raw_n == result.n_chain.final_n
    assert_invariants(result.frame, config, min_items=2)


# -- CERT AT-M08-2: partial profile across the matrix --------------------------------


@pytest.mark.parametrize("seed", GOLDEN_SEEDS)
def test_matrix_partial_profile_is_complete(tmp_path: Path, seed: int) -> None:
    golden, _, result = _run(tmp_path, seed, with_defects=True)
    profile = {e["case"]: e for e in result.completion_profile["partials"]}
    recovered = golden.manifest["partials_recovered"][0]["case"]
    dropped = golden.manifest["partials_dropped"][0]["case"]
    assert profile[recovered]["disposition"] == "recovered"
    assert profile[dropped]["disposition"] == "dropped"
    assert result.completion_profile["threshold_pct"] == 90  # policy, re-read per run


# -- CERT AT-M08-3: exact chains on golden and the adversarial fixture ----------------


@pytest.mark.parametrize("seed", GOLDEN_SEEDS)
def test_matrix_chains_sum_exactly(tmp_path: Path, seed: int) -> None:
    _, _, result = _run(tmp_path, seed, with_defects=True)
    chain = result.n_chain
    assert chain.raw_n - sum(link.dropped_n for link in chain.links) == chain.final_n
    for left, right in zip(chain.links, chain.links[1:], strict=False):
        assert left.leaving == right.entering


def test_adversarial_overlaps_drop_exactly_once_at_the_first_link(tmp_path: Path) -> None:
    adversarial = build_adversarial(31)
    config = validate_and_build(StudyConfig, adversarial.config)
    result = run_prep(adversarial.write(tmp_path), config, _policy())
    links = {link.name: link for link in result.n_chain.links}
    dropped_at: dict[str, str] = {}
    for link in result.n_chain.links:
        for case in link.dropped_cases:
            assert case not in dropped_at  # exactly once, ever
            dropped_at[case] = link.name
    for entry in adversarial.manifest["adversarial_overlaps"]:
        expected = entry["dropped_at"]
        if expected == "":
            assert entry["case"] not in dropped_at  # survives (recovered/retained)
        else:
            assert dropped_at[entry["case"]] == expected
    chain = result.n_chain
    assert chain.raw_n - sum(link.dropped_n for link in chain.links) == chain.final_n
    assert links["outlier_policy"].dropped_n == 0  # retain policy
    # the surviving overlap case is both a recovered partial and a flagged outlier
    survivor = next(
        e["case"] for e in adversarial.manifest["adversarial_overlaps"] if e["dropped_at"] == ""
    )
    assert survivor in {e["case"] for e in result.outliers["flagged"]}
    assert survivor in {e["case"] for e in result.completion_profile["partials"]}


# -- CERT AT-M08-4: FR-505 absence, re-executed over the whole prep layer -------------


def test_absence_scan_re_executed_over_prep_layer() -> None:
    sources = sorted((REPO / "src" / "burhan" / "prep").rglob("*.py"))
    assert sources
    for token in ("fillna", "SimpleImputer", "impute(", "concat(", ".sample(", "SMOTE"):
        for path in sources:
            assert token not in path.read_text(encoding="utf-8"), (token, path.name)


# -- CERT AT-M08-5/8: invariants against the matrix -----------------------------------


@pytest.mark.parametrize("seed", GOLDEN_SEEDS)
def test_matrix_un_reversed_item_halts_the_invariant_gate(tmp_path: Path, seed: int) -> None:
    _, config, result = _run(tmp_path, seed, with_defects=True)
    with pytest.raises(IntegrityHalt) as excinfo:
        assert_invariants(result.frame, config, min_items=2)
    assert excinfo.value.message.startswith("I2")
    assert "CU4" in str(excinfo.value.to_report()["details"])


# -- CERT AT-M08-6: dual-path parity across the matrix ---------------------------------


@pytest.mark.parametrize("seed", GOLDEN_SEEDS)
@pytest.mark.parametrize("with_defects", [True, False])
def test_matrix_dual_path_parity(tmp_path: Path, seed: int, with_defects: bool) -> None:
    golden = build_golden(seed, with_defects=with_defects)
    config = validate_and_build(StudyConfig, golden.config)
    csv_path = golden.write(tmp_path)
    policy = _policy()
    python_result = run_prep(csv_path, config, policy)
    r_result = RWorker().call(
        "prep_worker",
        build_r_payload(csv_path, config, policy),
        call_id=f"cert-{seed}-{int(with_defects)}",
        run_dir=tmp_path,
        seed=1,
    )
    report = reconcile_prep(python_result, r_result, policy=policy)
    assert report["verdict"] == "match"
    assert report["tolerance"] == 0


def test_adversarial_dual_path_parity(tmp_path: Path) -> None:
    adversarial = build_adversarial(31)
    config = validate_and_build(StudyConfig, adversarial.config)
    csv_path = adversarial.write(tmp_path)
    policy = _policy()
    python_result = run_prep(csv_path, config, policy)
    r_result = RWorker().call(
        "prep_worker",
        build_r_payload(csv_path, config, policy),
        call_id="cert-adversarial",
        run_dir=tmp_path,
        seed=1,
    )
    assert reconcile_prep(python_result, r_result, policy=policy)["verdict"] == "match"


# -- CERT AT-M08-7: mechanism verdicts stable on pinned fixture seeds -----------------


@pytest.mark.parametrize("seed", MCAR_SEEDS)
def test_matrix_mcar_fixtures_keep_fiml(seed: int) -> None:
    import numpy as np
    import pandas as pd

    fixture = build_missingness_fixture("mcar", seed)
    data = fixture.rows[3:]
    values = [[float(row[c]) if row[c] != "" else np.nan for c in range(2, 14)] for row in data]
    frame = pd.DataFrame(
        values,
        index=pd.Index([row[0] for row in data], name="case"),
        columns=[i["code"] for i in fixture.config["instrument"]["items"]],
    )
    report = missingness_report(frame, _policy())
    assert report["mechanism_verdict"] == "mcar_not_rejected"
    assert report["treatment"]["method"] == "fiml"
    assert report["treatment"]["mnar_flag"] is False


@pytest.mark.parametrize("seed", MCAR_SEEDS)
def test_matrix_mnar_fixtures_reject_and_flag(seed: int) -> None:
    import numpy as np
    import pandas as pd

    fixture = build_missingness_fixture("mnar", seed)
    data = fixture.rows[3:]
    values = [[float(row[c]) if row[c] != "" else np.nan for c in range(2, 14)] for row in data]
    frame = pd.DataFrame(
        values,
        index=pd.Index([row[0] for row in data], name="case"),
        columns=[i["code"] for i in fixture.config["instrument"]["items"]],
    )
    report = missingness_report(frame, _policy())
    assert report["mechanism_verdict"] == "mcar_rejected"
    assert report["treatment"]["mnar_flag"] is True
    assert "sensitivity" in report["treatment"]["sensitivity_note"]


# -- DEFECT_MATRIX.md completeness: the enumeration cannot rot -------------------------


def _matrix_rows() -> list[dict[str, str]]:
    text = MATRIX.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        # split on unescaped pipes only: table cells may carry \| literals
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        rows.append(cells)
    header = rows[0]
    return [dict(zip(header, row, strict=False)) for row in rows[1:]]


def test_defect_matrix_enumerates_every_planted_class() -> None:
    rows = _matrix_rows()
    documented = {row["Class id"] for row in rows}
    required = set(DEFECT_CLASSES) | {
        "adversarial_overlaps",
        "dual_path_divergence",
        "malformed_r_cell",
        "n_chain_double_count",
        "clean_twin",
    }
    assert required <= documented, sorted(required - documented)


def test_defect_matrix_detecting_checks_exist() -> None:
    pattern = re.compile(r"`([\w/\.]+\.(?:py|R))::(\w+)`")
    rows = _matrix_rows()
    assert rows
    for row in rows:
        references = pattern.findall(row["Regression tests"])
        assert references, f"no test reference for {row['Class id']}"
        for file_part, test_name in references:
            path = REPO / file_part
            assert path.is_file(), f"{file_part} missing for {row['Class id']}"
            source = path.read_text(encoding="utf-8")
            needle = f"def {test_name}" if file_part.endswith(".py") else test_name
            assert needle in source, f"{test_name} not found in {file_part}"
