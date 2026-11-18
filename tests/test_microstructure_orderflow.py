"""Tests for trade-based order-flow metrics. All offline, no network access."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from myquant.microstructure.orderflow import (
    BucketConfig,
    bucket_open,
    compute_order_flow_metrics,
)
from myquant.microstructure.trades import Trade

INGESTED = datetime(2026, 11, 18, 7, 0, 0, tzinfo=UTC)


def _trade(
    trade_id: int,
    minute: int,
    second: int,
    side: str,
    price: float,
    size: float,
) -> Trade:
    return Trade(
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        event_time=datetime(2026, 11, 18, 5, minute, second, tzinfo=UTC),
        available_at=datetime(2026, 11, 18, 5, minute, second, tzinfo=UTC),
        ingested_at=INGESTED,
        trade_id=trade_id,
        price=price,
        size=size,
        aggressor_side=side,  # type: ignore[arg-type]
        source_id="okx-public",
    )


def test_bucket_open_aligns_to_boundaries() -> None:
    ts = datetime(2026, 11, 18, 5, 7, 33, tzinfo=UTC)
    assert bucket_open(ts, timedelta(minutes=1)) == datetime(
        2026, 11, 18, 5, 7, 0, tzinfo=UTC
    )
    assert bucket_open(ts, timedelta(minutes=5)) == datetime(
        2026, 11, 18, 5, 5, 0, tzinfo=UTC
    )
    assert bucket_open(ts, timedelta(hours=1)) == datetime(
        2026, 11, 18, 5, 0, 0, tzinfo=UTC
    )
    # A trade exactly on a boundary belongs to the bucket opening there.
    assert bucket_open(
        datetime(2026, 11, 18, 5, 5, 0, tzinfo=UTC), timedelta(minutes=5)
    ) == datetime(2026, 11, 18, 5, 5, 0, tzinfo=UTC)


def test_bucket_config_rejects_bad_widths_and_thresholds() -> None:
    with pytest.raises(ValueError, match="divide a UTC day evenly"):
        BucketConfig(bucket_width=timedelta(minutes=7))
    with pytest.raises(ValueError, match="positive whole number"):
        BucketConfig(bucket_width=timedelta(seconds=0))
    with pytest.raises(ValueError, match="threshold must be positive"):
        BucketConfig(bucket_width=timedelta(minutes=1), large_trade_threshold=0.0)
    # 1m / 5m / 1H are all valid.
    for width in (timedelta(minutes=1), timedelta(minutes=5), timedelta(hours=1)):
        assert BucketConfig(bucket_width=width).width_seconds > 0


def test_metrics_hand_computed_values() -> None:
    trades = [
        _trade(1, 0, 1, "buy", 65000.0, 2.0),
        _trade(2, 0, 30, "sell", 65010.0, 0.5),
        _trade(3, 0, 59, "buy", 64990.0, 0.5),
        _trade(4, 2, 0, "sell", 65020.0, 3.0),
    ]
    config = BucketConfig(bucket_width=timedelta(minutes=1), large_trade_threshold=1.0)
    metrics = compute_order_flow_metrics(trades, config=config)
    assert len(metrics) == 3  # 05:00, 05:01 (empty), 05:02

    first = metrics[0]
    assert first.bucket_open == datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)
    assert first.trade_count == 3
    assert first.buy_count == 2
    assert first.sell_count == 1
    assert first.total_volume == pytest.approx(3.0)
    assert first.buy_volume == pytest.approx(2.5)
    assert first.sell_volume == pytest.approx(0.5)
    assert first.cvd_delta == pytest.approx(2.0)
    assert first.cvd_cumulative == pytest.approx(2.0)
    assert first.volume_imbalance == pytest.approx(2.0 / 3.0)
    assert first.count_imbalance == pytest.approx(1.0 / 3.0)
    assert first.vwap == pytest.approx(65000.0)
    assert first.large_trade_volume == pytest.approx(2.0)
    assert first.large_trade_share == pytest.approx(2.0 / 3.0)
    assert first.first_price == 65000.0
    assert first.last_price == 64990.0

    empty = metrics[1]
    assert empty.trade_count == 0
    assert empty.total_volume == 0.0
    assert empty.cvd_delta == 0.0
    assert empty.cvd_cumulative == pytest.approx(2.0)
    assert empty.volume_imbalance is None
    assert empty.count_imbalance is None
    assert empty.vwap is None
    assert empty.large_trade_share is None
    assert empty.first_price is None

    last = metrics[2]
    assert last.trade_count == 1
    assert last.cvd_delta == pytest.approx(-3.0)
    assert last.cvd_cumulative == pytest.approx(-1.0)
    assert last.volume_imbalance == pytest.approx(-1.0)
    assert last.count_imbalance == pytest.approx(-1.0)
    assert last.vwap == pytest.approx(65020.0)
    assert last.large_trade_share == pytest.approx(1.0)


def test_cvd_increments_sum_to_total() -> None:
    trades = [
        _trade(1, 0, 1, "buy", 65000.0, 2.0),
        _trade(2, 1, 1, "sell", 65000.0, 0.5),
        _trade(3, 2, 1, "buy", 65000.0, 1.5),
        _trade(4, 3, 1, "sell", 65000.0, 4.0),
    ]
    config = BucketConfig(bucket_width=timedelta(minutes=1))
    metrics = compute_order_flow_metrics(trades, config=config, start_cvd=10.0)
    total_delta = sum(m.cvd_delta for m in metrics)
    assert total_delta == pytest.approx(metrics[-1].cvd_cumulative - 10.0)
    assert metrics[-1].cvd_cumulative == pytest.approx(10.0 + 2.0 - 0.5 + 1.5 - 4.0)


def test_metrics_empty_input_and_single_trade() -> None:
    config = BucketConfig(bucket_width=timedelta(minutes=5))
    assert compute_order_flow_metrics([], config=config) == ()
    single = compute_order_flow_metrics(
        [_trade(1, 3, 30, "sell", 65000.0, 0.25)], config=config
    )
    assert len(single) == 1
    assert single[0].bucket_open == datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)
    assert single[0].trade_count == 1
    assert single[0].volume_imbalance == pytest.approx(-1.0)
    assert single[0].vwap == pytest.approx(65000.0)
    assert single[0].large_trade_share == pytest.approx(0.0)


def test_metrics_hourly_bucketing_and_start_cvd() -> None:
    trades = [
        _trade(1, 0, 1, "buy", 65000.0, 1.0),
        _trade(2, 59, 59, "sell", 65010.0, 1.0),
    ]
    config = BucketConfig(bucket_width=timedelta(hours=1))
    metrics = compute_order_flow_metrics(trades, config=config)
    assert len(metrics) == 1
    assert metrics[0].trade_count == 2
    assert metrics[0].cvd_delta == pytest.approx(0.0)
    assert metrics[0].volume_imbalance == pytest.approx(0.0)
