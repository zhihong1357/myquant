"""Publication-lag alignment and CPI step-function features (study 007).

Study 005 recorded a stated limitation: FRED values are posted after the
close, sometimes the next morning, so ``available_at`` equal to the close
is optimistic by up to a day. This module makes that lag explicit.

**The FRED publication lag (verified before preregistration).** A FRED
daily value dated t is posted on the next business day, not the same
evening and not two days later. Evidence (2026-11-18, fetch at 06:26
UTC = 01:26 EST, about 9.4 hours after Tuesday 2026-11-17's close):
VIXCLS and DGS10 both end at 2026-11-16 (Monday) — Tuesday's value is
not posted yet, which rules out same-evening posting, while Monday's
value is already available, which rules out a two-business-day posting
delay (a two-day lag would have left Monday's value unposted until
Wednesday morning). So the value dated t is available from the morning
of t+1, and at the close of any day t the latest available FRED value
is the previous trading day's: a **one-trading-day availability lag**.
Yahoo and OKX market data carry no such lag (the close is knowable at
the close), so they are not shifted.

**Lagged changes (diff-then-join, with the shift between diff and
join).** A lagged level series is the original level series shifted
forward by ``lag_steps`` positions on the series' own dates: the value
dated t becomes the value available at t+lag. Its changes are the
original changes shifted by the same amount, so the lagged change at
own-date t is the original change at the own-date ``lag_steps`` before
t. Changes are computed per series on its own dates first (study 003's
diff-then-join lesson: a partial holiday in one leg must not corrupt
another leg's one-day change), shifted, then aligned to the panel's
return index. The first ``lag_steps`` panel rows have no lagged change
(nothing shifted into them) and are dropped by the caller.

**What the lag does to an event study.** A lagged event window [0,+1]
in availability terms covers reference-date changes [-1,0]: the
statement-day change plus the day-before change, not the statement-day
plus the day-after change. The estimation window shifts back by the
same amount ([-60,-11] availability = [-61,-12] reference), which moves
a 50-day mean by one day and is second-order. The verdict question is
whether study 005's TYVIX finding survives that shift — not whether
study 005 was wrong: both alignments are conditionally correct, under
different availability assumptions.

**CPI step functions.** The CPI is a monthly series published with a
multi-week lag (the reference month's value is released about two weeks
into the next month). Two alignments of the same month-on-month log
changes are built here:

- **PIT (release-day aligned):** the predictor at a bar's close is the
  most recent CPI month-on-month value released on or before the bar's
  close date. A release on date D is knowable at the close of D (08:30
  ET release, 16:00 ET close), so release-day rows carry the fresh
  print. This is the test alignment.
- **Naive (reference-month aligned):** the predictor at a bar's close
  is the month-on-month value of the reference month containing the
  close date — as if the month's CPI were known during the month itself.
  That is 2-6 weeks of lookahead. It is descriptive only: comparing it
  against the PIT version quantifies the lookahead bias the lag would
  otherwise smuggle in.

Both functions are evaluated at **bar close dates**: for an SPX daily
bar the close date is the trading date; for an OKX daily bar (open
16:00 UTC) the close date is the open date plus one day. A CPI release
at 08:30 ET on date D is knowable at any close on D, so the same
release-date rule serves both venues once each bar is dated by its
close.

This module is pure (no network, no market data). Fetching and
verification live in the study 007 fetch script; the lag check lives
in the study manifest.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from myquant.contracts import Observation
from myquant.studies.macro import CPIRelease


@dataclass(frozen=True)
class CPIMonthChange:
    """One CPI month-on-month log change with its reference month."""

    reference_month: str  # "YYYY-MM"
    log_change: float


def shift_changes_by_positions(changes: pd.Series, steps: int) -> pd.Series:
    """Shift a per-series change series forward by ``steps`` positions.

    The change dated t moves to the own-date ``steps`` positions later:
    after a one-step shift, the change at t is the original change at
    the previous own date. This is the lag operation in its simplest
    form; :func:`lagged_changes_on_index` applies it per series before
    alignment to a panel index.
    """
    if not isinstance(changes, pd.Series):
        raise TypeError("changes must be a pandas Series")
    if not isinstance(changes.index, pd.DatetimeIndex):
        raise TypeError("changes must use a DatetimeIndex")
    if changes.index.tz is None:
        raise ValueError("changes index must be timezone-aware")
    if not changes.index.is_monotonic_increasing:
        raise ValueError("changes index must be sorted in ascending order")
    if not changes.index.is_unique:
        raise ValueError("changes index must not contain duplicate timestamps")
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 0:
        raise ValueError("steps must be a non-negative integer")
    return changes.shift(steps)


def lagged_panel_index(
    index: pd.DatetimeIndex,
    lag_steps: int,
) -> pd.DatetimeIndex:
    """Drop the leading rows that have no lagged change.

    A lag of ``lag_steps`` positions leaves the first ``lag_steps`` rows
    of a return index without a lagged value (nothing shifted into
    them); every later row has one. The caller passes the truncated
    index to :func:`lagged_changes_on_index`, which then fails loudly
    on any remaining gap.
    """
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("index must be a DatetimeIndex")
    if not isinstance(lag_steps, int) or isinstance(lag_steps, bool):
        raise TypeError("lag_steps must be an integer")
    if lag_steps < 0:
        raise ValueError("lag_steps must be non-negative")
    if lag_steps >= len(index):
        raise ValueError("lag_steps must be smaller than the index length")
    return index[lag_steps:]


def reference_window_for_lagged(
    pre_event_steps: int,
    post_event_steps: int,
    lag_steps: int,
) -> tuple[int, int]:
    """Reference-date window covered by a lagged availability window.

    An event window [-pre, +post] in availability terms covers
    reference-date changes [-(pre + lag), +(post - lag)]: every lagged
    change at availability date t is the original change at reference
    date t - lag. For the study 005 window [0,+1] with a one-day lag,
    the lagged window covers reference dates [-1,0].
    """
    for name, value in (
        ("pre_event_steps", pre_event_steps),
        ("post_event_steps", post_event_steps),
        ("lag_steps", lag_steps),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    return (-(pre_event_steps + lag_steps), post_event_steps - lag_steps)


def _close_series_for(
    observations: Sequence[Observation],
    instrument_id: str,
    field: str,
) -> pd.Series:
    """One instrument's field values as a time-sorted series (own dates)."""
    rows = [
        (item.event_time, item.value)
        for item in observations
        if item.instrument_id == instrument_id and item.field == field
    ]
    if not rows:
        raise ValueError(
            f"no {field!r} observations for instrument {instrument_id!r}"
        )
    series = pd.Series(
        {time: value for time, value in rows},
        dtype="float64",
    )
    if len(series) != len(rows):
        raise ValueError(
            f"duplicate {field!r} event times for instrument {instrument_id!r}"
        )
    series.index = pd.DatetimeIndex(series.index, tz="UTC")
    return series.sort_index()


