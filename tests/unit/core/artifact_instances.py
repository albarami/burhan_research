"""Known-valid base instances for the five JSON machine contracts.

StudyConfig's base instance is the governed worked example
(``schemas/study_config.example.yaml``); these dicts cover the other five.
Every optional field and nested structure is exercised so the conformance
harness can mutate at every keyword site. Accessors return deep copies.
"""

from __future__ import annotations

import copy
from typing import Any

_SHA_A = "a" * 64
_SHA_B = "b" * 64

_INSTANCES: dict[str, dict[str, Any]] = {
    "results_store_entry": {
        "schema_version": 1,
        "id": "measurement.loadings.first_order.R_TI.R9.std",
        "value": 0.812,
        "se": 0.041,
        "ci_low": 0.73,
        "ci_high": 0.89,
        "ci_level": 0.95,
        "p": 0.001,
        "df": 24,
        "n": 312,
        "unit": "std_loading",
        "stage": "measurement",
        "engine": "r_lavaan",
        "playbook_step": "measurement.cfa_first_order",
        "params": {"estimator": "MLR", "standardized": True},
        "created": "2026-07-02T09:00:00Z",
        "hash": _SHA_A,
    },
    "provenance_entry": {
        "schema_version": 1,
        "seq": 1,
        "ts": "2026-07-02T09:00:00Z",
        "stage": "prep",
        "actor": "invariant",
        "event_type": "invariant_pass",
        "rule_ref": "policy.prep.range_check",
        "trigger": "post-preparation invariant sweep",
        "effect": "all values within declared scale ranges",
        "artifact_refs": [{"path": "prep/invariants.json", "sha256": _SHA_B}],
        "details": {"checked_items": 15},
    },
    "decision_entry": {
        "schema_version": 1,
        "seq": 3,
        "ts": "2026-07-02T09:05:00Z",
        "stage": "assumptions",
        "decision_point": "estimator_determination",
        "rule_id": "assumptions.estimator.mardia_violation",
        "rule_version": "1.0",
        "inputs": {"mardia_skew_p": 0.001, "categories_min": 7},
        "decision": "MLR",
        "rationale": "Multivariate non-normality; robust ML per playbook PB-07.",
        "alternatives_considered": ["ML", "WLSMV"],
        "flags": ["FLAG-004"],
        "protected": False,
    },
    "run_manifest": {
        "schema_version": 1,
        "run_id": "20260702T090000Z",
        "study_id": "example-adoption-2026",
        "started": "2026-07-02T09:00:00Z",
        "finished": "2026-07-02T10:30:00Z",
        "state": "COMPLETED",
        "master_seed": 424242,
        "engine": {"version": "0.1.0", "git_commit": "98bf13f", "git_dirty": False},
        "hashes": {
            "study_config": "c" * 64,
            "decision_policy": "d" * 64,
            "protected_registry": "e" * 64,
            "playbook": "f" * 64,
            "prompts": {
                "node_a": {"version": "1.0", "sha256": "0" * 63 + "a"},
                "node_b": {"version": "1.0", "sha256": "0" * 63 + "b"},
                "node_c": {"version": "1.0", "sha256": "0" * 63 + "c"},
            },
            "uv_lock": "1" * 64,
            "renv_lock": "2" * 64,
        },
        "environment": {
            "python": "3.12.6",
            "r": "4.4.1",
            "os": "Linux WSL2 Ubuntu 24.04",
            "blas_threads": 1,
            "max_workers": 16,
            "doctor_passed": True,
            "doctor_report_sha256": "3" * 64,
        },
        "llm_nodes": {
            "node_a": {
                "provider": "anthropic",
                "model": "claude-pinned",
                "lineage": "anthropic.claude",
                "temperature": 0,
                "prompt_version": "1.0",
            },
            "node_b": {
                "provider": "anthropic",
                "model": "claude-pinned",
                "lineage": "anthropic.claude",
                "temperature": 0,
            },
            "node_c": {
                "provider": "openai",
                "model": "gpt-pinned",
                "lineage": "openai.gpt",
                "temperature": 0,
            },
        },
        "stages": [
            {
                "stage": "ingest",
                "state": "PASSED",
                "started": "2026-07-02T09:00:00Z",
                "finished": "2026-07-02T09:01:00Z",
                "artifact_tree_sha256": "4" * 64,
                "notes": "ok",
            },
            {"stage": "contract", "state": "PASSED", "started": "2026-07-02T09:01:00Z"},
        ],
        "advisory": False,
        "seal": {"hash_tree_root": "5" * 64, "sealed_at": "2026-07-02T10:30:00Z"},
    },
    "reference_comparison": {
        "schema_version": 1,
        "study_id": "dba-validation-study",
        "run_id": "20260702T090000Z",
        "reference_source": {
            "description": "Prior manual SPSS/AMOS analysis",
            "documents": [{"path": "reference/manual_results.pdf", "sha256": "6" * 64}],
            "caveats": "Manual work may contain item-handling errors.",
        },
        "comparisons": [
            {
                "comparison_id": "CMP-001",
                "domain": "fit",
                "metric": "RMSEA",
                "reference_value": 0.061,
                "burhan_value": 0.058,
                "burhan_stat_id": "structural.fit.rmsea",
                "delta": -0.003,
                "tolerance": 0.005,
                "status": "match",
                "classification": "unresolved",
                "investigation": "delta inside doc-12 tolerance",
                "resolution": "none required",
            },
            {
                "comparison_id": "CMP-002",
                "domain": "hypothesis_verdict",
                "metric": "H3a verdict",
                "reference_value": "supported",
                "burhan_value": None,
                "delta": None,
                "tolerance": None,
                "status": "reference_missing",
            },
        ],
        "summary": {
            "total": 2,
            "matches": 1,
            "divergent": 0,
            "reference_missing": 1,
            "burhan_only": 0,
            "unresolved": 2,
        },
        "signoff": {"researcher": "S. Al Barami", "date": "2026-07-02", "notes": "n/a"},
    },
}


def valid_instance(name: str) -> dict[str, Any]:
    """Return a deep copy of the known-valid instance for ``name``."""
    return copy.deepcopy(_INSTANCES[name])


def instance_names() -> list[str]:
    """Names of the five dict-based instances (study_config lives on disk)."""
    return sorted(_INSTANCES)
