"""Timestamp-aware cross-market lead/lag research primitives."""

from __future__ import annotations

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
    if not source_lags or any(lag < 1 for lag in source_lags):
        raise ValueError("source_lags must contain positive integers (>= 1)")
    if frame[timestamp_column].isna().any():
        raise ValueError("timestamps cannot be missing")
    if frame[timestamp_column].duplicated().any():
        raise ValueError("timestamps must be unique before lag construction")
    ordered = frame.sort_values(timestamp_column).copy()
    for lag in source_lags:
        ordered[f"source_lag_{lag}"] = ordered["source_value"].shift(lag)
    return ordered.reset_index(drop=True)
