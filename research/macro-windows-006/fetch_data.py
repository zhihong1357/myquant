"""Fetch OKX panels and the Treasury auction calendar for study 006.

Run after preregistration, from the repo root:

    .venv/bin/python research/macro-windows-006/fetch_data.py

Pulls daily candles (2021-01-21 to 2026-11-18) and 1H candles
(2025-01-02 to 2026-11-18) for BTC/ETH/SOL perpetuals from OKX public
REST, mirroring research/options-expiry-004/fetch_data.py. Raw response
pages go to the gitignored cache under data/cache/macro-windows-006/raw/
(content-addressed RawStore); parsed confirmed candles become
observations in data/cache/macro-windows-006/pit-1d/ and pit-1h/
(ParquetPITStore, one store per frequency — daily and hourly
observations share event times but carry different values).

The macro calendars are validated here, not fetched:

- CPI: the committed research/macro-windows-006/cpi_calendar.json
  (extracted from BLS schedule pages by text fetch; BLS returns HTTP
  403 to direct connections). Validated for counts (71 releases),
  known dates (2026-11-10, the delayed 2025-10-24 release) and
  reference-month continuity.
- FOMC: research/fomc-event-study-005/fomc_calendar.json (reused from
  study 005). Validated for the 48 scheduled statements in 2021-2026.
- Treasury auctions: fetched from the U.S. Treasury Fiscal Data API
  (auctions_query, v1) for auction_date 2021-01-01 to 2026-11-18 and
  cross-checked against the TreasuryDirect `auctioned` endpoint. The
  Fiscal Data API lags the live schedule by about four weeks (latest
  record 2026-10-22 at fetch time), so recent coupon auction dates are
  taken from the TreasuryDirect listing and recorded as the tail
  supplement. Auction days are descriptive only; they never enter the
  main macro window.

Only the manifest (endpoints, parameters, date ranges, payload
SHA-256, calendar verification), the panel summary (counts only, no
raw prices) and the extracted Treasury auction calendar (public
schedule data, a small JSON file) are written into this research
directory for commit. Raw payloads and parquet never leave the local
cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from myquant.adapters.okx import (
    BAR_DURATIONS,
    candles_to_observations,
    fetch_history,
    parse_candles_response,
)
from myquant.pit import ParquetPITStore
from myquant.quality import SeriesKey, inspect_observations
from myquant.raw import RawStore
from myquant.sources import SourceRegistry
from myquant.studies.macro import (
    annual_counts,
    build_macro_window,
    load_auction_calendar,
    load_cpi_calendar,
    load_fomc_statement_dates,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "macro-windows-006"
STUDY_005_ROOT = REPO_ROOT / "research" / "fomc-event-study-005"

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
FISCALDATA_SOURCE_ID = "fiscaldata"
FISCALDATA_SOURCE_VERSION = 1
OKX_VENUE = "okx"

# Instrument ids match research/macro-windows-006/preregister.py (single
# source of truth is the committed catalog under
# research/macro-windows-006/catalog/).
INSTRUMENTS: dict[str, str] = {
    "crypto:btc-usdt-perp": "BTC-USDT-SWAP",
    "crypto:eth-usdt-perp": "ETH-USDT-SWAP",
    "crypto:sol-usdt-perp": "SOL-USDT-SWAP",
}

DAILY_START = datetime(2021, 1, 21, 16, 0, tzinfo=UTC)
DAILY_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
HOURLY_START = datetime(2025, 1, 2, 0, 0, tzinfo=UTC)
HOURLY_END = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)

OKX_FETCH_PLAN: tuple[tuple[str, str, datetime, datetime], ...] = (
    ("crypto:btc-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:eth-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:sol-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:btc-usdt-perp", "1H", HOURLY_START, HOURLY_END),
    ("crypto:eth-usdt-perp", "1H", HOURLY_START, HOURLY_END),
    ("crypto:sol-usdt-perp", "1H", HOURLY_START, HOURLY_END),
)

FIELDS = ("open", "high", "low", "close", "volume")

# CPI calendar expectations (committed file, validated here).
EXPECTED_CPI_RELEASES = 71
EXPECTED_CPI_KNOWN_DATES: tuple[date, ...] = (
    date(2026, 11, 10),  # October 2026 CPI (the pre-study spot check)
    date(2025, 10, 24),  # September 2025 CPI, delayed by the shutdown
    date(2021, 1, 13),  # first release in the calendar
    date(2026, 12, 10),  # last release in the calendar
)
EXPECTED_CPI_NOT_PUBLISHED = "2025-10"  # October 2025 CPI, never published

# FOMC calendar expectations (study 005 file, reused here).
EXPECTED_FOMC_STATEMENTS_2021_2026 = 48
EXPECTED_FOMC_KNOWN_DATES: tuple[date, ...] = (
    date(2021, 1, 27),  # first statement in the sample
    date(2026, 10, 28),  # most recent statement before the study
)

# Macro-window counts asserted from the committed calendars (same
# numbers preregister.py verifies before registering the hypotheses).
EXPECTED_WINDOW_BARS_IN_SAMPLE = 116
EXPECTED_CPI_BARS_IN_SAMPLE = 69
EXPECTED_FOMC_BARS_IN_SAMPLE = 47
EXPECTED_OVERLAP_BARS_TOTAL = 1

# Treasury auction calendar (Fiscal Data API, v1).
AUCTION_START = date(2021, 1, 1)
AUCTION_END = date(2026, 11, 18)
FISCALDATA_BASE_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
    "/v1/accounting/od/auctions_query"
)
TREASURYDIRECT_AUCTIONED_URL = (
    "https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json"
)
AUCTION_PAGE_SIZE = 100
# Coupon-bearing securities only: bills auction weekly and are not
# event days. TIPS are Notes (inflation_index_security == "Yes") and
# stay in; they are still scheduled coupon auctions.
COUPON_TYPES = frozenset({"Note", "Bond"})
# Wide sanity bounds on distinct coupon auction days per year (a real
# year runs ~100-120). These catch gross parse/fetch errors only; the
# cross-check against TreasuryDirect is the real verification.
MIN_COUPON_DAYS_FULL_YEAR = 80
MAX_COUPON_DAYS_FULL_YEAR = 140
MIN_COUPON_DAYS_2026 = 70  # partial year, through the fetch date


def _fetch_url(url: str, *, timeout_seconds: float = 60.0) -> bytes:
    """Fetch one URL with retries (mirrors study 005's helper)."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "myquant-research/0.1"}
    )
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= 3:
                raise RuntimeError(
                    f"fetch failed with HTTP {exc.code}: {url}"
                ) from exc
        except OSError as exc:
            if attempt >= 3:
                raise RuntimeError(f"fetch failed: {url}: {exc}") from exc
        attempt += 1
        delay = 1.0 * (2 ** (attempt - 1))
        logger.warning("fetch failed; retrying in %.1fs (attempt %d)", delay, attempt)
        time.sleep(delay)


