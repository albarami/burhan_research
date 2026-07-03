"""Monte Carlo power: population model and simsem wiring (FR-401; PB-01;
AT-M09-5).

The population parameterization is the governed PB-01
``montecarlo_population`` criterion (researcher change, 2026-07-03):
standardized loadings .70, hypothesized structural paths .30, exogenous
construct correlations .30, residual variances implied by
standardization. The values are parsed from the criterion — never
hard-coded — and the standardization is solved exactly: latent
disturbances come from the reduced-form covariance recursion in causal
order, so every latent variance in the population model equals 1 and the
syntax carries exact numbers, not approximations.

The simulation itself runs in the R worker (simsem over lavaan, the
authoritative engine), seeded through the call payload: identical seeds
produce identical power estimates (NFR-101). Python builds the two
lavaan syntaxes (population: all values fixed; analysis: free,
marker-scaled) and reads back per-focal-path power.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import numpy as np

from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    from pathlib import Path

    from burhan.core.artifacts.models import StudyConfig
    from burhan.core.playbook import Playbook
    from burhan.core.policy import Policy
    from burhan.core.rworker import RWorker

_POPULATION_RULE = re.compile(
    r"^\s*loadings\s+\.(\d+)\s*/\s*paths\s+\.(\d+)\s*/\s*corr\s+\.(\d+)\s*$"
)


def population_values(playbook: Playbook) -> dict[str, float]:
    """Parse PB-01 ``montecarlo_population`` ('loadings .70 / paths .30 / corr .30')."""
    for criterion in playbook.criteria("PB-01"):
        if criterion.get("name") == "montecarlo_population":
            match = _POPULATION_RULE.match(str(criterion.get("value", "")))
            if match is None:
                halt(
                    IntegrityHalt(
                        "PB-01 montecarlo_population value is not parseable",
                        report={"value": str(criterion.get("value"))},
                    )
                )
            return {
                "loading": float(f"0.{match.group(1)}"),
                "path": float(f"0.{match.group(2)}"),
                "correlation": float(f"0.{match.group(3)}"),
            }
    halt(
        IntegrityHalt(
            "playbook PB-01 lacks the montecarlo_population criterion "
            "(governed parameterization required; no invented values)",
            report={"criteria": [c.get("name") for c in playbook.criteria("PB-01")]},
        )
    )


def _topological_latents(config: StudyConfig) -> list[str]:
    """Latents in causal order (predecessors first); cycles halt."""
    direct = [(h.from_, h.to) for h in config.hypotheses if h.effect == "direct"]
    second_order = {
        c.code: list(c.components or []) for c in config.constructs if c.level == "second_order"
    }
    nodes = [c.code for c in config.constructs]
    incoming: dict[str, set[str]] = {node: set() for node in nodes}
    for source, target in direct:
        incoming[target].add(source)
    for parent, members in second_order.items():
        for member in members:
            incoming[member].add(parent)  # components are caused by the second-order factor
    ordered: list[str] = []
    remaining = dict(incoming)
    while remaining:
        ready = sorted(node for node, sources in remaining.items() if not sources)
        if not ready:
            halt(
                IntegrityHalt(
                    "hypothesized structural model is not acyclic; the "
                    "population model cannot be standardized",
                    report={"unresolved": sorted(remaining)},
                )
            )
        for node in ready:
            ordered.append(node)
            del remaining[node]
        for sources in remaining.values():
            sources.difference_update(ready)
    return ordered


def standardized_population(config: StudyConfig, *, playbook: Playbook) -> dict[str, Any]:
    """Exact standardized population: paths, correlations, disturbances.

    Solves the latent covariance recursion in causal order so that every
    latent variance is 1: for each caused latent, cov with every earlier
    latent is the path-weighted sum of its predictors' covariances, and
    its disturbance is 1 minus the explained variance.
    """
    values = population_values(playbook)
    ordered = _topological_latents(config)
    index = {code: position for position, code in enumerate(ordered)}
    direct = [(h.from_, h.to) for h in config.hypotheses if h.effect == "direct"]
    second_order = {
        c.code: list(c.components or []) for c in config.constructs if c.level == "second_order"
    }
    predictors: dict[str, list[str]] = {code: [] for code in ordered}
    for source, target in direct:
        predictors[target].append(source)
    for parent, members in second_order.items():
        for member in members:
            predictors[member].append(parent)

    caused = {code for code, sources in predictors.items() if sources}
    exogenous = [code for code in ordered if code not in caused]

    size = len(ordered)
    covariance = np.zeros((size, size))
    for code in exogenous:
        covariance[index[code], index[code]] = 1.0
    for one in exogenous:
        for two in exogenous:
            if one != two:
                covariance[index[one], index[two]] = values["correlation"]

    disturbances: dict[str, float] = {}
    for code in ordered:
        sources = predictors[code]
        if not sources:
            continue
        beta = np.zeros(size)
        for source in sources:
            beta[index[source]] = (
                values["path"] if code not in _components(config) else values["loading"]
            )
        row = covariance @ beta
        explained = float(beta @ covariance @ beta)
        if explained >= 1.0:
            halt(
                IntegrityHalt(
                    "population parameterization over-explains a latent "
                    "(R-squared >= 1); the governed values cannot be applied",
                    report={"latent": code, "explained": round(explained, 6)},
                )
            )
        position = index[code]
        covariance[position, :] = row
        covariance[:, position] = row
        covariance[position, position] = 1.0
        disturbances[code] = 1.0 - explained
    return {
        "values": values,
        "order": ordered,
        "disturbances": {k: round(v, 10) for k, v in disturbances.items()},
    }


def _components(config: StudyConfig) -> set[str]:
    members: set[str] = set()
    for construct in config.constructs:
        if construct.level == "second_order":
            members.update(construct.components or [])
    return members


def lavaan_syntaxes(config: StudyConfig, *, playbook: Playbook) -> dict[str, Any]:
    """Population (fixed values) and analysis (free) lavaan model syntax."""
    population = standardized_population(config, playbook=playbook)
    values = population["values"]
    loading = values["loading"]
    residual = round(1.0 - loading * loading, 10)
    indicators = {c.code: list(c.indicators or []) for c in config.constructs}
    second_order = {
        c.code: list(c.components or []) for c in config.constructs if c.level == "second_order"
    }
    caused = set(population["disturbances"])
    exogenous = [code for code in population["order"] if code not in caused]

    population_lines: list[str] = []
    analysis_lines: list[str] = []
    for construct in config.constructs:
        if construct.level != "first_order":
            continue
        codes = indicators[construct.code]
        population_lines.append(
            f"{construct.code} =~ " + " + ".join(f"{loading}*{item}" for item in codes)
        )
        analysis_lines.append(f"{construct.code} =~ " + " + ".join(codes))
        population_lines.extend(f"{item} ~~ {residual}*{item}" for item in codes)
    for parent, members in second_order.items():
        population_lines.append(
            f"{parent} =~ " + " + ".join(f"{loading}*{member}" for member in members)
        )
        analysis_lines.append(f"{parent} =~ " + " + ".join(members))
    focal: list[str] = []
    for hypothesis in config.hypotheses:
        if hypothesis.effect != "direct":
            continue
        population_lines.append(f"{hypothesis.to} ~ {values['path']}*{hypothesis.from_}")
        analysis_lines.append(f"{hypothesis.to} ~ {hypothesis.from_}")
        focal.append(f"{hypothesis.to}~{hypothesis.from_}")
    for position, one in enumerate(exogenous):
        for two in exogenous[position + 1 :]:
            population_lines.append(f"{one} ~~ {values['correlation']}*{two}")
    for code in exogenous:
        population_lines.append(f"{code} ~~ 1*{code}")
    for code, disturbance in population["disturbances"].items():
        population_lines.append(f"{code} ~~ {disturbance}*{code}")
    return {
        "population_model": "\n".join(population_lines),
        "analysis_model": "\n".join(analysis_lines),
        "focal_paths": focal,
        "population": population,
    }


def montecarlo_power(
    config: StudyConfig,
    *,
    n: int,
    seed: int,
    policy: Policy,
    playbook: Playbook,
    rworker: RWorker,
    run_dir: Path,
    call_id: str,
    alpha: float = 0.05,
    replications: int | None = None,
) -> dict[str, Any]:
    """Simulated power for the focal structural paths (PB-01, simsem).

    ``replications`` defaults to the policy rule
    ``power.montecarlo.replications``; tests pass a smaller count — the
    determinism contract (identical seed ⇒ identical estimates) holds at
    any count.
    """
    reps = (
        int(policy.rule("power.montecarlo.replications"))
        if replications is None
        else int(replications)
    )
    if reps < 2 or n < 10:
        halt(
            IntegrityHalt(
                "Monte Carlo power needs replications >= 2 and N >= 10",
                report={"replications": reps, "n": n},
            )
        )
    syntaxes = lavaan_syntaxes(config, playbook=playbook)
    result = rworker.call(
        "power_worker",
        {
            "op": "montecarlo",
            "population_model": syntaxes["population_model"],
            "analysis_model": syntaxes["analysis_model"],
            "focal_paths": syntaxes["focal_paths"],
            "n": n,
            "replications": reps,
            "alpha": alpha,
            "seed": seed,
        },
        call_id=call_id,
        run_dir=run_dir,
        seed=seed,
    )
    # No catch-and-continue, no raw dereference: the worker's power block
    # must exist, be a mapping, and carry a real number per focal path
    # (standards §4).
    raw_power = result.get("power")
    if not isinstance(raw_power, dict):
        halt(
            IntegrityHalt(
                "Monte Carlo result carries a missing or non-mapping power block",
                report={"power_type": type(raw_power).__name__},
            )
        )
    malformed = sorted(
        str(path)
        for path, value in raw_power.items()
        if isinstance(value, bool) or not isinstance(value, int | float)
    )
    if malformed:
        halt(
            IntegrityHalt(
                "Monte Carlo result carries nonnumeric power values",
                report={"paths": malformed},
            )
        )
    power = {str(path): float(value) for path, value in raw_power.items()}
    missing = sorted(set(syntaxes["focal_paths"]) - set(power))
    if missing:
        halt(
            IntegrityHalt(
                "Monte Carlo result lacks power for focal structural paths",
                report={"missing": missing},
            )
        )
    # No catch-and-continue: the convergence count must exist, be an
    # integer, and lie within [0, replications] — anything else is a
    # malformed worker result (standards §4).
    converged = result.get("converged")
    if isinstance(converged, bool) or not isinstance(converged, int) or not 0 <= converged <= reps:
        halt(
            IntegrityHalt(
                "Monte Carlo result carries a missing or malformed converged count",
                report={
                    "converged": repr(converged),
                    "replications": reps,
                },
            )
        )
    return {
        "replications": reps,
        "n": n,
        "seed": seed,
        "alpha": alpha,
        "power": power,
        "converged": converged,
        "population": syntaxes["population"]["values"],
    }
