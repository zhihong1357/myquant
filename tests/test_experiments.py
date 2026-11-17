from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from myquant.experiments import ExperimentRunner, TrialSpec
from myquant.hypotheses import (
    ExpectedDirection,
    HypothesisRegistry,
    HypothesisSpec,
    HypothesisState,
    MultiplicityCorrection,
    SampleWindow,
)
from myquant.registry import read_and_verify


def make_hypothesis():
    start = datetime(2020, 1, 1, tzinfo=UTC)
    day = timedelta(days=1)
    return HypothesisSpec(
        hypothesis_id="H0001",
        title="VIX leads MOVE repricing",
        research_question=(
            "Does the daily VIX change contain incremental information about "
            "the next-session MOVE index return after controlling for rates and equities?"
        ),
        mechanism=(
            "Options-implied equity volatility may reprice faster than Treasury "
            "volatility during cross-asset risk shocks."
        ),
        alternative_hypothesis=(
            "Lagged VIX changes explain a positive, out-of-sample component of "
            "future MOVE changes beyond the declared baseline."
        ),
        null_hypothesis=(
            "Lagged VIX changes have no incremental predictive value over the "
            "declared baseline after costs and dependence controls."
        ),
        universe=("index:vix", "index:move"),
        source_versions=("sample-vix@v1", "sample-move@v1"),
        observation_frequency="daily",
        horizon_seconds=86_400,
        target_definition="Next session close-to-close MOVE log return",
        feature_set=("vix_return_lag_1@v1", "rates_return_1d@v1"),
        model_definition=("OLS with intercept", "Newey-West HAC standard errors"),
        fixed_parameters=("lag=1", "winsorization=none"),
        benchmark="Intercept-only historical mean",
        cost_model="No direct trading claim; diagnostic forecast evaluation only",
        cost_assumptions=("No fills assumed at this stage",),
        train_window=SampleWindow(start=start, end=start + 365 * day),
        validation_window=SampleWindow(
            start=start + 366 * day,
            end=start + 500 * day,
        ),
        holdout_window=SampleWindow(
            start=start + 501 * day,
            end=start + 650 * day,
        ),
        purge_gap_seconds=86_400,
        minimum_train_observations=200,
        minimum_validation_observations=60,
        minimum_holdout_observations=60,
        primary_metric="Out-of-sample incremental R-squared",
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=0.01,
        familywise_alpha=0.05,
        multiple_testing_family="Cross-market volatility transmission v1",
        multiple_testing_method=MultiplicityCorrection.NONE,
        planned_test_count=1,
        missing_data_policy="No forward filling; exclude incomplete paired sessions",
        acceptance_criteria=("Holdout incremental R-squared exceeds 0.01",),
        rejection_criteria=("Holdout incremental R-squared is no greater than zero",),
        known_confounders=("Rates level", "Equity return"),
        exclusions=("Sessions with unscheduled market closures",),
        random_seed=17,
    )


def make_registry(tmp_path):
    registry = HypothesisRegistry(tmp_path / "hypotheses")
    registration = registry.register(make_hypothesis())
    return registry, registration


def make_trial(registration, **overrides):
    values = {
        "trial_id": "T0001",
        "hypothesis_id": registration.spec.hypothesis_id,
        "hypothesis_version": registration.version,
        "hypothesis_fingerprint": registration.spec_fingerprint,
        "description": "Test a synthetic preregistered lead-lag relationship",
        "seed": registration.spec.random_seed,
        "data_fingerprint": "a" * 64,
        "config_fingerprint": "b" * 64,
        "code_revision": "abcdef123456",
        "horizon_seconds": registration.spec.horizon_seconds,
        "source_versions": registration.spec.source_versions,
        "feature_set": registration.spec.feature_set,
        "model_definition": registration.spec.model_definition,
        "benchmark": registration.spec.benchmark,
        "cost_model": registration.spec.cost_model,
        "primary_metric": registration.spec.primary_metric,
        "expected_direction": registration.spec.expected_direction.value,
        "parameters": {"lag_steps": 1},
    }
    values.update(overrides)
    return TrialSpec(**values)


