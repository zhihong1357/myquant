"""Fetch market data and the FOMC calendar for the event study.

Run after preregistration, from the repo root:

    .venv/bin/python research/fomc-event-study-005/fetch_data.py

Pulls daily closes (2003-01-02 to 2026-11-16) for four FRED series
(VIXCLS, VXTYN, DGS10, BAA10Y) via the free fredgraph CSV endpoint and
for the S&P 500 index (^GSPC) via Yahoo's public chart endpoint, and
pulls the FOMC meeting calendar pages from federalreserve.gov
(fomchistorical{YYYY}.htm for 2003-2020, fomccalendars.htm for 2021
onwards) plus two cross-check pages (the 2003 schedule press release
and the 2020 minutes publication page). Raw payloads go to the
gitignored cache under data/cache/fomc-event-study-005/raw/
(content-addressed RawStore); parsed closes become observations in
data/cache/fomc-event-study-005/pit-1d/ (ParquetPITStore).

Only the manifest (endpoints, parameters, date ranges, payload
SHA-256, calendar verification), the panel summary (counts only, no
raw prices) and the extracted FOMC calendar (public schedule data, a
small JSON file) are written into this research directory for commit.
Raw payloads and parquet never leave the local cache.

Calendar verification (all checks must pass, or the script fails):
per-year scheduled-meeting counts (8 per year, 7 in 2020); the 2003
schedule press release reproduces all eight 2003 statement days; the
2020 minutes page reproduces the seven scheduled 2020 meetings plus
the unscheduled March 15 meeting; known-date spot checks (2008-12-16,
2003-09-16, 2020-12-16 scheduled; 2020-03-15, 2020-03-03, 2008-10-08,
2008-01-22, 2008-03-16 not scheduled).

Fail-fast checks (the ^MOVE lesson): the Yahoo meta longName must be
"S&P 500", and every vol-index / SPX close must be positive (log
changes need positive levels). DGS10 and BAA10Y are not
positivity-checked: a yield or spread can be zero or negative in
principle.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

from myquant.adapters.fred import (
    DAILY_CLOSE_UTC,
    fetch_series,
    series_to_observations,
)
from myquant.adapters.yahoo import chart_to_observations, fetch_chart
from myquant.pit import ParquetPITStore
from myquant.quality import SeriesKey, inspect_observations
from myquant.raw import RawStore
from myquant.sources import SourceRegistry
from myquant.studies.fomc import (
    FOMCMeeting,
    FOMCMeetingKind,
    annual_counts,
    excluded_meetings,
    merge_consecutive_meetings,
    parse_calendar_page,
    parse_historical_page,
    scheduled_meetings,
    statement_dates,
)
from myquant.studies.panel import build_synchronized_panel

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "fomc-event-study-005"

FRED_SOURCE_ID = "fred"
FRED_SOURCE_VERSION = 1
FRED_VENUE = "fred"
YAHOO_SOURCE_ID = "yahoo-finance"
YAHOO_SOURCE_VERSION = 1
YAHOO_VENUE = "yahoo-finance"
FEDERALRESERVE_SOURCE_ID = "federalreserve"
FEDERALRESERVE_SOURCE_VERSION = 1

# instrument_id, FRED series id, unit, require positive closes
FRED_PLAN: tuple[tuple[str, str, str, bool], ...] = (
    ("index:vix", "VIXCLS", "points", True),
    ("index:tyvix", "VXTYN", "points", True),
    ("rates:us-10y-yield", "DGS10", "percent", False),
    ("credit:baa-10y-spread", "BAA10Y", "percent", False),
)

SP500_INSTRUMENT_ID = "index:sp500"
SP500_SYMBOL = "^GSPC"
SP500_EXPECTED_LONG_NAME = "S&P 500"

WINDOW_START = date(2003, 1, 2)
WINDOW_END = date(2026, 11, 16)
MAIN_SAMPLE_END = date(2020, 5, 15)

ALL_INSTRUMENTS: tuple[str, ...] = tuple(
    instrument_id for instrument_id, _, _, _ in FRED_PLAN
) + (SP500_INSTRUMENT_ID,)

# The main (five-leg) panel needs TYVIX, which ends 2020-05-15; the
# extended (four-leg) panel runs to the fetch end.
EXTENDED_INSTRUMENTS: tuple[str, ...] = (
    "index:vix",
    "rates:us-10y-yield",
    "index:sp500",
    "credit:baa-10y-spread",
)

FED_BASE_URL = "https://www.federalreserve.gov/monetarypolicy"
HISTORICAL_YEARS: tuple[int, ...] = tuple(range(2003, 2021))
CALENDAR_PAGE_URL = f"{FED_BASE_URL}/fomccalendars.htm"
SCHEDULE_2003_URL = (
    "https://www.federalreserve.gov/boarddocs/press/monetary/2002/"
    "20020705/default.htm"
)
MINUTES_2020_URL = (
    "https://www.federalreserve.gov/publications/2020-minutes-of-fomc.htm"
)

# Expected scheduled-meeting counts: eight per year, seven in 2020 (the
# March 17-18 meeting was cancelled; the Committee acted at unscheduled
# meetings instead).
EXPECTED_ANNUAL_COUNTS: dict[int, int] = {
    year: 8 for year in range(2003, 2027)
} | {2020: 7}

# Known-date spot checks on the scheduled statement days.
EXPECTED_SCHEDULED = (
    date(2003, 9, 16),  # merged split September meeting
    date(2008, 12, 16),
    date(2020, 12, 16),
)
EXPECTED_NOT_SCHEDULED = (
    date(2008, 1, 22),  # emergency cut, decided by conference call
    date(2008, 3, 16),  # Bear Stearns action, decided by conference call
    date(2008, 10, 8),  # coordinated cut, decided by conference call
    date(2020, 3, 3),  # emergency cut, unscheduled meeting
    date(2020, 3, 15),  # emergency cut, unscheduled meeting
)

_MONTH_PATTERN = (
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)"
)


def _fetch_url(url: str, *, timeout_seconds: float = 60.0) -> bytes:
    """Fetch one URL with retries (Fed pages are plain static HTML)."""
    request = urllib.request.Request(url, headers={"User-Agent": "myquant-research/0.1"})
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


def _store_page(
    payload: bytes,
    url: str,
    *,
    raw_store: RawStore,
    fetched_at: datetime,
) -> dict:
    record = raw_store.put(
        payload,
        source_id=FEDERALRESERVE_SOURCE_ID,
        available_at=fetched_at,
        content_type="text/html",
        source_version=FEDERALRESERVE_SOURCE_VERSION,
        event_time=fetched_at,
        ingested_at=fetched_at,
    )
    return {
        "url": url,
        "byte_length": len(payload),
        "payload_sha256": record.payload_sha256,
        "record_id": record.record_id,
    }


def _parse_schedule_press_release(html: str) -> tuple[date, ...]:
    """Statement days from the 2003 schedule press release.

    The release lists the tentative 2003 schedule as "January 28-29
    (Tuesday-Wednesday) March 18 (Tuesday), May 6 (Tuesday), June 24-25
    (Tuesday-Wednesday), August 12 (Tuesday), September 16 (Tuesday),
    October 28 (Tuesday), December 9 (Tuesday)". The statement day is
    the last day of each listed range. Only the schedule list itself
    is parsed: the page header and footer mention the release date
    ("July 5, 2002") three times, so the text is sliced from the
    schedule marker to the footer before matching.
    """
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    marker = "tentative meeting schedule for 2003:"
    start = text.find(marker)
    if start < 0:
        raise ValueError("2003 schedule press release: schedule marker not found")
    footer = text.find("2002 Monetary policy", start)
    if footer < 0:
        raise ValueError("2003 schedule press release: footer marker not found")
    schedule_text = text[start + len(marker) : footer]
    month_numbers = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    pattern = re.compile(
        rf"{_MONTH_PATTERN}\s+(\d{{1,2}})(?:-(\d{{1,2}}))?"
    )
    statement_days: list[date] = []
    for match in pattern.finditer(schedule_text):
        month = month_numbers[match.group(1)]
        last_day = int(match.group(3)) if match.group(3) else int(match.group(2))
        statement_days.append(date(2003, month, last_day))
    if len(statement_days) != 8:
        raise ValueError(
            "2003 schedule press release: expected 8 meeting dates, "
            f"found {len(statement_days)}"
        )
    return tuple(statement_days)


def _parse_minutes_2020_page(html: str) -> tuple[tuple[date, date], ...]:
    """(start, end) meeting dates from the 2020 minutes publication page.

    The page lists "Meeting held on January 28–29, 2020" entries for
    the seven scheduled 2020 meetings plus the unscheduled March 15
    meeting (which replaced the cancelled March 17-18 meeting). The
    March 2 unscheduled meeting has no separate minutes entry on this
    page, so the cross-check compares against the scheduled meetings
    plus March 15 only.
    """
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    month_numbers = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    pattern = re.compile(
        rf"Meeting held on {_MONTH_PATTERN}\s+(\d{{1,2}})"
        r"(?:[–-](\d{1,2}))?,\s+2020"
    )
    meetings: list[tuple[date, date]] = []
    for match in pattern.finditer(text):
        month = month_numbers[match.group(1)]
        first_day = int(match.group(2))
        last_day = int(match.group(3)) if match.group(3) else first_day
        meetings.append(
            (date(2020, month, first_day), date(2020, month, last_day))
        )
    if len(meetings) != 8:
        raise ValueError(
            "2020 minutes page: expected 8 meetings with minutes, "
            f"found {len(meetings)}"
        )
    return tuple(meetings)


def fetch_fomc_calendar(
    *,
    raw_store: RawStore,
    fetched_at: datetime,
) -> tuple[dict, dict, list[dict]]:
    """Fetch, parse and verify the FOMC calendar (2003-2026).

    Returns the calendar document (written to fomc_calendar.json for
    commit), the verification record and the list of page fetch
    records (both for the manifest).
    Every verification check must pass or the fetch fails.
    """
    page_records: list[dict] = []
    all_meetings: list[FOMCMeeting] = []
    for year in HISTORICAL_YEARS:
        url = f"{FED_BASE_URL}/fomchistorical{year}.htm"
        payload = _fetch_url(url)
        page_records.append(
            _store_page(payload, url, raw_store=raw_store, fetched_at=fetched_at)
        )
        all_meetings.extend(
            parse_historical_page(payload.decode("utf-8", errors="replace"), year)
        )
        time.sleep(0.5)
    calendar_payload = _fetch_url(CALENDAR_PAGE_URL)
    page_records.append(
        _store_page(
            calendar_payload,
            CALENDAR_PAGE_URL,
            raw_store=raw_store,
            fetched_at=fetched_at,
        )
    )
    all_meetings.extend(
        parse_calendar_page(calendar_payload.decode("utf-8", errors="replace"))
    )

    merged, merges = merge_consecutive_meetings(tuple(all_meetings))
    scheduled = scheduled_meetings(merged)
    excluded = excluded_meetings(merged)
    statements = statement_dates(merged)
    counts = annual_counts(merged)

    # Verification 1: per-year scheduled counts (2003-2026 in sample;
    # 2027 is parsed but out of sample and checked separately).
    count_mismatches = {
        year: (counts.get(year, 0), expected)
        for year, expected in EXPECTED_ANNUAL_COUNTS.items()
        if counts.get(year, 0) != expected
    }
    if count_mismatches:
        raise ValueError(
            f"annual scheduled-meeting counts mismatch: {count_mismatches}"
        )
    if counts.get(2027, 0) != 8:
        raise ValueError(
            f"2027 scheduled-meeting count is {counts.get(2027, 0)}, expected 8"
        )

    # Verification 2: the 2003 schedule press release (second source).
    press_payload = _fetch_url(SCHEDULE_2003_URL)
    page_records.append(
        _store_page(
            press_payload,
            SCHEDULE_2003_URL,
            raw_store=raw_store,
            fetched_at=fetched_at,
        )
    )
    press_dates = _parse_schedule_press_release(
        press_payload.decode("utf-8", errors="replace")
    )
    parsed_2003 = tuple(
        day for day in statements if day.year == 2003
    )
    press_match = press_dates == parsed_2003
    if not press_match:
        raise ValueError(
            "2003 schedule press release does not match the parsed "
            f"calendar: {press_dates} vs {parsed_2003}"
        )

    # Verification 3: the 2020 minutes publication page (second source).
    minutes_payload = _fetch_url(MINUTES_2020_URL)
    page_records.append(
        _store_page(
            minutes_payload,
            MINUTES_2020_URL,
            raw_store=raw_store,
            fetched_at=fetched_at,
        )
    )
    minutes_meetings = _parse_minutes_2020_page(
        minutes_payload.decode("utf-8", errors="replace")
    )
    # The minutes page lists the seven scheduled 2020 meetings plus
    # the unscheduled March 15 meeting (which replaced the cancelled
    # March 17-18 meeting); the March 2 unscheduled meeting has no
    # separate minutes entry on that page.
    parsed_2020_with_minutes = tuple(
        (meeting.start_date, meeting.end_date)
        for meeting in merged
        if meeting.start_date.year == 2020
        and (
            meeting.kind is FOMCMeetingKind.SCHEDULED
            or meeting.start_date == date(2020, 3, 15)
        )
    )
    minutes_match = minutes_meetings == parsed_2020_with_minutes
    if not minutes_match:
        raise ValueError(
            "2020 minutes page does not match the parsed calendar: "
            f"{minutes_meetings} vs {parsed_2020_with_minutes}"
        )

    # Verification 4: known-date spot checks.
    statement_set = set(statements)
    missing = [day for day in EXPECTED_SCHEDULED if day not in statement_set]
    unexpected = [
        day for day in EXPECTED_NOT_SCHEDULED if day in statement_set
    ]
    if missing or unexpected:
        raise ValueError(
            f"spot checks failed: missing scheduled {missing}, "
            f"unexpected scheduled {unexpected}"
        )

    calendar = {
        "study": "fomc-event-study-005",
        "generated_by": "research/fomc-event-study-005/fetch_data.py",
        "fetched_at": fetched_at.isoformat(),
        "scheduled_meetings": [
            {
                "start_date": meeting.start_date.isoformat(),
                "end_date": meeting.end_date.isoformat(),
                "statement_date": meeting.statement_date.isoformat(),
                "source": meeting.source,
            }
            for meeting in scheduled
        ],
        "excluded_meetings": [
            {
                "start_date": meeting.start_date.isoformat(),
                "end_date": meeting.end_date.isoformat(),
                "kind": meeting.kind.value,
                "source": meeting.source,
            }
            for meeting in excluded
        ],
        "merges": [
            [start.isoformat(), end.isoformat()] for start, end in merges
        ],
        "annual_counts": {str(year): count for year, count in sorted(counts.items())},
    }
    verification = {
        "all_checks_passed": True,
        "scheduled_meetings": len(scheduled),
        "excluded_meetings": len(excluded),
        "merges": [
            [start.isoformat(), end.isoformat()] for start, end in merges
        ],
        "annual_counts_match": True,
        "press_release_2003_match": press_match,
        "minutes_2020_match": minutes_match,
        "spot_checks_passed": True,
        "notes": (
            "Calendar extracted from federalreserve.gov: "
            "fomchistorical{YYYY}.htm (2003-2020) and fomccalendars.htm "
            "(2021 onwards). 2027 meetings are parsed but out of sample. "
            "The 2003 schedule press release and the 2020 minutes "
            "publication page reproduce the parsed dates exactly."
        ),
    }
    return calendar, verification, page_records


def fetch_fred_one(
    instrument_id: str,
    series_id: str,
    unit: str,
    require_positive: bool,
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict:
    series = fetch_series(series_id, start=WINDOW_START, end=WINDOW_END)
    if require_positive and any(value <= 0 for _, value in series.observations):
        raise ValueError(
            f"{series_id}: non-positive close found; log changes need "
            "positive levels"
        )
    last_event_time = datetime.combine(
        series.observations[-1][0],
        DAILY_CLOSE_UTC,
        tzinfo=UTC,
    )
    record = raw_store.put(
        series.payload,
        source_id=FRED_SOURCE_ID,
        available_at=fetched_at,
        content_type="text/csv",
        source_version=FRED_SOURCE_VERSION,
        event_time=last_event_time,
        ingested_at=fetched_at,
    )
    observations = series_to_observations(
        series,
        instrument_id=instrument_id,
        venue=FRED_VENUE,
        source_id=FRED_SOURCE_ID,
        source_version=FRED_SOURCE_VERSION,
        ingested_at=fetched_at,
        unit=unit,
    )
    parquet_path = pit_store.write_batch(observations)
    return {
        "instrument_id": instrument_id,
        "fred_series": series_id,
        "endpoint": series.url,
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "rows": len(series.observations),
        "missing_values": series.missing_count,
        "first_date": series.observations[0][0].isoformat(),
        "last_date": series.observations[-1][0].isoformat(),
        "payload_sha256": record.payload_sha256,
        "record_id": record.record_id,
        "pit_store": "pit-1d",
        "pit_parquet": parquet_path.name,
        "pit_parquet_sha256": parquet_path.stem,
        "observation_rows": len(observations),
    }


def fetch_sp500(
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict:
    chart = fetch_chart(SP500_SYMBOL, start=WINDOW_START, end=WINDOW_END)
    if chart.long_name != SP500_EXPECTED_LONG_NAME:
        raise ValueError(
            f"Yahoo {SP500_SYMBOL!r}: meta longName is {chart.long_name!r}, "
            f"expected {SP500_EXPECTED_LONG_NAME!r}; refusing to guess "
            "the instrument"
        )
    if any(bar.close <= 0 for bar in chart.bars):
        raise ValueError(f"Yahoo {SP500_SYMBOL!r}: non-positive close found")
    last_event_time = datetime.combine(
        chart.bars[-1].trading_date,
        DAILY_CLOSE_UTC,
        tzinfo=UTC,
    )
    record = raw_store.put(
        chart.payload,
        source_id=YAHOO_SOURCE_ID,
        available_at=fetched_at,
        content_type="application/json",
        source_version=YAHOO_SOURCE_VERSION,
        event_time=last_event_time,
        ingested_at=fetched_at,
    )
    observations = chart_to_observations(
        chart,
        instrument_id=SP500_INSTRUMENT_ID,
        venue=YAHOO_VENUE,
        source_id=YAHOO_SOURCE_ID,
        source_version=YAHOO_SOURCE_VERSION,
        ingested_at=fetched_at,
        unit="points",
    )
    parquet_path = pit_store.write_batch(observations)
    return {
        "instrument_id": SP500_INSTRUMENT_ID,
        "yahoo_symbol": SP500_SYMBOL,
        "yahoo_long_name": chart.long_name,
        "endpoint": chart.url,
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "rows": len(chart.bars),
        "missing_values": chart.missing_count,
        "first_date": chart.bars[0].trading_date.isoformat(),
        "last_date": chart.bars[-1].trading_date.isoformat(),
        "payload_sha256": record.payload_sha256,
        "record_id": record.record_id,
        "pit_store": "pit-1d",
        "pit_parquet": parquet_path.name,
        "pit_parquet_sha256": parquet_path.stem,
        "observation_rows": len(observations),
    }


def main() -> None:
    fetched_at = datetime.now(UTC)
    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    source_registry.require_research_permission(
        FRED_SOURCE_ID, version=FRED_SOURCE_VERSION
    )
    source_registry.require_research_permission(
        YAHOO_SOURCE_ID, version=YAHOO_SOURCE_VERSION
    )
    source_registry.require_research_permission(
        FEDERALRESERVE_SOURCE_ID, version=FEDERALRESERVE_SOURCE_VERSION
    )
    pit_store = ParquetPITStore(CACHE_ROOT / "pit-1d", source_registry)

    fetches: list[dict] = []
    for instrument_id, series_id, unit, require_positive in FRED_PLAN:
        entry = fetch_fred_one(
            instrument_id,
            series_id,
            unit,
            require_positive,
            raw_store=raw_store,
            pit_store=pit_store,
            fetched_at=fetched_at,
        )
        fetches.append(entry)
        print(
            f"{instrument_id} ({series_id}): {entry['rows']} rows, "
            f"{entry['missing_values']} missing, "
            f"{entry['first_date']} to {entry['last_date']}"
        )
    sp500_entry = fetch_sp500(
        raw_store=raw_store,
        pit_store=pit_store,
        fetched_at=fetched_at,
    )
    fetches.append(sp500_entry)
    print(
        f"{SP500_INSTRUMENT_ID} ({SP500_SYMBOL}): {sp500_entry['rows']} rows, "
        f"{sp500_entry['missing_values']} missing, "
        f"{sp500_entry['first_date']} to {sp500_entry['last_date']}"
    )

    calendar, verification, page_records = fetch_fomc_calendar(
        raw_store=raw_store,
        fetched_at=fetched_at,
    )
    calendar_path = ROOT / "fomc_calendar.json"
    calendar_path.write_text(
        json.dumps(calendar, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"FOMC calendar: {verification['scheduled_meetings']} scheduled, "
        f"{verification['excluded_meetings']} excluded, "
        f"{len(verification['merges'])} merges; all checks passed"
    )

    observations = pit_store.query_as_of(fetched_at)
    expected_series: set[SeriesKey] = {
        (instrument_id, FRED_VENUE, "close", FRED_SOURCE_ID, FRED_SOURCE_VERSION)
        for instrument_id, _, _, _ in FRED_PLAN
    } | {
        (
            SP500_INSTRUMENT_ID,
            YAHOO_VENUE,
            "close",
            YAHOO_SOURCE_ID,
            YAHOO_SOURCE_VERSION,
        )
    }
    report = inspect_observations(
        observations,
        expected_series=expected_series,
    )
    quality = {
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

    # Main panel: five legs through the TYVIX coverage end (2020-05-15).
    # Extended panel: the four non-TYVIX legs through the fetch end.
    main_cutoff = datetime.combine(MAIN_SAMPLE_END, DAILY_CLOSE_UTC, tzinfo=UTC)
    main_observations = [
        item for item in observations if item.event_time <= main_cutoff
    ]
    main_panel = build_synchronized_panel(
        main_observations,
        instruments=ALL_INSTRUMENTS,
        field="close",
    )
    extended_panel = build_synchronized_panel(
        observations,
        instruments=EXTENDED_INSTRUMENTS,
        field="close",
    )
    panel_info = {
        "main": {
            "instruments": list(ALL_INSTRUMENTS),
            "close_rows": int(main_panel.closes.shape[0]),
            "return_rows": main_panel.row_count,
            "dropped_close_rows": main_panel.dropped_close_rows,
            "dropped_return_rows": main_panel.dropped_return_rows,
            "first_return_time": main_panel.first_time.isoformat(),
            "last_return_time": main_panel.last_time.isoformat(),
        },
        "extended": {
            "instruments": list(EXTENDED_INSTRUMENTS),
            "close_rows": int(extended_panel.closes.shape[0]),
            "return_rows": extended_panel.row_count,
            "dropped_close_rows": extended_panel.dropped_close_rows,
            "dropped_return_rows": extended_panel.dropped_return_rows,
            "first_return_time": extended_panel.first_time.isoformat(),
            "last_return_time": extended_panel.last_time.isoformat(),
        },
    }
    print(
        f"main panel: {main_panel.row_count} return rows, "
        f"{main_panel.dropped_close_rows} dropped close rows, "
        f"{main_panel.dropped_return_rows} dropped return rows"
    )
    print(
        f"extended panel: {extended_panel.row_count} return rows, "
        f"{extended_panel.dropped_close_rows} dropped close rows, "
        f"{extended_panel.dropped_return_rows} dropped return rows"
    )

    manifest = {
        "study": "fomc-event-study-005",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/fomc-event-study-005",
        "sources": [
            {"source_id": FRED_SOURCE_ID, "version": FRED_SOURCE_VERSION},
            {"source_id": YAHOO_SOURCE_ID, "version": YAHOO_SOURCE_VERSION},
            {
                "source_id": FEDERALRESERVE_SOURCE_ID,
                "version": FEDERALRESERVE_SOURCE_VERSION,
            },
        ],
        "fetches": fetches,
        "fomc_pages": page_records,
        "calendar_verification": verification,
        "quality": {"pit-1d": quality},
        "panel": panel_info,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}")
    summary = {
        "study": "fomc-event-study-005",
        "fetched_at": fetched_at.isoformat(),
        "fetches": [
            {
                "instrument_id": entry["instrument_id"],
                "rows": entry["rows"],
                "missing_values": entry["missing_values"],
                "first_date": entry["first_date"],
                "last_date": entry["last_date"],
            }
            for entry in fetches
        ],
        "calendar_verification": verification,
        "panel": panel_info,
        "quality_row_count": {"pit-1d": quality["row_count"]},
        "quality_issues": {"pit-1d": quality["issues"]},
    }
    summary_path = ROOT / "panel-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"panel summary written: {summary_path}")


if __name__ == "__main__":
    main()
