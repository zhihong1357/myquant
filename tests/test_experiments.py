import logging
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from myquant.contracts import MultiplicityCorrection
from myquant.experiments import (
    ExperimentRunner,
    TrialParameter,
    TrialSpec,
    git_head_revision,
)
from myquant.hypotheses import (
    ExpectedDirection,
    HypothesisRegistry,
    HypothesisSpec,
    HypothesisState,
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
        target_error_rate=0.05,
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
        "universe": registration.spec.universe,
        "observation_frequency": registration.spec.observation_frequency,
        "horizon_seconds": registration.spec.horizon_seconds,
        "target_definition": registration.spec.target_definition,
        "source_versions": registration.spec.source_versions,
        "feature_set": registration.spec.feature_set,
        "model_definition": registration.spec.model_definition,
        "benchmark": registration.spec.benchmark,
        "cost_model": registration.spec.cost_model,
        "primary_metric": registration.spec.primary_metric,
        "expected_direction": registration.spec.expected_direction.value,
        "parameters": (
            TrialParameter(name="lag", value=1),
            TrialParameter(name="winsorization", value="none"),
        ),
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


def test_runner_logs_trial_completion_and_failure(tmp_path, caplog):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)

    def explode(_spec):
        raise RuntimeError("boom")

    with caplog.at_level(logging.INFO, logger="myquant.experiments"):
        runner.run(make_trial(registration), lambda _spec: {"ok": True})
        with pytest.raises(RuntimeError):
            runner.run(make_trial(registration, trial_id="T0002"), explode)
    messages = [record.message for record in caplog.records]
    assert any("trial T0001" in message and "completed" in message for message in messages)
    assert any("trial T0002" in message and "failed" in message for message in messages)


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


def test_runner_accepts_numpy_scalar_and_array_metrics(tmp_path):
    registry, registration = make_registry(tmp_path)
    ledger = tmp_path / "trials.jsonl"
    runner = ExperimentRunner(ledger, registry)

    receipt = runner.run(
        make_trial(registration),
        lambda _spec: {
            "count": np.int64(42),
            "sharpe": np.float32(1.25),
            "converged": np.bool_(True),
            "fold_scores": np.array([0.1, 0.2, 0.3]),
            "nested": {"inner": np.int32(7)},
        },
    )

    assert receipt.status == "completed"
    assert receipt.metrics["count"] == 42
    assert isinstance(receipt.metrics["count"], int)
    assert receipt.metrics["sharpe"] == pytest.approx(1.25, abs=1e-6)
    assert receipt.metrics["converged"] is True
    assert receipt.metrics["fold_scores"] == pytest.approx([0.1, 0.2, 0.3])
    assert receipt.metrics["nested"]["inner"] == 7
    records = read_and_verify(ledger)
    assert records[0]["status"] == "completed"


def test_runner_rejects_numpy_nan_metrics_and_records_failure(tmp_path):
    registry, registration = make_registry(tmp_path)
    ledger = tmp_path / "trials.jsonl"
    runner = ExperimentRunner(ledger, registry)

    with pytest.raises(ValueError, match="Out of range float values"):
        runner.run(
            make_trial(registration),
            lambda _spec: {"sharpe": np.float64(float("nan"))},
        )

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
            universe=("equity:us:spy",),
            observation_frequency="1m",
            horizon_seconds=60,
            target_definition="Next minute return",
            source_versions=("feed@v1",),
            feature_set=("feature_a@v1",),
            model_definition=("baseline",),
            benchmark="baseline",
            cost_model="cost model",
            primary_metric="metric",
            expected_direction="positive",
        )


