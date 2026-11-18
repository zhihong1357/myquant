"""Shared dataset loader for the Stage 4b research scripts.

Loads a microstructure dataset from its committed manifest plus the
gitignored RawStore cache: re-reads the raw pages (verifying
checksums on read), re-parses them through the adapter, normalizes
trades and book snapshots, and filters trades to the manifest window.

Handles both manifest shapes: the 4a shape (``books`` entries with
``book_record_id``) and the 4b shape (``snapshots`` entries with
``record_id``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from myquant.adapters.okx_microstructure import (
    OKXTrade,
    parse_books_response,
    parse_trades_response,
)
from myquant.microstructure import (
    BookSnapshot,
    Trade,
    normalize_books_snapshot,
    normalize_trades,
)
from myquant.raw import RawStore

INST_ID = "BTC-USDT-SWAP"
INSTRUMENT_ID = "crypto:btc-usdt-perp"
VENUE = "okx"
SOURCE_ID = "okx-public"
SOURCE_VERSION = 1


@dataclass(frozen=True)
class LoadedDataset:
    """Normalized trades + snapshots for one manifest window."""

    trades: tuple[Trade, ...]
    snapshots: tuple[BookSnapshot, ...]
    manifest: dict[str, Any]
    parse_rejected: int
    duplicate_trade_ids: int
    non_monotonic: int


def load_dataset(manifest_path: str | Path, cache_root: str | Path) -> LoadedDataset:
    """Load and normalize one dataset from its manifest + RawStore cache."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_store = RawStore(Path(cache_root) / "raw")
    loaded_at = datetime.now(UTC)
    window_start = datetime.fromisoformat(manifest["window"]["start"])
    window_end = datetime.fromisoformat(manifest["window"]["end"])

    okx_trades: list[OKXTrade] = []
    parse_rejected = 0
    for page_entry in manifest["trades"]["pages"]:
        payload = raw_store.read_payload(page_entry["record_id"])
        page = parse_trades_response(payload, inst_id=INST_ID)
        okx_trades.extend(page.trades)
        parse_rejected += len(page.rejected)
    normalized = normalize_trades(
        okx_trades,
        parse_rejected=parse_rejected,
        instrument_id=INSTRUMENT_ID,
        venue=VENUE,
        source_id=SOURCE_ID,
        source_version=SOURCE_VERSION,
        ingested_at=loaded_at,
    )
    trades = tuple(
        t for t in normalized.trades if window_start <= t.event_time < window_end
    )

    snapshot_entries = manifest.get("snapshots", manifest.get("books", []))
    snapshots: list[BookSnapshot] = []
    for entry in snapshot_entries:
        record_id = entry.get("record_id") or entry.get("book_record_id")
        payload = raw_store.read_payload(record_id)
        okx_snapshot = parse_books_response(payload, inst_id=INST_ID)
        normalized_book = normalize_books_snapshot(
            okx_snapshot,
            instrument_id=INSTRUMENT_ID,
            venue=VENUE,
            source_id=SOURCE_ID,
            source_version=SOURCE_VERSION,
            ingested_at=loaded_at,
        )
        snapshots.append(normalized_book.snapshot)
    snapshots.sort(key=lambda snap: snap.snapshot_time)

    return LoadedDataset(
        trades=trades,
        snapshots=tuple(snapshots),
        manifest=manifest,
        parse_rejected=parse_rejected,
        duplicate_trade_ids=normalized.report.duplicate_trade_ids,
        non_monotonic=normalized.report.non_monotonic,
    )
