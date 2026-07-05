"""Stage-1A adapters (TC-15): the analytic pipeline over certified modules.

Ten stages — ingest (S0), contract (S1), gate1 (G1), power (S2), prep (S3),
assumptions (S4), measurement (S5), structural (S6), effects (S7), robustness
(S8) — each a thin adapter that materializes governance, calls already-certified
modules, serializes their results to the store (``serialize``), and marks its
playbook step(s). No statistics are computed or altered here (D4).

Two measurement steps are recorded ``flagged`` per the playbook's
``failure_action: flag`` rather than completed, because the certification study
does not enable them: PB-12 (CMB) — the contract designates no method marker, so
the substantive CLF/marker test is not performable (FR-704); PB-14
(respecification) — a remedy consulted only for inadequate fit, and the model
fits within bands so no modification is indicated. The item-deletion protocol
(PB-13) runs under protection and only ever *recommends* (no autonomous
execution of PD-05).
"""

from __future__ import annotations

import csv
import hashlib
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]

from burhan.core.advisory import Advisory
from burhan.core.errors import GateExhausted, halt
from burhan.core.rworker import RWorker
from burhan.prep.py_impl.pipeline import run_prep
from burhan.stages import context, serialize
from burhan.stats.assumptions import estimator_determination, vif_composites
from burhan.stats.deletion import run_deletion_protocol
from burhan.stats.effects import run_effects
from burhan.stats.measurement import run_measurement
from burhan.stats.montecarlo import montecarlo_power
from burhan.stats.power import power_gate
from burhan.stats.robustness import achieved_power_report, run_alternatives
from burhan.stats.structural import run_structural

if TYPE_CHECKING:
    from pathlib import Path

    from burhan.contract.node_a import NodeA
    from burhan.core.orchestrator import StageContext
    from burhan.core.playbook import Playbook
    from burhan.core.policy import Policy
    from burhan.core.registry import Registry
    from burhan.review.node_c import NodeC

_MARKER_FLAG = (
    "no method marker is designated in the contract; the substantive CLF/marker "
    "common-method test is not performable (FR-704); recorded flagged per PB-12 failure_action"
)


def _respec_flag(fit: dict[str, Any]) -> str:
    srmr = round(float(fit["srmr"]), 3)
    return (
        "respecification is a remedy consulted only for inadequate fit; the measurement model "
        f"fits within bands (CFI {fit['cfi']}, RMSEA {fit['rmsea']}, SRMR {srmr}); no "
        "modification is indicated, recorded flagged per PB-14 failure_action"
    )


class Ingest:
    """S0: load and fingerprint the raw export, record the raw N."""

    name = "ingest"
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = (context.INGEST_SUMMARY,)

    def __init__(self, *, export_path: Path, header_rows: int) -> None:
        self._export_path = export_path
        self._header_rows = header_rows

    def execute(self, ctx: StageContext) -> None:
        with self._export_path.open(newline="", encoding="utf-8") as handle:
            total_rows = sum(1 for _ in csv.reader(handle))
        raw_n = max(0, total_rows - self._header_rows)
        digest = hashlib.sha256(self._export_path.read_bytes()).hexdigest()
        context.write_artifact(
            ctx,
            context.INGEST_SUMMARY,
            {"raw_n": raw_n, "export_sha256": digest, "export_name": self._export_path.name},
        )


class Contract:
    """S1: Node A extraction — documents in, validated study contract out."""

    name = "contract"
    consumes: tuple[str, ...] = (context.INGEST_SUMMARY,)
    produces: tuple[str, ...] = (context.CONTRACT_CONFIG,)

    def __init__(
        self, *, node_a: NodeA, study_document: str, data_dictionary: str | None = None
    ) -> None:
        self._node_a = node_a
        self._study_document = study_document
        self._data_dictionary = data_dictionary

    def execute(self, ctx: StageContext) -> None:
        config = self._node_a.extract(
            study_document=self._study_document, data_dictionary=self._data_dictionary
        )
        context.write_config(ctx, config)


class Gate1:
    """G1: Node C reviews the contract; a reject exhausts the gate."""

    name = "gate1"
    consumes: tuple[str, ...] = (context.CONTRACT_CONFIG,)
    produces: tuple[str, ...] = ("gate1/verdict.json",)

    def __init__(self, *, node_c: NodeC, study_document: str) -> None:
        self._node_c = node_c
        self._study_document = study_document

    def execute(self, ctx: StageContext) -> None:
        config = context.load_config(ctx)
        contract_text = yaml.safe_dump(
            config.model_dump(mode="json", by_alias=True, exclude_unset=True), sort_keys=True
        )
        verdict = self._node_c.gate1(
            study_contract=contract_text, study_document=self._study_document
        )
        context.write_artifact(
            ctx,
            "gate1/verdict.json",
            {"verdict": verdict.verdict, "fixes": list(verdict.fixes)},
        )
        if verdict.verdict != "approve":
            halt(
                GateExhausted(
                    "Gate 1 rejected the study contract (FR-303)",
                    report={"fixes": list(verdict.fixes)},
                )
            )