def lagged_changes_on_index(
    observations: Sequence[Observation],
    *,
    instruments: tuple[str, ...],
    index: pd.DatetimeIndex,
    lag_steps: int,
    transform: str,
    field: str = "close",
    scale: float = 100.0,
) -> pd.DataFrame:
    """Per-instrument lagged changes aligned to a panel's return index.

    Each instrument's changes are computed on its own dates first
    (diff-then-join), shifted forward by ``lag_steps`` positions on
    those dates, then aligned to the supplied index. ``transform`` is
    ``"log"`` (log changes; levels must be positive) or ``"level"``
    (level changes times ``scale``; 100.0 turns a yield quoted in
    percent into basis points).

    The caller must pass an index whose first ``lag_steps`` rows are
    already dropped (see :func:`lagged_panel_index`): the shifted
    series has no value there. Every remaining index timestamp must
    have a lagged change for every instrument, or the call fails — a
    silently missing change on an event day would corrupt an event
    study.
    """
    if not instruments:
        raise ValueError("at least one instrument is required")
    if len(set(instruments)) != len(instruments):
        raise ValueError("instrument ids must be unique")
    if index.tz is None:
        raise ValueError("index must be timezone-aware")
    if not isinstance(lag_steps, int) or isinstance(lag_steps, bool):
        raise TypeError("lag_steps must be an integer")
    if lag_steps < 0:
        raise ValueError("lag_steps must be non-negative")
    if transform not in ("log", "level"):
        raise ValueError(f"transform must be 'log' or 'level': {transform!r}")
    if not np.isfinite(scale) or scale == 0.0:
        raise ValueError("scale must be a finite non-zero number")

    changes: dict[str, pd.Series] = {}
    for instrument_id in instruments:
        closes = _close_series_for(observations, instrument_id, field)
        if transform == "log":
            if (closes <= 0).any():
                raise ValueError(
                    f"log changes need positive levels for {instrument_id!r}"
                )
            own_changes = np.log(closes).diff()
        else:
            own_changes = closes.diff() * scale
        changes[instrument_id] = shift_changes_by_positions(
            own_changes, lag_steps
        )
    aligned = pd.DataFrame(changes).reindex(index)
    if bool(aligned.isna().any().any()):
        missing = sorted(
            {
                str(timestamp)
                for timestamp in aligned.index[aligned.isna().any(axis=1)]
            }
        )
        shown = ", ".join(missing[:5])
        suffix = " ..." if len(missing) > 5 else ""
        raise ValueError(
            "lagged changes are unavailable at some index timestamps: "
            f"{shown}{suffix}"
        )
    return aligned


