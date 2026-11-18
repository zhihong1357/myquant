"""Fetch Hyperliquid candles for the low-volatility study into the local cache.

Run after preregistration and after restoring the OKX cache with study
001's fetch script, from the repo root:

    .venv/bin/python research/btc-eth-001/fetch_data.py
    .venv/bin/python research/lowvol-002/fetch_data.py

Pulls daily candles (2023-01-01 to 2026-11-18) for BTC/ETH/SOL from
Hyperliquid public REST (candleSnapshot). Raw response pages go to the
gitignored cache under data/cache/lowvol-002/raw/ (content-addressed
RawStore); parsed closed, traded candles become observations in
data/cache/lowvol-002/pit-1d-hl/ (ParquetPITStore).

Hyperliquid daily bars open at 00:00 UTC (unlike OKX's 16:00 UTC), and
pre-launch candles carry zero trades (backfilled marks, no venue price
discovery): they are excluded and counted, so the panel starts at the
first actually-traded bar (2023-03-04 for SOL, the latest of the three
coins). The still-forming bar is excluded as well.

Only the manifest (endpoints, parameters, date ranges, payload SHA-256,
plus the OKX input state read from study 001's manifest at fetch time)
and the panel summary (counts only, no raw prices) are written into this
research directory for commit. Raw payloads and parquet never leave the
local cache.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from myquant.adapters.hyperliquid import (
    candles_to_observations,
    fetch_candles,
)
from myquant.pit import ParquetPITStore
from myquant.quality import SeriesKey, inspect_observations
from myquant.raw import RawStore
from myquant.sources import SourceRegistry

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "lowvol-002"
STUDY_001_ROOT = REPO_ROOT / "research" / "btc-eth-001"

SOURCE_ID = "hyperliquid-public"
SOURCE_VERSION = 1
VENUE = "hyperliquid"

# Instrument ids match research/lowvol-002/preregister.py (single source of
# truth is the committed catalog under research/lowvol-002/catalog/).
INSTRUMENTS: dict[str, str] = {
    "crypto:btc-usdt-perp": "BTC",
    "crypto:eth-usdt-perp": "ETH",
    "crypto:sol-usdt-perp": "SOL",
}

DAILY_START = datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
DAILY_END = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)

FETCH_PLAN: tuple[tuple[str, datetime, datetime], ...] = (
    ("crypto:btc-usdt-perp", DAILY_START, DAILY_END),
    ("crypto:eth-usdt-perp", DAILY_START, DAILY_END),
    ("crypto:sol-usdt-perp", DAILY_START, DAILY_END),
)

FIELDS = ("open", "high", "low", "close", "volume")


def expected_confirmed_opens(
    start: datetime,
    end: datetime,
    as_of: datetime,
) -> list[datetime]:
    """Daily 00:00 UTC grid opens in [start, end) whose bar had closed by `as_of`."""
    step = timedelta(days=1)
    opens: list[datetime] = []
    current = start
    while current < end:
        if current + step <= as_of:
            opens.append(current)
        current += step
    return opens


def fetch_one(
    instrument_id: str,
    start: datetime,
    end: datetime,
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict:
    coin = INSTRUMENTS[instrument_id]
    result = fetch_candles(
        coin,
        "1d",
        start=start,
        end=end,
        as_of=fetched_at,
        delay_seconds=0.5,
    )
    page_entries: list[dict[str, str]] = []
    for page in result.pages:
        record = raw_store.put(
            page.payload,
            source_id=SOURCE_ID,
            available_at=fetched_at,
            content_type="application/json",
            source_version=SOURCE_VERSION,
            event_time=result.candles[-1].open_time if result.candles else None,
            ingested_at=fetched_at,
        )
        page_entries.append(
            {
                "endpoint": "https://api.hyperliquid.xyz/info",
                "request_body": page.request_body,
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
        as_of=fetched_at,
    )
    parquet_path = pit_store.write_batch(observations)
    expected = expected_confirmed_opens(start, end, fetched_at)
    fetched_opens = {candle.open_time for candle in result.candles}
    first_open = result.candles[0].open_time if result.candles else None
    # Zero-trade candles must form exactly the leading run before the
    # first traded bar; anything else is a data surprise, fail closed.
    pre_launch = (
        [open_time for open_time in expected if open_time < first_open]
        if first_open is not None
        else []
    )
    if len(pre_launch) != result.excluded_zero_trade:
        raise ValueError(
            f"{instrument_id}: {result.excluded_zero_trade} zero-trade "
            f"candles excluded but {len(pre_launch)} expected opens precede "
            "the first traded bar; refusing to guess the gap structure"
        )
    missing = [
        open_time
        for open_time in expected
        if open_time not in fetched_opens and open_time not in set(pre_launch)
    ]
    return {
        "instrument_id": instrument_id,
        "hyperliquid_coin": coin,
        "bar": "1d",
        "endpoint": "https://api.hyperliquid.xyz/info",
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
        "excluded_unclosed": result.excluded_unclosed,
        "excluded_zero_trade": result.excluded_zero_trade,
        "missing_bars": len(missing),
        "missing_bar_opens": [item.isoformat() for item in missing],
        "pages": page_entries,
        "pit_store": "pit-1d-hl",
        "pit_parquet": parquet_path.name,
        "pit_parquet_sha256": parquet_path.stem,
        "observation_rows": len(observations),
    }


def read_okx_inputs() -> dict:
    """Record study 001's OKX fetch state at this fetch's time.

    Study 002's OKX panels come from study 001's cache (restored by
    re-running research/btc-eth-001/fetch_data.py). The manifest file on
    disk at fetch time describes that fetch; study 001's committed
    manifest is its own historical record and is left untouched.
    """
    manifest_path = STUDY_001_ROOT / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    return {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "fetched_at": manifest["fetched_at"],
        "cache_root": "data/cache/btc-eth-001",
        "fetches": [
            {
                "instrument_id": entry["instrument_id"],
                "bar": entry["bar"],
                "candles": entry["candles"],
                "missing_bars": entry["missing_bars"],
                "first_bar_open": entry["first_bar_open"],
                "last_bar_open": entry["last_bar_open"],
            }
            for entry in manifest["fetches"]
        ],
    }


def main() -> None:
    fetched_at = datetime.now(UTC)
    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    source_registry.require_research_permission(SOURCE_ID, version=SOURCE_VERSION)
    pit_store = ParquetPITStore(CACHE_ROOT / "pit-1d-hl", source_registry)

    fetches: list[dict] = []
    for instrument_id, start, end in FETCH_PLAN:
        entry = fetch_one(
            instrument_id,
            start,
            end,
            raw_store=raw_store,
            pit_store=pit_store,
            fetched_at=fetched_at,
        )
        fetches.append(entry)
        print(
            f"{instrument_id} 1d: {entry['candles']} candles, "
            f"{entry['excluded_zero_trade']} zero-trade excluded, "
            f"{entry['excluded_unclosed']} unclosed excluded, "
            f"{entry['missing_bars']} missing, "
            f"{len(entry['pages'])} pages"
        )

    observations = pit_store.query_as_of(fetched_at)
    expected_series: set[SeriesKey] = {
        (instrument_id, VENUE, field, SOURCE_ID, SOURCE_VERSION)
        for instrument_id, _, _ in FETCH_PLAN
        for field in FIELDS
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
    manifest = {
        "study": "lowvol-002",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/lowvol-002",
        "source_id": SOURCE_ID,
        "source_version": SOURCE_VERSION,
        "fetches": fetches,
        "quality": {"pit-1d-hl": quality},
        "okx_inputs": read_okx_inputs(),
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}")
    summary = {
        "study": "lowvol-002",
        "fetched_at": fetched_at.isoformat(),
        "panels": [
            {
                "instrument_id": entry["instrument_id"],
                "bar": entry["bar"],
                "candles": entry["candles"],
                "expected_confirmed_bars": entry["expected_confirmed_bars"],
                "excluded_zero_trade": entry["excluded_zero_trade"],
                "excluded_unclosed": entry["excluded_unclosed"],
                "missing_bars": entry["missing_bars"],
                "first_bar_open": entry["first_bar_open"],
                "last_bar_open": entry["last_bar_open"],
            }
            for entry in fetches
        ],
        "quality_row_count": {"pit-1d-hl": quality["row_count"]},
        "quality_issues": {"pit-1d-hl": quality["issues"]},
        "okx_inputs": manifest["okx_inputs"],
    }
    summary_path = ROOT / "panel-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"panel summary written: {summary_path}")


if __name__ == "__main__":
    main()
