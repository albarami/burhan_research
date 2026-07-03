"""Absence tests (AT-M08-4; FR-505; standards §3).

Mean substitution and synthetic-case generation are impossible by
construction: no code path exists. Proven three ways — source-token scan
over the whole prep layer, public-surface introspection, and behavior
(prepared cases are a subset of raw cases; missing stays missing).
"""

from __future__ import annotations

from pathlib import Path

from generator import build_golden

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.policy import Policy

REPO = Path(__file__).resolve().parents[3]
PREP_SOURCES = sorted((REPO / "src" / "burhan" / "prep").rglob("*.py"))


def test_prep_layer_exists_and_scan_covers_it() -> None:
    names = {path.name for path in PREP_SOURCES}
    assert {"n_chain.py", "invariants.py", "pipeline.py", "missingness.py"} <= names


def test_no_mean_substitution_code_path() -> None:  # AT-M08-4 (FR-505)
    forbidden = ("fillna", "SimpleImputer", "impute(", "interpolate", "replace_nan")
    for path in PREP_SOURCES:
        source = path.read_text(encoding="utf-8")
        hits = [token for token in forbidden if token in source]
        assert hits == [], f"{path.name}: {hits}"


def test_no_synthetic_case_code_path() -> None:  # AT-M08-4 (FR-505)
    # Nothing in prep concatenates, samples, resamples, or fabricates rows
    # (list.append of bookkeeping records is not row fabrication; the
    # behavioral subset test below carries that weight).
    forbidden = ("concat(", ".sample(", "resample", "SMOTE", "faker", "synthetic_case")
    for path in PREP_SOURCES:
        source = path.read_text(encoding="utf-8")
        hits = [token for token in forbidden if token in source]
        assert hits == [], f"{path.name}: {hits}"


def test_prep_public_surface_has_no_fill_or_generate_door() -> None:  # AT-M08-4
    import burhan.prep.py_impl.missingness as missingness
    import burhan.prep.py_impl.pipeline as pipeline

    banned_fragments = ("fill", "impute", "synthesi", "generate", "fabricat", "substitut")
    for module in (pipeline, missingness):
        public = [name for name in dir(module) if not name.startswith("_")]
        offenders = [
            name
            for name in public
            if any(fragment in name.lower() for fragment in banned_fragments)
        ]
        assert offenders == []


def test_behavior_no_new_cases_and_missing_stays_missing(tmp_path: Path) -> None:
    from burhan.prep.py_impl.pipeline import run_prep

    golden = build_golden(11, with_defects=True)
    config = validate_and_build(StudyConfig, golden.config)
    policy = Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")
    result = run_prep(golden.write(tmp_path), config, policy)

    raw_ids = {row[0] for row in golden.rows[3:]}
    prepared_ids = {case.split("#")[0] for case in result.frame.index}
    assert prepared_ids <= raw_ids  # never a case that was not collected

    # every engineered-missing cell of a surviving case is still missing
    import math

    for entry in golden.manifest["engineered_missingness"]:
        if entry["case"] in result.frame.index:
            assert math.isnan(result.frame.loc[entry["case"], entry["item"]])
