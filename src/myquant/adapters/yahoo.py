"""Yahoo Finance public chart API adapter (stdlib urllib only).

Fetches daily bars from the unauthenticated chart endpoint::

    https://query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>

The endpoint requires a browser-like User-Agent header; without one
Yahoo returns 401/403. Bars with a null close (missing days) are
excluded and counted.

Timestamp conventions (verified against the live endpoint on 2026-11-18):

- Each bar's timestamp is the market open (09:30 ET) in Unix seconds.
  The trading date is derived from that timestamp in America/New_York.
- The close value is recorded at the same 21:00 UTC convention as the
  FRED adapter (16:00 ET close, fixed; DST is not modelled), so Yahoo
  and FRED daily closes share one event-time grid.
- ``available_at`` equals the event time.
- The chart response carries ``meta.longName``; callers should record
  it for provenance and verify the symbol is the intended instrument
  (Yahoo ticker ``^MOVE``, for example, is a Northern Trust ETF, not the
  ICE BofA MOVE index).
"""

from __future__ import annotations

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

from myquant.contracts import Observation, require_utc

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart"
YAHOO_USER_AGENT = "Mozilla/5.0"
YAHOO_TERMS_URL = "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html"
NEW_YORK = ZoneInfo("America/New_York")

#: US equity close (16:00 ET) recorded as a fixed 21:00 UTC timestamp,
#: shared with the FRED adapter.
DAILY_CLOSE_UTC = dtime(21, 0, 0)


class YahooError(Exception):
    """Yahoo returned an error, or a response failed validation."""


@dataclass(frozen=True)
class YahooBar:
    """One daily bar: trading date plus the unadjusted close."""

    trading_date: date
    close: float


@dataclass(frozen=True)
class ParsedChart:
    """A validated chart response: bars, missing count and meta name."""

    symbol: str
    long_name: str | None
    bars: tuple[YahooBar, ...]
    missing_count: int


@dataclass(frozen=True)
class YahooChart:
    """One fetched Yahoo chart: parsed bars plus the raw payload."""

    symbol: str
    long_name: str | None
    bars: tuple[YahooBar, ...]
    missing_count: int
    url: str
    payload: bytes


def parse_chart_response(payload: bytes, *, symbol: str) -> ParsedChart:
    """Parse a Yahoo chart JSON payload into daily bars.

    Bars with a null close are counted as missing and excluded.
    Timestamps must be strictly increasing and closes finite. A
    ``chart.error`` payload (unknown or delisted symbol) and a meta
    symbol that does not match the requested symbol both fail closed.
    """
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise YahooError(f"Yahoo chart for {symbol!r}: payload is not JSON") from exc
    if not isinstance(document, dict):
        raise YahooError(f"Yahoo chart for {symbol!r}: top level is not an object")
    chart = document.get("chart")
    if not isinstance(chart, dict):
        raise YahooError(f"Yahoo chart for {symbol!r}: missing 'chart' object")
    error = chart.get("error")
    if error is not None:
        raise YahooError(f"Yahoo chart for {symbol!r}: {error}")
    results = chart.get("result")
    if not isinstance(results, list) or len(results) != 1:
        raise YahooError(
            f"Yahoo chart for {symbol!r}: expected exactly one result, "
            f"got {len(results) if isinstance(results, list) else results!r}"
        )
    result = results[0]
    if not isinstance(result, dict):
        raise YahooError(f"Yahoo chart for {symbol!r}: result is not an object")
    meta = result.get("meta")
    if not isinstance(meta, dict):
        raise YahooError(f"Yahoo chart for {symbol!r}: missing 'meta' object")
    meta_symbol = meta.get("symbol")
    if meta_symbol != symbol:
        raise YahooError(
            f"Yahoo chart for {symbol!r}: meta symbol is {meta_symbol!r}"
        )
    long_name = meta.get("longName")
    if long_name is not None and not isinstance(long_name, str):
        raise YahooError(f"Yahoo chart for {symbol!r}: longName is not a string")

    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list) or not timestamps:
        raise YahooError(f"Yahoo chart for {symbol!r}: no timestamps")
    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        raise YahooError(f"Yahoo chart for {symbol!r}: missing 'indicators'")
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or len(quotes) != 1:
        raise YahooError(f"Yahoo chart for {symbol!r}: expected one quote block")
    closes = quotes[0].get("close") if isinstance(quotes[0], dict) else None
    if not isinstance(closes, list):
        raise YahooError(f"Yahoo chart for {symbol!r}: missing close series")
    if len(closes) != len(timestamps):
        raise YahooError(
            f"Yahoo chart for {symbol!r}: {len(timestamps)} timestamps but "
            f"{len(closes)} closes"
        )

    bars: list[YahooBar] = []
    missing_count = 0
    previous_timestamp: float | None = None
    for timestamp, close in zip(timestamps, closes, strict=True):
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise YahooError(
                f"Yahoo chart for {symbol!r}: bad timestamp {timestamp!r}"
            )
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise YahooError(
                f"Yahoo chart for {symbol!r}: timestamps are not strictly increasing"
            )
        previous_timestamp = timestamp
        if close is None:
            missing_count += 1
            continue
        if isinstance(close, bool) or not isinstance(close, (int, float)):
            raise YahooError(
                f"Yahoo chart for {symbol!r}: bad close {close!r}"
            )
        value = float(close)
        if not math.isfinite(value):
            raise YahooError(
                f"Yahoo chart for {symbol!r}: non-finite close {close!r}"
            )
        trading_date = datetime.fromtimestamp(timestamp, tz=NEW_YORK).date()
        bars.append(YahooBar(trading_date=trading_date, close=value))
    if not bars:
        raise YahooError(f"Yahoo chart for {symbol!r}: no bars with a close")
    return ParsedChart(
        symbol=symbol,
        long_name=long_name,
        bars=tuple(bars),
        missing_count=missing_count,
    )


