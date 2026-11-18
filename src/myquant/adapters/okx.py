"""OKX public REST market-data adapter (no credentials, read-only).

Fetches candlestick history from OKX public endpoints using only the
standard library. No API key, no account access, no order placement.

Timestamp conventions (verified against the live API on 2026-11-18):

- A candle's ``ts`` is its **open** time in UTC milliseconds.
- Daily (``1D``) bars open at 16:00 UTC, i.e. midnight UTC+8. The bar
  labelled 2026-11-16T16:00Z covers 16:00 UTC 16 Nov to 16:00 UTC 17 Nov.
- Hourly (``1H``) bars open on the UTC hour.
- A bar becomes knowable at its close: ``available_at = open + bar duration``.
- Each row carries a ``confirm`` flag: ``"1"`` means the bar is complete,
  ``"0"`` means it is still forming. Only confirmed bars are returned by
  :func:`fetch_history`; forming bars are never admitted as observations.

Pagination uses ``/market/history-candles`` with the ``after`` cursor,
which returns bars strictly older than the given timestamp, newest first,
at most 100 per page. Requests are spaced by a small delay and retried
with exponential backoff on rate limits (429), server errors (5xx) and
transient network failures.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import Field, model_validator

from myquant.contracts import Observation, StrictContract, require_utc

logger = logging.getLogger(__name__)

BASE_URL = "https://www.okx.com/api/v5/market"
HISTORY_PATH = "/history-candles"
MAX_PAGE_SIZE = 100

#: Bar code to duration in seconds. Only bars used by registered research
#: are listed; unknown bars are rejected rather than guessed.
BAR_DURATIONS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1H": 3_600,
    "4H": 14_400,
    "1D": 86_400,
}


class OKXAPIError(Exception):
    """The OKX API returned an error payload or an unusable response."""


class OKXCandle(StrictContract):
    """One validated OKX candlestick bar."""

    instrument: str = Field(min_length=1)
    bar: str = Field(min_length=1)
    open_time: datetime
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float = Field(ge=0, allow_inf_nan=False)
    volume_currency: float = Field(ge=0, allow_inf_nan=False)
    confirmed: bool

    @model_validator(mode="after")
    def validate_candle(self) -> OKXCandle:
        if self.bar not in BAR_DURATIONS:
            raise ValueError(f"unsupported OKX bar: {self.bar!r}")
        if self.high < max(self.open, self.close):
            raise ValueError("candle high is below open/close")
        if self.low > min(self.open, self.close):
            raise ValueError("candle low is above open/close")
        object.__setattr__(self, "open_time", require_utc(self.open_time))
        return self

    @property
    def close_time(self) -> datetime:
        """When the bar completes and its values become knowable."""
        return self.open_time + timedelta(seconds=BAR_DURATIONS[self.bar])


@dataclass(frozen=True)
class FetchedPage:
    """One raw HTTP response kept for provenance and re-verification."""

    url: str
    payload: bytes


@dataclass(frozen=True)
class HistoryFetch:
    """Confirmed candles plus the raw pages they were parsed from."""

    candles: tuple[OKXCandle, ...]
    pages: tuple[FetchedPage, ...]


def _bar_seconds(bar: str) -> int:
    try:
        return BAR_DURATIONS[bar]
    except KeyError as exc:
        raise ValueError(f"unsupported OKX bar: {bar!r}") from exc


def parse_candles_response(
    payload: bytes,
    *,
    inst_id: str,
    bar: str,
) -> tuple[OKXCandle, ...]:
    """Parse one OKX candles response into validated candles, oldest first.

    This function is pure (no network access) so tests can run it against
    frozen fixtures. It validates the response code, row shape, timestamp
    order and OHLC consistency, and rejects duplicate timestamps.
    """
    _bar_seconds(bar)
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OKXAPIError(f"OKX response is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise OKXAPIError("OKX response is not a JSON object")
    if decoded.get("code") != "0":
        raise OKXAPIError(
            f"OKX API error code={decoded.get('code')!r} "
            f"msg={decoded.get('msg')!r}"
        )
    rows = decoded.get("data")
    if not isinstance(rows, list):
        raise OKXAPIError("OKX response has no 'data' list")

    candles: list[OKXCandle] = []
    previous_ts: int | None = None
    for row in rows:
        candle = _parse_row(row, inst_id=inst_id, bar=bar)
        open_ms = int(candle.open_time.timestamp() * 1000)
        if previous_ts is not None and open_ms > previous_ts:
            raise OKXAPIError(
                "OKX candles are not in newest-first order; "
                "refusing to guess the pagination order"
            )
        previous_ts = open_ms
        candles.append(candle)

    candles.sort(key=lambda item: item.open_time)
    seen: set[datetime] = set()
    for candle in candles:
        if candle.open_time in seen:
            raise OKXAPIError(
                f"duplicate OKX candle timestamp: {candle.open_time.isoformat()}"
            )
        seen.add(candle.open_time)
    return tuple(candles)


def _parse_row(row: Any, *, inst_id: str, bar: str) -> OKXCandle:
    if not isinstance(row, list) or len(row) != 9:
        raise OKXAPIError(
            "OKX candle row must have 9 elements "
            "[ts, open, high, low, close, volume, volCcy, volCcyQuote, confirm]"
        )
    ts_raw, open_raw, high_raw, low_raw, close_raw, vol_raw, vol_ccy_raw, _, confirm = row
    try:
        open_ms = int(ts_raw)
        values = [float(value) for value in (open_raw, high_raw, low_raw, close_raw)]
        volume = float(vol_raw)
        volume_currency = float(vol_ccy_raw)
    except (TypeError, ValueError) as exc:
        raise OKXAPIError(f"OKX candle row has non-numeric fields: {row!r}") from exc
    if confirm not in ("0", "1"):
        raise OKXAPIError(f"OKX candle confirm flag must be '0' or '1': {confirm!r}")
    try:
        return OKXCandle(
            instrument=inst_id,
            bar=bar,
            open_time=datetime.fromtimestamp(open_ms / 1000, tz=UTC),
            open=values[0],
            high=values[1],
            low=values[2],
            close=values[3],
            volume=volume,
            volume_currency=volume_currency,
            confirmed=confirm == "1",
        )
    except ValueError as exc:
        raise OKXAPIError(f"OKX candle failed validation: {exc}") from exc


def _default_transport(url: str, *, timeout_seconds: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "myquant-research/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return bytes(response.read())


def _fetch_url_with_retry(
    url: str,
    *,
    timeout_seconds: float,
    max_retries: int,
    base_delay_seconds: float,
    transport: Callable[[str], bytes] | None,
) -> bytes:
    """Fetch one URL, retrying rate limits, server errors and network faults."""
    fetch = transport or (
        lambda target: _default_transport(target, timeout_seconds=timeout_seconds)
    )
    attempt = 0
    while True:
        try:
            return fetch(url)
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= max_retries:
                raise OKXAPIError(
                    f"OKX request failed with HTTP {exc.code}: {url}"
                ) from exc
        except urllib.error.URLError as exc:
            if attempt >= max_retries:
                raise OKXAPIError(f"OKX request failed: {exc.reason}") from exc
        attempt += 1
        delay = base_delay_seconds * (2 ** (attempt - 1))
        logger.warning("OKX request failed; retrying in %.1fs (attempt %d)", delay, attempt)
        time.sleep(delay)


def fetch_history(
    inst_id: str,
    bar: str,
    *,
    start: datetime,
    end: datetime,
    page_size: int = MAX_PAGE_SIZE,
    delay_seconds: float = 0.2,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
) -> HistoryFetch:
    """Fetch confirmed candles with open times in [start, end).

    Pages ``/market/history-candles`` backwards from ``end`` until the
    requested start is covered. Returns candles in ascending time order
    plus the raw response bytes of every page, so the caller can store
    exact provenance. Forming (unconfirmed) bars are excluded.
    """
    _bar_seconds(bar)
    start_utc = require_utc(start)
    end_utc = require_utc(end)
    if end_utc <= start_utc:
        raise ValueError("fetch end must be after start")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")

    pages: list[FetchedPage] = []
    collected: dict[datetime, OKXCandle] = {}
    cursor_ms = int(end_utc.timestamp() * 1000)
    while True:
        url = (
            f"{BASE_URL}{HISTORY_PATH}?instId={inst_id}&bar={bar}"
            f"&after={cursor_ms}&limit={page_size}"
        )
        payload = _fetch_url_with_retry(
            url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            base_delay_seconds=1.0,
            transport=transport,
        )
        pages.append(FetchedPage(url=url, payload=payload))
        candles = parse_candles_response(payload, inst_id=inst_id, bar=bar)
        if not candles:
            break
        for candle in candles:
            if candle.confirmed and start_utc <= candle.open_time < end_utc:
                collected[candle.open_time] = candle
        oldest = candles[0].open_time
        if oldest <= start_utc:
            break
        next_cursor = int(oldest.timestamp() * 1000)
        if next_cursor >= cursor_ms:
            raise OKXAPIError("OKX pagination did not advance; refusing to loop")
        cursor_ms = next_cursor
        if delay_seconds:
            time.sleep(delay_seconds)

    ordered = tuple(collected[key] for key in sorted(collected))
    return HistoryFetch(candles=ordered, pages=tuple(pages))


def candles_to_observations(
    candles: Sequence[OKXCandle],
    *,
    instrument_id: str,
    venue: str,
    source_id: str,
    source_version: int,
    ingested_at: datetime,
) -> list[Observation]:
    """Convert confirmed candles to OHLCV observations.

    event_time is the bar open; available_at is the bar close (when the
    values became knowable). Only confirmed candles are converted; pass a
    forming candle and this raises instead of silently admitting it.
    """
    ingested = require_utc(ingested_at)
    observations: list[Observation] = []
    for candle in candles:
        if not candle.confirmed:
            raise ValueError(
                f"refusing to convert unconfirmed candle: "
                f"{candle.instrument} {candle.open_time.isoformat()}"
            )
        for field_name, value, unit in (
            ("open", candle.open, "USDT"),
            ("high", candle.high, "USDT"),
            ("low", candle.low, "USDT"),
            ("close", candle.close, "USDT"),
            ("volume", candle.volume, "contracts"),
        ):
            observations.append(
                Observation(
                    instrument_id=instrument_id,
                    venue=venue,
                    event_time=candle.open_time,
                    available_at=candle.close_time,
                    ingested_at=ingested,
                    field=field_name,
                    value=value,
                    unit=unit,
                    source_id=source_id,
                    source_version=source_version,
                )
            )
    return observations
