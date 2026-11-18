"""Point-in-time-correct volatility-regime classification.

Study 001's descriptive split used the full-sample median of trailing
30-day realized volatility. That is fine for description but leaks future
information into a predictive test: a row's regime label at time t would
depend on volatility observed after t. This module classifies regimes
using only data known at the decision time:

- Realized volatility at t is the sample standard deviation of the
  trailing ``rv_window`` returns ending at t (inclusive; the return over
  bar t is known at the decision time, the bar's close).
- The low-volatility threshold at t is the median of realized volatility
  over a strictly prior window: either the trailing ``median_window``
  values (daily) or all prior values with at least ``min_prior_values``
  observations (expanding, hourly). The current value is never included.
- A row is labelled low-volatility when its realized volatility is
  strictly below the threshold. Rows without a realized volatility or a
  threshold carry no label and are excluded; the excluded count is part
  of the result.

The module also provides the nested-model lead-lag test used for
regime-conditional hypotheses: the existing ``partial_lead_lag`` primitive
does not support interaction terms or row subsets, so the interaction and
low-volatility-subsample tests assemble their design matrices here from
the existing OLS and Newey-West HAC primitives instead.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from myquant.stats.hac import newey_west_hac
from myquant.stats.regression import ols_fit


@dataclass(frozen=True)
class RegimeClassification:
    """PIT-correct low-volatility labels for a return series."""

    is_low_vol: pd.Series
    realized_volatility: pd.Series
    threshold: pd.Series
    excluded_rows: int
    low_vol_rows: int
    high_vol_rows: int

    @property
    def labelled_rows(self) -> int:
        return int(self.is_low_vol.shape[0])


def _validate_return_series(returns: pd.Series) -> pd.Series:
    if not isinstance(returns, pd.Series):
        raise TypeError("returns must be a pandas Series")
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise TypeError("returns must use a DatetimeIndex")
    if returns.index.tz is None:
        raise ValueError("returns index must be timezone-aware")
    if not returns.index.is_monotonic_increasing:
        raise ValueError("returns index must be sorted in ascending order")
    if not returns.index.is_unique:
        raise ValueError("returns index must not contain duplicate timestamps")
    if returns.empty:
        raise ValueError("returns must not be empty")
    values = returns.to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("returns must not contain missing or infinite values")
    return returns


def trailing_realized_volatility(
    returns: pd.Series,
    window: int,
) -> pd.Series:
    """Trailing sample standard deviation (ddof=1) of log returns.

    The value at t covers the ``window`` returns ending at t, inclusive.
    The first ``window - 1`` rows are NaN: no partial window is used.
    This matches study 001's descriptive volatility definition.
    """
    _validate_return_series(returns)
    if not isinstance(window, int) or isinstance(window, bool) or window < 2:
        raise ValueError("window must be an integer of at least 2")
    return returns.rolling(window=window, min_periods=window).std()


def classify_low_volatility(
    returns: pd.Series,
    *,
    rv_window: int,
    median_window: int | None = None,
    min_prior_values: int = 1,
) -> RegimeClassification:
    """Classify each row as low-volatility using only prior information.

    With ``median_window`` set, the threshold at t is the median of the
    trailing ``median_window`` realized-volatility values strictly before
    t. With ``median_window`` left as None, the threshold is the expanding
    median of all realized-volatility values strictly before t, requiring
    at least ``min_prior_values`` of them. A row is low-volatility when
    its realized volatility is strictly below its threshold.
    """
    _validate_return_series(returns)
    if median_window is not None and (
        not isinstance(median_window, int)
        or isinstance(median_window, bool)
        or median_window < 1
    ):
        raise ValueError("median_window must be a positive integer or None")
    if (
        not isinstance(min_prior_values, int)
        or isinstance(min_prior_values, bool)
        or min_prior_values < 1
    ):
        raise ValueError("min_prior_values must be a positive integer")

    realized_vol = trailing_realized_volatility(returns, rv_window)
    prior_vol = realized_vol.shift(1)
    if median_window is not None:
        threshold = prior_vol.rolling(
            window=median_window, min_periods=median_window
        ).median()
    else:
        threshold = prior_vol.expanding(min_periods=min_prior_values).median()

    labelled = realized_vol.notna() & threshold.notna()
    if not bool(labelled.any()):
        raise ValueError("no rows carry both a realized volatility and a threshold")
    is_low_vol = (realized_vol[labelled] < threshold[labelled]).astype(bool)
    return RegimeClassification(
        is_low_vol=is_low_vol,
        realized_volatility=realized_vol[labelled],
        threshold=threshold[labelled],
        excluded_rows=int((~labelled).sum()),
        low_vol_rows=int(is_low_vol.sum()),
        high_vol_rows=int((~is_low_vol).sum()),
    )


@dataclass(frozen=True)
class NestedLeadLagTest:
    """Nested-model comparison for an added predictor's incremental signal.

    Mirrors :func:`myquant.stats.lead_lag.partial_lead_lag` but works on
    caller-aligned rows with an explicit extra-predictor set, so it can
    test an interaction term (base model includes the source, extra set is
    the interaction) or a row subset (rows pre-filtered by the caller).
    """

    observations: int
    effect_name: str
    coefficient: float
    standard_error: float | None
    t_statistic: float | None
    p_value: float | None
    partial_r_squared: float | None
    incremental_r_squared: float
    base_r_squared: float
    augmented_r_squared: float
    base_predictor_names: tuple[str, ...]
    augmented_predictor_names: tuple[str, ...]


def nested_lead_lag_test(
    target: Iterable[float],
    base_predictors: Mapping[str, Iterable[float]],
    extra_predictors: Mapping[str, Iterable[float]],
    *,
    effect_name: str,
    max_hac_lag: int,
) -> NestedLeadLagTest:
    """Test the incremental signal of ``extra_predictors`` over the base model.

    The base model fits the target on ``base_predictors``; the augmented
    model adds ``extra_predictors``. Inference on ``effect_name`` (which
    must be one of the extra predictors) uses Newey-West HAC standard
    errors. Partial R-squared is the proportional SSR reduction from the
    base to the augmented model, clamped to [0, 1] like
    ``partial_lead_lag``.
    """
    if not extra_predictors:
        raise ValueError("at least one extra predictor is required")
    if effect_name not in extra_predictors:
        raise ValueError(f"effect_name {effect_name!r} is not an extra predictor")
    overlap = set(base_predictors) & set(extra_predictors)
    if overlap:
        raise ValueError(f"predictor names overlap between models: {sorted(overlap)}")
    if not isinstance(max_hac_lag, int) or isinstance(max_hac_lag, bool):
        raise TypeError("max_hac_lag must be an integer")
    if max_hac_lag < 0:
        raise ValueError("max_hac_lag must be non-negative")

    augmented_predictors = {**base_predictors, **extra_predictors}
    base_fit = ols_fit(target, base_predictors)
    augmented_fit = ols_fit(target, augmented_predictors)
    hac = newey_west_hac(
        target,
        augmented_predictors,
        max_lag=max_hac_lag,
    )
    effect = next(
        coefficient for coefficient in hac.coefficients if coefficient.name == effect_name
    )
    base_error = base_fit.sum_squared_residuals
    partial_r_squared: float | None = None
    if base_error > 0.0:
        partial_r_squared = max(
            0.0,
            min(
                1.0,
                (base_error - augmented_fit.sum_squared_residuals) / base_error,
            ),
        )
    return NestedLeadLagTest(
        observations=augmented_fit.observations,
        effect_name=effect_name,
        coefficient=effect.estimate,
        standard_error=effect.standard_error,
        t_statistic=effect.t_statistic,
        p_value=effect.p_value,
        partial_r_squared=partial_r_squared,
        incremental_r_squared=augmented_fit.r_squared - base_fit.r_squared,
        base_r_squared=base_fit.r_squared,
        augmented_r_squared=augmented_fit.r_squared,
        base_predictor_names=tuple(base_predictors),
        augmented_predictor_names=tuple(augmented_predictors),
    )
