"""Descriptive lead-lag diagnostics for synchronized numeric series."""

from __future__ import annotations

from collections.abc import Iterable
from math import isfinite

import numpy as np
from pydantic import Field

from myquant.contracts import StrictContract


class LeadLagCorrelation(StrictContract):
    """Correlation between source[t] and target[t + lag_steps]."""

    lag_steps: int = Field(ge=0)
    observations: int = Field(ge=0)
    correlation: float | None


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
    if minimum_observations < 3:
        raise ValueError("minimum_observations must be at least 3")

    selected_lags = tuple(lag_steps)
    if not selected_lags:
        raise ValueError("at least one lag must be supplied")
    if any(isinstance(lag, bool) or not isinstance(lag, int) for lag in selected_lags):
        raise TypeError("lag_steps must contain integers")
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
