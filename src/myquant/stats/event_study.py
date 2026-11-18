"""Event-study estimators with explicit overlapping-window clustering."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from math import erf, isfinite, sqrt
from numbers import Integral

import numpy as np
import pandas as pd
from pydantic import Field

from myquant.contracts import StrictContract


class EventWindowObservation(StrictContract):
    """One event's cumulative abnormal return and overlap-cluster identity."""

    event_time: datetime
    cluster_id: int = Field(ge=0)
    window_observations: int = Field(ge=1)
    cumulative_abnormal_return: float = Field(allow_inf_nan=False)


class EventClusterResult(StrictContract):
    """Mean event CAR within one connected group of overlapping windows."""

    cluster_id: int = Field(ge=0)
    event_count: int = Field(ge=1)
    cumulative_abnormal_return: float = Field(allow_inf_nan=False)


class EventStudyResult(StrictContract):
    """Event-study summary; inference treats independent overlap clusters as units."""

    event_count: int = Field(ge=1)
    cluster_count: int = Field(ge=1)
    pre_event_steps: int = Field(ge=0)
    post_event_steps: int = Field(ge=0)
    events: tuple[EventWindowObservation, ...]
    clusters: tuple[EventClusterResult, ...]
    mean_cluster_car: float = Field(allow_inf_nan=False)
    cluster_standard_error: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    z_statistic: float | None = Field(default=None, allow_inf_nan=False)
    two_sided_p_value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


def event_study(
    returns: pd.Series,
    events: Sequence[pd.Timestamp],
    *,
    pre_event_steps: int,
    post_event_steps: int,
    expected_returns: pd.Series | None = None,
) -> EventStudyResult:
    """Estimate event-window CARs and cluster events with overlapping windows.

    Event timestamps must exactly match the timezone-aware return index. The
    inclusive window is [-pre_event_steps, +post_event_steps]. If expected
    returns are supplied, abnormal returns are observed minus expected;
    otherwise raw returns are treated as abnormal (a zero-return benchmark).

    Intersecting event windows are merged into connected overlap clusters.
    Inference uses the mean CAR per cluster, not each event as an independent
    observation. The normal-reference p-value is descriptive/asymptotic and
    is omitted when fewer than two independent clusters are available.

    This function does not estimate a market model, adjust for confounders,
    infer causal effects, or account for events omitted from the supplied list.
    """
    if not isinstance(returns, pd.Series):
        raise TypeError("returns must be a pandas Series")
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise TypeError("returns must use a DatetimeIndex")
    index = returns.index
    if index.tz is None:
        raise ValueError("returns index must be timezone-aware")
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError("returns index must be sorted and unique")
    if isinstance(pre_event_steps, bool) or not isinstance(pre_event_steps, Integral):
        raise TypeError("pre_event_steps must be an integer")
    if isinstance(post_event_steps, bool) or not isinstance(post_event_steps, Integral):
        raise TypeError("post_event_steps must be an integer")
    if pre_event_steps < 0 or post_event_steps < 0:
        raise ValueError("event-window steps must be non-negative")
    if not events:
        raise ValueError("at least one event timestamp is required")

    values = returns.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        raise ValueError("returns must contain only finite observations")
    if expected_returns is not None:
        if not isinstance(expected_returns, pd.Series):
            raise TypeError("expected_returns must be a pandas Series")
        if not expected_returns.index.equals(index):
            raise ValueError("expected_returns index must exactly match returns")
        expected = expected_returns.to_numpy(dtype=float, na_value=np.nan)
        if not np.isfinite(expected).all():
            raise ValueError("expected_returns must contain only finite observations")
        abnormal = values - expected
    else:
        abnormal = values.copy()

    normalized_events: list[pd.Timestamp] = []
    positions: list[int] = []
    for event in events:
        timestamp = pd.Timestamp(event)
        if timestamp.tzinfo is None:
            raise ValueError("event timestamps must be timezone-aware")
        try:
            position = int(index.get_loc(timestamp))
        except KeyError as exc:
            raise ValueError(f"event timestamp is not present in returns index: {timestamp}") from exc
        if position - pre_event_steps < 0 or position + post_event_steps >= len(index):
            raise ValueError("every event window must fit completely inside returns")
        normalized_events.append(timestamp)
        positions.append(position)

    if len(set(normalized_events)) != len(normalized_events):
        raise ValueError("event timestamps must be unique")
    ordered = sorted(zip(positions, normalized_events, strict=True), key=lambda item: item[0])
    width_left = int(pre_event_steps)
    width_right = int(post_event_steps)

    cluster_members: list[list[tuple[int, pd.Timestamp]]] = []
    current_end = -1
    for position, timestamp in ordered:
        window_start = position - width_left
        window_end = position + width_right
        if not cluster_members or window_start > current_end:
            cluster_members.append([])
            current_end = window_end
        else:
            current_end = max(current_end, window_end)
        cluster_id = len(cluster_members) - 1
        cluster_members[cluster_id].append((position, timestamp))

    event_results: list[EventWindowObservation] = []
    cluster_results: list[EventClusterResult] = []
    for cluster_id, members in enumerate(cluster_members):
        event_cars: list[float] = []
        for position, timestamp in members:
            start = position - width_left
            end = position + width_right + 1
            car = float(np.sum(abnormal[start:end]))
            if not isfinite(car):
                raise ValueError("event CAR calculation overflowed")
            event_cars.append(car)
            event_results.append(
                EventWindowObservation(
                    event_time=timestamp.to_pydatetime(),
                    cluster_id=cluster_id,
                    window_observations=width_left + width_right + 1,
                    cumulative_abnormal_return=car,
                )
            )
        cluster_car = float(np.mean(event_cars))
        cluster_results.append(
            EventClusterResult(
                cluster_id=cluster_id,
                event_count=len(members),
                cumulative_abnormal_return=cluster_car,
            )
        )

    cluster_cars = np.asarray(
        [cluster.cumulative_abnormal_return for cluster in cluster_results],
        dtype=float,
    )
    mean_car = float(np.mean(cluster_cars))
    standard_error: float | None = None
    z_statistic: float | None = None
    p_value: float | None = None
    if cluster_cars.size >= 2:
        standard_error = float(np.std(cluster_cars, ddof=1) / sqrt(cluster_cars.size))
        if standard_error > 0.0:
            z_statistic = mean_car / standard_error
            p_value = float(1.0 - erf(abs(z_statistic) / sqrt(2.0)))
            p_value = max(0.0, min(1.0, p_value))

    return EventStudyResult(
        event_count=len(event_results),
        cluster_count=len(cluster_results),
        pre_event_steps=width_left,
        post_event_steps=width_right,
        events=tuple(sorted(event_results, key=lambda item: item.event_time)),
        clusters=tuple(cluster_results),
        mean_cluster_car=mean_car,
        cluster_standard_error=standard_error,
        z_statistic=z_statistic,
        two_sided_p_value=p_value,
    )
