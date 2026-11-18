"""Canonical order-book snapshots: OKX books normalized to the research schema.

A snapshot is a single point in time, not a continuous book. REST
returns snapshots only; reconstructing the continuous book needs the
WebSocket stream and is out of scope for Stage 4a (see
``docs/microstructure.md``).

Derived quantities (all computed from the snapshot's own levels):

- ``best_bid`` / ``best_ask``: highest bid / lowest ask, or ``None``
  when that side is empty.
- ``mid``: (best bid + best ask) / 2, or ``None`` when either side is
  empty.
- ``spread``: best ask - best bid (absolute, same units as price);
  ``spread_bps``: spread / mid * 10_000.
- ``depth_bid(n)`` / ``depth_ask(n)``: summed size over the top ``n``
  levels of each side.
- ``imbalance(n)``: (bid depth - ask depth) / (bid depth + ask depth)
  over the top ``n`` levels, in [-1, 1]; ``None`` when both depths are
  zero. This is a descriptive depth ratio, not a prediction and not a
  statement about who is bidding or offering.
- ``microprice``: (best bid * best ask size + best ask * best bid
  size) / (best bid size + best ask size); ``None`` when either side
  is empty or both best sizes are zero.

A crossed book (best bid >= best ask) is detected and reported as a
data-quality issue by :func:`normalize_books_snapshot`; the snapshot
itself is still returned, because a crossed snapshot is data (a
transient exchange state or a feed glitch) and the consumer decides
how to treat it. Empty sides are reported the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import Field, model_validator

from myquant.adapters.okx_microstructure import OKXBookSnapshot
from myquant.contracts import StrictContract, require_utc


class BookLevel(StrictContract):
    """One price level of a normalized order-book snapshot."""

    price: float = Field(gt=0, allow_inf_nan=False)
    size: float = Field(ge=0, allow_inf_nan=False)
    order_count: int = Field(ge=0)


class BookSnapshot(StrictContract):
    """One normalized order-book snapshot (a point in time, not a stream)."""

    schema_version: int = Field(default=1, ge=1)
    instrument_id: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    snapshot_time: datetime
    available_at: datetime
    ingested_at: datetime
    seq_id: int = Field(ge=0)
    asks: tuple[BookLevel, ...]
    bids: tuple[BookLevel, ...]
    source_id: str = Field(min_length=1)
    source_version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_snapshot(self) -> BookSnapshot:
        snapshot = require_utc(self.snapshot_time)
        available = require_utc(self.available_at)
        ingested = require_utc(self.ingested_at)
        if ingested < available:
            raise ValueError("ingested_at cannot precede available_at")
        ask_prices = [level.price for level in self.asks]
        bid_prices = [level.price for level in self.bids]
        if ask_prices != sorted(ask_prices) or len(set(ask_prices)) != len(ask_prices):
            raise ValueError("asks must be strictly ascending by price")
        if bid_prices != sorted(bid_prices, reverse=True) or (
            len(set(bid_prices)) != len(bid_prices)
        ):
            raise ValueError("bids must be strictly descending by price")
        object.__setattr__(self, "snapshot_time", snapshot)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "ingested_at", ingested)
        return self

    @property
    def best_bid(self) -> float | None:
        """Highest bid price, or None when the bid side is empty."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        """Lowest ask price, or None when the ask side is empty."""
        return self.asks[0].price if self.asks else None

    @property
    def best_bid_size(self) -> float | None:
        return self.bids[0].size if self.bids else None

    @property
    def best_ask_size(self) -> float | None:
        return self.asks[0].size if self.asks else None

    @property
    def mid(self) -> float | None:
        """Midpoint of best bid/ask, or None when either side is empty."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> float | None:
        """Best ask minus best bid, or None when either side is empty."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def spread_bps(self) -> float | None:
        """Spread in basis points of mid, or None when mid is undefined."""
        mid = self.mid
        spread = self.spread
        if mid is None or spread is None or mid == 0:
            return None
        return spread / mid * 10_000

    def depth_bid(self, levels: int) -> float:
        """Summed bid size over the top ``levels`` levels."""
        if levels < 1:
            raise ValueError("levels must be >= 1")
        return float(sum(level.size for level in self.bids[:levels]))

    def depth_ask(self, levels: int) -> float:
        """Summed ask size over the top ``levels`` levels."""
        if levels < 1:
            raise ValueError("levels must be >= 1")
        return float(sum(level.size for level in self.asks[:levels]))

    def depth_total(self, levels: int) -> float:
        """Summed size over the top ``levels`` levels of both sides."""
        return self.depth_bid(levels) + self.depth_ask(levels)

    def imbalance(self, levels: int) -> float | None:
        """Top-``levels`` depth imbalance in [-1, 1].

        (bid depth - ask depth) / (bid depth + ask depth). ``None``
        when both depths are zero. Descriptive only: it measures
        resting depth, not intent or future direction.
        """
        bid = self.depth_bid(levels)
        ask = self.depth_ask(levels)
        total = bid + ask
        if total == 0:
            return None
        return (bid - ask) / total

    @property
    def microprice(self) -> float | None:
        """Size-weighted midpoint from the best levels.

        (best bid * best ask size + best ask * best bid size) /
        (best bid size + best ask size). ``None`` when either side is
        empty or both best sizes are zero.
        """
        bid = self.best_bid
        ask = self.best_ask
        bid_size = self.best_bid_size
        ask_size = self.best_ask_size
        if bid is None or ask is None or bid_size is None or ask_size is None:
            return None
        total = bid_size + ask_size
        if total == 0:
            return None
        return (bid * ask_size + ask * bid_size) / total


@dataclass(frozen=True)
class NormalizedBook:
    """A normalized snapshot plus its data-quality issues, if any."""

    snapshot: BookSnapshot
    quality_issues: tuple[str, ...]


def normalize_books_snapshot(
    okx_snapshot: OKXBookSnapshot,
    *,
    instrument_id: str,
    venue: str,
    source_id: str,
    source_version: int = 1,
    ingested_at: datetime,
) -> NormalizedBook:
    """Normalize a parsed OKX snapshot to a canonical record.

    Detects (but does not drop) crossed books and empty sides, and
    reports them as quality issues on the result.
    """
    ingested = require_utc(ingested_at)
    snapshot_time = require_utc(okx_snapshot.snapshot_time)
    snapshot = BookSnapshot(
        instrument_id=instrument_id,
        venue=venue,
        snapshot_time=snapshot_time,
        available_at=snapshot_time,
        ingested_at=ingested,
        seq_id=okx_snapshot.seq_id,
        asks=tuple(
            BookLevel(price=level.price, size=level.size, order_count=level.order_count)
            for level in okx_snapshot.asks
        ),
        bids=tuple(
            BookLevel(price=level.price, size=level.size, order_count=level.order_count)
            for level in okx_snapshot.bids
        ),
        source_id=source_id,
        source_version=source_version,
    )
    issues: list[str] = []
    if not snapshot.bids:
        issues.append("empty bid side")
    if not snapshot.asks:
        issues.append("empty ask side")
    if (
        snapshot.best_bid is not None
        and snapshot.best_ask is not None
        and snapshot.best_bid >= snapshot.best_ask
    ):
        issues.append(
            f"crossed book: best bid {snapshot.best_bid} >= "
            f"best ask {snapshot.best_ask}"
        )
    return NormalizedBook(snapshot=snapshot, quality_issues=tuple(issues))
