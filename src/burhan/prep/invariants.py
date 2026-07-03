"""Post-preparation invariants I1–I7 (FR-507; AT-M08-5/8).

Pure assertions over the prepared model-item frame (reversal applied,
values numeric, NaN = missing) and the validated contract. They re-assert
independently of the contract-stage validators (V1–V7): preparation never
assumes an upstream gate ran. Each failure is a hard failure naming
exactly its invariant; reports carry case IDs, item codes, and counts —
never respondent values.

I2 is the sign-flip verification (AT-M08-8): after reversal, a genuinely
reverse-coded item correlates positively with the mean of its construct
siblings. An item whose data arrived un-reversed — even though the
declaration is correct — anti-correlates after the flip and halts here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    # Untyped third-party edge (no stubs in the locked dependency set).
    import pandas as pd  # type: ignore[import-untyped]

    from burhan.core.artifacts.models import StudyConfig


def i1_ranges(frame: pd.DataFrame, config: StudyConfig) -> None:
    """I1: every prepared value lies within its item's declared scale."""
    violations: list[dict[str, object]] = []
    for item in config.instrument.items:
        if item.code not in frame.columns:
            continue
        column = frame[item.code].dropna()
        outside = column[(column < item.scale.min) | (column > item.scale.max)]
        if len(outside):
            violations.append({"item": item.code, "cases": sorted(outside.index.tolist())})
    if violations:
        halt(
            IntegrityHalt(
                "I1: values outside declared scale ranges after preparation",
                report={"violations": violations},
            )
        )


def i2_reverse_sign_flip(frame: pd.DataFrame, config: StudyConfig) -> None:
    """I2: every reverse-coded item verified by correlation sign-flip."""
    indicators = {c.code: list(c.indicators or []) for c in config.constructs}
    failures: list[dict[str, object]] = []
    for item in config.instrument.items:
        if not item.reverse_coded or item.code not in frame.columns:
            continue
        siblings = [
            code
            for code in indicators.get(item.construct_ref, [])
            if code != item.code and code in frame.columns
        ]
        if not siblings:
            failures.append({"item": item.code, "reason": "no siblings to verify against"})
            continue
        correlation = frame[item.code].corr(frame[siblings].mean(axis=1))
        if not correlation > 0:  # NaN (unverifiable) fails too
            failures.append(
                {
                    "item": item.code,
                    "reason": "post-reversal correlation with construct siblings is not positive",
                }
            )
    if failures:
        halt(
            IntegrityHalt(
                "I2: reverse-coded item failed sign-flip verification "
                "(un-reversed data cannot pass, however declared)",
                report={"failures": failures},
            )
        )


def i3_unmapped_items(frame: pd.DataFrame, config: StudyConfig) -> None:
    """I3: zero unmapped items — every designed item is a prepared column."""
    missing = sorted({i.code for i in config.instrument.items} - set(frame.columns))
    if missing:
        halt(
            IntegrityHalt(
                "I3: designed items missing from the prepared frame",
                report={"unmapped_items": missing},
            )
        )


def i4_orphan_columns(frame: pd.DataFrame, config: StudyConfig) -> None:
    """I4: zero orphan columns — every prepared column is a designed item."""
    orphans = sorted(set(frame.columns) - {i.code for i in config.instrument.items})
    if orphans:
        halt(
            IntegrityHalt(
                "I4: prepared frame carries columns that are not designed items",
                report={"orphan_columns": orphans},
            )
        )


def i5_paths_resolvable(frame: pd.DataFrame, config: StudyConfig) -> None:
    """I5: every hypothesized path resolves to constructs with prepared items."""
    indicators = {c.code: list(c.indicators or []) for c in config.constructs}
    components = {c.code: list(c.components or []) for c in config.constructs}

    def measured(construct: str) -> bool:
        own = [code for code in indicators.get(construct, []) if code in frame.columns]
        if own:
            return True
        return any(measured(component) for component in components.get(construct, []))

    unresolved: list[dict[str, str]] = []
    for hypothesis in config.hypotheses:
        for construct in (hypothesis.from_, hypothesis.to, *(hypothesis.via or [])):
            if construct not in indicators or not measured(construct):
                unresolved.append({"hypothesis": hypothesis.id, "construct": construct})
    if unresolved:
        halt(
            IntegrityHalt(
                "I5: hypothesized path not resolvable against the prepared frame",
                report={"unresolved": unresolved},
            )
        )


def i6_min_items(frame: pd.DataFrame, config: StudyConfig, *, minimum: int) -> None:
    """I6: every first-order construct keeps at least the minimum item count.

    A column that is entirely missing carries no information — it does not
    count toward the minimum.
    """
    below: list[dict[str, object]] = []
    for construct in config.constructs:
        if construct.level != "first_order":
            continue
        informative = [
            code
            for code in construct.indicators or []
            if code in frame.columns and frame[code].notna().any()
        ]
        if len(informative) < minimum:
            below.append(
                {
                    "construct": construct.code,
                    "informative_items": len(informative),
                    "minimum": minimum,
                }
            )
    if below:
        halt(
            IntegrityHalt(
                "I6: construct below the minimum item count after preparation",
                report={"below_minimum": below},
            )
        )


def i7_higher_order(frame: pd.DataFrame, config: StudyConfig) -> None:
    """I7: every declared higher-order structure is fully specified."""
    second_order = [c for c in config.constructs if c.level == "second_order"]
    first_order = {c.code: c for c in config.constructs if c.level == "first_order"}
    problems: list[dict[str, str]] = []
    if second_order and config.higher_order is None:
        problems.extend(
            {"construct": c.code, "problem": "no higher_order specification"} for c in second_order
        )
    if config.higher_order is not None and not second_order:
        problems.append(
            {"construct": "-", "problem": "higher_order block without second-order construct"}
        )
    for construct in second_order:
        for component in construct.components or []:
            component_construct = first_order.get(component)
            prepared = [
                code
                for code in (component_construct.indicators or [] if component_construct else [])
                if code in frame.columns
            ]
            if component_construct is None or not prepared:
                problems.append(
                    {
                        "construct": construct.code,
                        "problem": f"component {component} has no prepared items",
                    }
                )
    if problems:
        halt(
            IntegrityHalt(
                "I7: higher-order structure not fully specified",
                report={"problems": problems},
            )
        )


def assert_invariants(frame: pd.DataFrame, config: StudyConfig, *, min_items: int) -> None:
    """Run I1–I7 in order; the first violated invariant halts, named alone."""
    i1_ranges(frame, config)
    i2_reverse_sign_flip(frame, config)
    i3_unmapped_items(frame, config)
    i4_orphan_columns(frame, config)
    i5_paths_resolvable(frame, config)
    i6_min_items(frame, config, minimum=min_items)
    i7_higher_order(frame, config)
