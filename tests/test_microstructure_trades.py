"""Tests for trade normalization. All offline, no network access."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from myquant.adapters.okx_microstructure import OKXTrade
from myquant.microstructure.trades import Trade, normalize_trades

INGESTED = datetime(2026, 11, 18, 7, 0, 0, tzinfo=UTC)


def _okx_trade(
    trade_id: int,
    second: int,
    side: str = "buy",
    price: float = 65000.0,
    size: float = 0.5,
) -> OKXTrade:
    return OKXTrade(
        instrument="BTC-USDT-SWAP",
        trade_id=trade_id,
        event_time=datetime(2026, 11, 18, 5, 0, second, tzinfo=UTC),
        price=price,
        size=size,
        side=side,  # type: ignore[arg-type]
    )


def test_normalize_maps_fields_and_sorts_by_trade_id() -> None:
    result = normalize_trades(
        [_okx_trade(102, 2, "sell", 64999.0, 0.2), _okx_trade(101, 1)],
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert [t.trade_id for t in result.trades] == [101, 102]
    first = result.trades[0]
    assert first.instrument_id == "crypto:btc-usdt-perp"
    assert first.venue == "okx"
    assert first.event_time == datetime(2026, 11, 18, 5, 0, 1, tzinfo=UTC)
    assert first.available_at == first.event_time
    assert first.ingested_at == INGESTED
    assert first.aggressor_side == "buy"
    assert first.source_id == "okx-public"
    assert first.source_version == 1
    assert result.report.received == 2
    assert result.report.accepted == 2
    assert result.report.first_trade_id == 101
    assert result.report.last_trade_id == 102


def test_normalize_counts_duplicates_and_keeps_first() -> None:
    first = _okx_trade(101, 1, "buy", 65000.0, 0.5)
    duplicate = _okx_trade(101, 1, "sell", 64999.0, 9.9)
    result = normalize_trades(
        [first, duplicate, _okx_trade(102, 2)],
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert [t.trade_id for t in result.trades] == [101, 102]
    assert result.trades[0].aggressor_side == "buy"
    assert result.trades[0].size == 0.5
    assert result.report.duplicate_trade_ids == 1
    assert result.report.accepted == 2


def test_normalize_counts_non_monotonic_event_times() -> None:
    # Trade 102 is timestamped before trade 101: inconsistent batch.
    result = normalize_trades(
        [
            _okx_trade(101, 5),
            _okx_trade(102, 3),
            _okx_trade(103, 7),
        ],
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert [t.trade_id for t in result.trades] == [101, 103]
    assert result.report.non_monotonic == 1
    assert result.report.accepted == 2


def test_normalize_accepts_same_millisecond_trades() -> None:
    result = normalize_trades(
        [_okx_trade(101, 1), _okx_trade(102, 1), _okx_trade(103, 1)],
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert result.report.accepted == 3
    assert result.report.non_monotonic == 0


def test_normalize_empty_input() -> None:
    result = normalize_trades(
        [],
        parse_rejected=4,
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert result.trades == ()
    assert result.report.received == 0
    assert result.report.accepted == 0
    assert result.report.parse_rejected == 4
    assert result.report.first_trade_id is None
    assert result.report.last_event_time is None


def test_trade_rejects_ingested_before_available() -> None:
    with pytest.raises(ValueError, match="ingested_at cannot precede"):
        Trade(
            instrument_id="crypto:btc-usdt-perp",
            venue="okx",
            event_time=datetime(2026, 11, 18, 5, 0, 1, tzinfo=UTC),
            available_at=datetime(2026, 11, 18, 5, 0, 1, tzinfo=UTC),
            ingested_at=datetime(2026, 11, 18, 4, 0, 0, tzinfo=UTC),
            trade_id=1,
            price=65000.0,
            size=0.5,
            aggressor_side="buy",
            source_id="okx-public",
        )
