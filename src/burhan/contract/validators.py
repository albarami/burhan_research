"""Cross-field contract validators V1–V7 (study_config.schema.yaml:230-246).

Pure functions over the validated model; each failure is a hard failure
naming exactly its validator (FR-205 — never a guess, never a silent
default). V6 delegates to the TC-05 crosswalk, which owns the zero-orphan
accounting against the actual export.

The dictionary cross-check (FR-204) lives here too: the data dictionary is
authoritative for what it declares, and any conflict with the extracted
contract — including reverse-coding the document was silent about — is a
hard failure citing the conflict.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt, halt

_DICT_LINE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*\|\s*(.+?)\s*$")


def v1_construct_refs(config: StudyConfig) -> None:
    """V1: every item's construct_ref resolves to a first_order construct."""
    first_order = {c.code for c in config.constructs if c.level == "first_order"}
    bad = {
        item.code: item.construct_ref
        for item in config.instrument.items
        if item.construct_ref not in first_order
    }
    if bad:
        halt(
            IntegrityHalt(
                "V1: item construct_ref does not resolve to a first_order construct",
                report={"unresolved": bad},
            )
        )


def v2_indicators(config: StudyConfig, *, min_designed_items: int) -> None:
    """V2: indicators exist as items; designed pools meet the playbook minimum."""
    item_codes = {item.code for item in config.instrument.items}
    for construct in config.constructs:
        if construct.level != "first_order":
            continue
        indicators = construct.indicators or []
        ghosts = sorted(set(indicators) - item_codes)
        if ghosts:
            halt(
                IntegrityHalt(
                    "V2: construct indicators missing from the instrument",
                    report={"construct": construct.code, "missing_items": ghosts},
                )
            )
        if len(indicators) < min_designed_items:
            halt(
                IntegrityHalt(
                    "V2: designed pool below the playbook minimum",
                    report={
                        "construct": construct.code,
                        "designed": len(indicators),
                        "minimum": min_designed_items,
                    },
                )
            )


def v3_higher_order(config: StudyConfig) -> None:
    """V3: components resolve to first_order; higher_order block iff second_order."""
    first_order = {c.code for c in config.constructs if c.level == "first_order"}
    second_order = [c for c in config.constructs if c.level == "second_order"]
    for construct in second_order:
        ghosts = sorted(set(construct.components or []) - first_order)
        if ghosts:
            halt(
                IntegrityHalt(
                    "V3: second_order components must resolve to first_order constructs",
                    report={"construct": construct.code, "unresolved": ghosts},
                )
            )
    if second_order and config.higher_order is None:
        halt(
            IntegrityHalt(
                "V3: second_order constructs declared without a higher_order block",
                report={"second_order": [c.code for c in second_order]},
            )
        )
    if not second_order and config.higher_order is not None:
        halt(
            IntegrityHalt(
                "V3: higher_order block present without any second_order construct",
                report={},
            )
        )


def v4_model_references(config: StudyConfig) -> None:
    """V4: model/hypothesis references resolve; via required for indirect."""
    constructs = {c.code for c in config.constructs}

    def check(refs: Iterable[str], where: str) -> None:
        ghosts = sorted(set(refs) - constructs)
        if ghosts:
            halt(
                IntegrityHalt(
                    "V4: unresolved construct reference",
                    report={"where": where, "unresolved": ghosts},
                )
            )

    check(config.model.exogenous, "model.exogenous")
    check(config.model.endogenous, "model.endogenous")
    check(config.model.mediators or [], "model.mediators")
    for hypothesis in config.hypotheses:
        check([hypothesis.from_, hypothesis.to], f"hypothesis {hypothesis.id}")
        if hypothesis.effect == "indirect":
            if not hypothesis.via:
                halt(
                    IntegrityHalt(
                        "V4: indirect hypothesis requires a via chain",
                        report={"hypothesis": hypothesis.id},
                    )
                )
            check(hypothesis.via, f"hypothesis {hypothesis.id} via")


