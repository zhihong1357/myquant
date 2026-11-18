"""Tests for PIT-correct volatility-regime classification.

All tests use constructed or seeded synthetic data; no test touches real
market data or the network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from myquant.stats.lead_lag import partial_lead_lag
from myquant.studies.regime import (
    classify_low_volatility,
    nested_lead_lag_test,
    trailing_realized_volatility,
)


def _series(values: list[float], *, start: str = "2023-01-01", freq: str = "D") -> pd.Series:
    index = pd.date_range(start=start, periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=index, dtype=float)


def test_trailing_rv_matches_hand_computation() -> None:
    returns = _series([0.01, -0.01, 0.02, -0.02, 0.005])
    rv = trailing_realized_volatility(returns, 3)
    assert np.isnan(rv.iloc[0])
    assert np.isnan(rv.iloc[1])
    assert rv.iloc[2] == pytest.approx(np.std([0.01, -0.01, 0.02], ddof=1))
    assert rv.iloc[4] == pytest.approx(np.std([0.02, -0.02, 0.005], ddof=1))


def test_trailing_median_classification_hand_computed() -> None:
    # Low-volatility first half, high-volatility second half; the trailing
    # median must lag the regime change (it only sees the past).
    rng = np.random.default_rng(7)
    low = rng.normal(0.0, 0.005, size=60)
    high = rng.normal(0.0, 0.05, size=60)
    returns = _series(list(np.concatenate([low, high])))
    result = classify_low_volatility(returns, rv_window=10, median_window=20)
    # RV needs 10 rows; the trailing median needs 20 prior RV values, so
    # the first labelled row is index 10 + 20 - 1 = 29.
    assert result.excluded_rows == 29
    assert result.labelled_rows == 91
    assert result.low_vol_rows + result.high_vol_rows == 91
    # Every labelled row's threshold uses only strictly prior RV values:
    # recompute one threshold independently.
    rv = trailing_realized_volatility(returns, 10)
    row = result.is_low_vol.index[10]
    position = returns.index.get_loc(row)
    expected_threshold = float(np.median(rv.iloc[position - 20 : position]))
    assert result.threshold.loc[row] == pytest.approx(expected_threshold)
    assert result.realized_volatility.loc[row] == pytest.approx(rv.iloc[position])
    assert bool(result.is_low_vol.loc[row]) == bool(
        rv.iloc[position] < expected_threshold
    )


def test_expanding_median_requires_min_prior_values() -> None:
    rng = np.random.default_rng(3)
    returns = _series(list(rng.normal(0.0, 0.01, size=800)), freq="h")
    result = classify_low_volatility(
        returns, rv_window=720, min_prior_values=30
    )
    # RV needs 720 rows (first at index 719); the expanding median needs
    # 30 prior RV values, so the first labelled row is index 749.
    assert result.excluded_rows == 749
    assert result.labelled_rows == 51
    first_labelled = returns.index[749]
    assert result.is_low_vol.index[0] == first_labelled


def test_daily_warm_up_count() -> None:
    rng = np.random.default_rng(11)
    returns = _series(list(rng.normal(0.0, 0.01, size=1415)))
    result = classify_low_volatility(returns, rv_window=30, median_window=252)
    # RV needs 30 rows; the trailing median needs 252 prior RV values, so
    # the first labelled row is index 281.
    assert result.excluded_rows == 281
    assert result.labelled_rows == 1134


def test_future_returns_cannot_change_past_labels() -> None:
    rng = np.random.default_rng(5)
    values = rng.normal(0.0, 0.01, size=400)
    returns = _series(list(values))
    before = classify_low_volatility(returns, rv_window=30, median_window=100)
    # Perturb every return from index 200 onward.
    perturbed = values.copy()
    perturbed[200:] *= 10.0
    after = classify_low_volatility(
        _series(list(perturbed)), rv_window=30, median_window=100
    )
    cutoff = returns.index[200]
    past_before = before.is_low_vol[before.is_low_vol.index < cutoff]
    past_after = after.is_low_vol[after.is_low_vol.index < cutoff]
    pd.testing.assert_series_equal(past_before, past_after)
    pd.testing.assert_series_equal(
        before.realized_volatility[before.realized_volatility.index < cutoff],
        after.realized_volatility[after.realized_volatility.index < cutoff],
    )
    pd.testing.assert_series_equal(
        before.threshold[before.threshold.index < cutoff],
        after.threshold[after.threshold.index < cutoff],
    )


def test_classification_rejects_bad_inputs() -> None:
    returns = _series([0.01, -0.01, 0.02])
    with pytest.raises(ValueError, match="at least 2"):
        trailing_realized_volatility(returns, 1)
    with pytest.raises(ValueError, match="positive integer"):
        classify_low_volatility(returns, rv_window=2, median_window=0)
    with pytest.raises(ValueError, match="positive integer"):
        classify_low_volatility(returns, rv_window=2, min_prior_values=0)
    with pytest.raises(ValueError, match="no rows carry"):
        classify_low_volatility(returns, rv_window=2, median_window=50)
    with pytest.raises(ValueError, match="missing or infinite"):
        classify_low_volatility(
            _series([0.01, float("nan"), 0.02, -0.01, 0.03]), rv_window=2
        )


def test_nested_test_recovers_known_interaction() -> None:
    rng = np.random.default_rng(42)
    n = 2000
    source = rng.normal(0.0, 1.0, size=n)
    factor = rng.normal(0.0, 1.0, size=n)
    lowvol = (rng.random(n) < 0.5).astype(float)
    noise = rng.normal(0.0, 1.0, size=n)
    # True interaction coefficient is 0.6; the source main effect is zero.
    target = 0.3 * factor + 0.6 * source * lowvol + noise
    result = nested_lead_lag_test(
        target,
        {"target_lag": rng.normal(0.0, 1.0, size=n), "factor": factor},
        {"source": source, "interaction": source * lowvol},
        effect_name="interaction",
        max_hac_lag=5,
    )
    assert result.observations == n
    assert result.coefficient == pytest.approx(0.6, abs=0.1)
    assert result.p_value is not None and result.p_value < 0.001
    assert result.partial_r_squared is not None and result.partial_r_squared > 0.05
    assert result.base_predictor_names == ("target_lag", "factor")
    assert result.augmented_predictor_names == (
        "target_lag",
        "factor",
        "source",
        "interaction",
    )


def test_nested_test_matches_partial_lead_lag() -> None:
    rng = np.random.default_rng(9)
    n = 500
    source = rng.normal(0.0, 1.0, size=n)
    target_series = rng.normal(0.0, 1.0, size=n)
    factor = rng.normal(0.0, 1.0, size=n)
    reference = partial_lead_lag(
        source,
        target_series,
        lag_steps=1,
        common_factors={"factor": factor},
        max_hac_lag=5,
    )
    result = nested_lead_lag_test(
        target_series[1:],
        {"target_lag": target_series[:-1], "factor": factor[:-1]},
        {"source": source[:-1]},
        effect_name="source",
        max_hac_lag=5,
    )
    assert result.observations == reference.observations
    assert result.coefficient == pytest.approx(reference.source_effect.estimate)
    assert result.p_value == pytest.approx(reference.source_effect.p_value)
    assert result.partial_r_squared == pytest.approx(reference.partial_r_squared)
    assert result.incremental_r_squared == pytest.approx(
        reference.incremental_r_squared
    )


def test_nested_test_validates_inputs() -> None:
    target = np.zeros(50)
    base = {"x": np.zeros(50)}
    with pytest.raises(ValueError, match="at least one extra predictor"):
        nested_lead_lag_test(target, base, {}, effect_name="z", max_hac_lag=1)
    with pytest.raises(ValueError, match="not an extra predictor"):
        nested_lead_lag_test(
            target, base, {"z": np.zeros(50)}, effect_name="y", max_hac_lag=1
        )
    with pytest.raises(ValueError, match="overlap"):
        nested_lead_lag_test(
            target, base, {"x": np.zeros(50)}, effect_name="x", max_hac_lag=1
        )
    with pytest.raises(ValueError, match="non-negative"):
        nested_lead_lag_test(
            target, base, {"z": np.zeros(50)}, effect_name="z", max_hac_lag=-1
        )
