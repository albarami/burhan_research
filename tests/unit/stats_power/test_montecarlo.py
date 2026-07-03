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


def test_pinned_seeds_reproduce_fixed_expected_outputs(tmp_path: Path) -> None:
    # Fixed expected outputs under the locked R environment (renv.lock):
    # captured once from the governed stack and pinned — any drift in
    # packages, model syntax, or seeding breaks these exact values.
    eleven = _run_montecarlo(tmp_path, 11, "mc-pin11")
    assert eleven["power"] == {"CUL~RES": 0.925, "INT~CUL": 0.95}
    assert eleven["converged"] == 40
    twelve = _run_montecarlo(tmp_path, 12, "mc-pin12")
    assert twelve["power"] == {"CUL~RES": 0.925, "INT~CUL": 0.85}
    assert twelve["converged"] == 40


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
