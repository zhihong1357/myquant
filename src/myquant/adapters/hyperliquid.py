"""Hyperliquid public REST market-data adapter (no credentials, read-only).

Fetches candlestick history from Hyperliquid's public ``/info`` endpoint
using only the standard library. No API key, no account access, no order
placement.

Timestamp conventions (verified against the live API on 2026-11-18):

- A candle's ``t`` is its **open** time in UTC milliseconds; ``T`` is the
  last millisecond of the bar (open + bar duration - 1ms).
- Daily (``1d``) bars open at **00:00 UTC** — a different daily anchor
  from OKX (16:00 UTC). Studies mixing venues must not assume the grids
  align; test C in study 002 builds its panel from Hyperliquid data alone.
- ``candleSnapshot`` returns the still-forming candle as well as closed
  ones, so a bar is admitted only when its close has passed
  (``close_time <= as_of``). Forming bars are never admitted.
- Candles before Hyperliquid's launch carry zero trades (``n == 0``) and
  zero volume: they are backfilled marks with no venue price discovery.
  ``fetch_candles`` excludes them and reports the excluded count, so the
  panel starts at the first actually-traded bar.

Only the daily interval is supported. The 1H ``candleSnapshot`` returned
an empty array in one probe (cause not investigated); hourly Hyperliquid
data is out of scope for this adapter rather than silently unreliable.
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

BASE_URL = "https://api.hyperliquid.xyz"
INFO_PATH = "/info"

#: Supported intervals and their durations in seconds. Only intervals used
#: by registered research are listed; unknown intervals are rejected
#: rather than guessed.
INTERVAL_DURATIONS: dict[str, int] = {
    "1d": 86_400,
}

#: Pagination window for candleSnapshot requests (the endpoint accepts an
#: explicit time range; windowing keeps responses small and auditable).
PAGE_WINDOW_DAYS = 365


class HyperliquidAPIError(Exception):
    """The Hyperliquid API returned an error or an unusable response."""


class HyperliquidCandle(StrictContract):
    """One validated Hyperliquid candlestick bar."""

    coin: str = Field(min_length=1)
    interval: str = Field(min_length=1)
    open_time: datetime
    close_end: datetime
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float = Field(ge=0, allow_inf_nan=False)
    trade_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_candle(self) -> HyperliquidCandle:
        if self.interval not in INTERVAL_DURATIONS:
            raise ValueError(f"unsupported Hyperliquid interval: {self.interval!r}")
        if self.high < max(self.open, self.close):
            raise ValueError("candle high is below open/close")
        if self.low > min(self.open, self.close):
            raise ValueError("candle low is above open/close")
        expected_close_end = self.open_time + timedelta(
            seconds=INTERVAL_DURATIONS[self.interval] - 0.001
        )
        if self.close_end != expected_close_end:
            raise ValueError(
                "candle close end is not open + bar duration - 1ms: "
                f"{self.close_end.isoformat()} vs {expected_close_end.isoformat()}"
            )
        object.__setattr__(self, "open_time", require_utc(self.open_time))
        object.__setattr__(self, "close_end", require_utc(self.close_end))
        return self

    @property
    def close_time(self) -> datetime:
        """When the bar completes and its values become knowable."""
        return self.open_time + timedelta(seconds=INTERVAL_DURATIONS[self.interval])

    @property
    def is_closed(self) -> bool:
        """Whether the bar's close has passed (relative to wall-clock now)."""
        return self.close_time <= datetime.now(UTC)


@dataclass(frozen=True)
class FetchedPage:
    """One raw HTTP request/response kept for provenance and re-verification."""

    request_body: str
    payload: bytes


@dataclass(frozen=True)
class CandleFetch:
    """Admitted candles plus the raw pages they were parsed from."""

    candles: tuple[HyperliquidCandle, ...]
    pages: tuple[FetchedPage, ...]
    excluded_unclosed: int
    excluded_zero_trade: int


def _interval_seconds(interval: str) -> int:
    try:
        return INTERVAL_DURATIONS[interval]
    except KeyError as exc:
        raise ValueError(f"unsupported Hyperliquid interval: {interval!r}") from exc