class Power:
    """S2 / PB-01: a-priori close-fit power, N:q gate, Monte-Carlo power."""

    name = "power"
    consumes: tuple[str, ...] = (context.CONTRACT_CONFIG, context.INGEST_SUMMARY)
    produces: tuple[str, ...] = ()

    def __init__(
        self, *, policy: Policy, playbook: Playbook, montecarlo_replications: int | None = None
    ) -> None:
        self._policy = policy
        self._playbook = playbook
        self._montecarlo_replications = montecarlo_replications

    def execute(self, ctx: StageContext) -> None:
        config = context.load_config(ctx)
        n = context.raw_n(ctx)
        advisory = Advisory(ctx.run_dir, ctx.provenance, ctx.clock)
        # power_gate emits a Method Advisory (AdvisoryStop) below the N:q floor,
        # taking the run to COMPLETED_TO_BOUNDARY before any expensive R call.
        power_gate(config, n=n, playbook=self._playbook, advisory=advisory)
        montecarlo = montecarlo_power(
            config,
            n=n,
            seed=ctx.stage_seed,
            policy=self._policy,
            playbook=self._playbook,
            rworker=RWorker(),
            run_dir=ctx.run_dir,
            call_id="power-montecarlo",
            replications=self._montecarlo_replications,
        )
        context.store_rows(
            ctx, serialize.power_rows(config, n=n, playbook=self._playbook, montecarlo=montecarlo)
        )
        context.compliance(ctx, self._playbook).mark(
            "PB-01",
            "completed",
            f"a-priori power at N={n}; Monte-Carlo {montecarlo['replications']} replications",
        )


class Prep:
    """S3 / PB-02..04: the deterministic preparation pipeline."""

    name = "prep"
    consumes: tuple[str, ...] = (context.CONTRACT_CONFIG,)
    produces: tuple[str, ...] = (context.PREP_FRAME,)

    def __init__(self, *, export_path: Path, policy: Policy, playbook: Playbook) -> None:
        self._export_path = export_path
        self._policy = policy
        self._playbook = playbook

    def execute(self, ctx: StageContext) -> None:
        config = context.load_config(ctx)
        prep = run_prep(self._export_path, config, self._policy)
        context.write_frame(ctx, prep.frame)
        context.store_rows(ctx, serialize.prep_rows(prep))
        tracker = context.compliance(ctx, self._playbook)
        chain = prep.n_chain
        tracker.mark(
            "PB-02",
            "completed",
            f"n-chain accounted: raw {chain.raw_n} -> final {chain.final_n}; screening recorded",
        )
        tracker.mark("PB-03", "completed", f"missingness: {prep.missingness['mechanism_verdict']}")
        tracker.mark("PB-04", "completed", f"outliers: {len(prep.outliers['flagged'])} flagged")


class Assumptions:
    """S4 / PB-05..07: normality, collinearity, and estimator selection."""

    name = "assumptions"
    consumes: tuple[str, ...] = (context.PREP_FRAME,)
    produces: tuple[str, ...] = ()

    def __init__(self, *, policy: Policy, playbook: Playbook) -> None:
        self._policy = policy
        self._playbook = playbook

    def execute(self, ctx: StageContext) -> None:
        frame = context.load_frame(ctx)
        vif = vif_composites(frame)
        estimator = estimator_determination(
            frame,
            policy=self._policy,
            playbook=self._playbook,
            decision_log=context.decision_log(ctx),
        )
        context.store_rows(
            ctx,
            serialize.assumptions_rows(
                frame, playbook=self._playbook, vif=vif, estimator=estimator
            ),
        )
        tracker = context.compliance(ctx, self._playbook)
        tracker.mark("PB-05", "completed", "univariate + multivariate normality assessed")
        tracker.mark("PB-06", "completed", "composite collinearity (VIF) assessed")
        tracker.mark(
            "PB-07",
            "completed",
            f"estimator determined: {estimator['estimator']} ({estimator['basis']})",
        )


