"""Fetch market data for the publication-lag study (H0011, H0012).

Run after preregistration, from the repo root:

    .venv/bin/python research/publication-lag-007/fetch_data.py

Pulls daily closes for the study 005 panel (four FRED series: VIXCLS,
VXTYN, DGS10, BAA10Y, 2003-01-02 to 2020-05-15) and the S&P 500 index
(^GSPC via Yahoo, 2003-01-02 to 2026-11-18, one fetch covering both
hypotheses), monthly CPIAUCSL (2020-11-01 to 2026-11-30 — the
2020-11 level is needed for the first MoM, reference month 2020-12),
and OKX BTC-USDT-SWAP daily candles (2021-01-01 to 2026-11-18).
Raw payloads go to the gitignored cache under
data/cache/publication-lag-007/raw/ (content-addressed RawStore);
parsed closes become observations in data/cache/publication-lag-007/
pit-1d/ (FRED + Yahoo, 21:00 UTC closes) and
data/cache/publication-lag-007/pit-okx-1d/ (OKX BTC, 16:00 UTC opens).

Only the manifest (endpoints, parameters, date ranges, payload
SHA-256, lag re-check, calendar validation) and the panel summary
(counts only, no raw prices) are written into this research directory
for commit. Raw payloads and parquet never leave the local cache.

The FOMC and CPI calendars are reused, not re-extracted: study 005's
fomc_calendar.json (199 scheduled meetings) and study 006's
cpi_calendar.json (71 releases) are validated through their loaders
here and the counts are recorded in the manifest.

FRED lag re-check (recorded in the manifest): an unbounded VIXCLS and
DGS10 fetch at fetch time, confirming the preregistration's N=1
finding — the last available date must be the most recent trading day
or the trading day before it (both are consistent with next-business-
day posting, depending on whether the fetch runs before or after the
morning posting); a last date older than that would falsify N=1 and
fail the fetch. The check payloads are raw-stored but NOT written to
PIT (they would duplicate the bounded series).

Fail-fast checks: the Yahoo meta longName must be "S&P 500", and every
vol-index / SPX / CPI close must be positive (log changes need
positive levels). DGS10 and BAA10Y are not positivity-checked: a yield
or spread can be zero or negative in principle.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from myquant.adapters.fred import (
    DAILY_CLOSE_UTC,
    fetch_series,
    series_to_observations,
)
from myquant.adapters.okx import (
    candles_to_observations,
    fetch_history,
    parse_candles_response,
)
from myquant.adapters.yahoo import chart_to_observations, fetch_chart
from myquant.pit import ParquetPITStore
from myquant.quality import SeriesKey, inspect_observations
from myquant.raw import RawStore
from myquant.sources import SourceRegistry
from myquant.studies.macro import load_cpi_calendar, load_fomc_statement_dates
from myquant.studies.panel import build_synchronized_panel

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "publication-lag-007"

FRED_SOURCE_ID = "fred"
FRED_SOURCE_VERSION = 1
FRED_VENUE = "fred"
YAHOO_SOURCE_ID = "yahoo-finance"
YAHOO_SOURCE_VERSION = 1
YAHOO_VENUE = "yahoo-finance"
OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
OKX_VENUE = "okx"

# instrument_id, FRED series id, unit, require positive closes
FRED_DAILY_PLAN: tuple[tuple[str, str, str, bool], ...] = (
    ("index:vix", "VIXCLS", "points", True),
    ("index:tyvix", "VXTYN", "points", True),
    ("rates:us-10y-yield", "DGS10", "percent", False),
    ("credit:baa-10y-spread", "BAA10Y", "percent", False),
)

CPI_INSTRUMENT_ID = "macro:cpi-mom"
CPI_SERIES_ID = "CPIAUCSL"

SP500_INSTRUMENT_ID = "index:sp500"
SP500_SYMBOL = "^GSPC"
SP500_EXPECTED_LONG_NAME = "S&P 500"

BTC_INSTRUMENT_ID = "crypto:btc-usdt-perp"
BTC_OKX_INST_ID = "BTC-USDT-SWAP"

FRED_DAILY_START = date(2003, 1, 2)
FRED_DAILY_END = date(2020, 5, 15)
SP500_START = date(2003, 1, 2)
SP500_END = date(2026, 11, 18)
CPI_START = date(2020, 11, 1)
CPI_END = date(2026, 11, 30)
BTC_START = datetime(2021, 1, 1, 16, 0, tzinfo=UTC)
BTC_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)

H0011_INSTRUMENTS: tuple[str, ...] = tuple(
    instrument_id for instrument_id, _, _, _ in FRED_DAILY_PLAN
) + (SP500_INSTRUMENT_ID,)

H0012_SP500_START = datetime(2021, 1, 4, 21, 0, tzinfo=UTC)
H0012_END = datetime(2026, 11, 18, 21, 0, tzinfo=UTC)

US_EASTERN = ZoneInfo("America/New_York")

# The lag re-check compares the last available FRED date against the
# most recent trading day (weekends stepped back; US holidays are not
# modelled — the check runs on a Wednesday, far from any holiday).
LAG_CHECK_SERIES: tuple[str, ...] = ("VIXCLS", "DGS10")


def _previous_trading_day(day: date) -> date:
    """The most recent weekday on or before ``day``."""
    current = day
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def fetch_fred_one(
    instrument_id: str,
    series_id: str,
    unit: str,
    require_positive: bool,
    start: date,
    end: date,
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict:
    series = fetch_series(series_id, start=start, end=end)
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
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
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
    chart = fetch_chart(SP500_SYMBOL, start=SP500_START, end=SP500_END)
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
        "window_start": SP500_START.isoformat(),
        "window_end": SP500_END.isoformat(),
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


def fetch_btc_daily(
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict:
    result = fetch_history(
        BTC_OKX_INST_ID,
        "1D",
        start=BTC_START,
        end=BTC_END,
        delay_seconds=0.25,
    )
    page_entries: list[dict[str, str]] = []
    for page in result.pages:
        page_candles = parse_candles_response(
            page.payload,
            inst_id=BTC_OKX_INST_ID,
            bar="1D",
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
        instrument_id=BTC_INSTRUMENT_ID,
        venue=OKX_VENUE,
        source_id=OKX_SOURCE_ID,
        source_version=OKX_SOURCE_VERSION,
        ingested_at=fetched_at,
    )
    parquet_path = pit_store.write_batch(observations)
    expected_opens: list[datetime] = []
    current = BTC_START
    while current < BTC_END:
        if current + timedelta(days=1) <= fetched_at:
            expected_opens.append(current)
        current += timedelta(days=1)
    fetched_opens = {candle.open_time for candle in result.candles}
    missing = [
        open_time for open_time in expected_opens if open_time not in fetched_opens
    ]
    return {
        "instrument_id": BTC_INSTRUMENT_ID,
        "okx_inst_id": BTC_OKX_INST_ID,
        "bar": "1D",
        "endpoint": "https://www.okx.com/api/v5/market/history-candles",
        "window_start": BTC_START.isoformat(),
        "window_end": BTC_END.isoformat(),
        "candles": len(result.candles),
        "first_bar_open": (
            result.candles[0].open_time.isoformat() if result.candles else None
        ),
        "last_bar_open": (
            result.candles[-1].open_time.isoformat() if result.candles else None
        ),
        "expected_confirmed_bars": len(expected_opens),
        "missing_bars": len(missing),
        "missing_bar_opens": [item.isoformat() for item in missing],
        "pages": page_entries,
        "pit_store": "pit-okx-1d",
        "pit_parquet": parquet_path.name,
        "pit_parquet_sha256": parquet_path.stem,
        "observation_rows": len(observations),
    }


def check_fred_lag(
    *,
    raw_store: RawStore,
    fetched_at: datetime,
) -> dict:
    """Re-check the FRED publication lag with unbounded fetches.

    The preregistration's N=1 finding (2026-11-18, 06:26 UTC) says a
    FRED value dated t is posted on the next business day. This check
    re-records the last available date for VIXCLS and DGS10 at fetch
    time. Either the most recent trading day (fetch ran after the
    morning posting) or the trading day before it (fetch ran before
    the posting) is consistent with N=1; anything older falsifies N=1
    and fails the fetch.
    """
    today_us = fetched_at.astimezone(US_EASTERN).date()
    most_recent = _previous_trading_day(today_us - timedelta(days=1))
    previous = _previous_trading_day(most_recent - timedelta(days=1))
    entries: dict[str, dict] = {}
    for series_id in LAG_CHECK_SERIES:
        series = fetch_series(series_id)
        last_date = series.observations[-1][0]
        record = raw_store.put(
            series.payload,
            source_id=FRED_SOURCE_ID,
            available_at=fetched_at,
            content_type="text/csv",
            source_version=FRED_SOURCE_VERSION,
            event_time=datetime.combine(
                last_date, DAILY_CLOSE_UTC, tzinfo=UTC
            ),
            ingested_at=fetched_at,
        )
        entries[series_id] = {
            "last_available_date": last_date.isoformat(),
            "rows": len(series.observations),
            "endpoint": series.url,
            "payload_sha256": record.payload_sha256,
            "record_id": record.record_id,
        }
        if last_date not in (most_recent, previous):
            raise ValueError(
                f"FRED lag re-check failed for {series_id}: last available "
                f"date is {last_date}, expected {most_recent} or {previous} "
                "(N=1 posting); the preregistered lag no longer holds"
            )
    return {
        "fetched_at": fetched_at.isoformat(),
        "today_us_eastern": today_us.isoformat(),
        "most_recent_trading_day": most_recent.isoformat(),
        "previous_trading_day": previous.isoformat(),
        "consistent_with_lag_steps": 1,
        "series": entries,
        "notes": (
            "Both series' last available date is the most recent "
            "trading day or the one before it, consistent with "
            "next-business-day posting (N=1). Whether it is the most "
            "recent day or the previous one depends on whether this "
            "fetch ran before or after FRED's morning posting."
        ),
    }


def validate_calendars() -> dict:
    """Validate the reused FOMC and CPI calendars through their loaders."""
    fomc_document = json.loads(
        (
            REPO_ROOT
            / "research"
            / "fomc-event-study-005"
            / "fomc_calendar.json"
        ).read_text(encoding="utf-8")
    )
    cpi_document = json.loads(
        (
            REPO_ROOT
            / "research"
            / "macro-windows-006"
            / "cpi_calendar.json"
        ).read_text(encoding="utf-8")
    )
    fomc = load_fomc_statement_dates(fomc_document)
    cpi = load_cpi_calendar(cpi_document)
    if len(fomc) != 199:
        raise ValueError(
            f"FOMC calendar has {len(fomc)} scheduled meetings, expected 199"
        )
    if len(cpi) != 71:
        raise ValueError(f"CPI calendar has {len(cpi)} releases, expected 71")
    return {
        "fomc": {
            "source": "research/fomc-event-study-005/fomc_calendar.json",
            "scheduled_meetings": len(fomc),
            "first_statement": fomc[0].isoformat(),
            "last_statement": fomc[-1].isoformat(),
        },
        "cpi": {
            "source": "research/macro-windows-006/cpi_calendar.json",
            "releases": len(cpi),
            "first_release": cpi[0].release_date.isoformat(),
            "last_release": cpi[-1].release_date.isoformat(),
        },
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
    for source_id, version in (
        (FRED_SOURCE_ID, FRED_SOURCE_VERSION),
        (YAHOO_SOURCE_ID, YAHOO_SOURCE_VERSION),
        (OKX_SOURCE_ID, OKX_SOURCE_VERSION),
    ):
        source_registry.require_research_permission(source_id, version=version)
    pit_store = ParquetPITStore(CACHE_ROOT / "pit-1d", source_registry)
    pit_okx_store = ParquetPITStore(CACHE_ROOT / "pit-okx-1d", source_registry)

    fetches: list[dict] = []
    for instrument_id, series_id, unit, require_positive in FRED_DAILY_PLAN:
        entry = fetch_fred_one(
            instrument_id,
            series_id,
            unit,
            require_positive,
            FRED_DAILY_START,
            FRED_DAILY_END,
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
    cpi_entry = fetch_fred_one(
        CPI_INSTRUMENT_ID,
        CPI_SERIES_ID,
        "index",
        True,
        CPI_START,
        CPI_END,
        raw_store=raw_store,
        pit_store=pit_store,
        fetched_at=fetched_at,
    )
    fetches.append(cpi_entry)
    print(
        f"{CPI_INSTRUMENT_ID} ({CPI_SERIES_ID}): {cpi_entry['rows']} rows, "
        f"{cpi_entry['missing_values']} missing, "
        f"{cpi_entry['first_date']} to {cpi_entry['last_date']}"
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
    btc_entry = fetch_btc_daily(
        raw_store=raw_store,
        pit_store=pit_okx_store,
        fetched_at=fetched_at,
    )
    fetches.append(btc_entry)
    print(
        f"{BTC_INSTRUMENT_ID} (1D): {btc_entry['candles']} candles, "
        f"{btc_entry['missing_bars']} missing, {len(btc_entry['pages'])} pages"
    )

    lag_check = check_fred_lag(raw_store=raw_store, fetched_at=fetched_at)
    print(
        "FRED lag re-check: "
        + ", ".join(
            f"{series_id} last available "
            f"{entry['last_available_date']}"
            for series_id, entry in lag_check["series"].items()
        )
        + f" (most recent trading day {lag_check['most_recent_trading_day']}); "
        "consistent with N=1"
    )

    calendar_validation = validate_calendars()
    print(
        f"calendars validated: FOMC "
        f"{calendar_validation['fomc']['scheduled_meetings']} scheduled, "
        f"CPI {calendar_validation['cpi']['releases']} releases"
    )

    observations = pit_store.query_as_of(fetched_at)
    expected_series: set[SeriesKey] = {
        (instrument_id, FRED_VENUE, "close", FRED_SOURCE_ID, FRED_SOURCE_VERSION)
        for instrument_id, _, _, _ in FRED_DAILY_PLAN
    } | {
        (
            CPI_INSTRUMENT_ID,
            FRED_VENUE,
            "close",
            FRED_SOURCE_ID,
            FRED_SOURCE_VERSION,
        ),
        (
            SP500_INSTRUMENT_ID,
            YAHOO_VENUE,
            "close",
            YAHOO_SOURCE_ID,
            YAHOO_SOURCE_VERSION,
        ),
    }
    quality = {
        "pit-1d": inspect_store(pit_store, expected_series, as_of=fetched_at),
        "pit-okx-1d": inspect_store(
            pit_okx_store,
            {
                (
                    BTC_INSTRUMENT_ID,
                    OKX_VENUE,
                    field,
                    OKX_SOURCE_ID,
                    OKX_SOURCE_VERSION,
                )
                for field in ("open", "high", "low", "close", "volume")
            },
            as_of=fetched_at,
        ),
    }

    # H0011 panel: five legs through the TYVIX coverage end (2020-05-15).
    h0011_cutoff = datetime.combine(FRED_DAILY_END, DAILY_CLOSE_UTC, tzinfo=UTC)
    h0011_observations = [
        item for item in observations if item.event_time <= h0011_cutoff
    ]
    h0011_panel = build_synchronized_panel(
        h0011_observations,
        instruments=H0011_INSTRUMENTS,
        field="close",
    )
    # H0012 SPX panel: single instrument, 2021-01-04 to 2026-11-18.
    h0012_spx_observations = [
        item
        for item in observations
        if item.instrument_id == SP500_INSTRUMENT_ID
        and H0012_SP500_START <= item.event_time <= H0012_END
    ]
    h0012_spx_panel = build_synchronized_panel(
        h0012_spx_observations,
        instruments=(SP500_INSTRUMENT_ID,),
        field="close",
    )
    # H0012 BTC panel: single instrument, OKX store.
    btc_observations = pit_okx_store.query_as_of(fetched_at)
    h0012_btc_panel = build_synchronized_panel(
        btc_observations,
        instruments=(BTC_INSTRUMENT_ID,),
        field="close",
    )
    panel_info = {
        "h0011": {
            "instruments": list(H0011_INSTRUMENTS),
            "close_rows": int(h0011_panel.closes.shape[0]),
            "return_rows": h0011_panel.row_count,
            "dropped_close_rows": h0011_panel.dropped_close_rows,
            "dropped_return_rows": h0011_panel.dropped_return_rows,
            "first_return_time": h0011_panel.first_time.isoformat(),
            "last_return_time": h0011_panel.last_time.isoformat(),
        },
        "h0012_spx": {
            "instruments": [SP500_INSTRUMENT_ID],
            "close_rows": int(h0012_spx_panel.closes.shape[0]),
            "return_rows": h0012_spx_panel.row_count,
            "dropped_close_rows": h0012_spx_panel.dropped_close_rows,
            "dropped_return_rows": h0012_spx_panel.dropped_return_rows,
            "first_return_time": h0012_spx_panel.first_time.isoformat(),
            "last_return_time": h0012_spx_panel.last_time.isoformat(),
        },
        "h0012_btc": {
            "instruments": [BTC_INSTRUMENT_ID],
            "close_rows": int(h0012_btc_panel.closes.shape[0]),
            "return_rows": h0012_btc_panel.row_count,
            "dropped_close_rows": h0012_btc_panel.dropped_close_rows,
            "dropped_return_rows": h0012_btc_panel.dropped_return_rows,
            "first_return_time": h0012_btc_panel.first_time.isoformat(),
            "last_return_time": h0012_btc_panel.last_time.isoformat(),
        },
        "cpi_monthly": {
            "instrument": CPI_INSTRUMENT_ID,
            "rows": cpi_entry["rows"],
            "first_date": cpi_entry["first_date"],
            "last_date": cpi_entry["last_date"],
        },
    }
    print(
        f"H0011 panel: {h0011_panel.row_count} return rows, "
        f"{h0011_panel.dropped_close_rows} dropped close rows, "
        f"{h0011_panel.dropped_return_rows} dropped return rows"
    )
    print(
        f"H0012 SPX panel: {h0012_spx_panel.row_count} return rows, "
        f"{h0012_spx_panel.dropped_close_rows} dropped close rows"
    )
    print(
        f"H0012 BTC panel: {h0012_btc_panel.row_count} return rows, "
        f"{h0012_btc_panel.dropped_close_rows} dropped close rows"
    )

    manifest = {
        "study": "publication-lag-007",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/publication-lag-007",
        "sources": [
            {"source_id": FRED_SOURCE_ID, "version": FRED_SOURCE_VERSION},
            {"source_id": YAHOO_SOURCE_ID, "version": YAHOO_SOURCE_VERSION},
            {"source_id": OKX_SOURCE_ID, "version": OKX_SOURCE_VERSION},
        ],
        "fetches": fetches,
        "fred_lag_check": lag_check,
        "calendar_validation": calendar_validation,
        "quality": quality,
        "panel": panel_info,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}")
    summary = {
        "study": "publication-lag-007",
        "fetched_at": fetched_at.isoformat(),
        "fetches": [
            {
                "instrument_id": entry["instrument_id"],
                "rows": entry.get("rows", entry.get("candles")),
                "missing_values": entry.get(
                    "missing_values", entry.get("missing_bars")
                ),
                "first_date": entry.get(
                    "first_date", entry.get("first_bar_open")
                ),
                "last_date": entry.get("last_date", entry.get("last_bar_open")),
            }
            for entry in fetches
        ],
        "fred_lag_check": lag_check,
        "calendar_validation": calendar_validation,
        "panel": panel_info,
        "quality_row_count": {
            name: value["row_count"] for name, value in quality.items()
        },
        "quality_issues": {
            name: value["issues"] for name, value in quality.items()
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