def _default_transport(url: str, *, timeout_seconds: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": YAHOO_USER_AGENT},
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
                raise YahooError(
                    f"Yahoo request failed with HTTP {exc.code}: {url}"
                ) from exc
        except OSError as exc:
            # URLError and raw socket errors (TimeoutError, ConnectionError)
            # are transient network faults; urllib does not wrap every
            # socket error in URLError, so catch OSError broadly.
            if attempt >= max_retries:
                raise YahooError(f"Yahoo request failed: {exc}") from exc
        attempt += 1
        delay = base_delay_seconds * (2 ** (attempt - 1))
        logger.warning(
            "Yahoo request failed; retrying in %.1fs (attempt %d)", delay, attempt
        )
        time.sleep(delay)


def fetch_chart(
    symbol: str,
    *,
    start: date,
    end: date,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
) -> YahooChart:
    """Fetch daily bars for ``symbol`` over the inclusive date range.

    ``period1`` is midnight UTC on ``start``; ``period2`` is midnight UTC
    on the day after ``end`` (Yahoo treats period2 as exclusive).
    """
    if not symbol:
        raise ValueError("symbol must not be empty")
    if end < start:
        raise ValueError("fetch end must not precede start")
    period1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    next_day = end + timedelta(days=1)
    period2 = int(
        datetime(next_day.year, next_day.month, next_day.day, tzinfo=UTC).timestamp()
    )
    params = urllib.parse.urlencode(
        {"period1": period1, "period2": period2, "interval": "1d"}
    )
    url = f"{YAHOO_CHART_URL}/{urllib.parse.quote(symbol, safe='')}?{params}"
    payload = _fetch_url_with_retry(
        url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        base_delay_seconds=1.0,
        transport=transport,
    )
    parsed = parse_chart_response(payload, symbol=symbol)
    return YahooChart(
        symbol=parsed.symbol,
        long_name=parsed.long_name,
        bars=parsed.bars,
        missing_count=parsed.missing_count,
        url=url,
        payload=payload,
    )


def chart_to_observations(
    chart: YahooChart,
    *,
    instrument_id: str,
    venue: str,
    source_id: str,
    source_version: int,
    ingested_at: datetime,
    unit: str,
    field: str = "close",
) -> list[Observation]:
    """Convert daily Yahoo bars to observations at the 21:00 UTC close.

    ``available_at`` equals the event time, matching the FRED adapter.
    """
    ingested = require_utc(ingested_at)
    observations: list[Observation] = []
    for bar in chart.bars:
        event_time = datetime.combine(bar.trading_date, DAILY_CLOSE_UTC, tzinfo=UTC)
        observations.append(
            Observation(
                instrument_id=instrument_id,
                venue=venue,
                event_time=event_time,
                available_at=event_time,
                ingested_at=ingested,
                field=field,
                value=bar.close,
                unit=unit,
                source_id=source_id,
                source_version=source_version,
            )
        )
    return observations
