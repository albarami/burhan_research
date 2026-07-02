"""Governed-document validation: schemas, playbook, policy, registry.

Runs from a clean checkout with only jsonschema+pyyaml installed. This is the
M0 CI gate and a permanent regression thereafter (FR-1301; loader checks
P1-P4, D2, R2; protected defaults FR-504/505/705).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
PLAYBOOKS = ROOT / "playbooks"
POLICY = ROOT / "policy"

JSON_SCHEMAS = [
    "results_store.schema.json",
    "provenance_log.schema.json",
    "decision_log.schema.json",
    "run_manifest.schema.json",
    "reference_comparison.schema.json",
]


def _yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text())


def test_json_schemas_metaschema_valid() -> None:
    for name in JSON_SCHEMAS:
        Draft202012Validator.check_schema(json.loads((SCHEMAS / name).read_text()))


def test_yaml_schemas_metaschema_valid() -> None:
    for p in [
        SCHEMAS / "study_config.schema.yaml",
        PLAYBOOKS / "playbook.schema.yaml",
        POLICY / "decision_policy.schema.yaml",
        POLICY / "protected_registry.schema.yaml",
    ]:
        Draft202012Validator.check_schema(_yaml(p))


def test_study_config_example_validates() -> None:
    sc = _yaml(SCHEMAS / "study_config.schema.yaml")
    ex = _yaml(SCHEMAS / "study_config.example.yaml")
    errs = list(Draft202012Validator(sc).iter_errors(ex))
    assert not errs, [e.message for e in errs]


def test_results_id_grammar() -> None:
    pat = re.compile(
        json.loads((SCHEMAS / "results_store.schema.json").read_text())["properties"]["id"][
            "pattern"
        ]
    )
    good = [
        "measurement.loadings.first_order.R_TI.R9.std",
        "structural.path.READINESS->PEOU.std",
        "effects.indirect.READINESS->INT.boot_ci",
        "structural.fit.rmsea",
        "prep.n_chain.final_n",
    ]
    bad = ["narrate.fit.rmsea", "structural..path", "Structural.fit.rmsea"]
    assert all(pat.fullmatch(g) for g in good)
    assert not any(pat.fullmatch(b) for b in bad)


def _leaf_paths(d: dict, prefix: str = ""):
    for k, v in d.items():
        p = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            yield from _leaf_paths(v, p)
            yield p
        else:
            yield p


def test_playbook_valid_and_crosschecks() -> None:
    sc = _yaml(PLAYBOOKS / "playbook.schema.yaml")
    pb = _yaml(PLAYBOOKS / "CB_SEM_PLAYBOOK_v1.0.yaml")
    assert not list(Draft202012Validator(sc).iter_errors(pb))
    ids = [s["id"] for s in pb["steps"]]
    assert len(ids) == len(set(ids)), "P1: duplicate step ids"
    order = [
        "power",
        "prep",
        "assumptions",
        "measurement",
        "structural",
        "effects",
        "robustness",
        "narrate",
        "package",
    ]
    stages = [s["stage"] for s in pb["steps"]]
    assert stages == sorted(stages, key=order.index), "P1: stage order"
    reg, used = set(pb["citations"]), set()
    for s in pb["steps"]:
        used |= set(s["citations"])
        for c in s.get("criteria", []):
            used |= set(c.get("citation_keys", []))
    assert used == reg, f"P2: citation mismatch {used ^ reg}"
    idpat = re.compile(
        r"^(power|prep|assumptions|measurement|structural|effects|robustness)\.[a-z_]+$"
    )
    assert all(
        idpat.fullmatch(o) for s in pb["steps"] for o in s.get("outputs", [])
    ), "P4: output prefix grammar"


def test_policy_registry_valid_and_refs_resolve() -> None:
    pol_sc = _yaml(POLICY / "decision_policy.schema.yaml")
    reg_sc = _yaml(POLICY / "protected_registry.schema.yaml")
    pol = _yaml(POLICY / "decision_policy.template.yaml")
    reg = _yaml(POLICY / "protected_decisions.registry.yaml")
    assert not list(Draft202012Validator(pol_sc).iter_errors(pol))
    assert not list(Draft202012Validator(reg_sc).iter_errors(reg))
    paths = set(_leaf_paths(pol))
    pb = _yaml(PLAYBOOKS / "CB_SEM_PLAYBOOK_v1.0.yaml")
    refs = {
        c["policy_ref"] for s in pb["steps"] for c in s.get("criteria", []) if "policy_ref" in c
    }
    refs |= {
        s["governance"]["preauthorization_policy_ref"] for s in pb["steps"] if "governance" in s
    }
    assert refs <= paths, f"D2/P3 unresolved: {sorted(refs - paths)}"
    dels = [d["delegation_ref"] for d in reg["protected_decisions"] if d.get("delegable")]
    assert all(d in paths for d in dels), "R2: delegation_ref unresolved"


def test_protected_defaults_hold() -> None:
    pol = _yaml(POLICY / "decision_policy.template.yaml")
    assert pol["measurement"]["item_deletion"]["preauthorized"] is False, "FR-705 default"
    assert pol["prep"]["missing_treatment"]["primary"] == "fiml", "FR-504"
    assert pol["verification"]["prep_cell_tolerance"] == 0, "FR-501"
