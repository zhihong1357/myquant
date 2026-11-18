"""Fetch the Stage 5a funding-rate history: OKX settled funding rates.

Run from the repo root:

    .venv/bin/python research/funding-history/fetch_data.py

Pulls the full reachable funding-rate history for BTC-USDT-SWAP,
ETH-USDT-SWAP and SOL-USDT-SWAP from OKX
``/public/funding-rate-history`` (public, no key), paging backwards
with the ``after`` cursor until the endpoint returns an empty page.
Also fetches the live ``/public/funding-rate`` row per instrument so
the settled rate can be cross-checked against the history row at the
previous settlement time.

Verified endpoint behaviour (2026-11-19; see
``src/myquant/adapters/okx_funding.py``):

- ``after=<ms>`` pages backwards (rows strictly older than the
  cursor, newest first, at most 100 per page). ``before`` does NOT
  page backwards on this endpoint — it acts as a lower bound — and
  is never sent.
- Reachable depth is about 93 days (oldest rows 2026-08-17). The
  exact retention rule is unknown; the manifest records the observed
  floor and the fetch date.

Raw response pages go to the gitignored cache under
``data/cache/funding-history/raw/`` (content-addressed RawStore).
Only the manifest (endpoints, parameters, per-page payload SHA-256
and RawStore record IDs, counts, time ranges, cross-checks) is
written into this research directory for commit. Raw payloads never
leave the local cache.

The manifest's own SHA-256 is not reproducible across pulls: it
embeds fetch timestamps. The fetched data is reproducible while the
window stays inside the endpoint's retention depth.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from myquant.adapters.okx_funding import (
    fetch_current_funding_rate,
    fetch_funding_history,
)
from myquant.raw import RawStore
from myquant.sources import SourceRegistry

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "funding-history"

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
INSTRUMENTS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay-seconds", type=float, default=0.2)
    args = parser.parse_args()

    fetched_at = datetime.now(UTC)
    raw_store = RawStore(CACHE_ROOT / "raw")
    source_registry = SourceRegistry(ROOT / "sources")
    source_registry.require_research_permission(
        OKX_SOURCE_ID, version=OKX_SOURCE_VERSION
    )

    manifest: dict = {
        "cache_root": "data/cache/funding-history",
        "source_id": OKX_SOURCE_ID,
        "source_version": OKX_SOURCE_VERSION,
        "endpoint": "/public/funding-rate-history",
        "current_endpoint": "/public/funding-rate",
        "fetch_started_at": fetched_at.isoformat(),
        "note": (
            "The manifest's own SHA-256 is not reproducible across pulls: "
            "it embeds fetch timestamps. The fetched data is reproducible "
            "while the window stays inside the endpoint's ~93-day depth "
            "(oldest rows 2026-08-17 as of 2026-11-19)."
        ),
        "instruments": {},
    }

    for inst_id in INSTRUMENTS:
        pages: list[dict] = []

        def _store_page(page, _pages=pages) -> None:
            record = raw_store.put(
                page.payload,
                source_id=OKX_SOURCE_ID,
                source_version=OKX_SOURCE_VERSION,
                available_at=fetched_at,
                content_type="application/json",
            )
            _pages.append(
                {
                    "url": page.url,
                    "record_id": record.record_id,
                    "payload_sha256": record.payload_sha256,
                    "byte_length": record.byte_length,
                }
            )

        fetched = fetch_funding_history(
            inst_id,
            page_size=100,
            delay_seconds=args.delay_seconds,
            on_page=_store_page,
        )
        rates = fetched.rates
        # The live current-rate row, for the settled-rate cross-check.
        current, current_page = fetch_current_funding_rate(inst_id)
        current_record = raw_store.put(
            current_page.payload,
            source_id=OKX_SOURCE_ID,
            source_version=OKX_SOURCE_VERSION,
            available_at=current.timestamp,
            content_type="application/json",
            # The exchange clock can run ahead of the local clock;
            # clamp ingestion so the RawStore invariant holds.
            ingested_at=max(datetime.now(UTC), current.timestamp),
        )
        cross_check: dict = {
            "current_record_id": current_record.record_id,
            "current_payload_sha256": current_record.payload_sha256,
            "current_funding_rate": current.funding_rate,
            "current_funding_time": current.funding_time.isoformat(),
            "next_funding_time": current.next_funding_time.isoformat(),
            "prev_funding_time": (
                current.prev_funding_time.isoformat()
                if current.prev_funding_time is not None
                else None
            ),
            "settled_funding_rate": current.settled_funding_rate,
            "max_funding_rate": current.max_funding_rate,
            "min_funding_rate": current.min_funding_rate,
        }
        if current.prev_funding_time is not None and current.settled_funding_rate is not None:
            history_row = next(
                (
                    row
                    for row in rates
                    if row.settlement_time == current.prev_funding_time
                ),
                None,
            )
            cross_check["history_row_at_prev_settlement"] = (
                history_row.funding_rate if history_row is not None else None
            )
            cross_check["settled_rate_matches_history"] = (
                history_row is not None
                and history_row.funding_rate == current.settled_funding_rate
            )
        manifest["instruments"][inst_id] = {
            "page_count": len(pages),
            "pages": pages,
            "rate_count": len(rates),
            "first_settlement": rates[0].settlement_time.isoformat() if rates else None,
            "last_settlement": rates[-1].settlement_time.isoformat() if rates else None,
            "rate_not_equal_realized_count": sum(
                1 for row in rates if row.funding_rate != row.realized_rate
            ),
            "methods": sorted({row.method for row in rates}),
            "formula_types": sorted({row.formula_type for row in rates}),
            "current_rate": cross_check,
        }
        print(
            f"{inst_id}: {len(rates)} rows, {len(pages)} pages, "
            f"{rates[0].settlement_time.isoformat()} -> "
            f"{rates[-1].settlement_time.isoformat()}, "
            f"settled-rate cross-check: "
            f"{cross_check.get('settled_rate_matches_history')}"
        )

    manifest["fetch_finished_at"] = datetime.now(UTC).isoformat()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"manifest written: {manifest_path}")


if __name__ == "__main__":
    main()
