"""OKX public REST funding-rate adapter (no credentials, read-only).

Covers ``/public/funding-rate-history`` (settled funding rates) and
``/public/funding-rate`` (the current period's rate, used for
cross-checks). Standard library only, same patterns as
``myquant.adapters.okx``.

Verified against the live API on 2026-11-19:

- History rows carry ``instId``, ``instType``, ``fundingRate``,
  ``realizedRate``, ``fundingTime`` (settlement time, UTC ms),
  ``method`` and ``formulaType``. On every row observed so far
  ``fundingRate == realizedRate`` and ``method == "current_period"``;
  the parser keeps both fields and the fetch report counts any
  divergence rather than assuming it.
- ``fundingTime`` is the settlement time: the row's rate is the rate
  settled at that time. Cross-checked live: the current-rate
  endpoint's ``settFundingRate`` for the interval ending
  2026-11-18T16:00:00Z equals the history row at that ``fundingTime``
  exactly, and its ``prevFundingTime`` is that same timestamp.
- Pagination uses ``after=<ms>`` as the backward cursor: it returns
  rows with ``fundingTime`` strictly older than the cursor, newest
  first, at most 100 per page. (Note: this is the opposite of the
  candles endpoint, where ``after`` pages backwards by timestamp in
  the same way — but on *this* endpoint ``before`` does NOT page
  backwards: verified live, ``before=<ts>`` returns rows strictly
  *newer* than the timestamp, i.e. it acts as a lower bound. The
  adapter pages with ``after`` only and never sends ``before``.)
- Reachable depth is about 93 days as of 2026-11-19 (oldest rows
  2026-08-17T16:00:00Z; 280 rows per instrument). The exact retention
  rule cannot be distinguished from a single pull — rolling window vs
  fixed floor — but a probe minutes before the fetch showed a 281st
  row (2026-08-17T08:00:00Z) for BTC and SOL that was gone by fetch
  time, consistent with a rolling window; the fetch report records
  the observed floor and the fetch date, and downstream users must
  not assume older history exists.
- The current-rate endpoint returns the rate for the interval in
  progress (``fundingRate``), the next settlement time
  (``nextFundingTime``), the last settled rate (``settFundingRate``)
  and the per-interval cap/floor (``maxFundingRate`` /
  ``minFundingRate``, +/-0.375%).

A positive funding rate means longs pay shorts at settlement. The
sign convention is documented again in ``myquant.execution.funding``,
which is where the series is consumed.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import Field, model_validator

from myquant.contracts import StrictContract, require_utc

logger = logging.getLogger(__name__)

PUBLIC_BASE_URL = "https://www.okx.com/api/v5/public"
FUNDING_HISTORY_PATH = "/funding-rate-history"
FUNDING_RATE_PATH = "/funding-rate"

#: ``funding-rate-history`` returns at most 100 rows per page.
MAX_FUNDING_PAGE_SIZE = 100


class OKXFundingError(Exception):
    """The OKX API returned an error payload or an unusable response."""


class OKXFundingRate(StrictContract):
    """One settled funding-rate row from ``funding-rate-history``.

    ``settlement_time`` is the funding settlement time (the row's
    ``fundingTime``); ``funding_rate`` is the rate settled at that
    time, per 8-hour interval (a decimal, e.g. 0.0001 = 0.01%).
    """

    instrument: str = Field(min_length=1)
    settlement_time: datetime
    funding_rate: float = Field(allow_inf_nan=False)
    realized_rate: float = Field(allow_inf_nan=False)
    method: str = Field(min_length=1)
    formula_type: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rate(self) -> OKXFundingRate:
        object.__setattr__(
            self, "settlement_time", require_utc(self.settlement_time)
        )
        return self


class OKXFundingRateCurrent(StrictContract):
    """The live funding-rate row from ``/public/funding-rate``."""

    instrument: str = Field(min_length=1)
    funding_rate: float = Field(allow_inf_nan=False)
    funding_time: datetime
    next_funding_time: datetime
    prev_funding_time: datetime | None = None
    settled_funding_rate: float | None = Field(default=None, allow_inf_nan=False)
    max_funding_rate: float = Field(allow_inf_nan=False)
    min_funding_rate: float = Field(allow_inf_nan=False)
    interest_rate: float = Field(allow_inf_nan=False)
    premium: float = Field(allow_inf_nan=False)
    timestamp: datetime

    @model_validator(mode="after")
    def validate_times(self) -> OKXFundingRateCurrent:
        object.__setattr__(self, "funding_time", require_utc(self.funding_time))
        object.__setattr__(
            self, "next_funding_time", require_utc(self.next_funding_time)
        )
        if self.prev_funding_time is not None:
            object.__setattr__(
                self, "prev_funding_time", require_utc(self.prev_funding_time)
            )
        object.__setattr__(self, "timestamp", require_utc(self.timestamp))
        return self


@dataclass(frozen=True)
class FetchedPage:
    """One raw HTTP response kept for provenance and re-verification."""

    url: str
    payload: bytes


@dataclass(frozen=True)
class FundingHistoryFetch:
    """Settled funding rates plus the raw pages they were parsed from."""

    rates: tuple[OKXFundingRate, ...]
    pages: tuple[FetchedPage, ...]


def _decode_response(payload: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OKXFundingError(f"OKX response is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise OKXFundingError("OKX response is not a JSON object")
    if decoded.get("code") != "0":
        raise OKXFundingError(
            f"OKX API error code={decoded.get('code')!r} "
            f"msg={decoded.get('msg')!r}"
        )
    return decoded


def _parse_history_row(row: Any, *, inst_id: str) -> OKXFundingRate:
    if not isinstance(row, dict):
        raise OKXFundingError(f"OKX funding row is not an object: {row!r}")
    if row.get("instId") != inst_id:
        raise OKXFundingError(
            f"OKX funding row is for {row.get('instId')!r}, expected {inst_id!r}"
        )
    try:
        settlement_ms = int(row["fundingTime"])
        funding_rate = float(row["fundingRate"])
        realized_rate = float(row["realizedRate"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OKXFundingError(f"OKX funding row has bad fields: {row!r}") from exc
    method = row.get("method")
    formula_type = row.get("formulaType")
    if not isinstance(method, str) or not method:
        raise OKXFundingError(f"OKX funding row has bad method: {row!r}")
    if not isinstance(formula_type, str) or not formula_type:
        raise OKXFundingError(f"OKX funding row has bad formulaType: {row!r}")
    try:
        return OKXFundingRate(
            instrument=inst_id,
            settlement_time=datetime.fromtimestamp(settlement_ms / 1000, tz=UTC),
            funding_rate=funding_rate,
            realized_rate=realized_rate,
            method=method,
            formula_type=formula_type,
        )
    except ValueError as exc:
        raise OKXFundingError(f"OKX funding row failed validation: {exc}") from exc


def parse_funding_history_response(
    payload: bytes,
    *,
    inst_id: str,
) -> tuple[OKXFundingRate, ...]:
    """Parse one funding-history response into validated rows, oldest first.

    Pure (no network access) so tests can run it against frozen
    fixtures. Rows are expected newest-first by settlement time, as
    the API returns them; a page that violates that order, or that
    repeats a settlement time, is rejected outright rather than
    silently re-sorted, because the pagination cursor depends on it.
    """
    decoded = _decode_response(payload)
    rows = decoded.get("data")
    if not isinstance(rows, list):
        raise OKXFundingError("OKX response has no 'data' list")

    rates: list[OKXFundingRate] = []
    previous_ms: int | None = None
    for row in rows:
        rate = _parse_history_row(row, inst_id=inst_id)
        settlement_ms = int(rate.settlement_time.timestamp() * 1000)
        if previous_ms is not None and settlement_ms >= previous_ms:
            raise OKXFundingError(
                "OKX funding rows are not in newest-first order; "
                "refusing to guess the pagination order"
            )
        previous_ms = settlement_ms
        rates.append(rate)

    rates.sort(key=lambda item: item.settlement_time)
    seen: set[datetime] = set()
    for rate in rates:
        if rate.settlement_time in seen:
            raise OKXFundingError(
                "duplicate OKX funding settlement time: "
                f"{rate.settlement_time.isoformat()}"
            )
        seen.add(rate.settlement_time)
    return tuple(rates)


def parse_funding_rate_response(
    payload: bytes,
    *,
    inst_id: str,
) -> OKXFundingRateCurrent:
    """Parse one funding-rate (current) response. Pure (no network)."""
    decoded = _decode_response(payload)
    rows = decoded.get("data")
    if not isinstance(rows, list) or len(rows) != 1:
        raise OKXFundingError(
            "OKX funding-rate response must contain exactly one row"
        )
    row = rows[0]
    if not isinstance(row, dict):
        raise OKXFundingError("OKX funding-rate row is not an object")
    try:
        funding_rate = float(row["fundingRate"])
        funding_ms = int(row["fundingTime"])
        next_ms = int(row["nextFundingTime"])
        max_rate = float(row["maxFundingRate"])
        min_rate = float(row["minFundingRate"])
        interest_rate = float(row["interestRate"])
        premium = float(row["premium"])
        ts_ms = int(row["ts"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OKXFundingError(f"OKX funding-rate row has bad fields: {row!r}") from exc
    prev_raw = row.get("prevFundingTime")
    settled_raw = row.get("settFundingRate")
    try:
        prev_time = (
            datetime.fromtimestamp(int(prev_raw) / 1000, tz=UTC)
            if prev_raw not in (None, "")
            else None
        )
        settled_rate = float(settled_raw) if settled_raw not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise OKXFundingError(
            f"OKX funding-rate row has bad prev/settled fields: {row!r}"
        ) from exc
    try:
        return OKXFundingRateCurrent(
            instrument=inst_id,
            funding_rate=funding_rate,
            funding_time=datetime.fromtimestamp(funding_ms / 1000, tz=UTC),
            next_funding_time=datetime.fromtimestamp(next_ms / 1000, tz=UTC),
            prev_funding_time=prev_time,
            settled_funding_rate=settled_rate,
            max_funding_rate=max_rate,
            min_funding_rate=min_rate,
            interest_rate=interest_rate,
            premium=premium,
            timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
        )
    except ValueError as exc:
        raise OKXFundingError(f"OKX funding-rate row failed validation: {exc}") from exc


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
                raise OKXFundingError(
                    f"OKX request failed with HTTP {exc.code}: {url}"
                ) from exc
        except urllib.error.URLError as exc:
            if attempt >= max_retries:
                raise OKXFundingError(f"OKX request failed: {exc.reason}") from exc
        attempt += 1
        delay = base_delay_seconds * (2 ** (attempt - 1))
        logger.warning("OKX request failed; retrying in %.1fs (attempt %d)", delay, attempt)
        time.sleep(delay)


def fetch_funding_history(
    inst_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    page_size: int = MAX_FUNDING_PAGE_SIZE,
    delay_seconds: float = 0.2,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    max_pages: int | None = None,
    transport: Callable[[str], bytes] | None = None,
    on_page: Callable[[FetchedPage], None] | None = None,
) -> FundingHistoryFetch:
    """Fetch settled funding rates, newest first, paged backwards.

    Pages ``after=<oldest settlement>`` backwards from the live head
    until the endpoint returns an empty page (the reachable depth,
    about 93 days as of 2026-11-19) or, with a ``start``, once the
    oldest fetched row is at or before ``start``. Rows are returned
    in ascending settlement-time order plus the raw response bytes
    of every page, so the caller can store exact provenance. ``end``
    (when given) drops rows at or after it; rows are settlement times
    in [start, end).

    ``on_page`` is called with each raw page as soon as it is fetched
    and parsed, so long pulls can persist pages incrementally instead
    of holding everything in memory until the end.
    """
    start_utc = require_utc(start) if start is not None else None
    end_utc = require_utc(end) if end is not None else None
    if start_utc is not None and end_utc is not None and end_utc <= start_utc:
        raise ValueError("fetch end must be after start")
    if page_size < 1 or page_size > MAX_FUNDING_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_FUNDING_PAGE_SIZE}")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")
    if max_pages is not None and max_pages < 1:
        raise ValueError("max_pages must be at least 1")

    pages: list[FetchedPage] = []
    collected: dict[datetime, OKXFundingRate] = {}
    cursor_ms: int | None = None
    while True:
        url = (
            f"{PUBLIC_BASE_URL}{FUNDING_HISTORY_PATH}"
            f"?instId={inst_id}&limit={page_size}"
        )
        if cursor_ms is not None:
            url += f"&after={cursor_ms}"
        payload = _fetch_url_with_retry(
            url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            base_delay_seconds=1.0,
            transport=transport,
        )
        fetched_page = FetchedPage(url=url, payload=payload)
        pages.append(fetched_page)
        rows = parse_funding_history_response(payload, inst_id=inst_id)
        if on_page is not None:
            on_page(fetched_page)
        if not rows:
            break
        for rate in rows:
            if start_utc is not None and rate.settlement_time < start_utc:
                continue
            if end_utc is not None and rate.settlement_time >= end_utc:
                continue
            collected[rate.settlement_time] = rate
        oldest = rows[0].settlement_time
        if start_utc is not None and oldest <= start_utc:
            break
        if max_pages is not None and len(pages) >= max_pages:
            break
        next_cursor = int(oldest.timestamp() * 1000)
        if cursor_ms is not None and next_cursor >= cursor_ms:
            raise OKXFundingError("OKX pagination did not advance; refusing to loop")
        cursor_ms = next_cursor
        if delay_seconds:
            time.sleep(delay_seconds)

    ordered = tuple(collected[key] for key in sorted(collected))
    return FundingHistoryFetch(rates=ordered, pages=tuple(pages))


def fetch_current_funding_rate(
    inst_id: str,
    *,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
) -> tuple[OKXFundingRateCurrent, FetchedPage]:
    """Fetch the live funding-rate row (current period + last settled)."""
    url = f"{PUBLIC_BASE_URL}{FUNDING_RATE_PATH}?instId={inst_id}"
    payload = _fetch_url_with_retry(
        url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        base_delay_seconds=1.0,
        transport=transport,
    )
    return parse_funding_rate_response(payload, inst_id=inst_id), FetchedPage(
        url=url, payload=payload
    )