def expected_confirmed_opens(
    start: datetime,
    end: datetime,
    bar: str,
    as_of: datetime,
) -> list[datetime]:
    """Grid opens in [start, end) whose bar had closed by `as_of`."""
    step = timedelta(seconds=BAR_DURATIONS[bar])
    opens: list[datetime] = []
    current = start
    while current < end:
        if current + step <= as_of:
            opens.append(current)
        current += step
    return opens


def pit_store_for(name: str, source_registry: SourceRegistry) -> ParquetPITStore:
    """One PIT store per frequency.

    Daily and hourly observations share event times (every daily bar
    opens at 16:00 UTC, which is also an hourly bar open) but carry
    different values, so they must never sit in the same store: PIT
    revision resolution keys on (instrument, venue, field, event_time,
    source, version) and would silently collapse the hourly value into
    the daily one. Frequency is part of the dataset identity, not the
    observation.
    """
    return ParquetPITStore(CACHE_ROOT / name, source_registry)


def fetch_okx_one(
    instrument_id: str,
    bar: str,
    start: datetime,
    end: datetime,
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict:
    okx_inst_id = INSTRUMENTS[instrument_id]
    result = fetch_history(
        okx_inst_id,
        bar,
        start=start,
        end=end,
        delay_seconds=0.25,
    )
    page_entries: list[dict[str, str]] = []
    for page in result.pages:
        page_candles = parse_candles_response(
            page.payload,
            inst_id=okx_inst_id,
            bar=bar,
        )
        confirmed = [candle for candle in page_candles if candle.confirmed]
        record = raw_store.put(
            page.payload,
            source_id=OKX_SOURCE_ID,
            available_at=fetched_at,
            content_type="application/json",
            source_version=OKX_SOURCE_VERSION,
            event_time=confirmed[-1].open_time if confirmed else None,
            ingested_at=fetched_at,
        )
        page_entries.append(
            {
                "url": page.url,
                "payload_sha256": record.payload_sha256,
                "record_id": record.record_id,
            }
        )
    observations = candles_to_observations(
        result.candles,
        instrument_id=instrument_id,
        venue=OKX_VENUE,
        source_id=OKX_SOURCE_ID,
        source_version=OKX_SOURCE_VERSION,
        ingested_at=fetched_at,
    )
    parquet_path = pit_store.write_batch(observations)
    expected = expected_confirmed_opens(start, end, bar, fetched_at)
    fetched_opens = {candle.open_time for candle in result.candles}
    missing = [open_time for open_time in expected if open_time not in fetched_opens]
    return {
        "instrument_id": instrument_id,
        "okx_inst_id": okx_inst_id,
        "bar": bar,
        "endpoint": "https://www.okx.com/api/v5/market/history-candles",
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "candles": len(result.candles),
        "first_bar_open": (
            result.candles[0].open_time.isoformat() if result.candles else None
        ),
        "last_bar_open": (
            result.candles[-1].open_time.isoformat() if result.candles else None
        ),
        "expected_confirmed_bars": len(expected),
        "missing_bars": len(missing),
        "missing_bar_opens": [item.isoformat() for item in missing],
        "pages": page_entries,
        "pit_store": f"pit-{bar.lower()}",
        "pit_parquet": parquet_path.name,
        "pit_parquet_sha256": parquet_path.stem,
        "observation_rows": len(observations),
    }


def validate_committed_calendars() -> dict:
    """Validate the CPI and FOMC calendars and the window counts.

    Coverage only: counts and known dates, no result-level information.
    Raises on any mismatch — the calendars are preregistered inputs, so
    a change here is a hard stop, not something to paper over.
    """
    cpi_path = ROOT / "cpi_calendar.json"
    fomc_path = STUDY_005_ROOT / "fomc_calendar.json"
    cpi_document = json.loads(cpi_path.read_text(encoding="utf-8"))
    fomc_document = json.loads(fomc_path.read_text(encoding="utf-8"))
    releases = load_cpi_calendar(cpi_document)
    release_dates = [release.release_date for release in releases]
    if len(releases) != EXPECTED_CPI_RELEASES:
        raise ValueError(
            f"CPI calendar: expected {EXPECTED_CPI_RELEASES} releases, "
            f"found {len(releases)}"
        )
    for known in EXPECTED_CPI_KNOWN_DATES:
        if known not in release_dates:
            raise ValueError(f"CPI calendar: missing known release {known}")
    not_published = [
        entry["reference_month"] for entry in cpi_document.get("not_published", [])
    ]
    if EXPECTED_CPI_NOT_PUBLISHED not in not_published:
        raise ValueError(
            "CPI calendar: missing not_published entry for "
            f"{EXPECTED_CPI_NOT_PUBLISHED}"
        )
    # Reference-month continuity: every reference month is the month
    # before its release month, and the sequence is consecutive except
    # for the never-published 2025-10.
    ref_months = [release.reference_month for release in releases]
    if ref_months[0] != "2020-12" or ref_months[-1] != "2026-11":
        raise ValueError(
            "CPI calendar: reference months run "
            f"{ref_months[0]}..{ref_months[-1]}, expected 2020-12..2026-11"
        )

    fomc_dates = load_fomc_statement_dates(fomc_document)
    fomc_sample = tuple(
        day for day in fomc_dates if 2021 <= day.year <= 2026
    )
    if len(fomc_sample) != EXPECTED_FOMC_STATEMENTS_2021_2026:
        raise ValueError(
            "FOMC calendar: expected "
            f"{EXPECTED_FOMC_STATEMENTS_2021_2026} statements in 2021-2026, "
            f"found {len(fomc_sample)}"
        )
    for known in EXPECTED_FOMC_KNOWN_DATES:
        if known not in fomc_sample:
            raise ValueError(f"FOMC calendar: missing known statement {known}")

    # build_macro_window takes release/statement dates and applies the
    # fixed offsets internally (CPI: day before; FOMC: same day). Only
    # the 2021-2026 statements enter the window, matching preregister.
    window = build_macro_window(release_dates, fomc_sample)
    panel_first = DAILY_START.date()
    panel_last = date(2026, 11, 16)  # last confirmed bar at fetch time
    in_sample = [bar for bar in window.window_bars if panel_first <= bar <= panel_last]
    cpi_in_sample = sum(
        1 for bar in window.cpi_bars if panel_first <= bar <= panel_last
    )
    fomc_in_sample = sum(
        1 for bar in window.fomc_bars if panel_first <= bar <= panel_last
    )
    if len(in_sample) != EXPECTED_WINDOW_BARS_IN_SAMPLE:
        raise ValueError(
            "macro window: expected "
            f"{EXPECTED_WINDOW_BARS_IN_SAMPLE} in-sample bars, "
            f"found {len(in_sample)}"
        )
    if cpi_in_sample != EXPECTED_CPI_BARS_IN_SAMPLE:
        raise ValueError(
            "macro window: expected "
            f"{EXPECTED_CPI_BARS_IN_SAMPLE} in-sample CPI bars, "
            f"found {cpi_in_sample}"
        )
    if fomc_in_sample != EXPECTED_FOMC_BARS_IN_SAMPLE:
        raise ValueError(
            "macro window: expected "
            f"{EXPECTED_FOMC_BARS_IN_SAMPLE} in-sample FOMC bars, "
            f"found {fomc_in_sample}"
        )
    if len(window.overlap_bars) != EXPECTED_OVERLAP_BARS_TOTAL:
        raise ValueError(
            "macro window: expected "
            f"{EXPECTED_OVERLAP_BARS_TOTAL} overlap bar(s), "
            f"found {len(window.overlap_bars)}"
        )
    return {
        "cpi": {
            "file": "research/macro-windows-006/cpi_calendar.json",
            "releases": len(releases),
            "first_release": release_dates[0].isoformat(),
            "last_release": release_dates[-1].isoformat(),
            "reference_months": f"{ref_months[0]}..{ref_months[-1]}",
            "not_published": not_published,
            "known_dates_checked": [
                item.isoformat() for item in EXPECTED_CPI_KNOWN_DATES
            ],
            "annual_counts": annual_counts(release_dates),
        },
        "fomc": {
            "file": "research/fomc-event-study-005/fomc_calendar.json",
            "statements_2021_2026": len(fomc_sample),
            "first_statement": fomc_sample[0].isoformat(),
            "last_statement": fomc_sample[-1].isoformat(),
            "known_dates_checked": [
                item.isoformat() for item in EXPECTED_FOMC_KNOWN_DATES
            ],
            "annual_counts": annual_counts(fomc_sample),
        },
        "macro_window": {
            "window_bars_total": len(window.window_bars),
            "cpi_bars_total": len(window.cpi_bars),
            "fomc_bars_total": len(window.fomc_bars),
            "overlap_bars": [
                item.isoformat() for item in window.overlap_bars
            ],
            "overlap_bars_in_sample": sum(
                1 for bar in window.overlap_bars if panel_first <= bar <= panel_last
            ),
            "window_bars_in_sample": len(in_sample),
            "cpi_bars_in_sample": cpi_in_sample,
            "fomc_bars_in_sample": fomc_in_sample,
            "panel_first_bar": panel_first.isoformat(),
            "panel_last_bar": panel_last.isoformat(),
        },
    }


def fetch_fiscaldata_auction_pages(
    *,
    raw_store: RawStore,
    fetched_at: datetime,
) -> tuple[list[dict], list[dict]]:
    """Page the Fiscal Data API auctions_query dataset.

    Returns (records, page manifest entries). The API's `total-count`
    is the authoritative total; paging stops on a short page. Each page
    payload is stored in the RawStore (gitignored cache).
    """
    records: list[dict] = []
    page_entries: list[dict] = []
    total_count: int | None = None
    page_number = 1
    while True:
        query = (
            f"filter=auction_date:gte:{AUCTION_START.isoformat()},"
            f"auction_date:lte:{AUCTION_END.isoformat()}"
            f"&page[size]={AUCTION_PAGE_SIZE}&sort=auction_date"
            f"&page[number]={page_number}"
        )
        url = f"{FISCALDATA_BASE_URL}?{query}"
        payload = _fetch_url(url)
        record = raw_store.put(
            payload,
            source_id=FISCALDATA_SOURCE_ID,
            available_at=fetched_at,
            content_type="application/json",
            source_version=FISCALDATA_SOURCE_VERSION,
            event_time=None,
            ingested_at=fetched_at,
        )
        page_entries.append(
            {
                "url": url,
                "byte_length": len(payload),
                "payload_sha256": record.payload_sha256,
                "record_id": record.record_id,
            }
        )
        parsed = json.loads(payload)
        page_records = parsed["data"]
        meta = parsed["meta"]
        if total_count is None:
            total_count = int(meta["total-count"])
        records.extend(page_records)
        print(
            f"Fiscal Data API page {page_number}: {len(page_records)} records "
            f"(total-count {total_count})"
        )
        if len(page_records) < AUCTION_PAGE_SIZE:
            break
        page_number += 1
        time.sleep(0.5)
    if total_count is None or len(records) != total_count:
        raise ValueError(
            "Fiscal Data API: fetched "
            f"{len(records)} records, total-count is {total_count}"
        )
    return records, page_entries


def fetch_treasurydirect_auctioned(
    *,
    raw_store: RawStore,
    fetched_at: datetime,
) -> tuple[list[dict], dict]:
    """Fetch the TreasuryDirect `auctioned` listing (250 most recent).

    The endpoint ignores date filters and caps at the 250 most recent
    auctioned securities, so it cannot build the historical calendar —
    it is the cross-check source for the recent window and the tail
    supplement for the weeks the Fiscal Data API has not published yet.
    """
    payload = _fetch_url(TREASURYDIRECT_AUCTIONED_URL)
    record = raw_store.put(
        payload,
        source_id=FISCALDATA_SOURCE_ID,
        available_at=fetched_at,
        content_type="application/json",
        source_version=FISCALDATA_SOURCE_VERSION,
        event_time=None,
        ingested_at=fetched_at,
    )
    entry = {
        "url": TREASURYDIRECT_AUCTIONED_URL,
        "byte_length": len(payload),
        "payload_sha256": record.payload_sha256,
        "record_id": record.record_id,
    }
    return json.loads(payload), entry


def _td_coupon_close_dates(records: list[dict]) -> dict[date, str]:
    """Distinct coupon close dates from TreasuryDirect records.

    Returns {close date: close time} — the close time is kept to verify
    the 1:00 PM ET competitive close behind the same-day window-bar
    offset for auction days.
    """
    close_dates: dict[date, str] = {}
    for item in records:
        if item.get("securityType") not in COUPON_TYPES:
            continue
        close_raw = item.get("competitiveAuctionCloseDate")
        if not close_raw:
            raise ValueError(
                "TreasuryDirect record missing competitiveAuctionCloseDate: "
                f"{item.get('cusip')}"
            )
        close_date = date.fromisoformat(close_raw[:10])
        close_time = str(item.get("competitiveAuctionCloseTime", ""))
        previous = close_dates.setdefault(close_date, close_time)
        if previous != close_time:
            # Two coupon auctions closing at different times on the
            # same day: keep both times in the record (joined).
            close_dates[close_date] = ";".join(sorted({previous, close_time}))
    return close_dates


def build_auction_calendar(
    fd_records: list[dict],
    td_records: list[dict],
    *,
    fetched_at: datetime,
) -> tuple[dict, dict]:
    """Build the coupon auction calendar and its verification record.

    Primary source: the Fiscal Data API (auction_date). Its coverage
    ends at the latest record it has published (about four weeks behind
    the live schedule); coupon auction dates after that come from the
    TreasuryDirect listing and are flagged as the tail supplement. The
    cross-check compares the two sources on their overlap window and
    must agree exactly for the calendar to be marked verified.
    """
    fd_coupon_dates: set[date] = set()
    fd_auction_dates: set[date] = set()
    type_counts: dict[str, int] = {}
    closing_times: dict[str, int] = {}
    for item in fd_records:
        auction_date = date.fromisoformat(item["auction_date"])
        fd_auction_dates.add(auction_date)
        security_type = str(item["security_type"])
        type_counts[security_type] = type_counts.get(security_type, 0) + 1
        if security_type in COUPON_TYPES:
            fd_coupon_dates.add(auction_date)
            closing = str(item.get("closing_time_comp", ""))
            if closing:
                closing_times[closing] = closing_times.get(closing, 0) + 1
    fd_coverage_end = max(fd_auction_dates)
    fd_coverage_start = min(fd_auction_dates)

    td_close_dates = _td_coupon_close_dates(td_records)
    td_window_start = min(td_close_dates)
    td_window_end = max(td_close_dates)

    # Cross-check on the overlap window: both sources must list the
    # same coupon auction dates between the TreasuryDirect window start
    # and the Fiscal Data coverage end.
    check_start = max(td_window_start, fd_coverage_start)
    check_end = fd_coverage_end
    fd_in_window = {
        day for day in fd_coupon_dates if check_start <= day <= check_end
    }
    td_in_window = {
        day for day in td_close_dates if check_start <= day <= check_end
    }
    only_fd = sorted(fd_in_window - td_in_window)
    only_td = sorted(td_in_window - fd_in_window)
    cross_check_passed = not only_fd and not only_td

    # Tail supplement: TreasuryDirect coupon close dates after the
    # Fiscal Data coverage end (the weeks the API has not published).
    tail_dates = sorted(
        day for day in td_close_dates if day > fd_coverage_end
    )
    coupon_dates = sorted(fd_coupon_dates | set(tail_dates))
    counts = annual_counts(coupon_dates)
    annual_bounds_passed = all(
        MIN_COUPON_DAYS_FULL_YEAR <= count <= MAX_COUPON_DAYS_FULL_YEAR
        for year, count in counts.items()
        if 2021 <= year <= 2025
    ) and (
        counts.get(2026, 0) >= MIN_COUPON_DAYS_2026
        and counts.get(2026, 0) <= MAX_COUPON_DAYS_FULL_YEAR
    )
    verified = cross_check_passed and annual_bounds_passed
    if not verified:
        logger.warning(
            "auction calendar NOT verified: cross-check passed=%s "
            "(only FD: %s; only TD: %s), annual bounds passed=%s",
            cross_check_passed,
            [item.isoformat() for item in only_fd],
            [item.isoformat() for item in only_td],
            annual_bounds_passed,
        )

    calendar = {
        "study": "macro-windows-006",
        "generated_by": "research/macro-windows-006/fetch_data.py",
        "fetched_at": fetched_at.isoformat(),
        "source": (
            "U.S. Department of the Treasury, Bureau of the Fiscal "
            "Service, Fiscal Data API, auctions_query dataset (v1)"
        ),
        "source_url": FISCALDATA_BASE_URL,
        "cross_check_source": (
            "TreasuryDirect TA_WS securities/auctioned endpoint "
            "(250 most recent auctioned securities)"
        ),
        "cross_check_url": TREASURYDIRECT_AUCTIONED_URL,
        "auction_date_range_queried": [
            AUCTION_START.isoformat(),
            AUCTION_END.isoformat(),
        ],
        "fiscaldata_coverage": [
            fd_coverage_start.isoformat(),
            fd_coverage_end.isoformat(),
        ],
        "treasurydirect_window": [
            td_window_start.isoformat(),
            td_window_end.isoformat(),
        ],
        "coupon_auction_dates": [day.isoformat() for day in coupon_dates],
        "tail_supplement_dates": [day.isoformat() for day in tail_dates],
        "tail_supplement_source": (
            "TreasuryDirect auctioned listing: coupon close dates after "
            "the Fiscal Data API coverage end, included because the two "
            "sources agree exactly on their overlap window."
        ),
        "annual_counts": counts,
        "total_auction_records": len(fd_records),
        "coupon_records": sum(
            count for kind, count in type_counts.items() if kind in COUPON_TYPES
        ),
        "records_by_security_type": type_counts,
        "coupon_closing_times_et": closing_times,
        "verified": verified,
        "verification": {
            "cross_check_window": [
                check_start.isoformat(),
                check_end.isoformat(),
            ],
            "fiscaldata_coupon_dates_in_window": len(fd_in_window),
            "treasurydirect_coupon_dates_in_window": len(td_in_window),
            "only_in_fiscaldata": [item.isoformat() for item in only_fd],
            "only_in_treasurydirect": [item.isoformat() for item in only_td],
            "cross_check_passed": cross_check_passed,
            "annual_count_bounds": {
                "full_year_min": MIN_COUPON_DAYS_FULL_YEAR,
                "full_year_max": MAX_COUPON_DAYS_FULL_YEAR,
                "min_2026": MIN_COUPON_DAYS_2026,
            },
            "annual_bounds_passed": annual_bounds_passed,
        },
        "note": (
            "Descriptive only: auction days never enter the main macro "
            "window (FOMC + CPI). Bills are excluded (weekly cash "
            "management, not event days). Auction results are announced "
            "shortly after the 1:00 PM ET competitive close, so an "
            "auction window bar is the auction day itself (same offset "
            "as FOMC); a minority of coupon records close at 11:30 AM "
            "ET, whose results sit near the 16:00 UTC bar boundary — "
            "see coupon_closing_times_et."
        ),
    }
    return calendar, {
        "fiscaldata_records": len(fd_records),
        "fiscaldata_coverage": [
            fd_coverage_start.isoformat(),
            fd_coverage_end.isoformat(),
        ],
        "treasurydirect_records": len(td_records),
        "treasurydirect_window": [
            td_window_start.isoformat(),
            td_window_end.isoformat(),
        ],
        "coupon_auction_dates": len(coupon_dates),
        "tail_supplement_dates": len(tail_dates),
        "verified": verified,
        "cross_check_passed": cross_check_passed,
    }


def inspect_store(
    pit_store: ParquetPITStore,
    expected_series: set[SeriesKey],
    *,
    as_of: datetime,
) -> dict:
    observations = pit_store.query_as_of(as_of)
    report = inspect_observations(observations, expected_series=expected_series)
    return {
        "row_count": report.row_count,
        "unique_series_count": report.unique_series_count,
        "unique_instrument_count": report.unique_instrument_count,
        "event_time_min": (
            report.event_time_min.isoformat() if report.event_time_min else None
        ),
        "event_time_max": (
            report.event_time_max.isoformat() if report.event_time_max else None
        ),
        "missing_expected_series": list(report.missing_expected_series),
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity.value,
                "message": issue.message,
                "count": issue.count,
            }
            for issue in report.issues
        ],
    }


