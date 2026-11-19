"""Fetch OKX candles and Deribit hourly DVOL for the BTC->BTC_DVOL study.

Run after preregistration, from the repo root:

    .venv/bin/python research/btc-dvol-013/fetch_data.py

Pulls daily candles (2021-03-01 to 2026-11-19) for BTC/ETH from OKX
public REST, and hourly DVOL points (2021-03-24 to the fetch time) for
BTC from the Deribit public DVOL endpoint. Raw response pages go to the
gitignored cache under data/cache/btc-dvol-013/raw/ (content-addressed
RawStore); parsed observations go to data/cache/btc-dvol-013/pit-1d/
(ParquetPITStore, one store — all three legs are daily on the 16:00
UTC grid).

DVOL snapshot convention (preregistered): the daily DVOL value is the
16:00 UTC snapshot — the close of the Deribit hourly DVOL row
timestamped 15:00 UTC — aligned to the OKX 1D bar grid (bars open
16:00 UTC). The daily DVOL endpoint (resolution 86400) timestamps
points at 00:00 UTC, which would leave an 8-hour overlap between the
predictor window (16:00-16:00 UTC) and the target window (00:00-00:00
UTC); the hourly snapshot removes it. The DVOL observation at bar-open
time 16:00 UTC on day D carries the snapshot value at 16:00 UTC on day
D+1 (the bar-close value, matching the OKX candle convention:
event_time is the bar open, the close value is the price at the bar
close, available_at is the bar close).

Endpoint behaviour verified 2026-11-19 (see the manifest's
dvol_endpoint note): the hourly endpoint (resolution 3600) returns
OHLC rows on the hour grid, inclusive of both window endpoints, and
caps at 1,000 points per call — a 60-day hourly window returned
exactly 1,000 rows, truncated from the start. The fetch therefore
chunks in 40-day windows (961 points) and refuses any chunk that
returns 1,000 points (the truncation signal).

Only the manifest (endpoints, parameters, date ranges, payload
SHA-256) and the panel summary (counts only, no raw prices) are
written into this research directory for commit. Raw payloads and
parquet never leave the local cache.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from myquant.adapters.deribit import DVOLPoint, fetch_volatility_index
from myquant.adapters.okx import (
    BAR_DURATIONS,
    candles_to_observations,
    fetch_history,
    parse_candles_response,
)
from myquant.contracts import Observation
from myquant.pit import ParquetPITStore
from myquant.quality import SeriesKey, inspect_observations
from myquant.raw import RawStore
from myquant.sources import SourceRegistry

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "btc-dvol-013"

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
OKX_VENUE = "okx"
DERIBIT_SOURCE_ID = "deribit"
DERIBIT_SOURCE_VERSION = 1
DERIBIT_VENUE = "deribit"

BTC = "crypto:btc-usdt-perp"
ETH = "crypto:eth-usdt-perp"
BTC_DVOL = "index:btc-dvol"

INSTRUMENTS: dict[str, str] = {
    BTC: "BTC-USDT-SWAP",
    ETH: "ETH-USDT-SWAP",
}

OKX_DAILY_START = datetime(2021, 3, 1, 16, 0, tzinfo=UTC)
OKX_DAILY_END = datetime(2026, 11, 19, 16, 0, tzinfo=UTC)

# DVOL hourly history starts 2021-03-24 (the daily series' first point,
# study 004); the hourly fetch starts at the same midnight.
DVOL_START = datetime(2021, 3, 24, 0, 0, tzinfo=UTC)
DVOL_CURRENCY = "BTC"
DVOL_RESOLUTION_SECONDS = 3_600
#: Chunk length for the hourly DVOL fetch: 40 days is 960 hours, so a
#: chunk returns at most 961 points — safely below the endpoint's
#: 1,000-point cap (verified 2026-11-19).
DVOL_CHUNK_DAYS = 40
#: The endpoint truncates a window to its last 1,000 points; a chunk
#: returning exactly this many points signals truncation and is refused.
DVOL_POINT_CAP = 1_000

FIELDS = ("open", "high", "low", "close", "volume")


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


def fetch_okx_one(
    instrument_id: str,
    bar: str,
    start: datetime,
    end: datetime,
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict[str, Any]:
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


def fetch_dvol_hourly(
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict[str, Any]:
    """Fetch hourly DVOL, extract the 16:00 UTC daily snapshots.

    The endpoint caps at 1,000 points per call (verified 2026-11-19),
    so the window is fetched in 40-day chunks (at most 961 points
    each). A chunk returning exactly 1,000 points signals truncation
    and is refused. Chunks overlap by one point (the endpoint includes
    both window endpoints), so points are deduplicated by timestamp.

    Snapshots: for each calendar date D, the snapshot is the close of
    the hourly row timestamped 15:00 UTC on D — the DVOL value at
    16:00 UTC on D. A snapshot is formed only when 16:00 UTC on D is
    before the fetch time (the close must already be knowable). A
    missing 15:00 row means a missing snapshot (counted, no forward
    filling). The daily observation at bar-open time 16:00 UTC on day
    D carries the snapshot value at 16:00 UTC on day D+1 (the
    bar-close value, matching the OKX candle convention), with
    available_at at the snapshot moment.
    """
    end = fetched_at.replace(minute=0, second=0, microsecond=0)
    pages: list[dict[str, str]] = []
    collected: dict[datetime, DVOLPoint] = {}
    chunk_start = DVOL_START
    chunk_seconds = DVOL_CHUNK_DAYS * 86_400
    chunks = 0
    while chunk_start < end:
        chunk_end = min(
            end,
            datetime.fromtimestamp(
                chunk_start.timestamp() + chunk_seconds, tz=UTC
            ),
        )
        result = fetch_volatility_index(
            DVOL_CURRENCY,
            start=chunk_start,
            end=chunk_end,
            resolution_seconds=DVOL_RESOLUTION_SECONDS,
            delay_seconds=0.2,
        )
        if len(result.points) >= DVOL_POINT_CAP:
            raise ValueError(
                "DVOL chunk returned "
                f"{len(result.points)} points (cap {DVOL_POINT_CAP}); "
                "the endpoint truncated the window — refusing to store "
                "a silently incomplete series"
            )
        for page in result.pages:
            record = raw_store.put(
                page.payload,
                source_id=DERIBIT_SOURCE_ID,
                available_at=fetched_at,
                content_type="application/json",
                source_version=DERIBIT_SOURCE_VERSION,
                event_time=result.points[-1].timestamp if result.points else None,
                ingested_at=fetched_at,
            )
            pages.append(
                {
                    "url": page.url,
                    "payload_sha256": record.payload_sha256,
                    "record_id": record.record_id,
                }
            )
        for point in result.points:
            collected[point.timestamp] = point
        chunks += 1
        chunk_start = chunk_end

    hourly_close = {ts: point.close for ts, point in collected.items()}
    hourly_timestamps = sorted(hourly_close)
    first_hour = hourly_timestamps[0] if hourly_timestamps else None
    last_hour = hourly_timestamps[-1] if hourly_timestamps else None

    # Snapshot dates: every calendar date from the first hourly row's
    # date to the last date whose 16:00 UTC is before the fetch time.
    snapshots: dict[datetime, float] = {}
    missing_snapshots: list[str] = []
    if first_hour is not None:
        day = first_hour.date()
        last_day = (fetched_at - timedelta(seconds=1)).date()
        # The snapshot at 16:00 UTC on D needs the 15:00 row on D and
        # 16:00 D < fetched_at; the last eligible date is the fetch
        # date itself when the fetch runs after 16:00 UTC.
        while day <= last_day:
            snapshot_time = datetime(day.year, day.month, day.day, 16, 0, tzinfo=UTC)
            if snapshot_time >= fetched_at:
                break
            row_time = datetime(day.year, day.month, day.day, 15, 0, tzinfo=UTC)
            if row_time in hourly_close:
                snapshots[snapshot_time] = hourly_close[row_time]
            else:
                missing_snapshots.append(snapshot_time.isoformat())
            day += timedelta(days=1)

    observations: list[Observation] = []
    for snapshot_time in sorted(snapshots):
        observations.append(
            Observation(
                instrument_id=BTC_DVOL,
                venue=DERIBIT_VENUE,
                event_time=snapshot_time - timedelta(days=1),
                available_at=snapshot_time,
                ingested_at=fetched_at,
                field="close",
                value=snapshots[snapshot_time],
                unit="percent",
                source_id=DERIBIT_SOURCE_ID,
                source_version=DERIBIT_SOURCE_VERSION,
            )
        )
    parquet_path = pit_store.write_batch(observations)
    return {
        "instrument_id": BTC_DVOL,
        "deribit_currency": DVOL_CURRENCY,
        "endpoint": "https://www.deribit.com/api/v2/public/get_volatility_index_data",
        "resolution_seconds": DVOL_RESOLUTION_SECONDS,
        "window_start": DVOL_START.isoformat(),
        "window_end": end.isoformat(),
        "chunk_days": DVOL_CHUNK_DAYS,
        "chunks": chunks,
        "hourly_points": len(collected),
        "first_hourly_point": first_hour.isoformat() if first_hour else None,
        "last_hourly_point": last_hour.isoformat() if last_hour else None,
        "snapshots": len(snapshots),
        "first_snapshot": (
            min(snapshots).isoformat() if snapshots else None
        ),
        "last_snapshot": (
            max(snapshots).isoformat() if snapshots else None
        ),
        "missing_snapshots": len(missing_snapshots),
        "missing_snapshot_times": missing_snapshots,
        "pages": pages,
        "pit_store": "pit-1d",
        "pit_parquet": parquet_path.name,
        "pit_parquet_sha256": parquet_path.stem,
        "observation_rows": len(observations),
        "dvol_endpoint_note": (
            "Verified 2026-11-19: the hourly endpoint (resolution 3600) "
            "returns OHLC rows [timestamp_ms, open, high, low, close] on "
            "the hour grid, inclusive of both window endpoints, and caps "
            "at 1,000 points per call (a 60-day hourly window returned "
            "exactly 1,000 rows, truncated from the start). Chunks of "
            "40 days return at most 961 points; a chunk returning 1,000 "
            "points is refused as truncation."
        ),
    }


def main() -> None:
    fetched_at = datetime.now(UTC)
    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    source_registry.require_research_permission(
        OKX_SOURCE_ID, version=OKX_SOURCE_VERSION
    )
    source_registry.require_research_permission(
        DERIBIT_SOURCE_ID, version=DERIBIT_SOURCE_VERSION
    )
    pit_store = ParquetPITStore(CACHE_ROOT / "pit-1d", source_registry)

    fetches: list[dict[str, Any]] = []
    for instrument_id in (BTC, ETH):
        entry = fetch_okx_one(
            instrument_id,
            "1D",
            OKX_DAILY_START,
            OKX_DAILY_END,
            raw_store=raw_store,
            pit_store=pit_store,
            fetched_at=fetched_at,
        )
        fetches.append(entry)
        print(
            f"{instrument_id} 1D: {entry['candles']} candles, "
            f"{entry['missing_bars']} missing, "
            f"{len(entry['pages'])} pages"
        )
    dvol_entry = fetch_dvol_hourly(
        raw_store=raw_store,
        pit_store=pit_store,
        fetched_at=fetched_at,
    )
    fetches.append(dvol_entry)
    print(
        f"{BTC_DVOL} hourly: {dvol_entry['hourly_points']} points, "
        f"{dvol_entry['snapshots']} snapshots, "
        f"{dvol_entry['missing_snapshots']} missing, "
        f"{dvol_entry['chunks']} chunks"
    )

    observations = pit_store.query_as_of(fetched_at)
    expected_series: set[SeriesKey] = {
        (instrument_id, OKX_VENUE, field, OKX_SOURCE_ID, OKX_SOURCE_VERSION)
        for instrument_id in (BTC, ETH)
        for field in FIELDS
    }
    expected_series.add(
        (BTC_DVOL, DERIBIT_VENUE, "close", DERIBIT_SOURCE_ID, DERIBIT_SOURCE_VERSION)
    )
    report = inspect_observations(
        observations,
        expected_series=expected_series,
    )
    quality = {
        "pit-1d": {
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
    }
    manifest = {
        "study": "btc-dvol-013",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/btc-dvol-013",
        "source_ids": [OKX_SOURCE_ID, DERIBIT_SOURCE_ID],
        "source_versions": {
            OKX_SOURCE_ID: OKX_SOURCE_VERSION,
            DERIBIT_SOURCE_ID: DERIBIT_SOURCE_VERSION,
        },
        "fetches": fetches,
        "quality": quality,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}")
    summary = {
        "study": "btc-dvol-013",
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
            for entry in fetches
            if entry["instrument_id"] in (BTC, ETH)
        ],
        "dvol_panel": {
            "instrument_id": BTC_DVOL,
            "hourly_points": dvol_entry["hourly_points"],
            "first_hourly_point": dvol_entry["first_hourly_point"],
            "last_hourly_point": dvol_entry["last_hourly_point"],
            "snapshots": dvol_entry["snapshots"],
            "first_snapshot": dvol_entry["first_snapshot"],
            "last_snapshot": dvol_entry["last_snapshot"],
            "missing_snapshots": dvol_entry["missing_snapshots"],
        },
        "quality_row_count": {
            store: report["row_count"] for store, report in quality.items()
        },
        "quality_issues": {
            store: report["issues"] for store, report in quality.items()
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