def cpi_mom_log_changes(monthly_levels: pd.Series) -> pd.Series:
    """Month-on-month log changes from monthly CPI levels.

    The input is indexed by reference month (one observation per month,
    dated anywhere inside the month — FRED dates monthly CPIAUCSL by
    the first of the month). Levels must be positive. Months need not
    be consecutive: a missing month (the October 2025 CPI was never
    published) leaves the MoM undefined for that month and for the
    month after it (its comparison base is missing), and both carry
    NaN; every other month's MoM is the log change against the
    previous month. The output is indexed by month-start and carries
    NaN where the MoM is undefined.
    """
    if not isinstance(monthly_levels, pd.Series):
        raise TypeError("monthly_levels must be a pandas Series")
    if not isinstance(monthly_levels.index, pd.DatetimeIndex):
        raise TypeError("monthly_levels must use a DatetimeIndex")
    if monthly_levels.index.tz is None:
        raise ValueError("monthly_levels index must be timezone-aware")
    if not monthly_levels.index.is_monotonic_increasing:
        raise ValueError("monthly_levels index must be sorted in ascending order")
    if not monthly_levels.index.is_unique:
        raise ValueError("monthly_levels index must not contain duplicate timestamps")
    if monthly_levels.empty:
        raise ValueError("monthly_levels must not be empty")
    values = monthly_levels.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("monthly_levels must not contain missing or infinite values")
    if (values <= 0).any():
        raise ValueError("CPI levels must be positive for log changes")
    # Drop the timezone before converting to periods: the month is
    # determined by the UTC date, so this is lossless for month
    # extraction, and it avoids the tz-drop warning.
    months = monthly_levels.index.tz_localize(None).to_period("M")
    if len(months) != len(set(months)):
        raise ValueError("monthly_levels has more than one observation per month")
    # Reindex onto the full monthly grid so a missing month breaks the
    # diff for itself and for the month after it (no base month).
    full_index = pd.period_range(months[0], months[-1], freq="M")
    aligned = pd.Series(values, index=months).reindex(full_index)
    changes = np.log(aligned).diff()
    changes.index = pd.DatetimeIndex(
        [period.to_timestamp().tz_localize("UTC") for period in changes.index]
    )
    changes.name = "cpi_mom_log_change"
    return changes


def cpi_releases_without_mom(
    releases: Sequence[CPIRelease],
    mom_changes: pd.Series,
) -> tuple[CPIRelease, ...]:
    """Releases whose reference month has no defined MoM change.

    A release carries no usable MoM when its reference month's level
    is missing (the month was never published) or the previous month's
    level is missing (no comparison base). In this study's calendar
    the only such release is the November 2025 CPI (released
    2025-12-18): its reference month's MoM needs the never-published
    October 2025 level. Callers should assert the skipped set is
    exactly the expected one — a silently skipped release would hide a
    calendar error.
    """
    by_month = {
        timestamp.strftime("%Y-%m"): float(value)
        for timestamp, value in mom_changes.items()
    }
    return tuple(
        release
        for release in releases
        if not np.isfinite(by_month.get(release.reference_month, np.nan))
    )


