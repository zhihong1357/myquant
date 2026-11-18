"""Fetch the Stage 4a validation dataset: OKX trades + book snapshots.

Run from the repo root:

    .venv/bin/python research/microstructure-4a/fetch_data.py

Pulls BTC-USDT-SWAP trades for a bounded two-hour window (default
2026-11-18 05:00-07:00 UTC, two complete UTC hours) via
``/market/history-trades`` pagination, plus one order-book snapshot
(sz=20) and one ticker before and after the trades pull. Raw response
pages go to the gitignored cache under
``data/cache/microstructure-4a/raw/`` (content-addressed RawStore).

Only the manifest (endpoints, parameters, time range, per-page
payload SHA-256 and RawStore record IDs, counts, trade-ID range,
book-snapshot records and ticker cross-checks) is written into this
research directory for commit. Raw payloads never leave the local
cache.

The manifest's own SHA-256 is not reproducible across pulls: it embeds
the fetch timestamps. What is reproducible is the fetched data (given
the window stays inside OKX's ~90-day history-trades depth) and every
number derived from it.

Use ``--start`` / ``--end`` (ISO UTC, e.g. 2026-11-18T05:00:00Z) to
pull a different window. Windows longer than a few hours are
impractical through REST at ~40 trades/s and 100 rows per page; see
``docs/microstructure.md`` for the forward-recorder design.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from myquant.adapters.okx_microstructure import (
    fetch_books_snapshot,
    fetch_ticker,
    fetch_trades_history,
)
from myquant.raw import RawStore
from myquant.sources import SourceRegistry

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "microstructure-4a"

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
INST_ID = "BTC-USDT-SWAP"
BOOK_DEPTH = 20

DEFAULT_START = datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)
DEFAULT_END = datetime(2026, 11, 18, 7, 0, 0, tzinfo=UTC)


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must carry a timezone: {value!r}")
    return parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-11-18T05:00:00Z")
    parser.add_argument("--end", default="2026-11-18T07:00:00Z")
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    args = parser.parse_args()
    start = _parse_iso(args.start)
    end = _parse_iso(args.end)

    fetched_at = datetime.now(UTC)
    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    source_registry.require_research_permission(
        OKX_SOURCE_ID, version=OKX_SOURCE_VERSION
    )

    manifest: dict = {
        "cache_root": "data/cache/microstructure-4a",
        "instrument": INST_ID,
        "source_id": OKX_SOURCE_ID,
        "source_version": OKX_SOURCE_VERSION,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "fetch_started_at": fetched_at.isoformat(),
        "note": (
            "The manifest's own SHA-256 is not reproducible across pulls: "
            "it embeds fetch timestamps. The fetched data is reproducible "
            "while the window stays inside OKX's ~90-day history-trades depth."
        ),
    }

    def take_book_snapshot(label: str) -> dict:
        snapshot, book_page = fetch_books_snapshot(
            INST_ID, depth=BOOK_DEPTH, timeout_seconds=30.0
        )
        ticker, ticker_page = fetch_ticker(INST_ID, timeout_seconds=30.0)
        # The exchange clock can run a fraction of a second ahead of the
        # local clock; clamp ingestion to availability so the RawStore
        # invariant (ingested_at >= available_at) holds despite skew.
        book_ingested = max(datetime.now(UTC), snapshot.snapshot_time)
        ticker_ingested = max(datetime.now(UTC), ticker.ticker_time)
        book_record = raw_store.put(
            book_page.payload,
            source_id=OKX_SOURCE_ID,
            source_version=OKX_SOURCE_VERSION,
            event_time=snapshot.snapshot_time,
            available_at=snapshot.snapshot_time,
            content_type="application/json",
            ingested_at=book_ingested,
        )
        ticker_record = raw_store.put(
            ticker_page.payload,
            source_id=OKX_SOURCE_ID,
            source_version=OKX_SOURCE_VERSION,
            event_time=ticker.ticker_time,
            available_at=ticker.ticker_time,
            content_type="application/json",
            ingested_at=ticker_ingested,
        )
        record = {
            "label": label,
            "snapshot_time": snapshot.snapshot_time.isoformat(),
            "seq_id": snapshot.seq_id,
            "best_bid": snapshot.bids[0].price if snapshot.bids else None,
            "best_ask": snapshot.asks[0].price if snapshot.asks else None,
            "ask_levels": len(snapshot.asks),
            "bid_levels": len(snapshot.bids),
            "book_record_id": book_record.record_id,
            "book_payload_sha256": book_record.payload_sha256,
            "ticker_time": ticker.ticker_time.isoformat(),
            "ticker_bid": ticker.bid_price,
            "ticker_ask": ticker.ask_price,
            "ticker_last": ticker.last_price,
            "ticker_record_id": ticker_record.record_id,
            "ticker_payload_sha256": ticker_record.payload_sha256,
            "ticker_book_bid_match": (
                ticker.bid_price == snapshot.bids[0].price if snapshot.bids else None
            ),
            "ticker_book_ask_match": (
                ticker.ask_price == snapshot.asks[0].price if snapshot.asks else None
            ),
        }
        print(
            f"[{label}] book snapshot {snapshot.snapshot_time.isoformat()} "
            f"best {record['best_bid']} / {record['best_ask']}; "
            f"ticker bid/ask match: "
            f"{record['ticker_book_bid_match']}/{record['ticker_book_ask_match']}"
        )
        return record

    # One book snapshot + ticker before the trades pull, one after.
    book_records = [take_book_snapshot("before")]

    # Pages are persisted incrementally as they arrive, so a long pull
    # that fails midway still keeps the pages it already fetched.
    pages: list[dict] = []

    def _store_page(page) -> None:
        record = raw_store.put(
            page.payload,
            source_id=OKX_SOURCE_ID,
            source_version=OKX_SOURCE_VERSION,
            available_at=fetched_at,
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
        if len(pages) % 500 == 0:
            print(f"  ... {len(pages)} pages stored", flush=True)

    fetched = fetch_trades_history(
        INST_ID,
        start=start,
        end=end,
        page_size=100,
        delay_seconds=args.delay_seconds,
        on_page=_store_page,
    )
    manifest["trades"] = {
        "endpoint": "/market/history-trades",
        "page_size": 100,
        "delay_seconds": args.delay_seconds,
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
    }
    print(
        f"trades: {len(fetched.trades)} in window, "
        f"{len(pages)} pages, {len(fetched.rejected)} rejected rows, "
        f"{fetched.skipped_after_end} skipped after end"
    )

    book_records.append(take_book_snapshot("after"))

    manifest["books"] = book_records
    manifest["fetch_finished_at"] = datetime.now(UTC).isoformat()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"manifest written: {manifest_path}")


if __name__ == "__main__":
    main()
