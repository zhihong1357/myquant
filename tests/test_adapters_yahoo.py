"""Tests for the Yahoo Finance chart adapter.

All tests run offline against frozen fixtures; no test touches the network.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, date, datetime

import pytest

from myquant.adapters.yahoo import (
    YahooError,
    chart_to_observations,
    fetch_chart,
    parse_chart_response,
)


def _ts(year: int, month: int, day: int) -> int:
    """09:30 ET market-open timestamp, as Yahoo reports daily bars."""
    return int(datetime(year, month, day, 14, 30, tzinfo=UTC).timestamp())


# Frozen Yahoo chart response: three bars, one null close in the middle.
FIXTURE = {
    "chart": {
        "result": [
            {
                "meta": {
                    "currency": "USD",
                    "symbol": "^GSPC",
                    "exchangeName": "SNP",
                    "instrumentType": "INDEX",
                    "longName": "S&P 500",
                    "regularMarketPrice": 7340.53,
                },
                "timestamp": [_ts(2026, 11, 16), _ts(2026, 11, 17), _ts(2026, 11, 18)],
                "indicators": {
                    "quote": [
                        {
                            "close": [7340.53, None, 7335.21],
                            "volume": [1000, 1100, 1200],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}

FIXTURE_BYTES = json.dumps(FIXTURE).encode("utf-8")


def test_parse_returns_bars_missing_count_and_long_name() -> None:
    parsed = parse_chart_response(FIXTURE_BYTES, symbol="^GSPC")
    assert parsed.symbol == "^GSPC"
    assert parsed.long_name == "S&P 500"
    assert parsed.missing_count == 1
    assert [(b.trading_date, b.close) for b in parsed.bars] == [
        (date(2026, 11, 16), 7340.53),
        (date(2026, 11, 18), 7335.21),
    ]


def test_parse_rejects_chart_error() -> None:
    payload = json.dumps(
        {
            "chart": {
                "result": None,
                "error": {
                    "code": "Not Found",
                    "description": "No data found, symbol may be delisted",
                },
            }
        }
    ).encode("utf-8")
    with pytest.raises(YahooError, match="No data found"):
        parse_chart_response(payload, symbol="^TYVIX")


def test_parse_rejects_meta_symbol_mismatch() -> None:
    document = json.loads(FIXTURE_BYTES)
    document["chart"]["result"][0]["meta"]["symbol"] = "^DJI"
    with pytest.raises(YahooError, match="meta symbol"):
        parse_chart_response(json.dumps(document).encode(), symbol="^GSPC")


def test_parse_rejects_empty_result() -> None:
    payload = json.dumps({"chart": {"result": [], "error": None}}).encode("utf-8")
    with pytest.raises(YahooError, match="exactly one result"):
        parse_chart_response(payload, symbol="^GSPC")


def test_parse_rejects_missing_chart_object() -> None:
    with pytest.raises(YahooError, match="missing 'chart'"):
        parse_chart_response(b"{}", symbol="^GSPC")


def test_parse_rejects_non_json_payload() -> None:
    with pytest.raises(YahooError, match="not JSON"):
        parse_chart_response(b"<!DOCTYPE html>", symbol="^GSPC")


def test_parse_rejects_non_increasing_timestamps() -> None:
    document = json.loads(FIXTURE_BYTES)
    document["chart"]["result"][0]["timestamp"] = [
        _ts(2026, 11, 17),
        _ts(2026, 11, 16),
        _ts(2026, 11, 18),
    ]
    with pytest.raises(YahooError, match="not strictly increasing"):
        parse_chart_response(json.dumps(document).encode(), symbol="^GSPC")


def test_parse_rejects_length_mismatch() -> None:
    document = json.loads(FIXTURE_BYTES)
    document["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [7340.53]
    with pytest.raises(YahooError, match="timestamps but"):
        parse_chart_response(json.dumps(document).encode(), symbol="^GSPC")


def test_parse_rejects_non_finite_close() -> None:
    document = json.loads(FIXTURE_BYTES)
    document["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [
        float("inf"),
        None,
        7335.21,
    ]
    with pytest.raises(YahooError, match="non-finite close"):
        parse_chart_response(json.dumps(document).encode(), symbol="^GSPC")


def test_parse_rejects_all_null_closes() -> None:
    document = json.loads(FIXTURE_BYTES)
    document["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [
        None,
        None,
        None,
    ]
    with pytest.raises(YahooError, match="no bars with a close"):
        parse_chart_response(json.dumps(document).encode(), symbol="^GSPC")


def test_fetch_chart_uses_transport_and_builds_url() -> None:
    seen: list[str] = []

    def transport(url: str) -> bytes:
        seen.append(url)
        return FIXTURE_BYTES

    chart = fetch_chart(
        "^GSPC",
        start=date(2026, 11, 16),
        end=date(2026, 11, 18),
        transport=transport,
    )
    assert chart.symbol == "^GSPC"
    assert chart.long_name == "S&P 500"
    assert len(chart.bars) == 2
    assert chart.missing_count == 1
    assert chart.payload == FIXTURE_BYTES
    assert seen == [chart.url]
    assert "%5EGSPC" in chart.url
    assert "interval=1d" in chart.url
    period1 = int(datetime(2026, 11, 16, tzinfo=UTC).timestamp())
    period2 = int(datetime(2026, 11, 19, tzinfo=UTC).timestamp())
    assert f"period1={period1}" in chart.url
    assert f"period2={period2}" in chart.url


def test_fetch_chart_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="end must not precede start"):
        fetch_chart(
            "^GSPC",
            start=date(2026, 11, 18),
            end=date(2026, 11, 16),
            transport=lambda url: FIXTURE_BYTES,
        )


def test_fetch_chart_retries_429_then_succeeds() -> None:
    calls = {"count": 0}

    def transport(url: str) -> bytes:
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return FIXTURE_BYTES

    chart = fetch_chart(
        "^GSPC",
        start=date(2026, 11, 16),
        end=date(2026, 11, 18),
        transport=transport,
    )
    assert len(chart.bars) == 2
    assert calls["count"] == 2


def test_fetch_chart_retries_timeout_then_succeeds() -> None:
    calls = {"count": 0}

    def transport(url: str) -> bytes:
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("The read operation timed out")
        return FIXTURE_BYTES

    chart = fetch_chart(
        "^GSPC",
        start=date(2026, 11, 16),
        end=date(2026, 11, 18),
        transport=transport,
    )
    assert len(chart.bars) == 2
    assert calls["count"] == 2


def test_fetch_chart_raises_after_max_retries() -> None:
    def transport(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)

    with pytest.raises(YahooError, match="HTTP 503"):
        fetch_chart(
            "^GSPC",
            start=date(2026, 11, 16),
            end=date(2026, 11, 18),
            max_retries=1,
            transport=transport,
        )


def test_chart_to_observations_uses_close_convention() -> None:
    chart = fetch_chart(
        "^GSPC",
        start=date(2026, 11, 16),
        end=date(2026, 11, 18),
        transport=lambda url: FIXTURE_BYTES,
    )
    observations = chart_to_observations(
        chart,
        instrument_id="index:sp500",
        venue="yahoo-finance",
        source_id="yahoo-finance",
        source_version=1,
        ingested_at=datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
        unit="points",
    )
    assert len(observations) == 2
    first = observations[0]
    assert first.source_id == "yahoo-finance"
    assert first.venue == "yahoo-finance"
    assert first.instrument_id == "index:sp500"
    assert first.field == "close"
    assert first.event_time == datetime(2026, 11, 16, 21, 0, tzinfo=UTC)
    assert first.available_at == first.event_time
    assert first.value == 7340.53
    assert first.unit == "points"