def parse_candles_response(
    payload: bytes,
    *,
    coin: str,
    interval: str,
) -> tuple[HyperliquidCandle, ...]:
    """Parse one candleSnapshot response into validated candles, oldest first.

    This function is pure (no network access) so tests can run it against
    frozen fixtures. It validates the response shape, coin/interval tags,
    OHLC consistency and the close-end convention, and rejects duplicate
    timestamps. Forming and zero-trade candles are returned here; the
    fetch layer decides admission.
    """
    _interval_seconds(interval)
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HyperliquidAPIError(
            f"Hyperliquid response is not valid JSON: {exc}"
        ) from exc
    if not isinstance(decoded, list):
        raise HyperliquidAPIError("Hyperliquid candleSnapshot response is not a list")

    candles = [_parse_candle(row, coin=coin, interval=interval) for row in decoded]
    candles.sort(key=lambda item: item.open_time)
    seen: set[datetime] = set()
    for candle in candles:
        if candle.open_time in seen:
            raise HyperliquidAPIError(
                f"duplicate Hyperliquid candle timestamp: {candle.open_time.isoformat()}"
            )
        seen.add(candle.open_time)
    return tuple(candles)


def _parse_candle(row: Any, *, coin: str, interval: str) -> HyperliquidCandle:
    if not isinstance(row, dict):
        raise HyperliquidAPIError(f"Hyperliquid candle row is not an object: {row!r}")
    required = ("t", "T", "s", "i", "o", "c", "h", "l", "v", "n")
    if any(key not in row for key in required):
        raise HyperliquidAPIError(
            f"Hyperliquid candle row is missing fields: {row!r}"
        )
    if row["s"] != coin:
        raise HyperliquidAPIError(
            f"Hyperliquid candle coin mismatch: {row['s']!r} != {coin!r}"
        )
    if row["i"] != interval:
        raise HyperliquidAPIError(
            f"Hyperliquid candle interval mismatch: {row['i']!r} != {interval!r}"
        )
    try:
        open_ms = int(row["t"])
        close_ms = int(row["T"])
        values = [float(row[key]) for key in ("o", "c", "h", "l")]
        volume = float(row["v"])
        trade_count = int(row["n"])
    except (TypeError, ValueError) as exc:
        raise HyperliquidAPIError(
            f"Hyperliquid candle row has non-numeric fields: {row!r}"
        ) from exc
    try:
        return HyperliquidCandle(
            coin=coin,
            interval=interval,
            open_time=datetime.fromtimestamp(open_ms / 1000, tz=UTC),
            close_end=datetime.fromtimestamp(close_ms / 1000, tz=UTC),
            open=values[0],
            close=values[1],
            high=values[2],
            low=values[3],
            volume=volume,
            trade_count=trade_count,
        )
    except ValueError as exc:
        raise HyperliquidAPIError(f"Hyperliquid candle failed validation: {exc}") from exc