def main() -> None:
    fetched_at = datetime.now(UTC)
    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    source_registry.require_research_permission(
        OKX_SOURCE_ID, version=OKX_SOURCE_VERSION
    )
    source_registry.require_research_permission(
        FISCALDATA_SOURCE_ID, version=FISCALDATA_SOURCE_VERSION
    )
    pit_stores = {
        "pit-1d": pit_store_for("pit-1d", source_registry),
        "pit-1h": pit_store_for("pit-1h", source_registry),
    }

    okx_fetches: list[dict] = []
    for instrument_id, bar, start, end in OKX_FETCH_PLAN:
        entry = fetch_okx_one(
            instrument_id,
            bar,
            start,
            end,
            raw_store=raw_store,
            pit_store=pit_stores[f"pit-{bar.lower()}"],
            fetched_at=fetched_at,
        )
        okx_fetches.append(entry)
        print(
            f"{instrument_id} {bar}: {entry['candles']} candles, "
            f"{entry['missing_bars']} missing, {len(entry['pages'])} pages"
        )

    calendar_validation = validate_committed_calendars()
    macro_window = calendar_validation["macro_window"]
    print(
        f"CPI {calendar_validation['cpi']['releases']} releases, "
        f"FOMC {calendar_validation['fomc']['statements_2021_2026']} "
        "statements 2021-2026, "
        f"macro window {macro_window['window_bars_in_sample']} in-sample bars "
        f"({macro_window['cpi_bars_in_sample']} CPI + "
        f"{macro_window['fomc_bars_in_sample']} FOMC), "
        f"{len(macro_window['overlap_bars'])} overlap bar(s) total"
    )

    fd_records, fd_page_entries = fetch_fiscaldata_auction_pages(
        raw_store=raw_store, fetched_at=fetched_at
    )
    td_records, td_entry = fetch_treasurydirect_auctioned(
        raw_store=raw_store, fetched_at=fetched_at
    )
    auction_calendar, auction_summary = build_auction_calendar(
        fd_records, td_records, fetched_at=fetched_at
    )
    auction_path = ROOT / "treasury_auction_calendar.json"
    auction_path.write_text(
        json.dumps(auction_calendar, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"auction calendar written: {auction_path} "
        f"({auction_summary['coupon_auction_dates']} coupon auction dates, "
        f"verified={auction_summary['verified']}, "
        f"tail supplement {auction_summary['tail_supplement_dates']} dates)"
    )
    # The committed calendar must load through the study module's own
    # loader (sorted, unique, well-formed).
    loaded_auction_dates = load_auction_calendar(auction_calendar)
    if len(loaded_auction_dates) != auction_summary["coupon_auction_dates"]:
        raise ValueError("auction calendar failed to round-trip through the loader")

    quality: dict[str, dict] = {}
    for store_name in ("pit-1d", "pit-1h"):
        expected_series: set[SeriesKey] = {
            (instrument_id, OKX_VENUE, field, OKX_SOURCE_ID, OKX_SOURCE_VERSION)
            for instrument_id in INSTRUMENTS
            for field in FIELDS
        }
        quality[store_name] = inspect_store(
            pit_stores[store_name], expected_series, as_of=fetched_at
        )

    manifest = {
        "study": "macro-windows-006",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/macro-windows-006",
        "okx_fetches": okx_fetches,
        "calendar_validation": calendar_validation,
        "auction_fetch": {
            "fiscaldata_pages": fd_page_entries,
            "treasurydirect": td_entry,
            "summary": auction_summary,
        },
        "quality": quality,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}")
    summary = {
        "study": "macro-windows-006",
        "fetched_at": fetched_at.isoformat(),
        "okx_panels": [
            {
                "instrument_id": entry["instrument_id"],
                "bar": entry["bar"],
                "candles": entry["candles"],
                "expected_confirmed_bars": entry["expected_confirmed_bars"],
                "missing_bars": entry["missing_bars"],
                "first_bar_open": entry["first_bar_open"],
                "last_bar_open": entry["last_bar_open"],
            }
            for entry in okx_fetches
        ],
        "calendar_validation": calendar_validation,
        "auction_calendar": auction_summary,
        "quality_row_count": {
            name: report["row_count"] for name, report in quality.items()
        },
        "quality_issues": {
            name: report["issues"] for name, report in quality.items()
        },
    }
    summary_path = ROOT / "panel-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"panel summary written: {summary_path}")


if __name__ == "__main__":
    main()
