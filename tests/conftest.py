"""Shared test factories for hypothesis preregistration fixtures.

`make_spec` is the canonical valid preregistration used by the governance
tests. Test modules that need a deliberately different variant should call
it with overrides for exactly the fields that differ, rather than copying
the whole factory.
"""

from datetime import UTC, datetime, timedelta

from myquant.contracts import MultiplicityCorrection
from myquant.hypotheses import (
    ExpectedDirection,
    HypothesisSpec,
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
        "feature_set": ("vix_return_lag_1@v1", "rates_return_1d@v1"),
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
        "target_error_rate": 0.05,
        "multiple_testing_family": "Cross-market volatility transmission v1",
        "multiple_testing_method": MultiplicityCorrection.NONE,
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
