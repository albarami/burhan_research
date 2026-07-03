"""Monte Carlo power (AT-M09-5; FR-401; PB-01 montecarlo_population).

The population parameterization comes from the governed playbook
criterion (researcher change, 2026-07-03); the standardization is solved
exactly and hand-verified here; the simulation runs through simsem in
the R worker, and identical seeds produce identical power estimates.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from generator import build_golden

from burhan.core.artifacts.loader import validate_and_build
from burhan.core.artifacts.models import StudyConfig
from burhan.core.errors import IntegrityHalt
from burhan.core.playbook import Playbook
from burhan.core.policy import Policy
from burhan.core.rworker import RWorker
from burhan.stats.montecarlo import (
    lavaan_syntaxes,
    montecarlo_power,
    population_values,
    standardized_population,
)

REPO = Path(__file__).resolve().parents[3]


def _playbook() -> Playbook:
    return Playbook.load(REPO / "playbooks" / "CB_SEM_PLAYBOOK_v1.0.yaml", mode="certification")


def _policy() -> Policy:
    return Policy.load(REPO / "policy" / "decision_policy.template.yaml", mode="certification")


def _golden_config() -> StudyConfig:
    return validate_and_build(StudyConfig, build_golden(11).config)


def _example_config() -> StudyConfig:
    import yaml

    data = yaml.safe_load(
        (REPO / "schemas" / "study_config.example.yaml").read_text(encoding="utf-8")
    )
    return validate_and_build(StudyConfig, data)


# -- governed parameterization (no invented values) ------------------------------------


def test_population_values_come_from_the_playbook() -> None:
    values = population_values(_playbook())
    assert values == {"loading": 0.70, "path": 0.30, "correlation": 0.30}


def test_missing_population_criterion_halts() -> None:
    class Doctored:
        @staticmethod
        def criteria(step_id: str) -> list[dict[str, str]]:
            return []

    with pytest.raises(IntegrityHalt) as excinfo:
        population_values(Doctored())  # type: ignore[arg-type]
    assert "montecarlo_population" in excinfo.value.message


def test_standardized_disturbances_hand_derived_golden() -> None:
    population = standardized_population(_golden_config(), playbook=_playbook())
    # chain RES -> CUL -> INT at beta .30: each endogenous R^2 = .09
    assert population["disturbances"] == {"CUL": 0.91, "INT": 0.91}


def test_standardized_disturbances_hand_derived_worked_example() -> None:
    population = standardized_population(_example_config(), playbook=_playbook())
    disturbances = population["disturbances"]
    # components load .70 on ENB: 1 - .49
    assert disturbances["RES"] == pytest.approx(0.51)
    assert disturbances["CUL"] == pytest.approx(0.51)
    # PU ~ .3*ENB and ATT ~ .3*PU: 1 - .09
    assert disturbances["PU"] == pytest.approx(0.91)
    assert disturbances["ATT"] == pytest.approx(0.91)
    # INT ~ .3*ATT + .3*ENB with cov(ATT, ENB) = .09:
    # R^2 = .09 + .09 + 2(.3)(.3)(.09) = .1962
    assert disturbances["INT"] == pytest.approx(1 - 0.1962)


def test_lavaan_syntaxes_carry_exact_population_values() -> None:
    syntaxes = lavaan_syntaxes(_golden_config(), playbook=_playbook())
    population = syntaxes["population_model"]
    assert "RES =~ 0.7*RS1 + 0.7*RS2 + 0.7*RS3 + 0.7*RS4" in population
    assert "RS1 ~~ 0.51*RS1" in population
    assert "CUL ~ 0.3*RES" in population
    assert "RES ~~ 1*RES" in population
    assert "CUL ~~ 0.91*CUL" in population
    analysis = syntaxes["analysis_model"]
    assert "RES =~ RS1 + RS2 + RS3 + RS4" in analysis
    assert "CUL ~ RES" in analysis
    assert syntaxes["focal_paths"] == ["CUL~RES", "INT~CUL"]


def test_second_order_population_syntax() -> None:
    syntaxes = lavaan_syntaxes(_example_config(), playbook=_playbook())
    population = syntaxes["population_model"]
    assert "ENB =~ 0.7*RES + 0.7*CUL" in population
    assert "RES ~~ 0.51*RES" in population
    assert "ENB ~~ 1*ENB" in population


class _DoctoredPlaybook:
    def __init__(self, value: str) -> None:
        self._value = value

    def criteria(self, step_id: str) -> list[dict[str, str]]:
        return [{"name": "montecarlo_population", "value": self._value}]


def test_unparseable_population_value_halts() -> None:
    with pytest.raises(IntegrityHalt) as excinfo:
        population_values(_DoctoredPlaybook("generous"))  # type: ignore[arg-type]
    assert "not parseable" in excinfo.value.message


def test_cyclic_structural_model_halts() -> None:
    data = build_golden(11).config
    data["hypotheses"].append(
        {"id": "H3", "effect": "direct", "from": "INT", "to": "RES", "sign": "positive"}
    )  # RES -> CUL -> INT -> RES
    data["model"]["endogenous"] = ["CUL", "INT", "RES"]
    data["model"]["exogenous"] = ["RES"]
    config = validate_and_build(StudyConfig, data)
    with pytest.raises(IntegrityHalt) as excinfo:
        standardized_population(config, playbook=_playbook())
    assert "acyclic" in excinfo.value.message


def _two_exogenous_config() -> StudyConfig:
    data = build_golden(11).config
    data["hypotheses"] = [
        {"id": "H1", "effect": "direct", "from": "RES", "to": "INT", "sign": "positive"},
        {"id": "H2", "effect": "direct", "from": "CUL", "to": "INT", "sign": "positive"},
    ]
    data["model"] = {"exogenous": ["RES", "CUL"], "endogenous": ["INT"]}
    return validate_and_build(StudyConfig, data)


def test_exogenous_correlations_enter_population_and_syntax() -> None:
    syntaxes = lavaan_syntaxes(_two_exogenous_config(), playbook=_playbook())
    population = syntaxes["population_model"]
    assert "CUL ~~ 0.3*RES" in population or "RES ~~ 0.3*CUL" in population
    # INT ~ .3*RES + .3*CUL with corr(RES, CUL)=.3:
    # R^2 = .09 + .09 + 2(.3)(.3)(.3) = .234
    disturbances = syntaxes["population"]["disturbances"]
    assert disturbances["INT"] == pytest.approx(1 - 0.234)


def test_over_explained_population_halts() -> None:
    playbook = _DoctoredPlaybook("loadings .70 / paths .90 / corr .90")
    with pytest.raises(IntegrityHalt) as excinfo:
        standardized_population(_two_exogenous_config(), playbook=playbook)  # type: ignore[arg-type]
    assert "over-explains" in excinfo.value.message


class _CannedWorker:
    def __init__(self, result: dict[str, object]) -> None:
        self._result = result

    def call(self, *args: object, **kwargs: object) -> dict[str, object]:
        return self._result


@pytest.mark.parametrize(
    "converged",
    [
        None,  # absent entirely
        "forty",  # not an integer
        41,  # exceeds replications
        -1,  # negative
        39.5,  # non-integral number
    ],
)
def test_malformed_converged_halts_typed(
    tmp_path: Path, converged: object
) -> None:  # REJECT-TC09 round 2 fix 1
    result: dict[str, object] = {"power": {"CUL~RES": 0.9, "INT~CUL": 0.9}}
    if converged is not None:
        result["converged"] = converged
    with pytest.raises(IntegrityHalt) as excinfo:  # typed, never a silent default
        montecarlo_power(
            _golden_config(),
            n=200,
            seed=1,
            policy=_policy(),
            playbook=_playbook(),
            rworker=_CannedWorker(result),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id=f"mc-conv-{converged}",
            replications=40,
        )
    assert "converged" in excinfo.value.message


@pytest.mark.parametrize(
    "result",
    [
        {"converged": 40},  # power absent entirely (reviewer probe: raw KeyError)
        {"power": ["CUL~RES", 0.9], "converged": 40},  # not a mapping
        {"power": "high", "converged": 40},  # not a mapping either
        {"power": {"CUL~RES": "strong", "INT~CUL": 0.9}, "converged": 40},  # nonnumeric
        {"power": {"CUL~RES": None, "INT~CUL": 0.9}, "converged": 40},  # null value
        {"power": {"CUL~RES": True, "INT~CUL": 0.9}, "converged": 40},  # bool value
    ],
)
def test_malformed_power_halts_typed(
    tmp_path: Path, result: dict[str, object]
) -> None:  # REJECT-TC09 round 4: raw KeyError/TypeError probes
    with pytest.raises(IntegrityHalt) as excinfo:  # typed, never KeyError
        montecarlo_power(
            _golden_config(),
            n=200,
            seed=1,
            policy=_policy(),
            playbook=_playbook(),
            rworker=_CannedWorker(result),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="mc-power-shape",
            replications=40,
        )
    assert "power" in excinfo.value.message


def test_missing_focal_power_in_result_halts(tmp_path: Path) -> None:
    class HollowWorker:
        @staticmethod
        def call(*args: object, **kwargs: object) -> dict[str, object]:
            return {"power": {}, "converged": 40}

    with pytest.raises(IntegrityHalt) as excinfo:
        montecarlo_power(
            _golden_config(),
            n=200,
            seed=1,
            policy=_policy(),
            playbook=_playbook(),
            rworker=HollowWorker(),  # type: ignore[arg-type]
            run_dir=tmp_path,
            call_id="mc-hollow",
            replications=40,
        )
    assert "lacks power" in excinfo.value.message


# -- AT-M09-5: seed determinism through simsem -----------------------------------------


def _run_montecarlo(tmp_path: Path, seed: int, call_id: str) -> dict[str, object]:
    return montecarlo_power(
        _golden_config(),
        n=200,
        seed=seed,
        policy=_policy(),
        playbook=_playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id=call_id,
        replications=40,  # policy's 1000 is the production count; the
        # determinism contract holds at any count
    )


def test_identical_seeds_produce_identical_power(tmp_path: Path) -> None:  # AT-M09-5
    first = _run_montecarlo(tmp_path, 11, "mc-a")
    second = _run_montecarlo(tmp_path, 11, "mc-b")
    assert first["power"] == second["power"]
    assert first["converged"] == second["converged"]


def _registry() -> dict[str, object]:
    import json

    loaded = json.loads(
        (REPO / "tests" / "fixtures" / "known_answers" / "montecarlo_pins.json").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(loaded, dict)
    return loaded


def _assert_within_band(
    observed: dict[str, float], anchors: dict[str, float], band: float, *, seed_name: str
) -> None:
    """Typed band check (E-R5): any focal value outside anchor ± band halts."""
    from burhan.core.errors import halt

    for path, anchor in anchors.items():
        value = observed.get(path)
        if value is None or abs(float(value) - float(anchor)) > band:
            halt(
                IntegrityHalt(
                    "Monte Carlo output outside the certified tolerance band "
                    "(04 §7 cross-platform numeric policy)",
                    report={
                        "seed": seed_name,
                        "path": path,
                        "band": band,
                        "deviation": None
                        if value is None
                        else round(abs(float(value) - float(anchor)), 6),
                    },
                )
            )


def test_registry_integrity_unconditional() -> None:
    # E-R5: runs identically with or without the workstation marker.
    registry = _registry()
    assert registry["certified_marker"] == "BURHAN_CERTIFIED_WORKSTATION"
    assert int(registry["replications"]) == 400  # type: ignore[arg-type]
    band = registry["band"]
    assert isinstance(band, dict) and 0.0 < float(band["value"]) < 0.2
    assert "MCSE" in str(band["justification"])
    workstation = registry["workstation"]
    assert isinstance(workstation, dict)
    assert "BURHAN_CERTIFIED_WORKSTATION" in str(workstation["captured"])
    for seed_key in ("seed_11", "seed_12"):
        anchors = workstation[seed_key]  # type: ignore[index]
        assert set(anchors) == {"CUL~RES", "INT~CUL"}
        for value in anchors.values():
            assert 0.0 <= float(value) <= 1.0
    assert int(workstation["converged"]) == 400  # type: ignore[arg-type]


def test_certified_anchor_values(tmp_path: Path) -> None:
    # E-R5 semantics: on the certified workstation (governed marker set),
    # the R=400 anchors are asserted EXACTLY (byte-equal quantized values,
    # converged exact) — a mismatch is broken certification. On any other
    # host, the SAME anchors are asserted within the registry's tolerance
    # band (typed halt outside it) plus exact convergence — a value
    # assertion, never a skip. Identical-seed determinism is asserted
    # separately and everywhere by the test above.
    import os

    registry = _registry()
    replications = int(registry["replications"])  # type: ignore[arg-type]
    workstation = registry["workstation"]
    band = float(registry["band"]["value"])  # type: ignore[index, arg-type]
    marked = os.environ.get("BURHAN_CERTIFIED_WORKSTATION") == "1"

    eleven = montecarlo_power(
        _golden_config(),
        n=200,
        seed=11,
        policy=_policy(),
        playbook=_playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id="anchor-11",
        replications=replications,
    )
    twelve = montecarlo_power(
        _golden_config(),
        n=200,
        seed=12,
        policy=_policy(),
        playbook=_playbook(),
        rworker=RWorker(),
        run_dir=tmp_path,
        call_id="anchor-12",
        replications=replications,
    )
    assert eleven["converged"] == replications
    assert twelve["converged"] == replications
    if marked:
        assert eleven["power"] == workstation["seed_11"]  # type: ignore[index]
        assert twelve["power"] == workstation["seed_12"]  # type: ignore[index]
    else:
        _assert_within_band(
            eleven["power"],  # type: ignore[arg-type]
            workstation["seed_11"],  # type: ignore[index, arg-type]
            band,
            seed_name="seed_11",
        )
        _assert_within_band(
            twelve["power"],  # type: ignore[arg-type]
            workstation["seed_12"],  # type: ignore[index, arg-type]
            band,
            seed_name="seed_12",
        )


def test_band_check_negative_control() -> None:
    # E-R5: materially wrong Monte Carlo outputs FAIL the band check —
    # a silently broken simulation cannot ride the tolerance. Runs in
    # every environment, marker or not.
    registry = _registry()
    anchors = registry["workstation"]["seed_11"]  # type: ignore[index]
    band = float(registry["band"]["value"])  # type: ignore[index, arg-type]
    wrong = {path: float(value) + 0.20 for path, value in anchors.items()}  # type: ignore[union-attr]
    with pytest.raises(IntegrityHalt) as excinfo:
        _assert_within_band(wrong, anchors, band, seed_name="seed_11")  # type: ignore[arg-type]
    assert "tolerance band" in excinfo.value.message
    within = {path: float(value) + 0.03 for path, value in anchors.items()}  # type: ignore[union-attr]
    _assert_within_band(within, anchors, band, seed_name="seed_11")  # type: ignore[arg-type]
    missing = {next(iter(anchors)): float(next(iter(anchors.values())))}  # type: ignore[union-attr, call-overload, arg-type]
    with pytest.raises(IntegrityHalt):
        _assert_within_band(missing, anchors, band, seed_name="seed_11")  # type: ignore[arg-type]


def test_replications_default_from_policy(tmp_path: Path) -> None:
    # The default replication count is the policy rule; the guard proves
    # the read without paying for a 1000-rep simulation.
    with pytest.raises(IntegrityHalt) as excinfo:
        montecarlo_power(
            _golden_config(),
            n=5,  # under the guard floor
            seed=1,
            policy=_policy(),
            playbook=_playbook(),
            rworker=RWorker(),
            run_dir=tmp_path,
            call_id="mc-guard",
        )
    assert excinfo.value.to_report()["details"]["replications"] == 1000
