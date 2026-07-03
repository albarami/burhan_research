"""Golden-dataset generator CORE (FR-1501; TC-08a subset — TC-08c completes the matrix).

Deterministic by construction: every draw comes from ``numpy``'s seeded
``default_rng``; no ambient RNG, no clocks (timestamps are synthesized from
case ordinals). Each build returns the export rows (Qualtrics dialect,
three header rows), a schema-valid study-config dict, and a ground-truth
manifest naming exactly what was planted — the pipeline's detections are
measured against that manifest, class by class (AT-M08-1).

Planted defect classes (one instrument, 12 items, RS4/CU4 reverse-coded):

- ``duplicates`` — a repeated ResponseId (later occurrence keyed ``id#2``)
  and an identical-model-vector twin (policy ``prep.duplicates.keys``).
- ``attention_fails`` — the Q9_4 check answered off-expectation.
- ``straight_liners`` — zero variance across the first 8 model items.
- ``out_of_range`` — cells outside the declared 1..7 scale.
- ``un_reversed`` — CU4 stored unflipped although declared reverse-coded;
  the clean twin stores it correctly (AT-M08-8).
- ``engineered_missingness`` — blank cells on partial cases.
- ``partials_recovered`` / ``partials_dropped`` — 11/12 ≈ 91.7% (recovered
  at the ≥90% policy threshold) vs 8/12 ≈ 66.7% (dropped) (AT-M08-2).
- ``known_outliers`` — a coherent extreme responder (reversed items stored
  at the mirrored extreme), no constant run ≥ 8.

The missingness fixtures (AT-M08-7) reuse the same instrument with exactly
one blank cell per affected case (11/12 stays above the recovery
threshold): ``mcar`` scatters cells uniformly; ``mnar`` blanks CU2 exactly
where its own underlying response is high — missingness depending on the
unobserved value itself.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

DEFECT_CLASSES = (
    "duplicates",
    "attention_fails",
    "straight_liners",
    "out_of_range",
    "un_reversed",
    "engineered_missingness",
    "partials_recovered",
    "partials_dropped",
    "known_outliers",
)

_ITEMS = (
    ("RS1", "RES", "Q4_1", False),
    ("RS2", "RES", "Q4_2", False),
    ("RS3", "RES", "Q4_3", False),
    ("RS4", "RES", "Q4_4", True),
    ("CU1", "CUL", "Q5_1", False),
    ("CU2", "CUL", "Q5_2", False),
    ("CU3", "CUL", "Q5_3", False),
    ("CU4", "CUL", "Q5_4", True),
    ("IN1", "INT", "Q6_1", False),
    ("IN2", "INT", "Q6_2", False),
    ("IN3", "INT", "Q6_3", False),
    ("IN4", "INT", "Q6_4", False),
)
_CONSTRUCTS = ("RES", "CUL", "INT")
_COLUMNS = (
    ["ResponseId", "Q3"]
    + [hint for _, _, hint, _ in _ITEMS]
    + ["Q9_4", "Q42", "Progress", "Finished", "StartDate"]
)
_ITEM_OFFSET = 2  # first item column index
_ATTENTION_INDEX = _ITEM_OFFSET + len(_ITEMS)
_N_CLEAN = 32


def _config_dict() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "meta": {
            "study_id": "golden-adoption-2026",
            "title": "Golden certification study (generator core)",
            "source_documents": [
                {"role": "study_document", "path": "inputs/golden.docx", "sha256": "d" * 64}
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
                    "text": f"{code} statement about adoption.",
                    "construct_ref": construct,
                    "scale": {"type": "likert", "min": 1, "max": 7},
                    "reverse_coded": reverse,
                    "column_hint": hint,
                }
                for code, construct, hint, reverse in _ITEMS
            ]
        },
        "constructs": [
            {
                "code": construct,
                "name": construct,
                "level": "first_order",
                "measurement": "reflective",
                "indicators": [code for code, ref, _, _ in _ITEMS if ref == construct],
            }
            for construct in _CONSTRUCTS
        ],
        "model": {"exogenous": ["RES"], "endogenous": ["CUL", "INT"]},
        "hypotheses": [
            {"id": "H1", "effect": "direct", "from": "RES", "to": "CUL", "sign": "positive"},
            {"id": "H2", "effect": "direct", "from": "CUL", "to": "INT", "sign": "positive"},
        ],
        "data": {
            "file": "inputs/golden.csv",
            "format": "csv",
            "export_dialect": "qualtrics",
            "header_rows": 3,
            "id_column": "ResponseId",
            "consent_column": "Q3",
            "completion": {"progress_column": "Progress", "finished_column": "Finished"},
            "attention_checks": [{"column": "Q9_4", "expected": "5"}],
            "demographics": [{"code": "firm_size", "column_hint": "Q42", "type": "ordinal"}],
            "metadata_columns": ["StartDate"],
        },
    }


def _header_rows() -> list[list[str]]:
    texts = ["Response ID", "I consent to participate in this study."]
    texts += [f"{code} - {code} statement about adoption." for code, _, _, _ in _ITEMS]
    texts += [
        "Attention check: please select 5.",
        "What is the size of your firm?",
        "Progress",
        "Finished",
        "Start Date",
    ]
    import_ids = [f'{{"ImportId":"{column}"}}' for column in _COLUMNS]
    return [list(_COLUMNS), texts, import_ids]


def _raw_item_values(rng: np.random.Generator) -> list[int]:
    """One case's raw (pre-storage) responses: tight, construct-consistent.

    Clean draws stay within 2..6 so no legitimate case can cross the
    |z| > 3.29 univariate outlier criterion — planted outliers use the
    scale extremes and are the only cases that can flag (AT-M08-1's
    zero-false-positive requirement is engineered, not lucky).
    """
    latents = {construct: rng.normal(0.0, 0.55) for construct in _CONSTRUCTS}
    values = []
    for _, construct, _, _ in _ITEMS:
        value = 4.0 + latents[construct] + rng.normal(0.0, 0.45)
        values.append(int(np.clip(round(value), 2, 6)))
    return values


def _stored(values: list[int], *, un_reverse_cu4: bool) -> list[str]:
    """Storage form: reverse-coded items are flipped at collection.

    Runs of identical stored answers are capped at 5 so no clean case can
    ever trip the ≥8 zero-variance screen — straight-lining exists only
    where the manifest plants it (zero false positives by construction).
    """
    stored = []
    for (code, _, _, reverse), value in zip(_ITEMS, values, strict=True):
        flip = reverse and not (un_reverse_cu4 and code == "CU4")
        stored.append(8 - value if flip else value)
    run_value, run_length = None, 0
    for position, value in enumerate(stored):
        if value == run_value:
            run_length += 1
        else:
            run_value, run_length = value, 1
        if run_length == 5:
            stored[position] = value + 1 if value < 6 else value - 1
            run_value, run_length = stored[position], 1
    return [str(value) for value in stored]


@dataclass(frozen=True)
class GoldenStudy:
    """One generated study: export rows, contract dict, ground truth."""

    config: dict[str, Any]
    rows: list[list[str]]
    manifest: dict[str, list[dict[str, str]]]

    def column_index(self, item_code: str) -> int:
        for index, (code, _, _, _) in enumerate(_ITEMS):
            if code == item_code:
                return _ITEM_OFFSET + index
        raise KeyError(item_code)

    def write(self, directory: Path) -> Path:
        path = directory / "golden.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(self.rows)
        return path


def _case_row(
    case_id: str, items: list[str], rng: np.random.Generator, *, attention: str = "5"
) -> list[str]:
    firm_size = str(int(rng.integers(1, 6)))
    ordinal = int(case_id.split("_")[1].split("#")[0])
    timestamp = f"2026-06-01 09:{ordinal % 60:02d}"
    complete = all(cell != "" for cell in items)
    progress = "100" if complete else str(round(100 * sum(c != "" for c in items) / len(items)))
    finished = "1" if complete else "0"
    return [case_id, "1", *items, attention, firm_size, progress, finished, timestamp]


def build_golden(seed: int, *, with_defects: bool = True) -> GoldenStudy:
    """The golden study: 32 clean cases plus the planted-defect block."""
    rng = np.random.default_rng(seed)
    manifest: dict[str, list[dict[str, str]]] = {name: [] for name in DEFECT_CLASSES}
    raw_values = [_raw_item_values(rng) for _ in range(_N_CLEAN)]
    rows = _header_rows()
    for index, values in enumerate(raw_values, start=1):
        stored = _stored(values, un_reverse_cu4=with_defects)
        rows.append(_case_row(f"R_{index:03d}", stored, rng))
    if not with_defects:
        return GoldenStudy(config=_config_dict(), rows=rows, manifest=manifest)

    manifest["un_reversed"].append({"item": "CU4"})

    def plant(case_id: str, items: list[str], *, attention: str = "5") -> None:
        rows.append(_case_row(case_id, items, rng, attention=attention))

    # duplicates: repeated ResponseId (exact row copy) + identical model vector
    plant("R_001", list(rows[3][_ITEM_OFFSET:_ATTENTION_INDEX]))
    manifest["duplicates"].append(
        {"case": "R_001#2", "response_id": "R_001", "kind": "response_id"}
    )
    plant("R_034", list(rows[4][_ITEM_OFFSET:_ATTENTION_INDEX]))
    manifest["duplicates"].append(
        {"case": "R_034", "response_id": "R_034", "kind": "identical_model_vector"}
    )
    # attention fail
    plant("R_035", _stored(_raw_item_values(rng), un_reverse_cu4=True), attention="3")
    manifest["attention_fails"].append({"case": "R_035"})
    # straight-liner: constant across the first 8 model items
    liner = _stored(_raw_item_values(rng), un_reverse_cu4=True)
    liner[:8] = ["4"] * 8
    plant("R_036", liner)
    manifest["straight_liners"].append({"case": "R_036"})
    # out-of-range cells (one above range, one below)
    high = _stored(_raw_item_values(rng), un_reverse_cu4=True)
    high[1] = "9"  # RS2
    plant("R_037", high)
    manifest["out_of_range"].append({"case": "R_037", "item": "RS2"})
    low = _stored(_raw_item_values(rng), un_reverse_cu4=True)
    low[5] = "0"  # CU2
    plant("R_038", low)
    manifest["out_of_range"].append({"case": "R_038", "item": "CU2"})
    # partials: recovered at 11/12 ≈ 91.7%; dropped at 8/12 ≈ 66.7%
    recovered = _stored(_raw_item_values(rng), un_reverse_cu4=True)
    recovered[10] = ""  # IN3
    plant("R_039", recovered)
    manifest["partials_recovered"].append({"case": "R_039"})
    manifest["engineered_missingness"].append({"case": "R_039", "item": "IN3"})
    dropped = _stored(_raw_item_values(rng), un_reverse_cu4=True)
    for position, code in ((0, "RS1"), (4, "CU1"), (8, "IN1"), (9, "IN2")):
        dropped[position] = ""
        manifest["engineered_missingness"].append({"case": "R_040", "item": code})
    plant("R_040", dropped)
    manifest["partials_dropped"].append({"case": "R_040"})
    # known outlier: coherent extreme responder (reversed items mirrored),
    # varied enough to avoid any constant run of 8
    plant("R_041", ["7", "7", "6", "1", "7", "7", "6", "2", "7", "6", "7", "7"])
    manifest["known_outliers"].append({"case": "R_041"})
    return GoldenStudy(config=_config_dict(), rows=rows, manifest=manifest)


def build_adversarial(seed: int) -> GoldenStudy:
    """The overlapping-defect fixture (AT-M08-3; TC-08c matrix).

    Each planted case carries two defect classes at once; the N-chain must
    drop it exactly once at the FIRST applicable link (or keep it, when
    neither class drops). Ground truth lives in
    ``manifest["adversarial_overlaps"]`` as
    ``{case, classes, dropped_at}`` with ``dropped_at == ""`` for the
    surviving case (a recovered partial that is also a flagged, retained
    outlier).
    """
    rng = np.random.default_rng(seed)
    manifest: dict[str, list[dict[str, str]]] = {name: [] for name in DEFECT_CLASSES}
    manifest["adversarial_overlaps"] = []
    rows = _header_rows()
    for index in range(1, 33):  # golden-sized base: the outlier criterion
        # needs enough clean cases that one extreme cannot inflate the sd
        stored = _stored(_raw_item_values(rng), un_reverse_cu4=False)
        rows.append(_case_row(f"R_{index:03d}", stored, rng))

    def plant(
        case_id: str, items: list[str], classes: str, dropped_at: str, *, attention: str = "5"
    ) -> None:
        rows.append(_case_row(case_id, items, rng, attention=attention))
        manifest["adversarial_overlaps"].append(
            {"case": case_id, "classes": classes, "dropped_at": dropped_at}
        )

    # id-duplicate that also fails the attention check → leaves at duplicates
    plant(
        "R_001",
        list(rows[3][_ITEM_OFFSET:_ATTENTION_INDEX]),
        "duplicates+attention_fails",
        "duplicates",
        attention="2",
    )
    manifest["adversarial_overlaps"][-1]["case"] = "R_001#2"
    # straight-liner carrying an out-of-range cell → leaves at straight_liners
    liner = _stored(_raw_item_values(rng), un_reverse_cu4=False)
    liner[:8] = ["4"] * 8
    liner[10] = "9"
    plant("R_033", liner, "straight_liners+out_of_range", "straight_liners")
    # attention failure that is also a below-threshold partial → leaves at attention
    partial = _stored(_raw_item_values(rng), un_reverse_cu4=False)
    for position in (1, 5, 9):
        partial[position] = ""
    plant("R_034", partial, "attention_fails+partials_dropped", "attention_checks", attention="3")
    # extreme responder missing one cell → recovered partial AND flagged outlier,
    # retained under the policy treatment: survives every link
    plant(
        "R_035",
        ["7", "7", "6", "1", "7", "7", "6", "2", "7", "6", "7", ""],
        "known_outliers+partials_recovered",
        "",
    )
    return GoldenStudy(config=_config_dict(), rows=rows, manifest=manifest)


def build_missingness_fixture(kind: Literal["mcar", "mnar"], seed: int) -> GoldenStudy:
    """AT-M08-7 fixtures: same instrument, engineered missingness only.

    One blank cell per affected case keeps completion at 11/12 ≈ 91.7%,
    above the ≥90% recovery threshold — the mechanism test sees the
    missingness instead of the partial screen removing it.
    """
    rng = np.random.default_rng(seed)
    manifest: dict[str, list[dict[str, str]]] = {name: [] for name in DEFECT_CLASSES}
    rows = _header_rows()
    n_cases = 60
    rs1_index, cu2_index = 0, 5

    def fixture_values() -> list[int]:
        # Tighter latent coupling than the golden base: pattern-group means
        # must carry the mechanism signal for Little's test to see it.
        latents = {construct: rng.normal(0.0, 0.9) for construct in _CONSTRUCTS}
        return [
            int(np.clip(round(4.0 + latents[construct] + rng.normal(0.0, 0.25)), 1, 7))
            for _, construct, _, _ in _ITEMS
        ]

    for index in range(1, n_cases + 1):
        values = fixture_values()
        stored = _stored(values, un_reverse_cu4=False)
        mcar_hit = rng.random() < 0.3
        if kind == "mcar":
            if mcar_hit:
                position = int(rng.integers(0, len(_ITEMS)))
                stored[position] = ""
                manifest["engineered_missingness"].append(
                    {"case": f"R_{index:03d}", "item": _ITEMS[position][0]}
                )
        else:
            # mnar: missingness depends on the unobserved value itself, in
            # opposite directions on two items — high CU2 scorers go silent
            # on CU2, low RS1 scorers skip RS1.
            if values[cu2_index] >= 5:
                stored[cu2_index] = ""
                manifest["engineered_missingness"].append({"case": f"R_{index:03d}", "item": "CU2"})
            if values[rs1_index] <= 3:
                stored[rs1_index] = ""
                manifest["engineered_missingness"].append({"case": f"R_{index:03d}", "item": "RS1"})
            if values[cu2_index] >= 5 and values[rs1_index] >= 5:
                stored[rs1_index + 1] = ""  # extreme profiles also skip RS2
                manifest["engineered_missingness"].append({"case": f"R_{index:03d}", "item": "RS2"})
        rows.append(_case_row(f"R_{index:03d}", stored, rng))
    return GoldenStudy(config=_config_dict(), rows=rows, manifest=manifest)
