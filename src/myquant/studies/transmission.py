"""Timestamp-aware cross-market lead/lag research primitives."""

from __future__ import annotations

from numbers import Integral

import pandas as pd


def lead_lag_panel(
    frame: pd.DataFrame,
    *,
    source_lags: tuple[int, ...],
    timestamp_column: str = "timestamp",
) -> pd.DataFrame:
    """Build strictly prior source predictors on a synchronized input panel.

    Input must already be synchronized to a documented common calendar.
    Lag units are rows, not elapsed clock time. This function does not establish
    causality or choose a missing-data policy.
    """
    required = {timestamp_column, "source_value", "target_return"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if not source_lags:
        raise ValueError("source_lags must contain positive integers (>= 1)")
    if any(
        isinstance(lag, bool) or not isinstance(lag, Integral)
        for lag in source_lags
    ):
        raise TypeError("source_lags must contain integers")
    if any(lag < 1 for lag in source_lags):
        raise ValueError("source_lags must contain positive integers (>= 1)")
    timestamps = frame[timestamp_column]
    if not pd.api.types.is_datetime64_any_dtype(timestamps):
        raise TypeError("timestamp column must contain datetime values")
    if timestamps.dt.tz is None:
        raise ValueError("timestamps must be timezone-aware")
    if timestamps.isna().any():
        raise ValueError("timestamps cannot be missing")
    if timestamps.duplicated().any():
        raise ValueError("timestamps must be unique before lag construction")
    ordered = frame.sort_values(timestamp_column).copy()
    for lag in source_lags:
        ordered[f"source_lag_{lag}"] = ordered["source_value"].shift(lag)
    return ordered.reset_index(drop=True)
