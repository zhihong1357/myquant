"""Trade-based order-flow metrics, bucketed by event time.

Buckets are aligned to UTC boundaries (a 5-minute bucket opens on a
multiple of 5 minutes past the UTC hour) and each bucket's metrics use
only the trades inside that bucket, so a bucket's values are knowable
at the bucket's close and no future information leaks in. Empty buckets
between the first and last trade are included with zero counts and
``None`` for ratios that need a denominator.

Metrics per bucket (all descriptive; none of them is a signal or a
prediction):

- ``cvd_delta``: buy volume minus sell volume inside the bucket, in
  contracts. ``cvd_cumulative`` is the running sum of ``cvd_delta``
  from ``start_cvd`` (default 0). The increment sum equals the total:
  summing ``cvd_delta`` over all buckets gives the final cumulative
  CVD minus ``start_cvd``.
- ``volume_imbalance``: (buy volume - sell volume) / total volume, in
  [-1, 1]; ``None`` on an empty bucket.
- ``count_imbalance``: (buy count - sell count) / trade count, in
  [-1, 1]; ``None`` on an empty bucket.
- ``vwap``: volume-weighted average price inside the bucket; ``None``
  on an empty bucket.
- ``large_trade_share``: share of bucket volume from single trades
  with size >= ``large_trade_threshold``; ``None`` on an empty bucket.
  The threshold is arbitrary — the BTC default of 1.0 contracts is a
  round number, not a discovered boundary — and must be stated
  wherever the metric is reported.
- ``trade_count`` / ``total_volume``: bucket intensity (count and
  contracts).
- ``first_price`` / ``last_price``: first and last trade prices in
  the bucket, for smoke checks against the bucket's CVD direction.
  Direction agreement between CVD delta and the bucket's price change
  is a data sanity check, not evidence that CVD predicts price.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import Field

from myquant.contracts import StrictContract, require_utc
from myquant.microstructure.trades import Trade

SECONDS_PER_DAY = 86_400

#: Default large-trade threshold for BTC perpetuals, in contracts.
#: Arbitrary round number; see the module docstring.
DEFAULT_LARGE_TRADE_THRESHOLD_BTC = 1.0


@dataclass(frozen=True)
class BucketConfig:
    """Bucketing parameters. The width must divide a UTC day evenly."""

    bucket_width: timedelta
    large_trade_threshold: float = DEFAULT_LARGE_TRADE_THRESHOLD_BTC

    def __post_init__(self) -> None:
        width_seconds = self.bucket_width.total_seconds()
        if width_seconds <= 0 or width_seconds != int(width_seconds):
            raise ValueError("bucket_width must be a positive whole number of seconds")
        if SECONDS_PER_DAY % int(width_seconds) != 0:
            raise ValueError("bucket_width must divide a UTC day evenly")
        if self.large_trade_threshold <= 0:
            raise ValueError("large_trade_threshold must be positive")

    @property
    def width_seconds(self) -> int:
        return int(self.bucket_width.total_seconds())


def bucket_open(timestamp: datetime, width: timedelta) -> datetime:
    """Floor a timestamp to its bucket-open boundary (UTC-aligned)."""
    ts = require_utc(timestamp)
    width_seconds = int(width.total_seconds())
    midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((ts - midnight).total_seconds())
    return midnight + timedelta(seconds=(elapsed // width_seconds) * width_seconds)


class BucketMetrics(StrictContract):
    """Order-flow metrics for one event-time bucket."""

    bucket_open: datetime
    bucket_width_seconds: int = Field(gt=0)
    trade_count: int = Field(ge=0)
    buy_count: int = Field(ge=0)
    sell_count: int = Field(ge=0)
    total_volume: float = Field(ge=0, allow_inf_nan=False)
    buy_volume: float = Field(ge=0, allow_inf_nan=False)
    sell_volume: float = Field(ge=0, allow_inf_nan=False)
    cvd_delta: float = Field(allow_inf_nan=False)
    cvd_cumulative: float = Field(allow_inf_nan=False)
    volume_imbalance: float | None = Field(default=None, ge=-1, le=1)
    count_imbalance: float | None = Field(default=None, ge=-1, le=1)
    vwap: float | None = Field(default=None, gt=0)
    large_trade_volume: float = Field(ge=0, allow_inf_nan=False)
    large_trade_share: float | None = Field(default=None, ge=0, le=1)
    first_price: float | None = Field(default=None, gt=0)
    last_price: float | None = Field(default=None, gt=0)


def compute_order_flow_metrics(
    trades: tuple[Trade, ...] | list[Trade],
    *,
    config: BucketConfig,
    start_cvd: float = 0.0,
) -> tuple[BucketMetrics, ...]:
    """Bucket trades by event time and compute per-bucket metrics.

    Trades are ordered by (event_time, trade_id) before bucketing.
    Buckets run from the first trade's bucket to the last trade's
    bucket inclusive, stepping by the configured width; empty buckets
    in between are included with zero counts. Returns an empty tuple
    when given no trades.
    """
    ordered = sorted(trades, key=lambda item: (item.event_time, item.trade_id))
    if not ordered:
        return ()
    width = config.bucket_width
    first_bucket = bucket_open(ordered[0].event_time, width)
    last_bucket = bucket_open(ordered[-1].event_time, width)

    grouped: dict[datetime, list[Trade]] = {}
    for trade in ordered:
        grouped.setdefault(bucket_open(trade.event_time, width), []).append(trade)

    results: list[BucketMetrics] = []
    cvd_cumulative = start_cvd
    current = first_bucket
    while current <= last_bucket:
        bucket_trades = grouped.get(current, [])
        buy = [t for t in bucket_trades if t.aggressor_side == "buy"]
        sell = [t for t in bucket_trades if t.aggressor_side == "sell"]
        buy_volume = float(sum(t.size for t in buy))
        sell_volume = float(sum(t.size for t in sell))
        total_volume = buy_volume + sell_volume
        cvd_delta = buy_volume - sell_volume
        cvd_cumulative += cvd_delta
        large_volume = float(
            sum(t.size for t in bucket_trades if t.size >= config.large_trade_threshold)
        )
        results.append(
            BucketMetrics(
                bucket_open=current,
                bucket_width_seconds=config.width_seconds,
                trade_count=len(bucket_trades),
                buy_count=len(buy),
                sell_count=len(sell),
                total_volume=total_volume,
                buy_volume=buy_volume,
                sell_volume=sell_volume,
                cvd_delta=cvd_delta,
                cvd_cumulative=cvd_cumulative,
                volume_imbalance=(
                    (buy_volume - sell_volume) / total_volume
                    if total_volume > 0
                    else None
                ),
                count_imbalance=(
                    (len(buy) - len(sell)) / len(bucket_trades)
                    if bucket_trades
                    else None
                ),
                vwap=(
                    float(sum(t.price * t.size for t in bucket_trades)) / total_volume
                    if total_volume > 0
                    else None
                ),
                large_trade_volume=large_volume,
                large_trade_share=(
                    large_volume / total_volume if total_volume > 0 else None
                ),
                first_price=bucket_trades[0].price if bucket_trades else None,
                last_price=bucket_trades[-1].price if bucket_trades else None,
            )
        )
        current += width
    return tuple(results)
