"""Tests for the Hyperliquid public REST adapter.

All tests run offline against frozen fixtures; no test touches the network.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime

import pytest

from myquant.adapters.hyperliquid import (
    HyperliquidAPIError,
    candles_to_observations,
    fetch_candles,
    parse_candles_response,
)

# Frozen candleSnapshot response: oldest first, as the API returns it.
# The 2023-01-01 bar is a zero-trade backfilled mark; the 2026-11-18 bar
# is still forming at the fixture's as-of time.
FIXTURE = [
    {
        "t": 1672531200000,
        "T": 1672617599999,
        "s": "BTC",
        "i": "1d",
        "o": "16500.0",
        "c": "16600.0",
        "h": "16700.0",
        "l": "16400.0",
        "v": "0.0",
        "n": 0,
    },
    {
        "t": 1794528000000,
        "T": 1794614399999,
        "s": "BTC",
        "i": "1d",
        "o": "99000.0",
        "c": "98000.0",
        "h": "99500.0",
        "l": "97500.0",
        "v": "1234.5",
        "n": 98765,
    },
    {
        "t": 1794614400000,
        "T": 1794700799999,
        "s": "BTC",
        "i": "1d",
        "o": "98000.0",
        "c": "98500.0",
        "h": "99000.0",
        "l": "97800.0",
        "v": "999.0",
        "n": 54321,
    },
]

FIXTURE_BYTES = json.dumps(FIXTURE).encode("utf-8")
AS_OF = datetime(2026, 11, 18, 1, 30, tzinfo=UTC)


def _payload(rows: list) -> bytes:
    return json.dumps(rows).encode("utf-8")


def _row(**overrides: object) -> dict:
    row: dict = {
        "t": 1794528000000,
        "T": 1794614399999,
        "s": "BTC",
        "i": "1d",
        "o": "99000.0",
        "c": "98000.0",
        "h": "99500.0",
        "l": "97500.0",
        "v": "1234.5",
        "n": 98765,
    }
    row.update(overrides)
    return row


def test_parse_returns_ascending_candles() -> None:
    candles = parse_candles_response(FIXTURE_BYTES, coin="BTC", interval="1d")
    assert [c.open_time for c in candles] == [
        datetime(2023, 1, 1, tzinfo=UTC),
        datetime(2026, 11, 13, tzinfo=UTC),
        datetime(2026, 11, 14, tzinfo=UTC),
    ]
    assert candles[1].close == 98000.0
    assert candles[1].trade_count == 98765
    assert candles[1].close_time == datetime(2026, 11, 14, tzinfo=UTC)
    assert candles[0].trade_count == 0


def test_parse_rejects_non_list() -> None:
    with pytest.raises(HyperliquidAPIError, match="not a list"):
        parse_candles_response(b'{"error": "bad"}', coin="BTC", interval="1d")


def test_parse_rejects_wrong_coin() -> None:
    with pytest.raises(HyperliquidAPIError, match="coin mismatch"):
        parse_candles_response(_payload([_row(s="ETH")]), coin="BTC", interval="1d")


def test_parse_rejects_wrong_interval() -> None:
    with pytest.raises(HyperliquidAPIError, match="interval mismatch"):
        parse_candles_response(
            _payload([_row(i="1h")]), coin="BTC", interval="1d"
        )


def test_parse_rejects_unsupported_interval() -> None:
    # An unsupported interval is a caller error (ValueError), mirroring
    # the OKX adapter's treatment of unknown bars.
    with pytest.raises(ValueError, match="unsupported Hyperliquid interval"):
        parse_candles_response(_payload([_row()]), coin="BTC", interval="1h")


def test_parse_rejects_inconsistent_ohlc() -> None:
    # High below close.
    with pytest.raises(HyperliquidAPIError, match="high is below"):
        parse_candles_response(
            _payload([_row(h="97000.0")]), coin="BTC", interval="1d"
        )


def test_parse_rejects_bad_close_end() -> None:
    with pytest.raises(HyperliquidAPIError, match="close end"):
        parse_candles_response(
            _payload([_row(T=1794614400000)]), coin="BTC", interval="1d"
        )


def test_parse_rejects_duplicate_timestamp() -> None:
    with pytest.raises(HyperliquidAPIError, match="duplicate"):
        parse_candles_response(
            _payload([_row(), _row()]), coin="BTC", interval="1d"
        )


def test_parse_rejects_missing_field() -> None:
    row = _row()
    del row["n"]
    with pytest.raises(HyperliquidAPIError, match="missing fields"):
        parse_candles_response(_payload([row]), coin="BTC", interval="1d")


def test_fetch_excludes_forming_and_zero_trade() -> None:
    def transport(_body: bytes) -> bytes:
        return FIXTURE_BYTES

    result = fetch_candles(
        "BTC",
        "1d",
        start=datetime(2023, 1, 1, tzinfo=UTC),
        end=datetime(2026, 11, 19, tzinfo=UTC),
        as_of=datetime(2026, 11, 14, 12, 0, tzinfo=UTC),
        delay_seconds=0,
        transport=transport,
    )
    # Only the 2026-11-13 bar is closed and traded at the as-of time.
    assert [c.open_time for c in result.candles] == [
        datetime(2026, 11, 13, tzinfo=UTC)
    ]
    assert result.excluded_zero_trade == 1
    assert result.excluded_unclosed == 1
    assert len(result.pages) >= 1
    assert "candleSnapshot" in result.pages[0].request_body


def test_fetch_pages_across_windows_and_dedups() -> None:
    seen_bodies: list[str] = []

    def transport(body: bytes) -> bytes:
        seen_bodies.append(body.decode("utf-8"))
        return _payload([_row()])

    result = fetch_candles(
        "BTC",
        "1d",
        start=datetime(2023, 1, 1, tzinfo=UTC),
        end=datetime(2026, 11, 18, tzinfo=UTC),
        as_of=datetime(2026, 11, 18, tzinfo=UTC),
        delay_seconds=0,
        transport=transport,
    )
    # 365-day windows over ~3.9 years: 4 requests, one unique candle.
    assert len(seen_bodies) == 4
    assert len(result.candles) == 1
    assert result.pages[0].request_body == seen_bodies[0]


def test_fetch_retries_rate_limit_then_succeeds() -> None:
    attempts = {"count": 0}

    def transport(_body: bytes) -> bytes:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.HTTPError(
                "https://api.hyperliquid.xyz/info",
                429,
                "Too Many Requests",
                {},
                None,
            )
        return _payload([_row()])

    result = fetch_candles(
        "BTC",
        "1d",
        start=datetime(2026, 11, 13, tzinfo=UTC),
        end=datetime(2026, 11, 14, tzinfo=UTC),
        as_of=datetime(2026, 11, 18, tzinfo=UTC),
        delay_seconds=0,
        transport=transport,
    )
    assert attempts["count"] == 2
    assert len(result.candles) == 1


def test_fetch_rejects_bad_window() -> None:
    with pytest.raises(ValueError, match="end must be after start"):
        fetch_candles(
            "BTC",
            "1d",
            start=datetime(2026, 11, 14, tzinfo=UTC),
            end=datetime(2026, 11, 13, tzinfo=UTC),
            transport=lambda _body: b"[]",
        )


def test_candles_to_observations_rejects_unclosed() -> None:
    candles = parse_candles_response(FIXTURE_BYTES, coin="BTC", interval="1d")
    forming = candles[-1]
    assert forming.open_time == datetime(2026, 11, 14, tzinfo=UTC)
    with pytest.raises(ValueError, match="unclosed"):
        candles_to_observations(
            [forming],
            instrument_id="crypto:btc-usdt-perp",
            venue="hyperliquid",
            source_id="hyperliquid-public",
            source_version=1,
            ingested_at=AS_OF,
            as_of=datetime(2026, 11, 14, 12, 0, tzinfo=UTC),
        )


def test_candles_to_observations_rejects_zero_trade() -> None:
    candles = parse_candles_response(FIXTURE_BYTES, coin="BTC", interval="1d")
    with pytest.raises(ValueError, match="zero-trade"):
        candles_to_observations(
            [candles[0]],
            instrument_id="crypto:btc-usdt-perp",
            venue="hyperliquid",
            source_id="hyperliquid-public",
            source_version=1,
            ingested_at=AS_OF,
            as_of=AS_OF,
        )


def test_candles_to_observations_timestamps() -> None:
    candles = parse_candles_response(FIXTURE_BYTES, coin="BTC", interval="1d")
    observations = candles_to_observations(
        [candles[1]],
        instrument_id="crypto:btc-usdt-perp",
        venue="hyperliquid",
        source_id="hyperliquid-public",
        source_version=1,
        ingested_at=AS_OF,
        as_of=AS_OF,
    )
    assert len(observations) == 5
    close = next(item for item in observations if item.field == "close")
    assert close.event_time == datetime(2026, 11, 13, tzinfo=UTC)
    assert close.available_at == datetime(2026, 11, 14, tzinfo=UTC)
    assert close.value == 98000.0
    assert close.unit == "USD"
    volume = next(item for item in observations if item.field == "volume")
    assert volume.unit == "BTC"