def _default_transport(request_body: bytes, *, timeout_seconds: float) -> bytes:
    request = urllib.request.Request(
        f"{BASE_URL}{INFO_PATH}",
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "myquant-research/0.1",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return bytes(response.read())


def _post_with_retry(
    request_body: bytes,
    *,
    timeout_seconds: float,
    max_retries: int,
    base_delay_seconds: float,
    transport: Callable[[bytes], bytes] | None,
) -> bytes:
    """POST one request, retrying rate limits, server errors and network faults."""
    post = transport or (
        lambda body: _default_transport(body, timeout_seconds=timeout_seconds)
    )
    attempt = 0
    while True:
        try:
            return post(request_body)
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= max_retries:
                raise HyperliquidAPIError(
                    f"Hyperliquid request failed with HTTP {exc.code}"
                ) from exc
        except urllib.error.URLError as exc:
            if attempt >= max_retries:
                raise HyperliquidAPIError(
                    f"Hyperliquid request failed: {exc.reason}"
                ) from exc
        attempt += 1
        delay = base_delay_seconds * (2 ** (attempt - 1))
        logger.warning(
            "Hyperliquid request failed; retrying in %.1fs (attempt %d)",
            delay,
            attempt,
        )
        time.sleep(delay)


def _request_body(
    coin: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> bytes:
    body = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
        },
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def fetch_candles(
    coin: str,
    interval: str,
    *,
    start: datetime,
    end: datetime,
    as_of: datetime | None = None,
    delay_seconds: float = 0.5,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[bytes], bytes] | None = None,
) -> CandleFetch:
    """Fetch closed, traded candles with open times in [start, end).

    Pages ``candleSnapshot`` in fixed time windows and deduplicates by open
    time. A candle is admitted only when its close has passed
    (``close_time <= as_of``, defaulting to now) and it carries at least
    one trade; forming bars and zero-trade backfilled marks are excluded
    and counted. Returns candles in ascending time order plus the raw
    request/response bytes of every page, so the caller can store exact
    provenance.
    """
    _interval_seconds(interval)
    start_utc = require_utc(start)
    end_utc = require_utc(end)
    as_of_utc = require_utc(as_of) if as_of is not None else datetime.now(UTC)
    if end_utc <= start_utc:
        raise ValueError("fetch end must be after start")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")

    pages: list[FetchedPage] = []
    collected: dict[datetime, HyperliquidCandle] = {}
    seen: set[datetime] = set()
    excluded_unclosed = 0
    excluded_zero_trade = 0
    window = timedelta(days=PAGE_WINDOW_DAYS)
    cursor = start_utc
    while cursor < end_utc:
        window_end = min(cursor + window, end_utc)
        body = _request_body(coin, interval, cursor, window_end)
        payload = _post_with_retry(
            body,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            base_delay_seconds=1.0,
            transport=transport,
        )
        pages.append(
            FetchedPage(request_body=body.decode("utf-8"), payload=payload)
        )
        for candle in parse_candles_response(payload, coin=coin, interval=interval):
            if not (start_utc <= candle.open_time < end_utc):
                continue
            if candle.open_time in seen:
                continue
            seen.add(candle.open_time)
            if candle.close_time > as_of_utc:
                excluded_unclosed += 1
                continue
            if candle.trade_count == 0:
                excluded_zero_trade += 1
                continue
            collected[candle.open_time] = candle
        if window_end <= cursor:
            raise HyperliquidAPIError("Hyperliquid pagination did not advance")
        cursor = window_end
        if delay_seconds and cursor < end_utc:
            time.sleep(delay_seconds)

    ordered = tuple(collected[key] for key in sorted(collected))
    return CandleFetch(
        candles=ordered,
        pages=tuple(pages),
        excluded_unclosed=excluded_unclosed,
        excluded_zero_trade=excluded_zero_trade,
    )


def candles_to_observations(
    candles: Sequence[HyperliquidCandle],
    *,
    instrument_id: str,
    venue: str,
    source_id: str,
    source_version: int,
    ingested_at: datetime,
    as_of: datetime | None = None,
) -> list[Observation]:
    """Convert closed, traded candles to OHLCV observations.

    event_time is the bar open; available_at is the bar close (when the
    values became knowable). Forming or zero-trade candles are rejected
    rather than silently admitted.
    """
    ingested = require_utc(ingested_at)
    as_of_utc = require_utc(as_of) if as_of is not None else datetime.now(UTC)
    observations: list[Observation] = []
    for candle in candles:
        if candle.close_time > as_of_utc:
            raise ValueError(
                "refusing to convert unclosed candle: "
                f"{candle.coin} {candle.open_time.isoformat()}"
            )
        if candle.trade_count == 0:
            raise ValueError(
                "refusing to convert zero-trade candle: "
                f"{candle.coin} {candle.open_time.isoformat()}"
            )
        for field_name, value, unit in (
            ("open", candle.open, "USD"),
            ("high", candle.high, "USD"),
            ("low", candle.low, "USD"),
            ("close", candle.close, "USD"),
            ("volume", candle.volume, candle.coin),
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
