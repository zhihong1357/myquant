"""Timestamp-aware cross-market lead/lag research primitives."""

from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = {"timestamp", "source_value", "target_return"}


def lead_lag_panel(
    frame: pd.DataFrame,
    *,
    source_lags: tuple[int, ...],
    timestamp_column: str = "timestamp",
) -> pd.DataFrame:
    """Build lagged source predictors without changing row order.

    Input must already be synchronized to a documented common calendar.
    This function does not establish causality and does not handle missing-data
    policy on behalf of the caller.
    """
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if not source_lags or any(lag < 0 for lag in source_lags):
        raise ValueError("source_lags must be non-empty and non-negative")
    if frame[timestamp_column].duplicated().any():
        raise ValueError("timestamps must be unique before lag construction")
    ordered = frame.sort_values(timestamp_column).copy()
    for lag in source_lags:
        ordered[f"source_lag_{lag}"] = ordered["source_value"].shift(lag)
    return ordered.reset_index(drop=True)
