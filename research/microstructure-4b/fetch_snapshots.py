"""Fetch the Stage 4b dense validation dataset: live book snapshots + trades.

Run from the repo root:

    .venv/bin/python research/microstructure-4b/fetch_snapshots.py

Captures a short live window (default 10 minutes) of order-book
snapshots (sz=20) polled from ``/market/books`` at a target interval
(default 1.0s; the actual interval is whatever the request latency
allows, and is recorded), then pulls the same window's trades via
``/market/history-trades`` pagination. The 4a dataset has only two
snapshots for a two-hour tape, which cannot support crossing-cost
validation under the 4b staleness rule (a snapshot older than
``snapshot_max_age`` is unknown, never held) — this dense series is
the dataset the crossing/slippage/impact validation replays against.

Raw response pages go to the gitignored cache under
``data/cache/microstructure-4b/raw/`` (content-addressed RawStore).
Only the manifest (endpoints, parameters, time range, per-snapshot
and per-page payload SHA-256 and RawStore record IDs, counts) is
written into this research directory for commit. Raw payloads never
leave the local cache.

The manifest's own SHA-256 is not reproducible across pulls: it embeds
fetch timestamps. What is reproducible is the fetched data (the trade
window stays inside OKX's ~90-day history-trades depth; the snapshots
are a live capture and cannot be re-pulled — they exist only in the
local cache) and every number derived from it.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from myquant.adapters.okx_microstructure import (
    fetch_books_snapshot,
    fetch_trades_history,
)
from myquant.raw import RawStore
from myquant.sources import SourceRegistry

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "microstructure-4b"

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
INST_ID = "BTC-USDT-SWAP"
BOOK_DEPTH = 20

DEFAULT_DURATION_SECONDS = 600.0
DEFAULT_INTERVAL_SECONDS = 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()
    if args.duration_seconds <= 0:
        raise ValueError("duration must be positive")
    if args.interval_seconds <= 0:
        raise ValueError("interval must be positive")

    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    source_registry.require_research_permission(
        OKX_SOURCE_ID, version=OKX_SOURCE_VERSION
    )

    capture_started_at = datetime.now(UTC)
    deadline = time.monotonic() + args.duration_seconds
    snapshot_records: list[dict] = []
    snapshot_times: list[datetime] = []
    while True:
        loop_started = time.monotonic()
        snapshot, book_page = fetch_books_snapshot(
            INST_ID, depth=BOOK_DEPTH, timeout_seconds=30.0
        )
        # The exchange clock can run a fraction of a second ahead of the
        # local clock; clamp ingestion to availability so the RawStore
        # invariant (ingested_at >= available_at) holds despite skew.
        ingested = max(datetime.now(UTC), snapshot.snapshot_time)
        record = raw_store.put(
            book_page.payload,
            source_id=OKX_SOURCE_ID,
            source_version=OKX_SOURCE_VERSION,
            event_time=snapshot.snapshot_time,
            available_at=snapshot.snapshot_time,
            content_type="application/json",
            ingested_at=ingested,
        )
        snapshot_times.append(snapshot.snapshot_time)
        snapshot_records.append(
            {
                "snapshot_time": snapshot.snapshot_time.isoformat(),
                "seq_id": snapshot.seq_id,
                "best_bid": snapshot.bids[0].price if snapshot.bids else None,
                "best_ask": snapshot.asks[0].price if snapshot.asks else None,
                "ask_levels": len(snapshot.asks),
                "bid_levels": len(snapshot.bids),
                "record_id": record.record_id,
                "payload_sha256": record.payload_sha256,
                "byte_length": record.byte_length,
            }
        )
        if len(snapshot_records) % 100 == 0:
            print(f"  ... {len(snapshot_records)} snapshots stored", flush=True)
        if time.monotonic() >= deadline:
            break
        sleep_for = args.interval_seconds - (time.monotonic() - loop_started)
        if sleep_for > 0:
            time.sleep(sleep_for)
    capture_ended_at = datetime.now(UTC)
    print(
        f"snapshots: {len(snapshot_records)} in "
        f"{(capture_ended_at - capture_started_at).total_seconds():.1f}s"
    )

    window_start = snapshot_times[0]
    window_end = snapshot_times[-1]
    gaps = [
        (later - earlier).total_seconds()
        for earlier, later in zip(snapshot_times, snapshot_times[1:], strict=False)
    ]
    mean_gap = sum(gaps) / len(gaps) if gaps else 0.0
    max_gap = max(gaps) if gaps else 0.0

    # Trades for the capture window, pulled after the fact through
    # history-trades pagination (bounded: ~10 minutes).
    pages: list[dict] = []

    def _store_page(page) -> None:
        record = raw_store.put(
            page.payload,
            source_id=OKX_SOURCE_ID,
            source_version=OKX_SOURCE_VERSION,
            available_at=capture_ended_at,
            content_type="application/json",
        )
        pages.append(
            {
                "url": page.url,
                "record_id": record.record_id,
                "payload_sha256": record.payload_sha256,
                "byte_length": record.byte_length,
            }
        )

    fetched = fetch_trades_history(
        INST_ID,
        start=window_start,
        end=window_end,
        page_size=100,
        delay_seconds=0.1,
        on_page=_store_page,
    )
    print(
        f"trades: {len(fetched.trades)} in window, {len(pages)} pages, "
        f"{len(fetched.rejected)} rejected rows, "
        f"{fetched.skipped_after_end} skipped after end"
    )

    manifest: dict = {
        "cache_root": "data/cache/microstructure-4b",
        "instrument": INST_ID,
        "source_id": OKX_SOURCE_ID,
        "source_version": OKX_SOURCE_VERSION,
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "capture": {
            "target_interval_seconds": args.interval_seconds,
            "duration_seconds": args.duration_seconds,
            "snapshot_count": len(snapshot_records),
            "mean_snapshot_gap_seconds": mean_gap,
            "max_snapshot_gap_seconds": max_gap,
            "capture_started_at": capture_started_at.isoformat(),
            "capture_ended_at": capture_ended_at.isoformat(),
        },
        "snapshots": snapshot_records,
        "trades": {
            "endpoint": "/market/history-trades",
            "page_size": 100,
            "delay_seconds": 0.1,
            "page_count": len(pages),
            "pages": pages,
            "trade_count": len(fetched.trades),
            "rejected_row_count": len(fetched.rejected),
            "skipped_after_end": fetched.skipped_after_end,
            "first_trade_id": fetched.trades[0].trade_id if fetched.trades else None,
            "last_trade_id": fetched.trades[-1].trade_id if fetched.trades else None,
            "first_event_time": (
                fetched.trades[0].event_time.isoformat() if fetched.trades else None
            ),
            "last_event_time": (
                fetched.trades[-1].event_time.isoformat() if fetched.trades else None
            ),
        },
        "fetch_finished_at": datetime.now(UTC).isoformat(),
        "note": (
            "The manifest's own SHA-256 is not reproducible across pulls: "
            "it embeds fetch timestamps. The trade data is reproducible "
            "while the window stays inside OKX's ~90-day history-trades "
            "depth; the snapshots are a live capture and exist only in "
            "the local cache."
        ),
    }
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"manifest written: {manifest_path}")


if __name__ == "__main__":
    main()
