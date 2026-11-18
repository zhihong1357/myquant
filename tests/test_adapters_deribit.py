"""Offline tests for the Deribit public adapter (no network access)."""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime

import pytest

from myquant.adapters.deribit import (
    DeribitAPIError,
    DeribitInstrument,
    DVOLPoint,
    dvol_to_observations,
    fetch_instruments,
    fetch_volatility_index,
    parse_instruments_response,
    parse_volatility_response,
)


def _instruments_payload(rows: list[dict]) -> bytes:
    return json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": rows}
    ).encode("utf-8")


def _instrument_row(
    name: str,
    *,
    expiration_ms: int,
    option_type: str = "call",
    strike: float = 100_000.0,
) -> dict:
    return {
        "instrument_name": name,
        "base_currency": "BTC",
        "kind": "option",
        "option_type": option_type,
        "strike": strike,
        "expiration_timestamp": expiration_ms,
    }


def _volatility_payload(rows: list[list]) -> bytes:
    return json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": {"data": rows}}
    ).encode("utf-8")


class TestParseInstruments:
    def test_parses_and_sorts_by_expiry_then_name(self) -> None:
        payload = _instruments_payload(
            [
                _instrument_row("BTC-26DEC25-100000-C", expiration_ms=1766736000000),
                _instrument_row("BTC-27NOV26-90000-P", expiration_ms=1795766400000),
                _instrument_row("BTC-26DEC25-90000-P", expiration_ms=1766736000000),
            ]
        )
        parsed = parse_instruments_response(payload)
        assert [item.instrument_name for item in parsed] == [
            "BTC-26DEC25-100000-C",
            "BTC-26DEC25-90000-P",
            "BTC-27NOV26-90000-P",
        ]
        assert parsed[0].expiration_timestamp == datetime(
            2025, 12, 26, 8, 0, tzinfo=UTC
        )
        assert parsed[0].option_type == "call"
        assert parsed[0].strike == 100_000.0
        assert parsed[0].base_currency == "BTC"

    def test_parses_a_realistic_live_row(self) -> None:
        # A row shaped like the live get_instruments response (observed
        # 2026-11-18): no top-level "currency" field; the underlying is
        # "base_currency". Extra fields are ignored.
        payload = _instruments_payload(
            [
                {
                    "state": "open",
                    "price_index": "btc_usd",
                    "kind": "option",
                    "instrument_name": "BTC-18NOV26-52000-C",
                    "maker_commission": 0.0003,
                    "taker_commission": 0.0003,
                    "instrument_type": "reversed",
                    "expiration_timestamp": 1794988800000,
                    "instrument_id": 734193,
                    "settlement_currency": "BTC",
                    "settlement_period": "day",
                    "base_currency": "BTC",
                    "quote_currency": "BTC",
                    "strike": 52000.0,
                    "option_type": "call",
                    "is_active": True,
                    "contract_size": 1.0,
                }
            ]
        )
        parsed = parse_instruments_response(payload)
        assert len(parsed) == 1
        assert parsed[0].instrument_name == "BTC-18NOV26-52000-C"
        assert parsed[0].base_currency == "BTC"
        assert parsed[0].expiration_timestamp == datetime(
            2026, 11, 18, 8, 0, tzinfo=UTC
        )

    def test_error_payload_raises(self) -> None:
        payload = json.dumps(
            {"jsonrpc": "2.0", "error": {"code": 11001, "message": "bad currency"}}
        ).encode("utf-8")
        with pytest.raises(DeribitAPIError, match="API error"):
            parse_instruments_response(payload)

    def test_missing_expiration_raises(self) -> None:
        row = _instrument_row("BTC-26DEC25-100000-C", expiration_ms=1766736000000)
        del row["expiration_timestamp"]
        with pytest.raises(DeribitAPIError):
            parse_instruments_response(_instruments_payload([row]))

    def test_invalid_option_type_raises(self) -> None:
        row = _instrument_row(
            "BTC-26DEC25-100000-C",
            expiration_ms=1766736000000,
            option_type="straddle",
        )
        with pytest.raises(DeribitAPIError):
            parse_instruments_response(_instruments_payload([row]))

    def test_duplicate_instrument_raises(self) -> None:
        row = _instrument_row("BTC-26DEC25-100000-C", expiration_ms=1766736000000)
        with pytest.raises(DeribitAPIError, match="duplicate"):
            parse_instruments_response(_instruments_payload([row, row]))

    def test_non_json_raises(self) -> None:
        with pytest.raises(DeribitAPIError, match="not valid JSON"):
            parse_instruments_response(b"not json")


