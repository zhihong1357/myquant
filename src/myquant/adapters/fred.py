"""FRED (Federal Reserve Economic Data) public CSV adapter.

FRED publishes free economic series as CSV files at
``https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`` (no API key
required). Missing observations appear as empty values in the value
column (verified 2026-11-18: market holidays carry an empty field, not
``"."``; the ``"."`` encoding FRED documents for its API is also treated
as missing). FRED data is free to use with attribution to the Federal
Reserve Bank of St. Louis.

Timestamp conventions (verified against the live endpoint on 2026-11-18):

- Each row is a daily observation dated ``observation_date``.
- The value is the day's closing value; the event time is the US equity
  market close, 16:00 ET, recorded as 21:00 UTC (fixed; DST is not
  modelled, so the UTC offset is approximate in summer).
- ``available_at`` equals the event time. FRED's actual publication lag
  (values are posted after the close, sometimes the next morning) is not
  modelled; see the study report's stated limitations.
- FRED series are revised over time; the adapter fetches the current
  vintage and the fetch script records the payload SHA-256 in the
  manifest so a later pull can be compared.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as dtime

from myquant.contracts import Observation, require_utc

logger = logging.getLogger(__name__)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_TERMS_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"

# NOTE: do not set a custom or browser-like User-Agent here. FRED's edge
# hangs requests that carry a browser-like UA (bare "Mozilla/5.0" and a
# full Chrome UA both timed out) or an unknown custom UA, while the
# default urllib UA ("Python-urllib/3.12") and curl's default UA return
# 200 promptly (verified 2026-11-18). The transport therefore sends no
# User-Agent header and lets urllib identify itself honestly.

#: US equity close (16:00 ET) recorded as a fixed 21:00 UTC timestamp.
DAILY_CLOSE_UTC = dtime(21, 0, 0)

_SERIES_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class FredError(Exception):
    """FRED returned an error, or a response failed validation."""


@dataclass(frozen=True)
class FredSeries:
    """One fetched FRED series: dated values plus the raw payload."""

    series_id: str
    observations: tuple[tuple[date, float], ...]
    missing_count: int
    url: str
    payload: bytes


def parse_series_csv(
    payload: bytes,
    *,
    series_id: str,
) -> tuple[tuple[tuple[date, float], ...], int]:
    """Parse a fredgraph CSV payload into dated values and a missing count.

    Rows whose value is ``"."`` (or empty) are counted as missing and
    excluded. Dates must be strictly increasing and values finite. A
    non-CSV payload (for example the HTML error page FRED serves for an
    unknown series id) fails the header check.
    """
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FredError(f"FRED series {series_id!r}: payload is not UTF-8") from exc
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    if not rows:
        raise FredError(f"FRED series {series_id!r}: empty payload")
    if rows[0] != ["observation_date", series_id]:
        raise FredError(
            f"FRED series {series_id!r}: unexpected header {rows[0]!r}; "
            "expected ['observation_date', series_id]"
        )
    observations: list[tuple[date, float]] = []
    missing_count = 0
    previous_date: date | None = None
    for row in rows[1:]:
        if len(row) != 2:
            raise FredError(
                f"FRED series {series_id!r}: malformed row {row!r}; "
                "expected exactly two columns"
            )
        try:
            observation_date = date.fromisoformat(row[0].strip())
        except ValueError as exc:
            raise FredError(
                f"FRED series {series_id!r}: bad observation date {row[0]!r}"
            ) from exc
        if previous_date is not None and observation_date <= previous_date:
            raise FredError(
                f"FRED series {series_id!r}: dates are not strictly "
                f"increasing ({previous_date} then {observation_date})"
            )
        previous_date = observation_date
        raw_value = row[1].strip()
        if raw_value in ("", "."):
            missing_count += 1
            continue
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise FredError(
                f"FRED series {series_id!r}: bad value {row[1]!r} on "
                f"{observation_date}"
            ) from exc
        if not math.isfinite(value):
            raise FredError(
                f"FRED series {series_id!r}: non-finite value {row[1]!r} on "
                f"{observation_date}"
            )
        observations.append((observation_date, value))
    if not observations:
        raise FredError(f"FRED series {series_id!r}: no observations in payload")
    return tuple(observations), missing_count


def _default_transport(url: str, *, timeout_seconds: float) -> bytes:
    # No User-Agent header: urllib's default ("Python-urllib/3.12") is
    # what FRED's edge accepts; see the note above FRED_CSV_URL.
    request = urllib.request.Request(url)
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
                raise FredError(
                    f"FRED request failed with HTTP {exc.code}: {url}"
                ) from exc
        except OSError as exc:
            # URLError and raw socket errors (TimeoutError, ConnectionError)
            # are transient network faults; urllib does not wrap every
            # socket error in URLError, so catch OSError broadly.
            if attempt >= max_retries:
                raise FredError(f"FRED request failed: {exc}") from exc
        attempt += 1
        delay = base_delay_seconds * (2 ** (attempt - 1))
        logger.warning(
            "FRED request failed; retrying in %.1fs (attempt %d)", delay, attempt
        )
        time.sleep(delay)


def fetch_series(
    series_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
) -> FredSeries:
    """Fetch one FRED series as dated values plus its raw payload.

    ``start`` and ``end`` bound the ``cosd``/``coed`` query parameters
    (inclusive dates). Without them the full history is returned. The
    60s default timeout reflects the endpoint's observed latency (up to
    ~12s for a single series CSV)."""
    if not _SERIES_ID_PATTERN.fullmatch(series_id):
        raise ValueError(f"invalid FRED series id: {series_id!r}")
    if start is not None and end is not None and end < start:
        raise ValueError("fetch end must not precede start")
    params: dict[str, str] = {"id": series_id}
    if start is not None:
        params["cosd"] = start.isoformat()
    if end is not None:
        params["coed"] = end.isoformat()
    url = f"{FRED_CSV_URL}?{urllib.parse.urlencode(params)}"
    payload = _fetch_url_with_retry(
        url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        base_delay_seconds=1.0,
        transport=transport,
    )
    observations, missing_count = parse_series_csv(payload, series_id=series_id)
    return FredSeries(
        series_id=series_id,
        observations=observations,
        missing_count=missing_count,
        url=url,
        payload=payload,
    )


def series_to_observations(
    series: FredSeries,
    *,
    instrument_id: str,
    venue: str,
    source_id: str,
    source_version: int,
    ingested_at: datetime,
    unit: str,
    field: str = "close",
) -> list[Observation]:
    """Convert dated FRED values to observations at the 21:00 UTC close.

    ``available_at`` equals the event time; FRED's publication lag is
    not modelled (see the module docstring).
    """
    ingested = require_utc(ingested_at)
    observations: list[Observation] = []
    for observation_date, value in series.observations:
        event_time = datetime.combine(
            observation_date, DAILY_CLOSE_UTC, tzinfo=UTC
        )
        observations.append(
            Observation(
                instrument_id=instrument_id,
                venue=venue,
                event_time=event_time,
                available_at=event_time,
                ingested_at=ingested,
                field=field,
                value=value,
                unit=unit,
                source_id=source_id,
                source_version=source_version,
            )
        )
    return observations
