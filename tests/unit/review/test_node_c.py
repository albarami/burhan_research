"""Node C gate adapters (AT-M07-1/2/4; FR-301/302/305).

Gate 1 audits the contract against its source; the four seeded corruption
fixtures each draw REJECT with fixes naming the defect. Gate 2 audits the
findings draft against the results store and decision log. Node C reviews
artifacts only: no write access, no compute API — proven by introspection,
attempted calls, and a source-token absence scan.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from review_util import (
    CORRUPTIONS,
    FAITHFUL_CONTRACT,
    StubProvider,
    approve_yaml,
    bad_draft,
    decision_log_text,
    document,
    good_draft,
    reject_yaml,
    results_store_text,
    settings,
)

from burhan.core.errors import IntegrityHalt
from burhan.review.node_c import NodeC

REPO = Path(__file__).resolve().parents[3]


def _node(responses: dict[str, str]) -> NodeC:
    return NodeC(settings(), provider_call=StubProvider(responses))


# -- AT-M07-1: Gate 1 — faithful approves; each seeded corruption REJECTs ------------


def test_gate1_approves_the_faithful_contract() -> None:  # AT-M07-1
    node = _node({"faithful": approve_yaml()})
    verdict = node.gate1(
        study_contract=FAITHFUL_CONTRACT.read_text(encoding="utf-8"),
        study_document=document("faithful"),
    )
    assert verdict.verdict == "approve"
    assert verdict.fixes == ()


CORRUPTION_CASES = [
    ("dropped_hypothesis.yaml", "H4b", "hypothesis H4b is in the source but missing"),
    ("swapped_mapping.yaml", "RS3", "RS3 is mapped to CUL; the source assigns it to RES"),
    ("wrong_methodology.yaml", "PLS_SEM", "contract declares PLS_SEM; the source declares CB-SEM"),
    ("missing_reverse_code.yaml", "RS3", "source declares RS3 reverse-coded; contract does not"),
]


@pytest.mark.parametrize(("fixture", "defect_token", "fix_text"), CORRUPTION_CASES)
def test_gate1_rejects_each_seeded_corruption_naming_the_defect(
    fixture: str, defect_token: str, fix_text: str
) -> None:  # AT-M07-1
    variant = fixture.removesuffix(".yaml")
    node = _node({variant: reject_yaml(fix_text)})
    verdict = node.gate1(
        study_contract=(CORRUPTIONS / fixture).read_text(encoding="utf-8"),
        study_document=document(variant),
    )
    assert verdict.verdict == "reject"
    assert any(defect_token in fix for fix in verdict.fixes)


def test_corruption_fixtures_carry_exactly_their_seeded_defect() -> None:
    """The fixture set is the deliverable that matters (TC-07 Delivery Notes)."""
    faithful = yaml.safe_load(FAITHFUL_CONTRACT.read_text(encoding="utf-8"))

    dropped = yaml.safe_load((CORRUPTIONS / "dropped_hypothesis.yaml").read_text())
    assert "H4b" in {h["id"] for h in faithful["hypotheses"]}
    assert "H4b" not in {h["id"] for h in dropped["hypotheses"]}

    swapped = yaml.safe_load((CORRUPTIONS / "swapped_mapping.yaml").read_text())
    refs = {i["code"]: i["construct_ref"] for i in swapped["instrument"]["items"]}
    assert refs["RS3"] == "CUL" and refs["CU3"] == "RES"
    indicators = {c["code"]: c.get("indicators") for c in swapped["constructs"]}
    assert "CU3" in indicators["RES"] and "RS3" in indicators["CUL"]  # V1/V2-consistent

    wrong = yaml.safe_load((CORRUPTIONS / "wrong_methodology.yaml").read_text())
    assert wrong["methodology"]["declared"] == "PLS_SEM"

    missing = yaml.safe_load((CORRUPTIONS / "missing_reverse_code.yaml").read_text())
    flags = {i["code"]: i["reverse_coded"] for i in missing["instrument"]["items"]}
    assert flags["RS3"] is False
    assert {i["code"]: i["reverse_coded"] for i in faithful["instrument"]["items"]}["RS3"] is True


# -- AT-M07-2: Gate 2 — draft vs results store + decision log -------------------------


def test_gate2_rejects_unsupported_claim_and_omitted_hypothesis() -> None:  # AT-M07-2
    node = _node(
        {
            "bad-draft": reject_yaml(
                "draft claims H4a supported; store shows p=0.41 (unsupported)",
                "failed hypothesis H4b omitted from the draft",
            )
        }
    )
    verdict = node.gate2(
        findings_draft=bad_draft("bad-draft"),
        results_store=results_store_text(),
        decision_log=decision_log_text(),
    )
    assert verdict.verdict == "reject"
    assert any("H4a" in fix for fix in verdict.fixes)
    assert any("H4b" in fix for fix in verdict.fixes)


def test_gate2_approves_a_complete_supported_draft() -> None:
    draft = good_draft("good-draft")
    assert "effects.indirect.H4b" in draft  # cites the real store row (REJECT-TC07 fix 1)
    node = _node({"good-draft": approve_yaml()})
    verdict = node.gate2(
        findings_draft=draft,
        results_store=results_store_text(),
        decision_log=decision_log_text(),
    )
    assert verdict.verdict == "approve"


def test_gate2_store_fixture_rows_validate_against_the_governed_schema() -> None:
    # REJECT-TC07 round 2: FR-302 evidence must BE results-store rows — every
    # emitted fixture row validates against results_store.schema.json.
    import json

    from jsonschema import Draft202012Validator

    schema = json.loads(
        (REPO / "schemas" / "results_store.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    rows = [json.loads(line) for line in results_store_text().splitlines()]
    assert len(rows) == 3  # H1, H4a, H4b — the FR-302 evidence base
    for row in rows:
        validator.validate(row)


def test_bad_draft_prompt_carries_h4b_evidence_outside_the_draft() -> None:  # REJECT-TC07 fix 1
    # The omission defect must be provable from the artifacts Node C reviews:
    # the draft never names H4b, while the store's authoritative row and the
    # decision log's mediation entry do (FR-302).
    draft = bad_draft("bad-draft")
    assert "H4b" not in draft
    provider = StubProvider(
        {"bad-draft": reject_yaml("failed hypothesis H4b omitted from the draft")}
    )
    node = NodeC(settings(), provider_call=provider)
    node.gate2(
        findings_draft=draft,
        results_store=results_store_text(),
        decision_log=decision_log_text(),
    )
    prompt = provider.prompts[0]
    assert "effects.indirect.H4b" in prompt  # store row reaches the reviewer
    assert "H4b" in decision_log_text()  # the log's mediation decision names it too


# -- prompt wiring ---------------------------------------------------------------------


def test_gate1_prompt_carries_contract_document_and_dictionary() -> None:
    provider = StubProvider({"faithful": approve_yaml()})
    node = NodeC(settings(), provider_call=provider)
    node.gate1(
        study_contract=FAITHFUL_CONTRACT.read_text(encoding="utf-8"),
        study_document=document("faithful"),
        data_dictionary="RS3 | reverse-coded\nCU3 | reverse-coded\n",
    )
    prompt = provider.prompts[0]
    assert "study_id: example-adoption-2026" in prompt
    assert "STUDY-VARIANT: faithful" in prompt
    assert "RS3 | reverse-coded" in prompt
    assert "reject" in prompt  # the versioned template's verdict contract


def test_gate2_prompt_carries_draft_store_and_log() -> None:
    provider = StubProvider({"good-draft": approve_yaml()})
    node = NodeC(settings(), provider_call=provider)
    node.gate2(
        findings_draft=good_draft("good-draft"),
        results_store=results_store_text(),
        decision_log=decision_log_text(),
    )
    prompt = provider.prompts[0]
    assert "structural.path.H4a" in prompt
    assert "DECISION_LOG" in prompt
    assert "STUDY-VARIANT: good-draft" in prompt


def test_prompt_manifest_covers_both_gate_templates() -> None:  # AD-04
    node = _node({"faithful": approve_yaml()})
    entries = node.prompt_manifest()
    assert [entry["version"] for entry in entries] == ["v1_gate1", "v1_gate2"]
    assert all(len(entry["sha256"]) == 64 for entry in entries)


# -- AT-M07-4 (absence): review-only — no write access, no compute API ----------------


def test_node_c_public_surface_is_review_only() -> None:  # AT-M07-4 introspection
    node = _node({"faithful": approve_yaml()})
    public = {
        name for name in dir(node) if not name.startswith("_") and callable(getattr(node, name))
    }
    assert public == {"gate1", "gate2", "prompt_manifest"}


def test_node_c_rejects_artifact_paths_and_bytes_at_the_boundary() -> None:  # AT-M07-4
    node = _node({"faithful": approve_yaml()})
    with pytest.raises(IntegrityHalt) as excinfo:  # attempted call with a live path
        node.gate1(study_contract=Path("runs/live/study_config.yaml"), study_document="doc")
    assert "boundary" in excinfo.value.message
    with pytest.raises(IntegrityHalt):
        node.gate2(
            findings_draft="draft",
            results_store=b'{"id": "structural.path.H1"}',
            decision_log="log",
        )


def test_missing_gate_template_halts_typed(tmp_path: Path) -> None:
    # Startup inputs validate before use — typed halt, never FileNotFoundError.
    with pytest.raises(IntegrityHalt) as excinfo:
        NodeC(
            settings(),
            provider_call=StubProvider({}),
            template_dir=tmp_path / "absent",
        )
    assert "template" in excinfo.value.message


def test_node_c_module_has_no_write_or_compute_capability() -> None:  # AT-M07-4 absence
    source = (REPO / "src" / "burhan" / "review" / "node_c.py").read_text(encoding="utf-8")
    forbidden = (
        "write_text",
        "write_bytes",
        ".write(",
        "open(",
        "mkdir",
        "unlink",
        "rename",
        "rmtree",
        "shutil",
        "subprocess",
        "Rscript",
        "os.system",
        "to_csv",
        "run_r",
    )
    hits = [token for token in forbidden if token in source]
    assert hits == []
