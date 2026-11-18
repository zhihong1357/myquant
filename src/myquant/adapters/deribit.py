"""Deribit public REST adapter (no credentials, read-only).

Fetches option instrument listings and the Deribit Volatility Index
(DVOL) from Deribit public endpoints using only the standard library.
No API key, no account access, no order placement.

Timestamp conventions (verified against the live API on 2026-11-18):

- ``get_instruments`` returns one record per listed (or recently
  expired) instrument. ``expiration_timestamp`` is the settlement
  moment in UTC milliseconds (08:00 UTC on the expiry date). The live
  response carries ``base_currency`` (the underlying, e.g. "BTC") and
  no top-level ``currency`` field (verified 2026-11-18); the adapter
  parses the underlying from ``base_currency``.
- ``get_instruments`` with ``expired=true`` returns only the most
  recent batch of expired contracts, not the full history of expired
  instruments — it cannot reconstruct a historical expiry calendar.
- ``get_volatility_index_data`` returns daily OHLC-style rows
  ``[timestamp_ms, open, high, low, close]`` for the requested index;
  the ``currency`` parameter is required (omitting it returns HTTP 400).
  Daily points are timestamped at 00:00 UTC.
- Requests are spaced by a small delay and retried with exponential
  backoff on rate limits (429), server errors (5xx) and transient
  network failures.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import Field, model_validator

from myquant.contracts import Observation, StrictContract, require_utc

logger = logging.getLogger(__name__)

BASE_URL = "https://www.deribit.com/api/v2/public"
INSTRUMENTS_PATH = "/get_instruments"
VOLATILITY_PATH = "/get_volatility_index_data"

#: DVOL index names served by get_volatility_index_data.
DVOL_INDEX_NAMES: dict[str, str] = {
    "BTC": "btc_vol",
    "ETH": "eth_vol",
}


class DeribitAPIError(Exception):
    """The Deribit API returned an error payload or an unusable response."""


class DeribitInstrument(StrictContract):
    """One validated Deribit option instrument listing."""

    instrument_name: str = Field(min_length=1)
    base_currency: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    option_type: str | None = None
    strike: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    expiration_timestamp: datetime

    @model_validator(mode="after")
    def validate_instrument(self) -> DeribitInstrument:
        if self.option_type is not None and self.option_type not in ("call", "put"):
            raise ValueError(
                f"option_type must be 'call' or 'put': {self.option_type!r}"
            )
        object.__setattr__(
            self, "expiration_timestamp", require_utc(self.expiration_timestamp)
        )
        return self


class DVOLPoint(StrictContract):
    """One validated daily DVOL index point."""

    index_name: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    timestamp: datetime
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_point(self) -> DVOLPoint:
        if self.high < max(self.open, self.close):
            raise ValueError("DVOL high is below open/close")
        if self.low > min(self.open, self.close):
            raise ValueError("DVOL low is above open/close")
        object.__setattr__(self, "timestamp", require_utc(self.timestamp))
        return self


@dataclass(frozen=True)
class FetchedPage:
    """One raw HTTP response kept for provenance and re-verification."""

    url: str
    payload: bytes


@dataclass(frozen=True)
class InstrumentsFetch:
    """Parsed instruments plus the raw page they were parsed from."""

    instruments: tuple[DeribitInstrument, ...]
    pages: tuple[FetchedPage, ...]


@dataclass(frozen=True)
class VolatilityFetch:
    """Parsed DVOL points plus the raw pages they were parsed from."""

    points: tuple[DVOLPoint, ...]
    pages: tuple[FetchedPage, ...]


def _decode_response(payload: bytes, *, endpoint: str) -> dict[str, Any]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeribitAPIError(f"Deribit response is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise DeribitAPIError("Deribit response is not a JSON object")
    error = decoded.get("error")
    if error is not None:
        raise DeribitAPIError(f"Deribit API error on {endpoint}: {error!r}")
    result = decoded.get("result")
    if result is None:
        raise DeribitAPIError(f"Deribit response has no 'result': {endpoint}")
    return decoded


def parse_instruments_response(
    payload: bytes,
) -> tuple[DeribitInstrument, ...]:
    """Parse one get_instruments response, oldest expiry first.

    Pure (no network access) so tests can run it against frozen fixtures.
    """
    decoded = _decode_response(payload, endpoint="get_instruments")
    result = decoded["result"]
    if not isinstance(result, list):
        raise DeribitAPIError("get_instruments result is not a list")
    instruments: list[DeribitInstrument] = []
    for row in result:
        instruments.append(_parse_instrument_row(row))
    instruments.sort(key=lambda item: (item.expiration_timestamp, item.instrument_name))
    seen: set[str] = set()
    for instrument in instruments:
        if instrument.instrument_name in seen:
            raise DeribitAPIError(
                f"duplicate Deribit instrument: {instrument.instrument_name}"
            )
        seen.add(instrument.instrument_name)
    return tuple(instruments)


def _parse_instrument_row(row: Any) -> DeribitInstrument:
    if not isinstance(row, dict):
        raise DeribitAPIError(f"instrument row is not an object: {row!r}")
    try:
        expiration_ms = int(row["expiration_timestamp"])
        strike = row.get("strike")
        strike_value = float(strike) if strike is not None else None
        return DeribitInstrument(
            instrument_name=str(row["instrument_name"]),
            base_currency=str(row["base_currency"]),
            kind=str(row["kind"]),
            option_type=row.get("option_type"),
            strike=strike_value,
            expiration_timestamp=datetime.fromtimestamp(
                expiration_ms / 1000, tz=UTC
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DeribitAPIError(
            f"instrument row failed validation: {row!r}: {exc}"
        ) from exc


def parse_volatility_response(
    payload: bytes,
    *,
    index_name: str,
    currency: str,
) -> tuple[DVOLPoint, ...]:
    """Parse one get_volatility_index_data response, oldest first.

    Pure (no network access) so tests can run it against frozen fixtures.
    The response carries OHLC-style rows [timestamp_ms, open, high, low,
    close]; the index name and currency come from the request, not the
    payload, so callers pass them in.
    """
    decoded = _decode_response(payload, endpoint="get_volatility_index_data")
    result = decoded["result"]
    if not isinstance(result, dict):
        raise DeribitAPIError("get_volatility_index_data result is not an object")
    data = result.get("data")
    if not isinstance(data, list):
        raise DeribitAPIError("get_volatility_index_data result has no 'data' list")
    points: list[DVOLPoint] = []
    for row in data:
        points.append(_parse_volatility_row(row, index_name=index_name, currency=currency))
    points.sort(key=lambda item: item.timestamp)
    seen: set[datetime] = set()
    for point in points:
        if point.timestamp in seen:
            raise DeribitAPIError(
                f"duplicate DVOL timestamp: {point.timestamp.isoformat()}"
            )
        seen.add(point.timestamp)
    return tuple(points)


def _parse_volatility_row(
    row: Any,
    *,
    index_name: str,
    currency: str,
) -> DVOLPoint:
    if not isinstance(row, list) or len(row) != 5:
        raise DeribitAPIError(
            "DVOL row must have 5 elements "
            "[timestamp_ms, open, high, low, close]"
        )
    ts_raw, open_raw, high_raw, low_raw, close_raw = row
    try:
        timestamp_ms = int(ts_raw)
        values = [float(value) for value in (open_raw, high_raw, low_raw, close_raw)]
    except (TypeError, ValueError) as exc:
        raise DeribitAPIError(f"DVOL row has non-numeric fields: {row!r}") from exc
    try:
        return DVOLPoint(
            index_name=index_name,
            currency=currency,
            timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC),
            open=values[0],
            high=values[1],
            low=values[2],
            close=values[3],
        )
    except ValueError as exc:
        raise DeribitAPIError(f"DVOL point failed validation: {exc}") from exc


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
                raise DeribitAPIError(
                    f"Deribit request failed with HTTP {exc.code}: {url}"
                ) from exc
        except urllib.error.URLError as exc:
            if attempt >= max_retries:
                raise DeribitAPIError(f"Deribit request failed: {exc.reason}") from exc
        except (TimeoutError, OSError) as exc:
            if attempt >= max_retries:
                raise DeribitAPIError(f"Deribit request failed: {exc}") from exc
        attempt += 1
        delay = base_delay_seconds * (2 ** (attempt - 1))
        logger.warning(
            "Deribit request failed; retrying in %.1fs (attempt %d)", delay, attempt
        )
        time.sleep(delay)


def fetch_instruments(
    currency: str,
    *,
    kind: str = "option",
    expired: bool = False,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
) -> InstrumentsFetch:
    """Fetch one currency/kind instrument listing (listed or expired)."""
    query = urllib.parse.urlencode(
        {
            "currency": currency,
            "kind": kind,
            "expired": "true" if expired else "false",
        }
    )
    url = f"{BASE_URL}{INSTRUMENTS_PATH}?{query}"
    payload = _fetch_url_with_retry(
        url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        base_delay_seconds=1.0,
        transport=transport,
    )
    return InstrumentsFetch(
        instruments=parse_instruments_response(payload),
        pages=(FetchedPage(url=url, payload=payload),),
    )


def fetch_volatility_index(
    currency: str,
    *,
    start: datetime,
    end: datetime,
    resolution_seconds: int = 86_400,
    delay_seconds: float = 0.2,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
) -> VolatilityFetch:
    """Fetch daily DVOL points with timestamps in [start, end).

    The window is fetched in two-year chunks (the endpoint returns at
    most ~1,000 points per call in practice) and deduplicated by
    timestamp, so callers need not rely on the response's continuation
    token semantics.
    """
    index_name = DVOL_INDEX_NAMES.get(currency)
    if index_name is None:
        raise ValueError(f"no DVOL index for currency: {currency!r}")
    start_utc = require_utc(start)
    end_utc = require_utc(end)
    if end_utc <= start_utc:
        raise ValueError("fetch end must be after start")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")

    pages: list[FetchedPage] = []
    collected: dict[datetime, DVOLPoint] = {}
    chunk_start = start_utc
    two_years = 2 * 366 * 86_400  # seconds; covers leap years
    while chunk_start < end_utc:
        chunk_end = min(
            end_utc,
            datetime.fromtimestamp(
                chunk_start.timestamp() + two_years, tz=UTC
            ),
        )
        query = urllib.parse.urlencode(
            {
                "currency": currency,
                "index_name": index_name,
                "start_timestamp": int(chunk_start.timestamp() * 1000),
                "end_timestamp": int(chunk_end.timestamp() * 1000),
                "resolution": resolution_seconds,
            }
        )
        url = f"{BASE_URL}{VOLATILITY_PATH}?{query}"
        payload = _fetch_url_with_retry(
            url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            base_delay_seconds=1.0,
            transport=transport,
        )
        pages.append(FetchedPage(url=url, payload=payload))
        for point in parse_volatility_response(
            payload, index_name=index_name, currency=currency
        ):
            if start_utc <= point.timestamp < end_utc:
                collected[point.timestamp] = point
        chunk_start = chunk_end
        if delay_seconds and chunk_start < end_utc:
            time.sleep(delay_seconds)

    ordered = tuple(collected[key] for key in sorted(collected))
    return VolatilityFetch(points=ordered, pages=tuple(pages))


def dvol_to_observations(
    points: list[DVOLPoint] | tuple[DVOLPoint, ...],
    *,
    instrument_id: str,
    venue: str,
    source_id: str,
    source_version: int,
    ingested_at: datetime,
) -> list[Observation]:
    """Convert daily DVOL points to close observations.

    event_time is the point's 00:00 UTC timestamp; available_at is the
    next day's 00:00 UTC (when the daily point's close became knowable).
    Only the close is stored: the descriptive analysis uses daily DVOL
    closes, and OHLC fields would add no information about expiry windows.
    """
    ingested = require_utc(ingested_at)
    observations: list[Observation] = []
    for point in points:
        observations.append(
            Observation(
                instrument_id=instrument_id,
                venue=venue,
                event_time=point.timestamp,
                available_at=point.timestamp + timedelta(days=1),
                ingested_at=ingested,
                field="close",
                value=point.close,
                unit="percent",
                source_id=source_id,
                source_version=source_version,
            )
        )
    return observations
