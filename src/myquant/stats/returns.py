"""Transparent return and volatility estimators with explicit missing-data rules."""

from __future__ import annotations

from math import isfinite, sqrt

import numpy as np
import pandas as pd
from numpy.typing import NDArray


def _validate_time_series(series: pd.Series, *, name: str) -> NDArray[np.float64]:
    if not isinstance(series, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError(f"{name} must use a DatetimeIndex")
    if series.index.tz is None:
        raise ValueError(f"{name} index must be timezone-aware")
    if not series.index.is_monotonic_increasing:
        raise ValueError(f"{name} index must be sorted in ascending order")
    if not series.index.is_unique:
        raise ValueError(f"{name} index must not contain duplicate timestamps")

    try:
        values = series.to_numpy(dtype=np.float64, na_value=np.nan)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} values must be numeric") from exc

    finite_or_missing = np.isfinite(values) | np.isnan(values)
    if not finite_or_missing.all():
        raise ValueError(f"{name} values cannot contain positive or negative infinity")
    return values


def simple_returns(prices: pd.Series) -> pd.Series:
    """Calculate close-to-close simple returns without forward-filling gaps.

    The result is indexed by the timestamp at which each return becomes
    observable. Missing prices remain missing and invalidate the adjacent
    return; callers must choose an explicit missing-data policy downstream.
    """
    values = _validate_time_series(prices, name="prices")
    observed = values[~np.isnan(values)]
    if (observed <= 0).any():
        raise ValueError("prices must be strictly positive when observed")

    result = prices.astype(float) / prices.astype(float).shift(1) - 1.0
    result.name = "simple_return"
    return result


def log_returns(prices: pd.Series) -> pd.Series:
    """Calculate close-to-close continuously compounded returns.

    No missing value is filled. Both prices in a return pair must be observed.
    """
    values = _validate_time_series(prices, name="prices")
    observed = values[~np.isnan(values)]
    if (observed <= 0).any():
        raise ValueError("prices must be strictly positive when observed")

    result = np.log(prices.astype(float)).diff()
    result.name = "log_return"
    return result


def realized_variance(returns: pd.Series) -> float:
    """Return sum(r_t ** 2) over an explicitly complete return sample.

    This is an unannualized realized-variance measure over the supplied
    observation window. Missing returns are rejected rather than silently
    dropped, and the mean return is not subtracted.
    """
    values = _validate_time_series(returns, name="returns")
    if values.size == 0:
        raise ValueError("returns must contain at least one observation")
    if not np.isfinite(values).all():
        raise ValueError("returns must not contain missing observations")

    result = float(np.dot(values, values))
    if not isfinite(result):
        raise ValueError("realized variance overflowed")
    return result


def realized_volatility(returns: pd.Series) -> float:
    """Return the square root of unannualized realized variance."""
    return sqrt(realized_variance(returns))


def annualized_volatility(
    returns: pd.Series,
    *,
    periods_per_year: int,
) -> float:
    """Annualize sample standard deviation using sqrt(periods_per_year).

    Uses ddof=1 and requires at least two complete observations. This is a
    conventional annualized sample-volatility estimate, distinct from the
    unannualized sum-of-squares realized-volatility measure above.
    """
    values = _validate_time_series(returns, name="returns")
    if periods_per_year < 1:
        raise ValueError("periods_per_year must be positive")
    if values.size < 2:
        raise ValueError("at least two return observations are required")
    if not np.isfinite(values).all():
        raise ValueError("returns must not contain missing observations")

    result = float(np.std(values, ddof=1) * sqrt(periods_per_year))
    if not isfinite(result):
        raise ValueError("annualized volatility overflowed")
    return result
