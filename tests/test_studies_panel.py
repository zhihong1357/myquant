"""Tests for the synchronized panel builder."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from myquant.contracts import Observation
from myquant.studies.panel import build_synchronized_panel, level_changes_on_index

DAY = timedelta(days=1)
T0 = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)


def _observation(
    instrument: str,
    event_time: datetime,
    value: float,
    field: str = "close",
) -> Observation:
    return Observation(
        instrument_id=instrument,
        venue="okx",
        event_time=event_time,
        available_at=event_time + DAY,
        ingested_at=event_time + 2 * DAY,
        field=field,
        value=value,
        unit="USDT",
        source_id="okx-public",
        source_version=1,
    )


def _closes(
    instrument: str,
    prices: list[float],
    *,
    start: datetime = T0,
    skip: set[int] | None = None,
) -> list[Observation]:
    skip = skip or set()
    return [
        _observation(instrument, start + index * DAY, price)
        for index, price in enumerate(prices)
        if index not in skip
    ]


def test_panel_synchronizes_and_computes_true_one_bar_returns() -> None:
    observations = [
        *_closes("crypto:btc-usdt-perp", [100.0, 110.0, 121.0, 115.0]),
        *_closes("crypto:eth-usdt-perp", [10.0, 11.0, 12.0, 12.5]),
        *_closes("crypto:sol-usdt-perp", [5.0, 5.0, 6.0, 6.0]),
    ]
    panel = build_synchronized_panel(
        observations,
        instruments=(
            "crypto:btc-usdt-perp",
            "crypto:eth-usdt-perp",
            "crypto:sol-usdt-perp",
        ),
    )
    # First return row is dropped (no prior close); 3 return rows remain.
    assert panel.row_count == 3
    assert panel.dropped_close_rows == 0
    assert panel.dropped_return_rows == 1
    assert panel.returns["crypto:btc-usdt-perp"].iloc[0] == pytest.approx(
        math.log(110.0 / 100.0)
    )
    assert panel.returns["crypto:eth-usdt-perp"].iloc[2] == pytest.approx(
        math.log(12.5 / 12.0)
    )


def test_panel_drops_incomplete_rows_without_filling() -> None:
    observations = [
        *_closes("crypto:btc-usdt-perp", [100.0, 110.0, 121.0, 115.0]),
        # ETH misses the third bar. The synchronized panel loses that row,
        # and ETH's return on the fourth bar is invalidated: it would span
        # a two-day gap, not one bar, so it must not enter the panel.
        *_closes("crypto:eth-usdt-perp", [10.0, 11.0, 12.0, 12.5], skip={2}),
    ]
    panel = build_synchronized_panel(
        observations,
        instruments=("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        bar_seconds=86_400,
    )
    assert panel.dropped_close_rows == 1
    assert panel.row_count == 1
    assert panel.returns["crypto:eth-usdt-perp"].iloc[0] == pytest.approx(
        math.log(11.0 / 10.0)
    )
    # Neither the missing bar nor the return spanning its gap is admitted.
    assert (T0 + 2 * DAY) not in panel.returns.index
    assert (T0 + 3 * DAY) not in panel.returns.index


def test_panel_sorts_unsorted_input() -> None:
    observations = list(reversed(_closes("crypto:btc-usdt-perp", [100.0, 110.0])))
    observations.extend(_closes("crypto:eth-usdt-perp", [10.0, 11.0]))
    panel = build_synchronized_panel(
        observations,
        instruments=("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
    )
    assert panel.row_count == 1
    assert panel.returns.index.is_monotonic_increasing


def test_panel_rejects_duplicate_event_times() -> None:
    observations = _closes("crypto:btc-usdt-perp", [100.0, 110.0])
    observations.append(_observation("crypto:btc-usdt-perp", T0, 101.0))
    observations.extend(_closes("crypto:eth-usdt-perp", [10.0, 11.0]))
    with pytest.raises(ValueError, match="duplicate"):
        build_synchronized_panel(
            observations,
            instruments=("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        )


def test_panel_rejects_missing_instrument() -> None:
    observations = _closes("crypto:btc-usdt-perp", [100.0, 110.0])
    with pytest.raises(ValueError, match="no 'close' observations"):
        build_synchronized_panel(
            observations,
            instruments=("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        )


def test_panel_rejects_empty_panel() -> None:
    # Two bars each, but no shared timestamps at all.
    observations = _closes("crypto:btc-usdt-perp", [100.0, 110.0])
    observations.extend(
        _closes("crypto:eth-usdt-perp", [10.0, 11.0], start=T0 + 10 * DAY)
    )
    with pytest.raises(ValueError, match="no complete synchronized return rows"):
        build_synchronized_panel(
            observations,
            instruments=("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        )


def test_level_changes_diff_then_join_after_partial_holiday() -> None:
    # The rate leg trades every day; the equity leg is missing on day 2
    # (a partial holiday). The panel's return index is days 1 and 3.
    # Diff-then-join gives the rate leg's true one-day change on day 3
    # (2.30 - 2.20); join-then-diff would give the two-day change
    # (2.30 - 2.10) instead.
    observations = [
        *_closes("rates:us-10y-yield", [2.00, 2.10, 2.20, 2.30]),
        *_closes("index:sp500", [10.0, 11.0, 12.0, 13.0], skip={2}),
    ]
    panel = build_synchronized_panel(
        observations,
        instruments=("rates:us-10y-yield", "index:sp500"),
    )
    assert panel.row_count == 2
    changes = level_changes_on_index(
        observations,
        instruments=("rates:us-10y-yield",),
        index=panel.returns.index,
    )
    assert changes["rates:us-10y-yield"].iloc[0] == pytest.approx(10.0)
    assert changes["rates:us-10y-yield"].iloc[1] == pytest.approx(10.0)


def test_level_changes_scale_and_missing_timestamps() -> None:
    observations = [
        *_closes("rates:us-10y-yield", [2.00, 2.10, 2.20]),
        *_closes("index:sp500", [10.0, 11.0, 12.0]),
    ]
    panel = build_synchronized_panel(
        observations,
        instruments=("rates:us-10y-yield", "index:sp500"),
    )
    raw = level_changes_on_index(
        observations,
        instruments=("rates:us-10y-yield",),
        index=panel.returns.index,
        scale=1.0,
    )
    assert raw["rates:us-10y-yield"].iloc[0] == pytest.approx(0.10)
    # The first close has no prior close, so no change exists there.
    import pandas as pd

    bad_index = pd.DatetimeIndex([panel.closes.index[0]])
    with pytest.raises(ValueError, match="unavailable at some index timestamps"):
        level_changes_on_index(
            observations,
            instruments=("rates:us-10y-yield",),
            index=bad_index,
        )
