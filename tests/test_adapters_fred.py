"""Tests for the FRED public CSV adapter.

All tests run offline against frozen fixtures; no test touches the network.
"""

from __future__ import annotations

import urllib.error
from datetime import UTC, date, datetime

import pytest

from myquant.adapters.fred import (
    FredError,
    fetch_series,
    parse_series_csv,
    series_to_observations,
)

# Frozen fredgraph CSV: one "." missing row in the middle, one trailing
# blank line. Values are illustrative, not real FRED data.
FIXTURE_CSV = (
    b"observation_date,VIXCLS\n"
    b"2003-01-02,22.46\n"
    b"2003-01-03,.\n"
    b"2003-01-06,21.87\n"
    b"2003-01-07,21.02\n"
    b"\n"
)


def test_parse_returns_dated_values_and_missing_count() -> None:
    observations, missing_count = parse_series_csv(
        FIXTURE_CSV, series_id="VIXCLS"
    )
    assert observations == (
        (date(2003, 1, 2), 22.46),
        (date(2003, 1, 6), 21.87),
        (date(2003, 1, 7), 21.02),
    )
    assert missing_count == 1


def test_parse_rejects_html_error_page() -> None:
    payload = b"<!DOCTYPE html><html><body>Series not found</body></html>"
    with pytest.raises(FredError, match="unexpected header"):
        parse_series_csv(payload, series_id="BOGUS")


def test_parse_rejects_header_series_mismatch() -> None:
    payload = b"observation_date,VXNCLS\n2003-01-02,22.46\n"
    with pytest.raises(FredError, match="unexpected header"):
        parse_series_csv(payload, series_id="VIXCLS")


def test_parse_rejects_empty_payload() -> None:
    with pytest.raises(FredError, match="empty payload"):
        parse_series_csv(b"", series_id="VIXCLS")


def test_parse_rejects_header_only() -> None:
    with pytest.raises(FredError, match="no observations"):
        parse_series_csv(b"observation_date,VIXCLS\n", series_id="VIXCLS")


def test_parse_rejects_non_monotonic_dates() -> None:
    payload = (
        b"observation_date,VIXCLS\n"
        b"2003-01-06,21.87\n"
        b"2003-01-02,22.46\n"
    )
    with pytest.raises(FredError, match="not strictly increasing"):
        parse_series_csv(payload, series_id="VIXCLS")


def test_parse_rejects_duplicate_date() -> None:
    payload = (
        b"observation_date,VIXCLS\n"
        b"2003-01-02,22.46\n"
        b"2003-01-02,22.50\n"
    )
    with pytest.raises(FredError, match="not strictly increasing"):
        parse_series_csv(payload, series_id="VIXCLS")


def test_parse_rejects_bad_value() -> None:
    payload = b"observation_date,VIXCLS\n2003-01-02,abc\n"
    with pytest.raises(FredError, match="bad value"):
        parse_series_csv(payload, series_id="VIXCLS")


def test_parse_rejects_non_finite_value() -> None:
    payload = b"observation_date,VIXCLS\n2003-01-02,inf\n"
    with pytest.raises(FredError, match="non-finite"):
        parse_series_csv(payload, series_id="VIXCLS")


def test_parse_rejects_malformed_row() -> None:
    payload = b"observation_date,VIXCLS\n2003-01-02,22.46,extra\n"
    with pytest.raises(FredError, match="malformed row"):
        parse_series_csv(payload, series_id="VIXCLS")


def test_fetch_series_uses_transport_and_builds_url() -> None:
    seen: list[str] = []

    def transport(url: str) -> bytes:
        seen.append(url)
        return FIXTURE_CSV

    series = fetch_series(
        "VIXCLS",
        start=date(2003, 1, 2),
        end=date(2003, 1, 7),
        transport=transport,
    )
    assert series.series_id == "VIXCLS"
    assert len(series.observations) == 3
    assert series.missing_count == 1
    assert series.payload == FIXTURE_CSV
    assert seen == [series.url]
    assert "id=VIXCLS" in series.url
    assert "cosd=2003-01-02" in series.url
    assert "coed=2003-01-07" in series.url


def test_fetch_series_rejects_bad_series_id() -> None:
    with pytest.raises(ValueError, match="invalid FRED series id"):
        fetch_series("VIX CLS", transport=lambda url: FIXTURE_CSV)


def test_fetch_series_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="end must not precede start"):
        fetch_series(
            "VIXCLS",
            start=date(2003, 1, 7),
            end=date(2003, 1, 2),
            transport=lambda url: FIXTURE_CSV,
        )


def test_fetch_series_retries_429_then_succeeds() -> None:
    calls = {"count": 0}

    def transport(url: str) -> bytes:
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return FIXTURE_CSV

    series = fetch_series("VIXCLS", transport=transport)
    assert len(series.observations) == 3
    assert calls["count"] == 2


def test_fetch_series_retries_timeout_then_succeeds() -> None:
    calls = {"count": 0}

    def transport(url: str) -> bytes:
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("The read operation timed out")
        return FIXTURE_CSV

    series = fetch_series("VIXCLS", transport=transport)
    assert len(series.observations) == 3
    assert calls["count"] == 2


def test_fetch_series_raises_after_max_retries() -> None:
    def transport(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)

    with pytest.raises(FredError, match="HTTP 500"):
        fetch_series("VIXCLS", max_retries=1, transport=transport)


def test_fetch_series_does_not_retry_404() -> None:
    calls = {"count": 0}

    def transport(url: str) -> bytes:
        calls["count"] += 1
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    with pytest.raises(FredError, match="HTTP 404"):
        fetch_series("VIXCLS", transport=transport)
    assert calls["count"] == 1


def test_series_to_observations_uses_close_convention() -> None:
    series = fetch_series("VIXCLS", transport=lambda url: FIXTURE_CSV)
    observations = series_to_observations(
        series,
        instrument_id="index:vix",
        venue="fred",
        source_id="fred",
        source_version=1,
        ingested_at=datetime(2026, 11, 18, 12, 0, tzinfo=UTC),
        unit="points",
    )
    assert len(observations) == 3
    first = observations[0]
    assert first.source_id == "fred"
    assert first.source_version == 1
    assert first.venue == "fred"
    assert first.instrument_id == "index:vix"
    assert first.field == "close"
    assert first.event_time == datetime(2003, 1, 2, 21, 0, tzinfo=UTC)
    assert first.available_at == first.event_time
    assert first.value == 22.46
    assert first.unit == "points"
