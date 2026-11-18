"""Fetch OKX candles for the BTC/ETH transmission study into the local cache.

Run after preregistration, from the repo root:

    .venv/bin/python research/btc-eth-001/fetch_data.py

Pulls daily candles (2023-01-01 to 2026-11-18) for BTC/ETH/SOL and 1H
candles (last 90 days) for BTC/ETH/SOL from OKX public REST. Raw response
pages go to the gitignored cache under data/cache/btc-eth-001/raw/
(content-addressed RawStore); parsed confirmed candles become
observations in data/cache/btc-eth-001/pit-1d/ and pit-1h/
(ParquetPITStore, one store per frequency — see pit_store_for).

Only the manifest (endpoints, parameters, date ranges, payload SHA-256)
and the panel summary (counts only, no raw prices) are written into this
research directory for commit. Raw payloads and parquet never leave the
local cache.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
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

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "btc-eth-001"

SOURCE_ID = "okx-public"
SOURCE_VERSION = 1
VENUE = "okx"

# Instrument ids match research/btc-eth-001/preregister.py (single source of
# truth is the committed catalog under research/btc-eth-001/catalog/).
INSTRUMENTS: dict[str, str] = {
    "crypto:btc-usdt-perp": "BTC-USDT-SWAP",
    "crypto:eth-usdt-perp": "ETH-USDT-SWAP",
    "crypto:sol-usdt-perp": "SOL-USDT-SWAP",
}

DAILY_START = datetime(2023, 1, 1, 16, 0, tzinfo=UTC)
DAILY_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
HOURLY_START = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)
HOURLY_END = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)

FETCH_PLAN: tuple[tuple[str, str, datetime, datetime], ...] = (
    ("crypto:btc-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:eth-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:sol-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:btc-usdt-perp", "1H", HOURLY_START, HOURLY_END),
    ("crypto:eth-usdt-perp", "1H", HOURLY_START, HOURLY_END),
    # SOL 1H is the common-factor control for the 1H robustness test, so
    # that test (c) carries the same control structure as the primary test.
    ("crypto:sol-usdt-perp", "1H", HOURLY_START, HOURLY_END),
)

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


def pit_store_for(bar: str, source_registry: SourceRegistry) -> ParquetPITStore:
    """One PIT store per bar frequency.

    Daily and hourly observations share event times (every daily bar opens
    at 16:00 UTC, which is also an hourly bar open) but carry different
    values, so they must never sit in the same store: PIT revision
    resolution keys on (instrument, venue, field, event_time, source,
    version) and would silently collapse the hourly value into the daily
    one. Frequency is part of the dataset identity, not the observation.
    """
    return ParquetPITStore(CACHE_ROOT / f"pit-{bar.lower()}", source_registry)


def fetch_one(
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
            source_id=SOURCE_ID,
            available_at=fetched_at,
            content_type="application/json",
            source_version=SOURCE_VERSION,
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
        venue=VENUE,
        source_id=SOURCE_ID,
        source_version=SOURCE_VERSION,
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


def main() -> None:
    fetched_at = datetime.now(UTC)
    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    source_registry.require_research_permission(SOURCE_ID, version=SOURCE_VERSION)
    pit_stores = {
        bar: pit_store_for(bar, source_registry) for bar in ("1D", "1H")
    }

    fetches: list[dict] = []
    for instrument_id, bar, start, end in FETCH_PLAN:
        entry = fetch_one(
            instrument_id,
            bar,
            start,
            end,
            raw_store=raw_store,
            pit_store=pit_stores[bar],
            fetched_at=fetched_at,
        )
        fetches.append(entry)
        print(
            f"{instrument_id} {bar}: {entry['candles']} candles, "
            f"{entry['missing_bars']} missing, "
            f"{len(entry['pages'])} pages"
        )

    # Quality is inspected per frequency store: daily and hourly rows share
    # event times at 16:00 UTC, so a combined inspection would flag the
    # (expected, by-design) cross-frequency overlap as revision collisions.
    quality: dict[str, dict] = {}
    for bar, store in pit_stores.items():
        observations = store.query_as_of(fetched_at)
        expected_series: set[SeriesKey] = {
            (instrument_id, VENUE, field, SOURCE_ID, SOURCE_VERSION)
            for instrument_id, plan_bar, _, _ in FETCH_PLAN
            if plan_bar == bar
            for field in FIELDS
        }
        report = inspect_observations(
            observations,
            expected_series=expected_series,
        )
        quality[f"pit-{bar.lower()}"] = {
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
    manifest = {
        "study": "btc-eth-001",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/btc-eth-001",
        "source_id": SOURCE_ID,
        "source_version": SOURCE_VERSION,
        "fetches": fetches,
        "quality": quality,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(
        f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}"
    )
    summary = {
        "study": "btc-eth-001",
        "fetched_at": fetched_at.isoformat(),
        "panels": [
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
        ],
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