def test_trial_fingerprint_is_independent_of_trial_id_and_parameter_order(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)
    first = runner.run(
        make_trial(
            registration,
            parameters=(
                TrialParameter(name="lag", value=1),
                TrialParameter(name="winsorization", value="none"),
            ),
        ),
        lambda _spec: {"ok": True},
    )
    second = runner.run(
        make_trial(
            registration,
            trial_id="T0002",
            parameters=(
                TrialParameter(name="winsorization", value="none"),
                TrialParameter(name="lag", value=1),
            ),
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


def test_trial_parameter_order_is_canonical_and_deeply_immutable(tmp_path):
    _registry, registration = make_registry(tmp_path)
    first = make_trial(
        registration,
        parameters=(
            TrialParameter(name="b", value=2),
            TrialParameter(name="a", value=1),
        ),
    )
    second = make_trial(
        registration,
        parameters=(
            TrialParameter(name="a", value=1),
            TrialParameter(name="b", value=2),
        ),
    )
    assert first.parameters == second.parameters
    assert tuple(item.name for item in first.parameters) == ("a", "b")
    with pytest.raises(ValidationError):
        first.parameters[0].name = "changed"


def test_trial_parameter_rejects_duplicate_names_and_nonfinite_values(tmp_path):
    _registry, registration = make_registry(tmp_path)
    payload = make_trial(registration).model_dump()
    payload["parameters"] = (
        TrialParameter(name="same", value=1),
        TrialParameter(name="same", value=2),
    )
    with pytest.raises(ValidationError, match="must be unique"):
        TrialSpec.model_validate(payload)

    with pytest.raises(ValidationError):
        TrialParameter(name="bad", value=float("nan"))


def test_runner_refuses_changed_fixed_parameters_before_testing(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)
    wrong_trial = make_trial(
        registration,
        parameters=(
            TrialParameter(name="lag", value=2),
            TrialParameter(name="winsorization", value="none"),
        ),
    )

    with pytest.raises(PermissionError, match="parameters"):
        runner.run(wrong_trial, lambda _spec: {"score": 0.1})

    assert registry.get_state("H0001", 1) == HypothesisState.REGISTERED
    assert not (tmp_path / "trials.jsonl").exists()


def test_git_head_revision_reads_local_checkout(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git binary is not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    (repo / "file.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True, env=env)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"],
        check=True,
        env=env,
    )
    expected = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert git_head_revision(repo) == expected
    assert len(expected) == 40
    monkeypatch.chdir(repo)
    assert git_head_revision() == expected


def test_git_head_revision_returns_none_outside_a_repository(tmp_path):
    assert git_head_revision(tmp_path) is None
    assert git_head_revision(tmp_path / "missing") is None


def test_runner_refuses_changed_target_before_testing(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)
    wrong_trial = make_trial(
        registration,
        target_definition="Next five session MOVE return",
    )

    with pytest.raises(PermissionError, match="target_definition"):
        runner.run(wrong_trial, lambda _spec: {"score": 0.1})

    assert registry.get_state("H0001", 1) == HypothesisState.REGISTERED
    assert not (tmp_path / "trials.jsonl").exists()


def test_runner_accepts_numerically_equal_fixed_parameters(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)

    # The preregistration says lag=1; a float 1.0 is the same number.
    receipt = runner.run(
        make_trial(
            registration,
            trial_id="T0001",
            parameters=(
                TrialParameter(name="lag", value=1.0),
                TrialParameter(name="winsorization", value="none"),
            ),
        ),
        lambda _spec: {"ok": True},
    )
    assert receipt.status == "completed"

    # A boolean True is not the number 1: booleans compare as "true"/"false".
    with pytest.raises(PermissionError, match="parameters.*'lag'"):
        runner.run(
            make_trial(
                registration,
                trial_id="T0002",
                parameters=(
                    TrialParameter(name="lag", value=True),
                    TrialParameter(name="winsorization", value="none"),
                ),
            ),
            lambda _spec: {"ok": True},
        )


def test_runner_accepts_equivalent_decimal_spellings(tmp_path):
    spec = make_hypothesis().model_copy(
        update={"fixed_parameters": ("alpha=0.50", "lag=1", "threshold=1e-3")}
    )
    registry = HypothesisRegistry(tmp_path / "hypotheses")
    registration = registry.register(spec)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)

    receipt = runner.run(
        make_trial(
            registration,
            parameters=(
                TrialParameter(name="alpha", value=0.5),
                TrialParameter(name="lag", value=1),
                TrialParameter(name="threshold", value=0.001),
            ),
        ),
        lambda _spec: {"ok": True},
    )
    assert receipt.status == "completed"


def test_runner_parameter_mismatch_names_parameter_and_values(tmp_path):
    registry, registration = make_registry(tmp_path)
    runner = ExperimentRunner(tmp_path / "trials.jsonl", registry)

    with pytest.raises(
        PermissionError,
        match="parameters: 'lag' expected '1' but trial has '2'",
    ):
        runner.run(
            make_trial(
                registration,
                parameters=(
                    TrialParameter(name="lag", value=2),
                    TrialParameter(name="winsorization", value="none"),
                ),
            ),
            lambda _spec: {"score": 0.1},
        )

    with pytest.raises(PermissionError, match="'lag'.*missing from the trial"):
        runner.run(
            make_trial(
                registration,
                parameters=(TrialParameter(name="winsorization", value="none"),),
            ),
            lambda _spec: {"score": 0.1},
        )

    with pytest.raises(PermissionError, match="'surprise' is not preregistered"):
        runner.run(
            make_trial(
                registration,
                parameters=(
                    TrialParameter(name="lag", value=1),
                    TrialParameter(name="winsorization", value="none"),
                    TrialParameter(name="surprise", value=1),
                ),
            ),
            lambda _spec: {"score": 0.1},
        )

    assert registry.get_state("H0001", 1) == HypothesisState.REGISTERED
    assert not (tmp_path / "trials.jsonl").exists()
