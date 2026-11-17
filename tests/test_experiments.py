import pytest
from pydantic import ValidationError

from myquant.experiments import ExperimentRunner, TrialSpec
from myquant.registry import read_and_verify


def make_spec(**overrides):
    values = {
        "trial_id": "T0001",
        "hypothesis_id": "H0001",
        "description": "Test a synthetic lead-lag relationship",
        "seed": 7,
        "data_fingerprint": "a" * 64,
        "config_fingerprint": "b" * 64,
        "code_revision": "abcdef123456",
        "parameters": {"lag_steps": 3, "beta": 0.8},
    }
    values.update(overrides)
    return TrialSpec(**values)


def test_runner_records_success_with_reproducibility_metadata(tmp_path):
    runner = ExperimentRunner(tmp_path / "trials.jsonl")
    receipt = runner.run(
        make_spec(),
        lambda spec: {"correlation": 0.91, "n": 2_000, "seed": spec.seed},
    )
    records = read_and_verify(tmp_path / "trials.jsonl")
    assert receipt.status == "completed"
    assert len(receipt.spec_fingerprint) == 64
    assert records[0]["status"] == "completed"
    assert records[0]["result"]["spec"]["seed"] == 7
    assert records[0]["result"]["metrics"]["correlation"] == 0.91


def test_runner_records_failed_experiment_then_reraises(tmp_path):
    ledger = tmp_path / "trials.jsonl"
    runner = ExperimentRunner(ledger)

    def explode(_spec):
        raise RuntimeError("synthetic failure")

    with pytest.raises(RuntimeError, match="synthetic failure"):
        runner.run(make_spec(), explode)

    records = read_and_verify(ledger)
    assert len(records) == 1
    assert records[0]["status"] == "failed"
    assert records[0]["result"]["error_type"] == "RuntimeError"


def test_runner_refuses_duplicate_trial_ids(tmp_path):
    runner = ExperimentRunner(tmp_path / "trials.jsonl")
    runner.run(make_spec(), lambda _spec: {"metric": 1.0})
    with pytest.raises(FileExistsError, match="already exists"):
        runner.run(make_spec(), lambda _spec: {"metric": 2.0})


def test_runner_rejects_nan_metrics_and_records_failure(tmp_path):
    ledger = tmp_path / "trials.jsonl"
    runner = ExperimentRunner(ledger)
    with pytest.raises(ValueError, match="Out of range float values"):
        runner.run(make_spec(), lambda _spec: {"sharpe": float("nan")})
    records = read_and_verify(ledger)
    assert records[0]["status"] == "failed"


def test_trial_spec_requires_hash_fingerprints():
    with pytest.raises(ValidationError):
        make_spec(data_fingerprint="not-a-hash")


def test_trial_fingerprint_is_independent_of_parameter_key_order(tmp_path):
    runner = ExperimentRunner(tmp_path / "trials.jsonl")
    first = runner.run(
        make_spec(parameters={"a": 1, "b": 2}),
        lambda _spec: {"ok": True},
    )
    second = runner.run(
        make_spec(
            trial_id="T0002",
            parameters={"b": 2, "a": 1},
        ),
        lambda _spec: {"ok": True},
    )
    assert first.spec_fingerprint == second.spec_fingerprint
