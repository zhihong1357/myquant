from datetime import UTC

import numpy as np
import pandas as pd
import pytest

from myquant.stats.returns import (
    annualized_volatility,
    log_returns,
    realized_variance,
    realized_volatility,
    simple_returns,
)


def price_series(values):
    index = pd.date_range("2024-01-01", periods=len(values), freq="D", tz=UTC)
    return pd.Series(values, index=index, name="close", dtype=float)


def test_simple_returns_match_hand_calculation():
    result = simple_returns(price_series([100.0, 110.0, 121.0]))
    np.testing.assert_allclose(
        result.iloc[1:].to_numpy(),
        np.array([0.10, 0.10]),
        rtol=1e-12,
    )
    assert result.iloc[0] != result.iloc[0]


def test_log_returns_match_log_price_differences():
    result = log_returns(price_series([100.0, 110.0, 121.0]))
    expected = np.log(1.1)
    np.testing.assert_allclose(result.iloc[1:].to_numpy(), [expected, expected])
    assert result.name == "log_return"


def test_missing_prices_are_not_forward_filled():
    prices = price_series([100.0, np.nan, 121.0, 133.1])
    simple = simple_returns(prices)
    logarithmic = log_returns(prices)

    assert simple.iloc[:3].isna().all()
    assert logarithmic.iloc[:3].isna().all()
    assert simple.iloc[3] == pytest.approx(0.1)
    assert logarithmic.iloc[3] == pytest.approx(np.log(1.1))


def test_realized_variance_and_volatility_are_unannualized():
    returns = pd.Series(
        [0.01, -0.02, 0.03],
        index=pd.date_range("2024-01-01", periods=3, tz=UTC),
    )
    expected_variance = 0.01**2 + 0.02**2 + 0.03**2
    assert realized_variance(returns) == pytest.approx(expected_variance)
    assert realized_volatility(returns) == pytest.approx(np.sqrt(expected_variance))


def test_annualized_volatility_uses_sample_standard_deviation():
    values = np.array([0.01, -0.02, 0.03, 0.0])
    returns = pd.Series(
        values,
        index=pd.date_range("2024-01-01", periods=4, tz=UTC),
    )
    expected = np.std(values, ddof=1) * np.sqrt(252)
    assert annualized_volatility(returns, periods_per_year=252) == pytest.approx(expected)


def test_price_series_requires_ordered_unique_timezone_aware_index():
    naive = pd.Series([100.0, 101.0], index=pd.date_range("2024-01-01", periods=2))
    with pytest.raises(ValueError, match="timezone-aware"):
        log_returns(naive)

    duplicate_index = pd.DatetimeIndex(
        ["2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"]
    )
    duplicate = pd.Series([100.0, 101.0], index=duplicate_index)
    with pytest.raises(ValueError, match="duplicate"):
        simple_returns(duplicate)


def test_price_and_return_validation_rejects_invalid_values():
    with pytest.raises(ValueError, match="strictly positive"):
        log_returns(price_series([100.0, 0.0]))
    with pytest.raises(ValueError, match="infinity"):
        simple_returns(price_series([100.0, np.inf]))

    returns = pd.Series(
        [0.01, np.nan],
        index=pd.date_range("2024-01-01", periods=2, tz=UTC),
    )
    with pytest.raises(ValueError, match="missing"):
        realized_variance(returns)


def test_annualized_volatility_requires_two_complete_observations():
    one = pd.Series([0.01], index=pd.date_range("2024-01-01", periods=1, tz=UTC))
    with pytest.raises(ValueError, match="at least two"):
        annualized_volatility(one, periods_per_year=252)