class TestParseVolatility:
    def test_parses_and_sorts_oldest_first(self) -> None:
        payload = _volatility_payload(
            [
                [1763424000000, 56.26, 57.45, 55.64, 56.24],
                [1616544000000, 84.8, 95.94, 80.52, 95.04],
            ]
        )
        parsed = parse_volatility_response(
            payload, index_name="btc_vol", currency="BTC"
        )
        assert len(parsed) == 2
        assert parsed[0].timestamp == datetime(2021, 3, 24, tzinfo=UTC)
        assert parsed[0].close == 95.04
        assert parsed[1].timestamp == datetime(2025, 11, 18, tzinfo=UTC)
        assert parsed[0].index_name == "btc_vol"
        assert parsed[0].currency == "BTC"

    def test_missing_currency_error_raises(self) -> None:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "error": {"code": 10001, "message": "value required, param currency"},
            }
        ).encode("utf-8")
        with pytest.raises(DeribitAPIError, match="API error"):
            parse_volatility_response(payload, index_name="btc_vol", currency="BTC")

    def test_bad_row_length_raises(self) -> None:
        payload = _volatility_payload([[1616544000000, 84.8, 95.94]])
        with pytest.raises(DeribitAPIError, match="5 elements"):
            parse_volatility_response(payload, index_name="btc_vol", currency="BTC")

    def test_inconsistent_high_raises(self) -> None:
        payload = _volatility_payload([[1616544000000, 84.8, 50.0, 80.52, 95.04]])
        with pytest.raises(DeribitAPIError, match="validation"):
            parse_volatility_response(payload, index_name="btc_vol", currency="BTC")

    def test_duplicate_timestamp_raises(self) -> None:
        row = [1616544000000, 84.8, 95.94, 80.52, 95.04]
        payload = _volatility_payload([row, row])
        with pytest.raises(DeribitAPIError, match="duplicate"):
            parse_volatility_response(payload, index_name="btc_vol", currency="BTC")


class TestFetchInstruments:
    def test_url_carries_currency_kind_and_expired_flag(self) -> None:
        seen: list[str] = []

        def transport(url: str) -> bytes:
            seen.append(url)
            return _instruments_payload(
                [_instrument_row("BTC-27NOV26-100000-C", expiration_ms=1795766400000)]
            )

        fetched = fetch_instruments("BTC", expired=True, transport=transport)
        assert len(fetched.instruments) == 1
        assert "currency=BTC" in seen[0]
        assert "kind=option" in seen[0]
        assert "expired=true" in seen[0]
        assert fetched.pages[0].url == seen[0]

    def test_http_400_raises_without_retry(self) -> None:
        calls = {"count": 0}

        def transport(url: str) -> bytes:
            calls["count"] += 1
            raise urllib.error.HTTPError(url, 400, "bad request", {}, None)

        with pytest.raises(DeribitAPIError, match="HTTP 400"):
            fetch_instruments("BTC", transport=transport)
        assert calls["count"] == 1

    def test_http_429_retries_then_succeeds(self) -> None:
        calls = {"count": 0}

        def transport(url: str) -> bytes:
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)
            return _instruments_payload(
                [_instrument_row("BTC-27NOV26-100000-C", expiration_ms=1795766400000)]
            )

        fetched = fetch_instruments("BTC", transport=transport)
        assert len(fetched.instruments) == 1
        assert calls["count"] == 2


class TestFetchVolatility:
    def test_url_carries_currency_and_index_name(self) -> None:
        seen: list[str] = []

        def transport(url: str) -> bytes:
            seen.append(url)
            return _volatility_payload(
                [[1616544000000, 84.8, 95.94, 80.52, 95.04]]
            )

        fetched = fetch_volatility_index(
            "BTC",
            start=datetime(2021, 3, 24, tzinfo=UTC),
            end=datetime(2021, 4, 1, tzinfo=UTC),
            delay_seconds=0.0,
            transport=transport,
        )
        assert len(fetched.points) == 1
        assert "currency=BTC" in seen[0]
        assert "index_name=btc_vol" in seen[0]
        assert "resolution=86400" in seen[0]

    def test_unknown_currency_raises(self) -> None:
        with pytest.raises(ValueError, match="no DVOL index"):
            fetch_volatility_index(
                "SOL",
                start=datetime(2021, 3, 24, tzinfo=UTC),
                end=datetime(2021, 4, 1, tzinfo=UTC),
                transport=lambda url: _volatility_payload([]),
            )

    def test_points_outside_window_are_dropped(self) -> None:
        def transport(url: str) -> bytes:
            return _volatility_payload(
                [
                    [1616544000000, 84.8, 95.94, 80.52, 95.04],
                    [1616630400000, 90.0, 91.0, 89.0, 90.5],
                ]
            )

        fetched = fetch_volatility_index(
            "BTC",
            start=datetime(2021, 3, 24, tzinfo=UTC),
            end=datetime(2021, 3, 25, tzinfo=UTC),
            delay_seconds=0.0,
            transport=transport,
        )
        assert [point.timestamp for point in fetched.points] == [
            datetime(2021, 3, 24, tzinfo=UTC)
        ]


class TestDVOLToObservations:
    def test_close_observation_timestamps(self) -> None:
        points = (
            DVOLPoint(
                index_name="btc_vol",
                currency="BTC",
                timestamp=datetime(2021, 3, 24, tzinfo=UTC),
                open=84.8,
                high=95.94,
                low=80.52,
                close=95.04,
            ),
        )
        ingested = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
        observations = dvol_to_observations(
            points,
            instrument_id="index:btc-dvol",
            venue="deribit",
            source_id="deribit",
            source_version=1,
            ingested_at=ingested,
        )
        assert len(observations) == 1
        observation = observations[0]
        assert observation.field == "close"
        assert observation.value == 95.04
        assert observation.unit == "percent"
        assert observation.event_time == datetime(2021, 3, 24, tzinfo=UTC)
        # The daily close is knowable at the next day's 00:00 UTC.
        assert observation.available_at == datetime(2021, 3, 25, tzinfo=UTC)
        assert observation.ingested_at == ingested


class TestDeribitInstrumentContract:
    def test_naive_expiration_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            DeribitInstrument(
                instrument_name="BTC-27NOV26-100000-C",
                base_currency="BTC",
                kind="option",
                option_type="call",
                strike=100_000.0,
                expiration_timestamp=datetime(2026, 11, 27, 8, 0),
            )
