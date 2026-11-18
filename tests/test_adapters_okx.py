"""Tests for the OKX public REST adapter.

All tests run offline against frozen fixtures; no test touches the network.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime

import pytest

from myquant.adapters.okx import (
    OKXAPIError,
    candles_to_observations,
    fetch_history,
    parse_candles_response,
)

# Frozen OKX response: newest first, as the API returns it. The newest bar
# (2026-11-17T16:00Z) is still forming; the older two are confirmed.
FIXTURE = {
    "code": "0",
    "msg": "",
    "data": [
        ["1794931200000", "90000", "91000", "89000", "90500", "100", "1.1", "99500", "0"],
        ["1794844800000", "88000", "90500", "87000", "90000", "120", "1.3", "117000", "1"],
        ["1794758400000", "86000", "88500", "85000", "88000", "110", "1.25", "110000", "1"],
    ],
}

FIXTURE_BYTES = json.dumps(FIXTURE).encode("utf-8")


def _payload(rows: list) -> bytes:
    return json.dumps({"code": "0", "msg": "", "data": rows}).encode("utf-8")


def test_parse_returns_ascending_confirmed_and_forming() -> None:
    candles = parse_candles_response(
        FIXTURE_BYTES,
        inst_id="BTC-USDT-SWAP",
        bar="1D",
    )
    assert [c.open_time for c in candles] == [
        datetime(2026, 11, 15, 16, 0, tzinfo=UTC),
        datetime(2026, 11, 16, 16, 0, tzinfo=UTC),
        datetime(2026, 11, 17, 16, 0, tzinfo=UTC),
    ]
    assert candles[0].close == 88000.0
    assert candles[0].confirmed is True
    assert candles[-1].confirmed is False
    assert candles[0].close_time == datetime(2026, 11, 16, 16, 0, tzinfo=UTC)
    assert candles[0].volume_currency == 1.25


def test_parse_rejects_error_code() -> None:
    payload = json.dumps({"code": "50001", "msg": "rate limited", "data": []})
    with pytest.raises(OKXAPIError, match="50001"):
        parse_candles_response(payload.encode(), inst_id="BTC-USDT-SWAP", bar="1D")


def test_parse_rejects_short_row() -> None:
    with pytest.raises(OKXAPIError, match="9 elements"):
        parse_candles_response(
            _payload([["1794835200000", "88000"]]),
            inst_id="BTC-USDT-SWAP",
            bar="1D",
        )


def test_parse_rejects_inconsistent_ohlc() -> None:
    # High below close.
    row = ["1794835200000", "88000", "87000", "86000", "88000", "1", "1", "1", "1"]
    with pytest.raises(OKXAPIError, match="high is below"):
        parse_candles_response(_payload([row]), inst_id="BTC-USDT-SWAP", bar="1D")


def test_parse_rejects_bad_confirm_flag() -> None:
    row = ["1794835200000", "88000", "89000", "87000", "88000", "1", "1", "1", "2"]
    with pytest.raises(OKXAPIError, match="confirm flag"):
        parse_candles_response(_payload([row]), inst_id="BTC-USDT-SWAP", bar="1D")


def test_parse_rejects_non_newest_first_order() -> None:
    rows = list(reversed(FIXTURE["data"]))
    with pytest.raises(OKXAPIError, match="newest-first"):
        parse_candles_response(_payload(rows), inst_id="BTC-USDT-SWAP", bar="1D")


def test_parse_rejects_duplicate_timestamp() -> None:
    rows = [FIXTURE["data"][1], FIXTURE["data"][1]]
    with pytest.raises(OKXAPIError, match="duplicate"):
        parse_candles_response(_payload(rows), inst_id="BTC-USDT-SWAP", bar="1D")


def test_parse_rejects_unknown_bar() -> None:
    with pytest.raises(ValueError, match="unsupported OKX bar"):
        parse_candles_response(FIXTURE_BYTES, inst_id="BTC-USDT-SWAP", bar="3D")


def test_fetch_history_pages_backwards_and_filters() -> None:
    # Page 1 (newest): bars for Nov 17 (forming) and Nov 16 (confirmed).
    # Page 2 (older): bar for Nov 15 (confirmed).
    page1 = _payload(FIXTURE["data"][:2])
    page2 = _payload(FIXTURE["data"][2:])
    seen_urls: list[str] = []

    def fake_transport(url: str) -> bytes:
        seen_urls.append(url)
        if "after=1794844800000" in url:
            return page2
        return page1

    result = fetch_history(
        "BTC-USDT-SWAP",
        "1D",
        start=datetime(2026, 11, 15, 16, 0, tzinfo=UTC),
        end=datetime(2026, 11, 18, 16, 0, tzinfo=UTC),
        delay_seconds=0,
        transport=fake_transport,
    )
    # Only confirmed bars inside [start, end): Nov 15 and Nov 16.
    assert [c.open_time.day for c in result.candles] == [15, 16]
    assert len(result.pages) == 2
    assert "after=1794844800000" in seen_urls[1]


def test_fetch_history_stops_at_empty_page() -> None:
    calls: list[str] = []

    def fake_transport(url: str) -> bytes:
        calls.append(url)
        return _payload([])

    result = fetch_history(
        "BTC-USDT-SWAP",
        "1D",
        start=datetime(2020, 1, 1, tzinfo=UTC),
        end=datetime(2020, 1, 10, tzinfo=UTC),
        delay_seconds=0,
        transport=fake_transport,
    )
    assert result.candles == ()
    assert len(calls) == 1


def test_fetch_history_retries_rate_limits() -> None:
    attempts: list[str] = []

    def flaky_transport(url: str) -> bytes:
        attempts.append(url)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return _payload([])

    result = fetch_history(
        "BTC-USDT-SWAP",
        "1D",
        start=datetime(2020, 1, 1, tzinfo=UTC),
        end=datetime(2020, 1, 10, tzinfo=UTC),
        delay_seconds=0,
        transport=flaky_transport,
    )
    assert result.candles == ()
    assert len(attempts) == 3


def test_fetch_history_rejects_non_retryable_error() -> None:
    def bad_transport(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)

    with pytest.raises(OKXAPIError, match="HTTP 400"):
        fetch_history(
            "BTC-USDT-SWAP",
            "1D",
            start=datetime(2020, 1, 1, tzinfo=UTC),
            end=datetime(2020, 1, 10, tzinfo=UTC),
            delay_seconds=0,
            transport=bad_transport,
        )


def test_candles_to_observations_uses_close_as_available() -> None:
    candles = parse_candles_response(
        FIXTURE_BYTES,
        inst_id="BTC-USDT-SWAP",
        bar="1D",
    )
    confirmed = [c for c in candles if c.confirmed]
    observations = candles_to_observations(
        confirmed,
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        source_version=1,
        ingested_at=datetime(2026, 11, 18, 1, 0, tzinfo=UTC),
    )
    assert len(observations) == 2 * 5  # two bars x open/high/low/close/volume
    close = next(
        item
        for item in observations
        if item.field == "close"
        and item.event_time == datetime(2026, 11, 16, 16, 0, tzinfo=UTC)
    )
    assert close.value == 90000.0
    assert close.available_at == datetime(2026, 11, 17, 16, 0, tzinfo=UTC)
    assert close.unit == "USDT"
    volume = next(item for item in observations if item.field == "volume")
    assert volume.unit == "contracts"


def test_candles_to_observations_rejects_forming_bar() -> None:
    candles = parse_candles_response(
        FIXTURE_BYTES,
        inst_id="BTC-USDT-SWAP",
        bar="1D",
    )
    forming = [c for c in candles if not c.confirmed]
    with pytest.raises(ValueError, match="unconfirmed"):
        candles_to_observations(
            forming,
            instrument_id="crypto:btc-usdt-perp",
            venue="okx",
            source_id="okx-public",
            source_version=1,
            ingested_at=datetime(2026, 11, 18, 1, 0, tzinfo=UTC),
        )