def v5_hypotheses(config: StudyConfig) -> None:
    """V5: hypothesis ids unique; indirect chains reachable via direct links."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for hypothesis in config.hypotheses:
        if hypothesis.id in seen:
            duplicates.append(hypothesis.id)
        seen.add(hypothesis.id)
    if duplicates:
        halt(
            IntegrityHalt(
                "V5: duplicate hypothesis ids",
                report={"duplicates": sorted(set(duplicates))},
            )
        )
    direct_links = {(h.from_, h.to) for h in config.hypotheses if h.effect == "direct"}
    for hypothesis in config.hypotheses:
        if hypothesis.effect != "indirect" or not hypothesis.via:
            continue
        chain = [hypothesis.from_, *hypothesis.via, hypothesis.to]
        missing_links = [
            f"{a}->{b}"
            for a, b in zip(chain, chain[1:], strict=False)
            if (a, b) not in direct_links
        ]
        if missing_links:
            halt(
                IntegrityHalt(
                    "V5: indirect hypothesis chain is not structurally reachable "
                    "through declared direct paths",
                    report={"hypothesis": hypothesis.id, "missing_links": missing_links},
                )
            )


def v6_column_accounting(config: StudyConfig, export_path: Path) -> None:
    """V6: zero-orphan column accounting — delegated to the TC-05 crosswalk."""
    from burhan.contract.crosswalk import build_crosswalk

    try:
        build_crosswalk(export_path, config)
    except IntegrityHalt as exc:
        halt(
            IntegrityHalt(
                f"V6: column accounting failed — {exc.message}",
                report=exc.details,
            )
        )


def v7_reverse_coding(config: StudyConfig, *, source_reversed: set[str]) -> None:
    """V7: the contract's reverse_coded flags equal the sources' declarations."""
    declared = {item.code for item in config.instrument.items if item.reverse_coded}
    invented = sorted(declared - source_reversed)
    dropped = sorted(source_reversed - declared)
    if invented or dropped:
        halt(
            IntegrityHalt(
                "V7: reverse-coding must come only from the sources — never "
                "inferred, never dropped",
                report={"invented": invented, "dropped": dropped},
            )
        )


def cross_check_dictionary(config: StudyConfig, dictionary_text: str) -> None:
    """FR-204: the data dictionary is authoritative for what it declares.

    Dictionary lines have the form ``CODE | attribute[, attribute]``.
    Reverse-coding declarations carry explicit positive/negative semantics:
    the exact attribute token ``reverse-coded`` declares reversal, the exact
    token ``not reverse-coded`` declares its absence — substring matching
    (which would read the negative as positive) is a defect. A real conflict
    with the extracted contract in either direction is a hard failure citing
    the item and both sources; a consistent declaration passes.
    """
    item_by_code = {item.code: item for item in config.instrument.items}
    conflicts: list[dict[str, str]] = []
    for line in dictionary_text.splitlines():
        match = _DICT_LINE.match(line)
        if match is None:
            continue
        code = match.group(1)
        tokens = {token.strip() for token in match.group(2).lower().split(",")}
        positive = "reverse-coded" in tokens
        negative = "not reverse-coded" in tokens
        item = item_by_code.get(code)
        if item is None:
            conflicts.append({"item": code, "conflict": "dictionary item absent from contract"})
            continue
        if positive and negative:
            conflicts.append(
                {
                    "item": code,
                    "conflict": "dictionary declares both reverse-coded and not reverse-coded",
                }
            )
        elif positive and not item.reverse_coded:
            conflicts.append(
                {
                    "item": code,
                    "conflict": "dictionary declares reverse-coded; contract does not",
                }
            )
        elif negative and item.reverse_coded:
            conflicts.append(
                {
                    "item": code,
                    "conflict": "dictionary declares not reverse-coded; "
                    "contract declares reverse-coded",
                }
            )
    if conflicts:
        halt(
            IntegrityHalt(
                "data-dictionary cross-check failed (FR-204): unresolved "
                "conflicts are hard failures",
                report={"conflicts": conflicts},
            )
        )


def validate_contract(
    config: StudyConfig,
    *,
    source_reversed: set[str] | None = None,
    dictionary_text: str | None = None,
    export_path: Path | None = None,
    min_designed_items: int = 2,
) -> None:
    """Run V1–V7 (V6/V7 where their inputs are available) plus FR-204.

    The dictionary cross-check runs BEFORE V7: a dictionary-vs-contract
    conflict is an FR-204 failure in its own right (AT-M06-4), not a
    side-effect of the reverse-coding source comparison.
    """
    v1_construct_refs(config)
    v2_indicators(config, min_designed_items=min_designed_items)
    v3_higher_order(config)
    v4_model_references(config)
    v5_hypotheses(config)
    if export_path is not None:
        v6_column_accounting(config, export_path)
    if dictionary_text is not None:
        cross_check_dictionary(config, dictionary_text)
    if source_reversed is not None:
        v7_reverse_coding(config, source_reversed=source_reversed)
