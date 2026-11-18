"""Synchronized multi-instrument panels from point-in-time observations.

Builds one wide frame per field (closes, log returns) with instruments as
columns and event times as the index. Synchronization is an outer join on
the union of event times followed by dropping every incomplete row: no
forward filling, no interpolation. The dropped-row count is part of the
result so callers can report it.

Returns are computed per instrument on that instrument's own complete
series *before* synchronization, so a row dropped for another instrument's
missing value does not corrupt this instrument's returns. When the caller
supplies ``bar_seconds``, a return is admitted only when its two closes
are exactly one bar apart on the clock; a return spanning a gap in the
instrument's own series is invalidated rather than admitted as a
multi-bar return.

``level_changes_on_index`` applies the same diff-then-join pattern to
level changes (yields, spreads): each instrument's changes are computed
on its own series first and then aligned to a panel's return index, so
a partial holiday in one leg cannot turn another leg's one-day change
into a two-day change.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from myquant.contracts import Observation
from myquant.stats.returns import log_returns


@dataclass(frozen=True)
class SynchronizedPanel:
    """A synchronized panel of closes and log returns."""

    closes: pd.DataFrame
    returns: pd.DataFrame
    dropped_close_rows: int
    dropped_return_rows: int

    @property
    def row_count(self) -> int:
        return int(self.returns.shape[0])

    @property
    def first_time(self) -> pd.Timestamp:
        return self.returns.index[0]

    @property
    def last_time(self) -> pd.Timestamp:
        return self.returns.index[-1]


def _series_for(
    observations: Sequence[Observation],
    instrument_id: str,
    field: str,
) -> pd.Series:
    """One instrument's field values as a time-sorted series."""
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


def build_synchronized_panel(
    observations: Sequence[Observation],
    *,
    instruments: tuple[str, ...],
    field: str = "close",
    bar_seconds: int | None = None,
) -> SynchronizedPanel:
    """Synchronize closes and log returns across instruments.

    Rows are dropped when any instrument lacks a value at that event time;
    the first return row is always dropped (no prior close exists). When
    ``bar_seconds`` is given, returns spanning a gap in an instrument's own
    series are invalidated. Both drop counts are reported in the result.
    """
    if not instruments:
        raise ValueError("at least one instrument is required")
    if len(set(instruments)) != len(instruments):
        raise ValueError("instrument ids must be unique")
    if bar_seconds is not None and bar_seconds <= 0:
        raise ValueError("bar_seconds must be positive")

    close_series = {
        instrument_id: _series_for(observations, instrument_id, field)
        for instrument_id in instruments
    }
    closes_wide = pd.DataFrame(close_series)
    dropped_close_rows = int(closes_wide.isna().any(axis=1).sum())
    closes = closes_wide.dropna(how="any")

    return_series = {}
    for instrument_id, series in close_series.items():
        returns = log_returns(series)
        if bar_seconds is not None:
            gaps = series.index.to_series().diff().dt.total_seconds()
            returns = returns.where(gaps == bar_seconds)
        return_series[instrument_id] = returns
    returns_wide = pd.DataFrame(return_series)
    dropped_return_rows = int(returns_wide.isna().any(axis=1).sum())
    returns = returns_wide.dropna(how="any")
    if returns.empty:
        raise ValueError("no complete synchronized return rows remain")
    return SynchronizedPanel(
        closes=closes,
        returns=returns,
        dropped_close_rows=dropped_close_rows,
        dropped_return_rows=dropped_return_rows,
    )


def level_changes_on_index(
    observations: Sequence[Observation],
    *,
    instruments: tuple[str, ...],
    index: pd.DatetimeIndex,
    field: str = "close",
    scale: float = 100.0,
) -> pd.DataFrame:
    """Per-instrument level changes aligned to a panel's return index.

    Each instrument's changes are computed on its own complete series
    first (diff-then-join, the same pattern ``build_synchronized_panel``
    uses for log returns), then aligned to the supplied index. ``scale``
    converts the level unit: 100.0 turns a yield quoted in percent into
    basis points. Every index timestamp must have a change available
    for every instrument, or the call fails: a silently missing change
    on an event day would corrupt an event study.
    """
    if not instruments:
        raise ValueError("at least one instrument is required")
    if len(set(instruments)) != len(instruments):
        raise ValueError("instrument ids must be unique")
    if index.tz is None:
        raise ValueError("index must be timezone-aware")

    changes = {
        instrument_id: _series_for(observations, instrument_id, field).diff()
        * scale
        for instrument_id in instruments
    }
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
            "level changes are unavailable at some index timestamps: "
            f"{shown}{suffix}"
        )
    return aligned
