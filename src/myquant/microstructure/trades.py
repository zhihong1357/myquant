"""Canonical trade records: OKX trades normalized to the research schema.

A normalized :class:`Trade` carries the three clocks the architecture
requires — ``event_time`` (match time), ``available_at`` (when the
trade became knowable) and ``ingested_at`` (when MyQuant pulled it) —
plus the venue-neutral instrument id and the source identity.

Availability convention: a trade prints on the public trades feed at
match time, so ``available_at == event_time``. Network latency between
the exchange and the feed consumer is second-order and is not modelled;
the ingestion delay is visible as ``ingested_at - available_at``.

``side`` is the taker (aggressor) side of the match as reported by the
exchange. It is not a statement about trader identity or intent: public
trade data cannot show who traded or why.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from myquant.adapters.okx_microstructure import OKXTrade
from myquant.contracts import StrictContract, require_utc


class Trade(StrictContract):
    """One normalized trade."""

    schema_version: int = Field(default=1, ge=1)
    instrument_id: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    trade_id: int = Field(ge=0)
    price: float = Field(gt=0, allow_inf_nan=False)
    size: float = Field(gt=0, allow_inf_nan=False)
    aggressor_side: Literal["buy", "sell"]
    source_id: str = Field(min_length=1)
    source_version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_times(self) -> Trade:
        event = require_utc(self.event_time)
        available = require_utc(self.available_at)
        ingested = require_utc(self.ingested_at)
        if ingested < available:
            raise ValueError("ingested_at cannot precede available_at")
        object.__setattr__(self, "event_time", event)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "ingested_at", ingested)
        return self


@dataclass(frozen=True)
class TradeNormalizationReport:
    """Counts for one normalization run. Nothing is dropped silently."""

    received: int
    accepted: int
    parse_rejected: int
    duplicate_trade_ids: int
    non_monotonic: int
    first_trade_id: int | None
    last_trade_id: int | None
    first_event_time: datetime | None
    last_event_time: datetime | None


@dataclass(frozen=True)
class NormalizedTrades:
    """Normalized trades (ascending trade ID) plus the count report."""

    trades: tuple[Trade, ...]
    report: TradeNormalizationReport


def normalize_trades(
    okx_trades: tuple[OKXTrade, ...] | list[OKXTrade],
    *,
    parse_rejected: int = 0,
    instrument_id: str,
    venue: str,
    source_id: str,
    source_version: int = 1,
    ingested_at: datetime,
) -> NormalizedTrades:
    """Normalize parsed OKX trades to canonical records.

    Sorts by trade ID, drops duplicates (keeping the first occurrence),
    and drops rows whose event time decreases along trade-ID order —
    trade IDs are assigned sequentially at match time, so a decrease
    means the batch is internally inconsistent. Every dropped row is
    counted in the report; nothing is discarded silently.
    """
    ingested = require_utc(ingested_at)
    ordered = sorted(okx_trades, key=lambda item: item.trade_id)
    seen: set[int] = set()
    trades: list[Trade] = []
    duplicates = 0
    non_monotonic = 0
    max_event_time: datetime | None = None
    for okx_trade in ordered:
        if okx_trade.trade_id in seen:
            duplicates += 1
            continue
        seen.add(okx_trade.trade_id)
        event_time = require_utc(okx_trade.event_time)
        if max_event_time is not None and event_time < max_event_time:
            non_monotonic += 1
            continue
        max_event_time = event_time
        trades.append(
            Trade(
                instrument_id=instrument_id,
                venue=venue,
                event_time=event_time,
                available_at=event_time,
                ingested_at=ingested,
                trade_id=okx_trade.trade_id,
                price=okx_trade.price,
                size=okx_trade.size,
                aggressor_side=okx_trade.side,
                source_id=source_id,
                source_version=source_version,
            )
        )
    report = TradeNormalizationReport(
        received=len(ordered),
        accepted=len(trades),
        parse_rejected=parse_rejected,
        duplicate_trade_ids=duplicates,
        non_monotonic=non_monotonic,
        first_trade_id=trades[0].trade_id if trades else None,
        last_trade_id=trades[-1].trade_id if trades else None,
        first_event_time=trades[0].event_time if trades else None,
        last_event_time=trades[-1].event_time if trades else None,
    )
    return NormalizedTrades(trades=tuple(trades), report=report)