def test_runner_records_success_bound_to_preregistered_version(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)
    receipt = runner.run(
        make_trial(registration),
        lambda spec: {"correlation": 0.91, "n": 2_000, "seed": spec.seed},
    )
    records = read_and_verify(tmp_path / "trials.jsonl")

    assert receipt.status == "completed"
    assert receipt.hypothesis_version == 1
    assert receipt.hypothesis_fingerprint == registration.spec_fingerprint
    assert len(receipt.spec_fingerprint) == 64
    assert records[0]["status"] == "completed"
    assert records[0]["result"]["spec"]["seed"] == 17
    assert records[0]["result"]["metrics"]["correlation"] == 0.91
    assert registry.get_state("H0001", 1) == HypothesisState.TESTING


def test_runner_records_failed_experiment_and_keeps_it_in_testing(tmp_path):
    registry, registration = make_registry(tmp_path)
    ledger = tmp_path / "trials.jsonl"
    runner = ExperimentRunner(ledger, registry)

    def explode(_spec):
        raise RuntimeError("synthetic failure")

    with pytest.raises(RuntimeError, match="synthetic failure"):
        runner.run(make_trial(registration), explode)

    records = read_and_verify(ledger)
    assert len(records) == 1
    assert records[0]["status"] == "failed"
    assert records[0]["result"]["error_type"] == "RuntimeError"
    assert registry.get_state("H0001", 1) == HypothesisState.TESTING


def test_runner_refuses_duplicate_trial_ids(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)
    runner.run(make_trial(registration), lambda _spec: {"metric": 1.0})

    with pytest.raises(FileExistsError, match="already exists"):
        runner.run(make_trial(registration), lambda _spec: {"metric": 2.0})


def test_runner_rejects_nan_metrics_and_records_failure(tmp_path):
    registry, registration = make_registry(tmp_path)
    ledger = tmp_path / "trials.jsonl"
    runner = ExperimentRunner(ledger, registry)

    with pytest.raises(ValueError, match="Out of range float values"):
        runner.run(make_trial(registration), lambda _spec: {"sharpe": float("nan")})

    records = read_and_verify(ledger)
    assert records[0]["status"] == "failed"


def test_trial_spec_requires_hash_fingerprints():
    with pytest.raises(ValidationError):
        TrialSpec(
            trial_id="T0001",
            hypothesis_id="H0001",
            hypothesis_version=1,
            hypothesis_fingerprint="not-a-hash",
            description="Invalid trial with malformed preregistration hash",
            seed=1,
            data_fingerprint="a" * 64,
            config_fingerprint="b" * 64,
            code_revision="abcdef123456",
            horizon_seconds=60,
            source_versions=("feed@v1",),
            feature_set=("feature_a",),
            model_definition=("baseline",),
            benchmark="baseline",
            cost_model="cost model",
            primary_metric="metric",
            expected_direction="positive",
        )


def test_trial_fingerprint_is_independent_of_trial_id_and_dict_key_order(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)
    first = runner.run(
        make_trial(registration, parameters={"a": 1, "b": 2}),
        lambda _spec: {"ok": True},
    )
    second = runner.run(
        make_trial(
            registration,
            trial_id="T0002",
            parameters={"b": 2, "a": 1},
        ),
        lambda _spec: {"ok": True},
    )
    assert first.spec_fingerprint == second.spec_fingerprint


def test_runner_refuses_features_not_declared_in_preregistration(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)
    wrong_trial = make_trial(registration, feature_set=("undeclared_feature@v1",))

    with pytest.raises(PermissionError, match="feature_set"):
        runner.run(wrong_trial, lambda _spec: {"score": 0.1})

    assert registry.get_state("H0001", 1) == HypothesisState.REGISTERED
    assert not (tmp_path / "trials.jsonl").exists()


def test_runner_refuses_wrong_preregistration_fingerprint(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)
    wrong_trial = make_trial(registration, hypothesis_fingerprint="c" * 64)

    with pytest.raises(PermissionError, match="fingerprint"):
        runner.run(wrong_trial, lambda _spec: {"score": 0.1})


def test_runner_refuses_trials_for_terminal_hypothesis(tmp_path):
    registry, registration = make_registry(tmp_path)
    registry.transition(
        "H0001",
        1,
        HypothesisState.TESTING,
        reason="Testing opened manually",
    )
    registry.transition(
        "H0001",
        1,
        HypothesisState.REJECTED,
        reason="Predeclared rejection condition met",
    )
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)

    with pytest.raises(PermissionError, match="not open for trials"):
        runner.run(
            make_trial(registration),
            lambda _spec: {"score": 0.1},
        )
