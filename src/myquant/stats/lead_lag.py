"""Descriptive and factor-controlled lead-lag diagnostics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from numbers import Integral

import numpy as np
from pydantic import Field

from myquant.contracts import StrictContract
from myquant.stats.hac import HACCoefficient, HACResult, newey_west_hac
from myquant.stats.regression import OLSResult, ols_fit


class LeadLagCorrelation(StrictContract):
    """Correlation between source[t] and target[t + lag_steps]."""

    lag_steps: int = Field(ge=0)
    observations: int = Field(ge=0)
    correlation: float | None


class PartialLeadLagResult(StrictContract):
    """Nested-model comparison for the incremental information in source[t]."""

    lag_steps: int = Field(ge=1)
    observations: int = Field(ge=3)
    base_model: OLSResult
    augmented_model: OLSResult
    hac: HACResult
    source_effect: HACCoefficient
    incremental_r_squared: float = Field(allow_inf_nan=False)
    partial_r_squared: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
    )


def lead_lag_scan(
    source: Iterable[float],
    target: Iterable[float],
    *,
    lag_steps: Iterable[int],
    minimum_observations: int = 30,
) -> tuple[LeadLagCorrelation, ...]:
    """Calculate descriptive correlations across preselected forward lags.

    A positive lag means the source observation at time t is paired with the
    target at time t + lag. Inputs must already be synchronized, equally
    spaced, finite observations on a common calendar. This function does not
    resample, fill missing values, select a statistically significant lag, or
    establish causality. Lag choices should be declared before inspecting
    results when used for confirmatory research.
    """
    source_values = np.asarray(tuple(source), dtype=float)
    target_values = np.asarray(tuple(target), dtype=float)

    if source_values.ndim != 1 or target_values.ndim != 1:
        raise ValueError("source and target must be one-dimensional")
    if source_values.size != target_values.size:
        raise ValueError("source and target must have equal lengths")
    if source_values.size == 0:
        raise ValueError("source and target must not be empty")
    if not np.isfinite(source_values).all() or not np.isfinite(target_values).all():
        raise ValueError("source and target must contain only finite observations")
    if (
        isinstance(minimum_observations, bool)
        or not isinstance(minimum_observations, Integral)
        or minimum_observations < 3
    ):
        raise ValueError("minimum_observations must be an integer of at least 3")

    raw_lags = tuple(lag_steps)
    if not raw_lags:
        raise ValueError("at least one lag must be supplied")
    if any(isinstance(lag, bool) or not isinstance(lag, Integral) for lag in raw_lags):
        raise TypeError("lag_steps must contain integers")
    selected_lags = tuple(int(lag) for lag in raw_lags)
    if any(lag < 0 for lag in selected_lags):
        raise ValueError("lag_steps must be non-negative")
    if len(set(selected_lags)) != len(selected_lags):
        raise ValueError("lag_steps must be unique")

    observations = source_values.size
    results: list[LeadLagCorrelation] = []
    for lag in selected_lags:
        if lag >= observations:
            raise ValueError("each lag must be smaller than the sample length")

        if lag == 0:
            source_pair = source_values
            target_pair = target_values
        else:
            source_pair = source_values[:-lag]
            target_pair = target_values[lag:]

        count = int(source_pair.size)
        correlation: float | None = None
        if count >= minimum_observations:
            source_scale = float(np.std(source_pair))
            target_scale = float(np.std(target_pair))
            if source_scale > 0.0 and target_scale > 0.0:
                value = float(np.corrcoef(source_pair, target_pair)[0, 1])
                if isfinite(value):
                    correlation = max(-1.0, min(1.0, value))

        results.append(
            LeadLagCorrelation(
                lag_steps=lag,
                observations=count,
                correlation=correlation,
            )
        )
    return tuple(results)


def partial_lead_lag(
    source: Iterable[float],
    target: Iterable[float],
    *,
    lag_steps: int,
    common_factors: Mapping[str, Iterable[float]] | None = None,
    max_hac_lag: int,
    minimum_observations: int = 30,
) -> PartialLeadLagResult:
    """Test whether source[t] adds information about target[t + k].

    The base model predicts target[t + k] from target[t] and any supplied
    common factors observed at t. The augmented model adds source[t]. Thus
    every predictor must be available at t; controls measured only at t + k
    would leak future information and are not accepted by this interface.

    Both models use the same rows. R-squared changes are in-sample effect
    descriptions; the Newey-West HAC p-value is asymptotic and does not turn
    the result into a causal claim or tradable alpha. Predeclare the lag,
    control set, HAC bandwidth and complete testing family.
    """
    if isinstance(lag_steps, bool) or not isinstance(lag_steps, Integral):
        raise TypeError("lag_steps must be an integer")
    if lag_steps < 1:
        raise ValueError("lag_steps must be a positive integer")
    if (
        isinstance(minimum_observations, bool)
        or not isinstance(minimum_observations, Integral)
        or minimum_observations < 3
    ):
        raise ValueError("minimum_observations must be an integer of at least 3")

    source_values = np.asarray(tuple(source), dtype=float)
    target_values = np.asarray(tuple(target), dtype=float)
    if source_values.ndim != 1 or target_values.ndim != 1:
        raise ValueError("source and target must be one-dimensional")
    if source_values.size != target_values.size:
        raise ValueError("source and target must have equal lengths")
    if source_values.size == 0:
        raise ValueError("source and target must not be empty")
    if not np.isfinite(source_values).all() or not np.isfinite(target_values).all():
        raise ValueError("source and target must contain only finite observations")
    if lag_steps >= source_values.size:
        raise ValueError("lag_steps must be smaller than the sample length")

    aligned_observations = int(source_values.size - lag_steps)
    if aligned_observations < minimum_observations:
        raise ValueError("aligned sample is smaller than minimum_observations")

    base_predictors: dict[str, Iterable[float]] = {
        "target_lag": target_values[:-lag_steps],
    }
    factors = common_factors or {}
    for name, raw_values in factors.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("common-factor names must be non-empty strings")
        if name in {"intercept", "target_lag", "source"}:
            raise ValueError(f"reserved common-factor name: {name}")
        factor_values = np.asarray(tuple(raw_values), dtype=float)
        if factor_values.ndim != 1 or factor_values.size != target_values.size:
            raise ValueError(f"common factor '{name}' must match the input length")
        if not np.isfinite(factor_values).all():
            raise ValueError(f"common factor '{name}' must contain only finite values")
        base_predictors[name] = factor_values[:-lag_steps]

    response = target_values[lag_steps:]
    augmented_predictors = {
        **base_predictors,
        "source": source_values[:-lag_steps],
    }
    base_fit = ols_fit(response, base_predictors)
    augmented_fit = ols_fit(response, augmented_predictors)
    hac = newey_west_hac(
        response,
        augmented_predictors,
        max_lag=max_hac_lag,
    )
    source_effect = next(
        coefficient
        for coefficient in hac.coefficients
        if coefficient.name == "source"
    )

    base_error = base_fit.sum_squared_residuals
    partial_r_squared: float | None = None
    if base_error > 0.0:
        partial_r_squared = (
            base_error - augmented_fit.sum_squared_residuals
        ) / base_error
        partial_r_squared = max(0.0, min(1.0, partial_r_squared))

    return PartialLeadLagResult(
        lag_steps=int(lag_steps),
        observations=aligned_observations,
        base_model=base_fit,
        augmented_model=augmented_fit,
        hac=hac,
        source_effect=source_effect,
        incremental_r_squared=(
            augmented_fit.r_squared - base_fit.r_squared
        ),
        partial_r_squared=partial_r_squared,
    )