def _mom_lookup(
    releases: Sequence[CPIRelease],
    mom_changes: pd.Series,
) -> list[tuple[date, float]]:
    """(release_date, MoM log change) pairs, sorted by release date.

    Releases whose reference month has no defined MoM change are
    skipped (see :func:`cpi_releases_without_mom`): such a release
    publishes no usable MoM, so the step function keeps holding the
    previous value. Callers must check the skipped set explicitly.
    """
    by_month = {
        timestamp.strftime("%Y-%m"): float(value)
        for timestamp, value in mom_changes.items()
    }
    pairs: list[tuple[date, float]] = []
    for release in releases:
        value = by_month.get(release.reference_month, np.nan)
        if not np.isfinite(value):
            continue
        pairs.append((release.release_date, value))
    pairs.sort(key=lambda item: item[0])
    dates = [item[0] for item in pairs]
    if len(set(dates)) != len(dates):
        raise ValueError("CPI releases have duplicate release dates")
    return pairs


def build_cpi_step_function(
    releases: Sequence[CPIRelease],
    mom_changes: pd.Series,
    close_dates: pd.DatetimeIndex,
) -> pd.Series:
    """PIT CPI step function: latest released MoM value at each bar close.

    The value at close date d is the month-on-month log change of the
    most recent release with release_date <= d. A release on date D is
    knowable at the close of D (08:30 ET release, 16:00 ET close), so
    release-day rows carry the fresh print. Close dates before the
    first release carry NaN (no CPI value is available yet); callers
    drop those rows. A release whose reference month has no defined
    MoM (the November 2025 CPI, whose base month October 2025 was
    never published) does not move the step: it publishes no usable
    MoM, so the previous value keeps holding. Callers must check the
    skipped releases via :func:`cpi_releases_without_mom`.
    """
    if not isinstance(close_dates, pd.DatetimeIndex):
        raise TypeError("close_dates must be a DatetimeIndex")
    if close_dates.tz is None:
        raise ValueError("close_dates index must be timezone-aware")
    if not close_dates.is_monotonic_increasing:
        raise ValueError("close_dates index must be sorted in ascending order")
    if not close_dates.is_unique:
        raise ValueError("close_dates index must not contain duplicate timestamps")
    pairs = _mom_lookup(releases, mom_changes)
    release_dates = np.array([item[0] for item in pairs], dtype="datetime64[D]")
    values = np.array([item[1] for item in pairs], dtype=float)
    query = np.array(
        [item.date() for item in close_dates], dtype="datetime64[D]"
    )
    positions = np.searchsorted(release_dates, query, side="right") - 1
    step_values = np.where(
        positions >= 0, values[np.maximum(positions, 0)], np.nan
    )
    return pd.Series(step_values, index=close_dates, name="cpi_step_mom")


def build_cpi_naive_function(
    mom_changes: pd.Series,
    close_dates: pd.DatetimeIndex,
) -> pd.Series:
    """Naive CPI alignment: the reference month's MoM value, as if known.

    The value at close date d is the month-on-month log change of the
    reference month containing d — as if the month's CPI were known
    during the month itself. That is 2-6 weeks of lookahead (the
    reference month's value is released about two weeks into the next
    month). Descriptive only: comparing this against the PIT step
    function quantifies the lookahead bias. Close dates whose month has
    no MoM change (before the series starts, or the current incomplete
    month) carry NaN.
    """
    if not isinstance(close_dates, pd.DatetimeIndex):
        raise TypeError("close_dates must be a DatetimeIndex")
    if close_dates.tz is None:
        raise ValueError("close_dates index must be timezone-aware")
    if not close_dates.is_monotonic_increasing:
        raise ValueError("close_dates index must be sorted in ascending order")
    if not close_dates.is_unique:
        raise ValueError("close_dates index must not contain duplicate timestamps")
    by_month = {
        timestamp.strftime("%Y-%m"): float(value)
        for timestamp, value in mom_changes.items()
    }
    naive_values = np.array(
        [
            by_month.get(timestamp.strftime("%Y-%m"), np.nan)
            for timestamp in close_dates
        ],
        dtype=float,
    )
    return pd.Series(naive_values, index=close_dates, name="cpi_naive_mom")


def cpi_release_day_flags(
    close_dates: pd.DatetimeIndex,
    release_dates: Sequence[date],
) -> pd.Series:
    """Flag bars whose close date is a CPI release date.

    Release-day rows are the subsample for the H0012 secondary test:
    each is a fresh-information event (the predictor is the just-released
    print, known at the close). Release dates that are not trading days
    simply never appear in the index.
    """
    if not isinstance(close_dates, pd.DatetimeIndex):
        raise TypeError("close_dates must be a DatetimeIndex")
    dates = set(release_dates)
    flags = [item.date() in dates for item in close_dates]
    return pd.Series(flags, index=close_dates, dtype=bool)
