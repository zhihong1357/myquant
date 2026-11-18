"""Constant-mean event-study helpers on a panel index.

These helpers prepare inputs for the repo's event-study estimator
(``myquant.stats.event_study.event_study``); they do not estimate
anything themselves. The constant-mean benchmark says each event's
expected return is the mean observed return over its estimation window
``[-estimation_start_steps, -estimation_end_steps]`` (trading-day
positions relative to the event). Because the estimator takes a single
expected-return series for the whole sample, the expected series
carries each event's estimation mean on that event's window days
``[-pre_event_steps, +post_event_steps]`` and 0.0 elsewhere: the
estimator only sums abnormal returns inside event windows, so the
off-window fill value never enters a CAR (it must still be finite, per
the estimator's contract). Event windows that overlap each other are
rejected: two events would need different expected values on the same
day.

One-sided p-values are derived from asymptotically normal statistics
(the event-study z-statistic, the HAC t-statistic) as ``Phi(z)`` for
the "less than" direction and ``1 - Phi(z)`` for "greater than".
"""

from __future__ import annotations

from collections.abc import Sequence
from math import erf, sqrt

import numpy as np
import pandas as pd

from myquant.stats.event_study import EventStudyResult, event_study


def filter_events_to_panel(
    returns_index: pd.DatetimeIndex,
    events: Sequence[pd.Timestamp],
    *,
    estimation_start_steps: int,
    estimation_end_steps: int,
    pre_event_steps: int,
    post_event_steps: int,
) -> tuple[tuple[pd.Timestamp, ...], tuple[dict[str, str], ...]]:
    """Split events into included ones and excluded ones with reasons.

    An event is included only if its t=0 timestamp is present in the
    returns index and both its full estimation window
    ``[-estimation_start_steps, -estimation_end_steps]`` and its full
    event window ``[-pre_event_steps, +post_event_steps]`` fit inside
    the index. Excluded events are reported with a reason so the trial
    can count them (early-sample events lack a full estimation window;
    a t=0 on a partial holiday is absent from the synchronized panel).
    """
    if estimation_start_steps <= estimation_end_steps:
        raise ValueError(
            "estimation_start_steps must exceed estimation_end_steps "
            f"({estimation_start_steps} vs {estimation_end_steps})"
        )
    if estimation_end_steps < 1:
        raise ValueError("estimation_end_steps must be at least 1")
    if pre_event_steps < 0 or post_event_steps < 0:
        raise ValueError("event-window steps must be non-negative")
    included: list[pd.Timestamp] = []
    excluded: list[dict[str, str]] = []
    index_length = len(returns_index)
    for event in events:
        timestamp = pd.Timestamp(event)
        try:
            position = int(returns_index.get_loc(timestamp))
        except KeyError:
            excluded.append(
                {
                    "event": timestamp.isoformat(),
                    "reason": "t=0 not present in the panel index",
                }
            )
            continue
        if position - estimation_start_steps < 0:
            excluded.append(
                {
                    "event": timestamp.isoformat(),
                    "reason": (
                        "estimation window [-"
                        f"{estimation_start_steps},-{estimation_end_steps}] "
                        "extends before the panel start"
                    ),
                }
            )
            continue
        if position - pre_event_steps < 0:
            excluded.append(
                {
                    "event": timestamp.isoformat(),
                    "reason": "event window starts before the panel start",
                }
            )
            continue
        if position + post_event_steps >= index_length:
            excluded.append(
                {
                    "event": timestamp.isoformat(),
                    "reason": "event window extends past the panel end",
                }
            )
            continue
        included.append(timestamp)
    return tuple(included), tuple(excluded)


def constant_mean_expected_returns(
    returns: pd.Series,
    events: Sequence[pd.Timestamp],
    *,
    estimation_start_steps: int,
    estimation_end_steps: int,
    pre_event_steps: int,
    post_event_steps: int,
) -> pd.Series:
    """Expected-return series for the constant-mean benchmark.

    Each event's expected return is the mean observed return over its
    estimation window; that mean is written onto the event's window
    days and 0.0 elsewhere (never summed by the estimator). Raises if
    any event's windows do not fit inside the returns index or if two
    events' windows overlap.
    """
    included, excluded = filter_events_to_panel(
        returns.index,
        events,
        estimation_start_steps=estimation_start_steps,
        estimation_end_steps=estimation_end_steps,
        pre_event_steps=pre_event_steps,
        post_event_steps=post_event_steps,
    )
    if excluded:
        raise ValueError(
            "events do not fit the panel: "
            + "; ".join(
                f"{item['event']} ({item['reason']})" for item in excluded
            )
        )
    values = returns.to_numpy(dtype=float)
    expected = np.zeros(values.shape, dtype=float)
    filled = np.zeros(values.shape, dtype=bool)
    for event in included:
        position = int(returns.index.get_loc(event))
        estimation = values[
            position - estimation_start_steps : position
            - estimation_end_steps
            + 1
        ]
        mean = float(np.mean(estimation))
        start = position - pre_event_steps
        end = position + post_event_steps + 1
        if filled[start:end].any():
            raise ValueError(
                f"event windows overlap at {event.isoformat()}; the "
                "constant-mean expected series cannot hold two means "
                "on the same day"
            )
        expected[start:end] = mean
        filled[start:end] = True
    return pd.Series(expected, index=returns.index, name="expected_return")


def run_constant_mean_event_study(
    returns: pd.Series,
    events: Sequence[pd.Timestamp],
    *,
    estimation_start_steps: int,
    estimation_end_steps: int,
    pre_event_steps: int,
    post_event_steps: int,
) -> EventStudyResult:
    """Run the repo's event-study estimator with a constant-mean benchmark."""
    expected = constant_mean_expected_returns(
        returns,
        events,
        estimation_start_steps=estimation_start_steps,
        estimation_end_steps=estimation_end_steps,
        pre_event_steps=pre_event_steps,
        post_event_steps=post_event_steps,
    )
    return event_study(
        returns,
        list(events),
        pre_event_steps=pre_event_steps,
        post_event_steps=post_event_steps,
        expected_returns=expected,
    )


def one_sided_normal_p_value(z_statistic: float, *, direction: str) -> float:
    """One-sided p-value from an asymptotically normal statistic.

    ``direction="less"`` returns P(Z <= z) (the alternative is a
    negative effect); ``direction="greater"`` returns P(Z >= z).
    Applies to the event-study z-statistic and to HAC t-statistics,
    both of which use the standard-normal reference distribution.
    """
    if direction not in ("less", "greater"):
        raise ValueError(f"direction must be 'less' or 'greater': {direction!r}")
    cdf = 0.5 * (1.0 + erf(z_statistic / sqrt(2.0)))
    return cdf if direction == "less" else 1.0 - cdf


def standardized_mean_car(result: EventStudyResult) -> float:
    """Mean CAR divided by the cross-event standard deviation of CARs.

    Uses the per-event CARs (with non-overlapping windows each event is
    its own cluster, so the per-event and per-cluster CARs coincide).
    Returns 0.0 when the cross-event dispersion is zero.
    """
    cars = np.asarray(
        [event.cumulative_abnormal_return for event in result.events],
        dtype=float,
    )
    dispersion = float(np.std(cars, ddof=1)) if cars.size >= 2 else 0.0
    if dispersion == 0.0:
        return 0.0
    return float(result.mean_cluster_car / dispersion)