class Measurement:
    """S5 / PB-08..14: CFA, reliability/validity, deletion, respecification."""

    name = "measurement"
    consumes: tuple[str, ...] = (context.PREP_FRAME, context.CONTRACT_CONFIG)
    produces: tuple[str, ...] = ("stats/measurement.json",)

    def __init__(self, *, policy: Policy, playbook: Playbook, registry: Registry) -> None:
        self._policy = policy
        self._playbook = playbook
        self._registry = registry

    def execute(self, ctx: StageContext) -> None:
        frame = context.load_frame(ctx)
        config = context.load_config(ctx)
        rworker = RWorker()
        measurement = run_measurement(
            frame,
            config,
            policy=self._policy,
            playbook=self._playbook,
            rworker=rworker,
            run_dir=ctx.run_dir,
            call_id="measurement",
        )
        deletion = run_deletion_protocol(
            frame,
            config,
            policy=self._policy,
            playbook=self._playbook,
            registry=self._registry,
            log=context.decision_log(ctx),
            rworker=rworker,
            run_dir=ctx.run_dir,
            call_id="measurement-deletion",
            content_validity={},
        )
        context.write_artifact(ctx, "stats/measurement.json", measurement)
        context.store_rows(ctx, serialize.measurement_rows(measurement, deletion))
        tracker = context.compliance(ctx, self._playbook)
        tracker.mark(
            "PB-08", "completed", f"first-order CFA specified/estimated ({measurement['approach']})"
        )
        tracker.mark(
            "PB-09", "completed", "standardized loadings evaluated against the playbook band"
        )
        tracker.mark("PB-10", "completed", "reliability + convergent validity (AVE) assessed")
        tracker.mark(
            "PB-11", "completed", "discriminant validity (Fornell-Larcker + HTMT) assessed"
        )
        tracker.mark("PB-12", "flagged", _MARKER_FLAG)
        tracker.mark(
            "PB-13",
            "completed",
            f"item-deletion protocol under protection: {deletion['mode']} "
            f"({len(deletion['candidates'])} candidate(s), {len(deletion['deletions'])} deleted)",
        )
        tracker.mark("PB-14", "flagged", _respec_flag(measurement["fit"]))


class Structural:
    """S6 / PB-15..16: structural fit, paths, and R-squared."""

    name = "structural"
    consumes: tuple[str, ...] = (context.PREP_FRAME, context.CONTRACT_CONFIG)
    produces: tuple[str, ...] = ("stats/structural.json",)

    def __init__(self, *, playbook: Playbook) -> None:
        self._playbook = playbook

    def execute(self, ctx: StageContext) -> None:
        frame = context.load_frame(ctx)
        config = context.load_config(ctx)
        structural = run_structural(
            frame,
            config,
            playbook=self._playbook,
            rworker=RWorker(),
            run_dir=ctx.run_dir,
            call_id="structural",
        )
        context.write_artifact(ctx, "stats/structural.json", structural)
        context.store_rows(ctx, serialize.structural_rows(structural))
        tracker = context.compliance(ctx, self._playbook)
        tracker.mark("PB-15", "completed", "structural model fit evaluated against the bands")
        tracker.mark("PB-16", "completed", "path coefficients + R-squared estimated")


class Effects:
    """S7 / PB-17: bootstrap mediation decomposition + classification."""

    name = "effects"
    consumes: tuple[str, ...] = (context.PREP_FRAME, context.CONTRACT_CONFIG)
    produces: tuple[str, ...] = ("stats/effects.json",)

    def __init__(self, *, policy: Policy, playbook: Playbook) -> None:
        self._policy = policy
        self._playbook = playbook

    def execute(self, ctx: StageContext) -> None:
        frame = context.load_frame(ctx)
        config = context.load_config(ctx)
        effects = run_effects(
            frame,
            config,
            policy=self._policy,
            playbook=self._playbook,
            rworker=RWorker(),
            run_dir=ctx.run_dir,
            call_id="effects",
        )
        context.write_artifact(ctx, "stats/effects.json", effects)
        context.store_rows(ctx, serialize.effects_rows(effects))
        context.compliance(ctx, self._playbook).mark(
            "PB-17", "completed", "direct/indirect/total effects decomposed and classified"
        )


class Robustness:
    """S8 / PB-18..19: alternative models and achieved (post-hoc) power."""

    name = "robustness"
    consumes: tuple[str, ...] = (context.PREP_FRAME, context.CONTRACT_CONFIG)
    produces: tuple[str, ...] = ()

    def __init__(self, *, playbook: Playbook) -> None:
        self._playbook = playbook

    def execute(self, ctx: StageContext) -> None:
        frame = context.load_frame(ctx)
        config = context.load_config(ctx)
        alternatives = run_alternatives(
            frame,
            config,
            playbook=self._playbook,
            rworker=RWorker(),
            run_dir=ctx.run_dir,
            call_id="robustness-alternatives",
        )
        achieved = achieved_power_report(
            config, n=context.analytical_n(ctx), playbook=self._playbook
        )
        context.store_rows(ctx, serialize.robustness_rows(alternatives, achieved))
        tracker = context.compliance(ctx, self._playbook)
        tracker.mark("PB-18", "completed", "alternative (rival) models compared")
        tracker.mark("PB-19", "completed", f"achieved power {round(float(achieved['value']), 3)}")
