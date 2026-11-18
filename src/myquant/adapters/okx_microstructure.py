"""OKX public REST microstructure adapter: trades, books, ticker.

Read-only, no credentials. Covers the trade/quote endpoints the candle
adapter does not: ``/market/trades``, ``/market/history-trades``,
``/market/books`` and ``/market/ticker``.

Verified against the live API on 2026-11-18:

- Trade rows are JSON objects with ``instId``, ``tradeId``, ``px``,
  ``sz``, ``side``, ``ts`` and ``source``. ``side`` is the **taker**
  side (``buy``/``sell``); it says nothing about trader identity or
  intent. ``ts`` is the match time in UTC milliseconds. ``source`` is
  ``"0"`` on every row observed.
- ``history-trades`` paginates backwards with ``after=<tradeId>`` and
  returns trades with strictly smaller trade IDs, newest first, at most
  100 per page. Trade IDs are contiguous (no gaps observed between
  consecutive pages), so the cursor advances by exactly the page size.
- The oldest trade retrievable through ``history-trades`` for
  BTC-USDT-SWAP is trade 2843636428, dated 2026-08-20 00:01:56 UTC —
  a rolling window of about 90 days, verified by bisection on 2026-11-18
  (see ``docs/microstructure.md``). Pulling the full window through
  REST is infeasible (~300M trades); use a bounded recent window or a
  forward recorder instead.
- Book levels are 4-element arrays ``[price, size, "0", order_count]``:
  the third element is deprecated and always ``"0"``; the fourth is the
  number of orders at that price. Asks arrive ascending, bids
  descending. Snapshots carry a ``seqId`` (monotonic per instrument)
  and a millisecond ``ts``.
- The ticker's best bid/ask prices match the books snapshot's best
  bid/ask (sizes may differ by a few hundred milliseconds of book
  movement between the two calls).

Row-level problems in a trades page (bad side, non-positive price or
size, unparseable fields, wrong instrument, duplicate trade ID) are
collected as rejections instead of raising, so one bad row cannot kill
a 100-row page; the caller must count them. Payload-level problems
(bad JSON, non-zero API code, ``data`` not a list, broken pagination
order) raise :class:`OKXMicrostructureError`.
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
from typing import Any, Literal

from pydantic import Field

from myquant.adapters.okx import BASE_URL
from myquant.contracts import StrictContract, require_utc

logger = logging.getLogger(__name__)

TRADES_PATH = "/trades"
HISTORY_TRADES_PATH = "/history-trades"
BOOKS_PATH = "/books"
TICKER_PATH = "/ticker"

#: ``history-trades`` returns at most 100 rows per page.
MAX_TRADES_PAGE_SIZE = 100
#: ``books`` accepts ``sz`` between 1 and 400.
MAX_BOOK_DEPTH = 400


class OKXMicrostructureError(Exception):
    """The OKX API returned an error payload or an unusable response."""


class OKXTrade(StrictContract):
    """One validated OKX trade (taker side only)."""

    instrument: str = Field(min_length=1)
    trade_id: int = Field(ge=0)
    event_time: datetime
    price: float = Field(gt=0, allow_inf_nan=False)
    size: float = Field(gt=0, allow_inf_nan=False)
    side: Literal["buy", "sell"]
    source: str = Field(default="0")


@dataclass(frozen=True)
class RejectedTradeRow:
    """One trade row that failed validation, kept for counting."""

    row_json: str
    reason: str


@dataclass(frozen=True)
class TradesPage:
    """Parsed trades from one response page, oldest first."""

    trades: tuple[OKXTrade, ...]
    rejected: tuple[RejectedTradeRow, ...]


@dataclass(frozen=True)
class FetchedPage:
    """One raw HTTP response kept for provenance and re-verification."""

    url: str
    payload: bytes


@dataclass(frozen=True)
class TradesFetch:
    """Trades in [start, end) plus raw pages and rejection counts."""

    trades: tuple[OKXTrade, ...]
    pages: tuple[FetchedPage, ...]
    rejected: tuple[RejectedTradeRow, ...]
    skipped_after_end: int


class OKXBookLevel(StrictContract):
    """One price level of an OKX order-book snapshot."""

    price: float = Field(gt=0, allow_inf_nan=False)
    size: float = Field(ge=0, allow_inf_nan=False)
    order_count: int = Field(ge=0)


class OKXBookSnapshot(StrictContract):
    """One validated OKX order-book snapshot."""

    instrument: str = Field(min_length=1)
    snapshot_time: datetime
    seq_id: int = Field(ge=0)
    asks: tuple[OKXBookLevel, ...]
    bids: tuple[OKXBookLevel, ...]


class OKXTicker(StrictContract):
    """Best bid/ask/last from the OKX ticker endpoint."""

    instrument: str = Field(min_length=1)
    ticker_time: datetime
    bid_price: float = Field(gt=0, allow_inf_nan=False)
    bid_size: float = Field(ge=0, allow_inf_nan=False)
    ask_price: float = Field(gt=0, allow_inf_nan=False)
    ask_size: float = Field(ge=0, allow_inf_nan=False)
    last_price: float = Field(gt=0, allow_inf_nan=False)


def _decode_response(payload: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OKXMicrostructureError(f"OKX response is not valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise OKXMicrostructureError("OKX response is not a JSON object")
    if decoded.get("code") != "0":
        raise OKXMicrostructureError(
            f"OKX API error code={decoded.get('code')!r} "
            f"msg={decoded.get('msg')!r}"
        )
    return decoded


def _parse_trade_row(row: Any, *, inst_id: str) -> OKXTrade:
    if not isinstance(row, dict):
        raise OKXMicrostructureError(f"OKX trade row is not an object: {row!r}")
    if row.get("instId") != inst_id:
        raise OKXMicrostructureError(
            f"OKX trade row is for {row.get('instId')!r}, expected {inst_id!r}"
        )
    try:
        trade_id = int(row["tradeId"])
        event_ms = int(row["ts"])
        price = float(row["px"])
        size = float(row["sz"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OKXMicrostructureError(f"OKX trade row has bad fields: {row!r}") from exc
    side = row.get("side")
    if side not in ("buy", "sell"):
        raise OKXMicrostructureError(f"OKX trade row has bad side: {row!r}")
    try:
        return OKXTrade(
            instrument=inst_id,
            trade_id=trade_id,
            event_time=datetime.fromtimestamp(event_ms / 1000, tz=UTC),
            price=price,
            size=size,
            side=side,
            source=str(row.get("source", "0")),
        )
    except ValueError as exc:
        raise OKXMicrostructureError(f"OKX trade failed validation: {exc}") from exc


def parse_trades_response(
    payload: bytes,
    *,
    inst_id: str,
) -> TradesPage:
    """Parse one OKX trades response into validated trades, oldest first.

    Pure (no network access) so tests can run it against frozen
    fixtures. Rows are expected newest-first by trade ID, as the API
    returns them; a page that violates that order is rejected outright
    rather than silently re-sorted, because the pagination cursor
    depends on the order. Individual bad rows are collected as
    rejections; the caller must count them.
    """
    decoded = _decode_response(payload)
    rows = decoded.get("data")
    if not isinstance(rows, list):
        raise OKXMicrostructureError("OKX response has no 'data' list")

    trades: list[OKXTrade] = []
    rejected: list[RejectedTradeRow] = []
    seen_ids: set[int] = set()
    previous_id: int | None = None
    for row in rows:
        try:
            trade = _parse_trade_row(row, inst_id=inst_id)
        except OKXMicrostructureError as exc:
            rejected.append(
                RejectedTradeRow(
                    row_json=json.dumps(row, sort_keys=True, default=str),
                    reason=str(exc),
                )
            )
            continue
        if trade.trade_id in seen_ids:
            rejected.append(
                RejectedTradeRow(
                    row_json=json.dumps(row, sort_keys=True, default=str),
                    reason=f"duplicate trade_id {trade.trade_id} within page",
                )
            )
            continue
        if previous_id is not None and trade.trade_id >= previous_id:
            raise OKXMicrostructureError(
                "OKX trades are not in newest-first trade-ID order; "
                "refusing to guess the pagination order"
            )
        previous_id = trade.trade_id
        seen_ids.add(trade.trade_id)
        trades.append(trade)

    trades.sort(key=lambda item: item.trade_id)
    return TradesPage(trades=tuple(trades), rejected=tuple(rejected))


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
                raise OKXMicrostructureError(
                    f"OKX request failed with HTTP {exc.code}: {url}"
                ) from exc
        except urllib.error.URLError as exc:
            if attempt >= max_retries:
                raise OKXMicrostructureError(f"OKX request failed: {exc.reason}") from exc
        attempt += 1
        delay = base_delay_seconds * (2 ** (attempt - 1))
        logger.warning("OKX request failed; retrying in %.1fs (attempt %d)", delay, attempt)
        time.sleep(delay)


def fetch_trades_history(
    inst_id: str,
    *,
    start: datetime,
    end: datetime,
    page_size: int = MAX_TRADES_PAGE_SIZE,
    delay_seconds: float = 0.1,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
    on_page: Callable[[FetchedPage], None] | None = None,
) -> TradesFetch:
    """Fetch trades with event times in [start, end).

    Pages ``/market/history-trades`` backwards from the most recent
    trade until the requested start is covered. Returns trades in
    ascending time order plus the raw response bytes of every page, so
    the caller can store exact provenance. Trades newer than ``end``
    (fetched only because paging starts at the live head) are counted
    in ``skipped_after_end`` and dropped.

    ``on_page`` is called with each raw page as soon as it is fetched
    and parsed, so long pulls can persist pages incrementally instead
    of holding everything in memory until the end.
    """
    start_utc = require_utc(start)
    end_utc = require_utc(end)
    if end_utc <= start_utc:
        raise ValueError("fetch end must be after start")
    if page_size < 1 or page_size > MAX_TRADES_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_TRADES_PAGE_SIZE}")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")

    pages: list[FetchedPage] = []
    rejected: list[RejectedTradeRow] = []
    collected: dict[int, OKXTrade] = {}
    skipped_after_end = 0
    cursor: int | None = None
    while True:
        url = (
            f"{BASE_URL}{HISTORY_TRADES_PATH}?instId={inst_id}&limit={page_size}"
        )
        if cursor is not None:
            url += f"&after={cursor}"
        payload = _fetch_url_with_retry(
            url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            base_delay_seconds=1.0,
            transport=transport,
        )
        fetched_page = FetchedPage(url=url, payload=payload)
        pages.append(fetched_page)
        page = parse_trades_response(payload, inst_id=inst_id)
        if on_page is not None:
            on_page(fetched_page)
        rejected.extend(page.rejected)
        if not page.trades:
            break
        for trade in page.trades:
            if trade.event_time >= end_utc:
                skipped_after_end += 1
            elif trade.event_time >= start_utc:
                collected[trade.trade_id] = trade
        oldest = page.trades[0]
        if oldest.event_time < start_utc:
            break
        next_cursor = oldest.trade_id
        if cursor is not None and next_cursor >= cursor:
            raise OKXMicrostructureError(
                "OKX trade pagination did not advance; refusing to loop"
            )
        cursor = next_cursor
        if delay_seconds:
            time.sleep(delay_seconds)

    ordered = tuple(
        collected[key]
        for key in sorted(collected, key=lambda tid: (collected[tid].event_time, tid))
    )
    return TradesFetch(
        trades=ordered,
        pages=tuple(pages),
        rejected=tuple(rejected),
        skipped_after_end=skipped_after_end,
    )


def _parse_book_level(level: Any) -> OKXBookLevel:
    if not isinstance(level, list) or len(level) != 4:
        raise OKXMicrostructureError(
            "OKX book level must have 4 elements "
            "[price, size, deprecated, order_count]"
        )
    price_raw, size_raw, deprecated, orders_raw = level
    if deprecated != "0":
        raise OKXMicrostructureError(
            "OKX book level third element is not '0' (deprecated field changed); "
            f"refusing to guess the level format: {level!r}"
        )
    try:
        price = float(price_raw)
        size = float(size_raw)
        order_count = int(orders_raw)
    except (TypeError, ValueError) as exc:
        raise OKXMicrostructureError(
            f"OKX book level has non-numeric fields: {level!r}"
        ) from exc
    try:
        return OKXBookLevel(price=price, size=size, order_count=order_count)
    except ValueError as exc:
        raise OKXMicrostructureError(f"OKX book level failed validation: {exc}") from exc


def parse_books_response(
    payload: bytes,
    *,
    inst_id: str,
) -> OKXBookSnapshot:
    """Parse one OKX books response into a validated snapshot.

    Pure (no network access). Asks must arrive ascending and bids
    descending by price, as the API returns them; a snapshot that
    violates that order is rejected outright.
    """
    decoded = _decode_response(payload)
    rows = decoded.get("data")
    if not isinstance(rows, list) or len(rows) != 1:
        raise OKXMicrostructureError(
            "OKX books response must contain exactly one snapshot"
        )
    row = rows[0]
    if not isinstance(row, dict):
        raise OKXMicrostructureError("OKX books snapshot is not an object")
    try:
        snapshot_ms = int(row["ts"])
        seq_id = int(row["seqId"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OKXMicrostructureError(
            f"OKX books snapshot has bad ts/seqId: {row!r}"
        ) from exc
    asks = tuple(_parse_book_level(level) for level in row.get("asks", []))
    bids = tuple(_parse_book_level(level) for level in row.get("bids", []))
    ask_prices = [level.price for level in asks]
    bid_prices = [level.price for level in bids]
    if ask_prices != sorted(ask_prices) or len(set(ask_prices)) != len(ask_prices):
        raise OKXMicrostructureError("OKX asks are not strictly ascending by price")
    if bid_prices != sorted(bid_prices, reverse=True) or (
        len(set(bid_prices)) != len(bid_prices)
    ):
        raise OKXMicrostructureError("OKX bids are not strictly descending by price")
    try:
        return OKXBookSnapshot(
            instrument=inst_id,
            snapshot_time=datetime.fromtimestamp(snapshot_ms / 1000, tz=UTC),
            seq_id=seq_id,
            asks=asks,
            bids=bids,
        )
    except ValueError as exc:
        raise OKXMicrostructureError(f"OKX book snapshot failed validation: {exc}") from exc


def fetch_books_snapshot(
    inst_id: str,
    *,
    depth: int = 5,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
) -> tuple[OKXBookSnapshot, FetchedPage]:
    """Fetch one order-book snapshot at the requested depth."""
    if depth < 1 or depth > MAX_BOOK_DEPTH:
        raise ValueError(f"depth must be between 1 and {MAX_BOOK_DEPTH}")
    url = f"{BASE_URL}{BOOKS_PATH}?instId={inst_id}&sz={depth}"
    payload = _fetch_url_with_retry(
        url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        base_delay_seconds=1.0,
        transport=transport,
    )
    return parse_books_response(payload, inst_id=inst_id), FetchedPage(
        url=url, payload=payload
    )


def parse_ticker_response(
    payload: bytes,
    *,
    inst_id: str,
) -> OKXTicker:
    """Parse one OKX ticker response. Pure (no network access)."""
    decoded = _decode_response(payload)
    rows = decoded.get("data")
    if not isinstance(rows, list) or len(rows) != 1:
        raise OKXMicrostructureError("OKX ticker response must contain exactly one row")
    row = rows[0]
    if not isinstance(row, dict):
        raise OKXMicrostructureError("OKX ticker row is not an object")
    try:
        ticker_ms = int(row["ts"])
        bid_price = float(row["bidPx"])
        bid_size = float(row["bidSz"])
        ask_price = float(row["askPx"])
        ask_size = float(row["askSz"])
        last_price = float(row["last"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OKXMicrostructureError(f"OKX ticker row has bad fields: {row!r}") from exc
    try:
        return OKXTicker(
            instrument=inst_id,
            ticker_time=datetime.fromtimestamp(ticker_ms / 1000, tz=UTC),
            bid_price=bid_price,
            bid_size=bid_size,
            ask_price=ask_price,
            ask_size=ask_size,
            last_price=last_price,
        )
    except ValueError as exc:
        raise OKXMicrostructureError(f"OKX ticker failed validation: {exc}") from exc


def fetch_ticker(
    inst_id: str,
    *,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
    transport: Callable[[str], bytes] | None = None,
) -> tuple[OKXTicker, FetchedPage]:
    """Fetch the current ticker (best bid/ask/last) for cross-checks."""
    url = f"{BASE_URL}{TICKER_PATH}?instId={inst_id}"
    payload = _fetch_url_with_retry(
        url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        base_delay_seconds=1.0,
        transport=transport,
    )
    return parse_ticker_response(payload, inst_id=inst_id), FetchedPage(
        url=url, payload=payload
    )
