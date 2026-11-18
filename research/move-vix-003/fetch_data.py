"""Fetch FRED series and Yahoo ^GSPC for the MOVE/VIX/VXN study.

Run after preregistration, from the repo root:

    .venv/bin/python research/move-vix-003/fetch_data.py

Pulls daily closes (2003-01-02 to 2020-05-15, the TYVIX coverage window)
for five FRED series (VIXCLS, VXNCLS, VXTYN, DGS10, BAA10Y) via the free
fredgraph CSV endpoint and for the S&P 500 index (^GSPC) via Yahoo's
public chart endpoint. Raw payloads go to the gitignored cache under
data/cache/move-vix-003/raw/ (content-addressed RawStore); parsed closes
become observations in data/cache/move-vix-003/pit-1d/ (ParquetPITStore).

Only the manifest (endpoints, parameters, date ranges, payload SHA-256)
and the panel summary (counts only, no raw prices) are written into this
research directory for commit. Raw payloads and parquet never leave the
local cache.

Fail-fast checks (the ^MOVE lesson): the Yahoo meta longName must be
"S&P 500", and every vol-index / SPX close must be positive (log changes
need positive levels). DGS10 and BAA10Y are not positivity-checked: a
yield or spread can be zero or negative in principle.
"""

from __future__ import annotations

import hashlib
import json
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
from myquant.studies.panel import build_synchronized_panel

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "move-vix-003"

FRED_SOURCE_ID = "fred"
FRED_SOURCE_VERSION = 1
FRED_VENUE = "fred"
YAHOO_SOURCE_ID = "yahoo-finance"
YAHOO_SOURCE_VERSION = 1
YAHOO_VENUE = "yahoo-finance"

# instrument_id, FRED series id, unit, require positive closes
FRED_PLAN: tuple[tuple[str, str, str, bool], ...] = (
    ("index:vix", "VIXCLS", "points", True),
    ("index:vxn", "VXNCLS", "points", True),
    ("index:tyvix", "VXTYN", "points", True),
    ("rates:us-10y-yield", "DGS10", "percent", False),
    ("credit:baa-10y-spread", "BAA10Y", "percent", False),
)

SP500_INSTRUMENT_ID = "index:sp500"
SP500_SYMBOL = "^GSPC"
SP500_EXPECTED_LONG_NAME = "S&P 500"

WINDOW_START = date(2003, 1, 2)
WINDOW_END = date(2020, 5, 15)

ALL_INSTRUMENTS: tuple[str, ...] = tuple(
    instrument_id for instrument_id, _, _, _ in FRED_PLAN
) + (SP500_INSTRUMENT_ID,)


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

    # Synchronized daily panel (no bar_seconds: US trading days have
    # weekend gaps, so returns are per-trading-day log returns).
    panel = build_synchronized_panel(
        observations,
        instruments=ALL_INSTRUMENTS,
        field="close",
    )
    panel_info = {
        "instruments": list(ALL_INSTRUMENTS),
        "close_rows": int(panel.closes.shape[0]),
        "return_rows": panel.row_count,
        "dropped_close_rows": panel.dropped_close_rows,
        "dropped_return_rows": panel.dropped_return_rows,
        "first_return_time": panel.first_time.isoformat(),
        "last_return_time": panel.last_time.isoformat(),
    }
    print(
        f"panel: {panel.row_count} return rows, "
        f"{panel.dropped_close_rows} dropped close rows, "
        f"{panel.dropped_return_rows} dropped return rows"
    )

    manifest = {
        "study": "move-vix-003",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/move-vix-003",
        "sources": [
            {"source_id": FRED_SOURCE_ID, "version": FRED_SOURCE_VERSION},
            {"source_id": YAHOO_SOURCE_ID, "version": YAHOO_SOURCE_VERSION},
        ],
        "fetches": fetches,
        "quality": {"pit-1d": quality},
        "panel": panel_info,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}")
    summary = {
        "study": "move-vix-003",
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
