from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from myquant.hypotheses import (
    ExpectedDirection,
    HypothesisRegistry,
    HypothesisSpec,
    HypothesisState,
    SampleWindow,
)


def make_spec(**overrides):
    start = datetime(2020, 1, 1, tzinfo=UTC)
    day = timedelta(days=1)
    values = {
        "hypothesis_id": "H0001",
        "title": "VIX leads MOVE repricing",
        "research_question": (
            "Does the daily VIX change contain incremental information about "
            "the next-session MOVE index return after controlling for rates and equities?"
        ),
        "mechanism": (
            "Options-implied equity volatility may reprice faster than Treasury "
            "volatility during cross-asset risk shocks."
        ),
        "alternative_hypothesis": (
            "Lagged VIX changes explain a positive, out-of-sample component of "
            "future MOVE changes beyond the declared baseline."
        ),
        "null_hypothesis": (
            "Lagged VIX changes have no incremental predictive value over the "
            "declared baseline after costs and dependence controls."
        ),
        "universe": ("index:vix", "index:move"),
        "source_versions": ("sample-vix@v1", "sample-move@v1"),
        "observation_frequency": "daily",
        "horizon_seconds": 86_400,
        "target_definition": "Next session close-to-close MOVE log return",
        "feature_set": ("vix_return_lag_1", "rates_return_1d"),
        "model_definition": ("OLS with intercept", "Newey-West HAC standard errors"),
        "fixed_parameters": ("lag=1", "winsorization=none"),
        "benchmark": "Intercept-only historical mean",
        "cost_model": "No direct trading claim; diagnostic forecast evaluation only",
        "cost_assumptions": ("No fills assumed at this stage",),
        "train_window": SampleWindow(start=start, end=start + 365 * day),
        "validation_window": SampleWindow(
            start=start + 365 * day + day,
            end=start + 500 * day,
        ),
        "holdout_window": SampleWindow(
            start=start + 500 * day + day,
            end=start + 650 * day,
        ),
        "purge_gap_seconds": 86_400,
        "minimum_train_observations": 200,
        "minimum_validation_observations": 60,
        "minimum_holdout_observations": 60,
        "primary_metric": "Out-of-sample incremental R-squared",
        "expected_direction": ExpectedDirection.POSITIVE,
        "minimum_effect_size": 0.01,
        "familywise_alpha": 0.05,
        "multiple_testing_family": "Cross-market volatility transmission v1",
        "planned_test_count": 1,
        "missing_data_policy": "No forward filling; exclude incomplete paired sessions",
        "acceptance_criteria": (
            "Holdout incremental R-squared exceeds 0.01",
            "Direction is stable across at least two predeclared subsamples",
        ),
        "rejection_criteria": (
            "Holdout incremental R-squared is no greater than zero",
            "Result disappears after the declared confounder controls",
        ),
        "known_confounders": ("Rates level", "Equity return", "Global risk factor"),
        "exclusions": ("Sessions with unscheduled market closures",),
        "random_seed": 17,
    }
    values.update(overrides)
    return HypothesisSpec(**values)


def test_initial_registration_is_immutable_and_versioned(tmp_path):
    registry = HypothesisRegistry(tmp_path)
    spec = make_spec()
    registered = registry.register(spec)

    assert registered.version == 1
    assert registered.spec == spec
    assert registry.get("H0001") == registered
    assert registry.get_state("H0001", 1) == HypothesisState.REGISTERED
    assert len(registry.read_events()) == 1


def test_pre_trial_amendment_creates_new_version_and_supersedes_old(tmp_path):
    registry = HypothesisRegistry(tmp_path)
    first = registry.register(make_spec())
    second_spec = make_spec(title="VIX leads MOVE repricing v2")
    second = registry.register(
        second_spec,
        amendment_reason="Clarified title before any trial was started",
    )

    assert second.version == 2
    assert second.supersedes_version == 1
    assert registry.get("H0001", version=1) == first
    assert registry.get("H0001", version=2).spec == second_spec
    assert registry.get_state("H0001", 1) == HypothesisState.SUPERSEDED
    assert registry.get_state("H0001", 2) == HypothesisState.REGISTERED


def test_amendment_requires_reason_and_no_trial_started(tmp_path):
    registry = HypothesisRegistry(tmp_path)
    registry.register(make_spec())
    with pytest.raises(ValueError, match="requires a reason"):
        registry.register(make_spec(title="Changed hypothesis title"))

    registry.transition(
        "H0001",
        1,
        HypothesisState.TESTING,
        reason="First trial began",
    )
    with pytest.raises(PermissionError, match="after testing has started"):
        registry.register(
            make_spec(title="Changed after testing"),
            amendment_reason="Trying to change it after results",
        )


def test_invalid_state_transition_is_rejected(tmp_path):
    registry = HypothesisRegistry(tmp_path)
    registry.register(make_spec())
    with pytest.raises(ValueError, match="invalid hypothesis transition"):
        registry.transition(
            "H0001",
            1,
            HypothesisState.SUPPORTED,
            reason="Attempting to skip testing",
        )


def test_terminal_states_cannot_be_reopened(tmp_path):
    registry = HypothesisRegistry(tmp_path)
    registry.register(make_spec())
    registry.transition(
        "H0001",
        1,
        HypothesisState.TESTING,
        reason="First trial began",
    )
    registry.transition(
        "H0001",
        1,
        HypothesisState.REJECTED,
        reason="The preregistered holdout criteria failed",
    )
    with pytest.raises(ValueError, match="invalid hypothesis transition"):
        registry.transition(
            "H0001",
            1,
            HypothesisState.TESTING,
            reason="Trying to reopen a rejected study",
        )


def test_registration_detects_snapshot_tampering(tmp_path):
    registry = HypothesisRegistry(tmp_path)
    registration = registry.register(make_spec())
    path = (
        tmp_path
        / "registrations"
        / "H0001"
        / f"v{registration.version}.json"
    )
    payload = path.read_text()
    path.write_text(payload.replace("VIX leads MOVE repricing", "Edited after registration"))

    with pytest.raises(ValueError, match="integrity"):
        registry.get("H0001", version=1)


def test_registry_detects_lifecycle_event_tampering(tmp_path):
    registry = HypothesisRegistry(tmp_path)
    registry.register(make_spec())
    event_log = tmp_path / "hypothesis-events.jsonl"
    event_log.write_text(event_log.read_text().replace("Initial preregistration", "edited"))

    with pytest.raises(ValueError, match="event hash mismatch"):
        registry.read_events()


def test_time_splits_must_respect_prediction_horizon_purge():
    start = datetime(2020, 1, 1, tzinfo=UTC)
    day = timedelta(days=1)
    with pytest.raises(ValidationError, match="purge_gap_seconds"):
        make_spec(
            purge_gap_seconds=3_600,
            horizon_seconds=86_400,
        )
    with pytest.raises(ValidationError, match="purge boundary"):
        make_spec(
            validation_window=SampleWindow(
                start=start + 365 * day,
                end=start + 500 * day,
            )
        )


def test_reject_duplicate_features_and_bad_source_version():
    with pytest.raises(ValidationError, match="feature_set entries"):
        make_spec(feature_set=("vix_return_lag_1", "vix_return_lag_1"))
    with pytest.raises(ValidationError, match="source_versions"):
        make_spec(source_versions=("sample-vix", "sample-move@v1"))
