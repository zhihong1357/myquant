"""Fetch the Stage 5a validation panel: daily OKX candles + specs.

Run from the repo root:

    .venv/bin/python research/portfolio-5a/fetch_panel.py

Pulls confirmed 1D candles for BTC-USDT-SWAP, ETH-USDT-SWAP and
SOL-USDT-SWAP with open times in [2026-09-30T16:00Z,
2026-11-18T16:00Z) — 49 daily bars per instrument, the first bar
covering 2026-10-01 in UTC+8 and the last bar closing
2026-11-18T16:00Z — plus the instrument specifications
(contract value, tick size, lot/min size) for the same three swaps
from ``/public/instruments``.

Daily bars open at 16:00 UTC (midnight UTC+8); a bar's values are
knowable at its close (open + 24h). Only confirmed bars are kept;
the script fails loudly if the 49-bar grid is incomplete, since the
validation depends on a complete panel.

Raw response pages go to the gitignored cache under
``data/cache/portfolio-5a/raw/`` (content-addressed RawStore).
Only the manifest (endpoints, parameters, per-page payload SHA-256
and RawStore record IDs, counts, time ranges, contract specs) is
written into this research directory for commit. Raw payloads never
leave the local cache.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from myquant.adapters.okx import fetch_history
from myquant.raw import RawStore
from myquant.sources import SourceRegistry

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "portfolio-5a"

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
INSTRUMENTS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP")
BAR = "1D"
WINDOW_START = datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
EXPECTED_BARS = 49
INSTRUMENTS_URL = "https://www.okx.com/api/v5/public/instruments"


def _fetch_instruments(inst_id: str) -> bytes:
    """Fetch one instrument's spec row (small public call, retried)."""
    url = f"{INSTRUMENTS_URL}?instType=SWAP&instId={inst_id}"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "myquant-research/0.1"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                return bytes(response.read())
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(1.0 * (2**attempt))
    raise RuntimeError(f"instruments fetch failed for {inst_id}: {last_error}")


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
        "cache_root": "data/cache/portfolio-5a",
        "source_id": OKX_SOURCE_ID,
        "source_version": OKX_SOURCE_VERSION,
        "endpoint": "/market/history-candles",
        "instruments_endpoint": "/public/instruments",
        "bar": BAR,
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "expected_bars_per_instrument": EXPECTED_BARS,
        "fetch_started_at": fetched_at.isoformat(),
        "note": (
            "Daily bars open at 16:00 UTC (midnight UTC+8). The window "
            "covers 2026-10-01 to 2026-11-18 in UTC+8 terms; the first "
            "bar opens 2026-09-30T16:00Z and the last closes "
            "2026-11-18T16:00Z."
        ),
        "instruments": {},
    }

    for inst_id in INSTRUMENTS:
        fetched = fetch_history(
            inst_id,
            BAR,
            start=WINDOW_START,
            end=WINDOW_END,
            delay_seconds=args.delay_seconds,
        )
        candles = fetched.candles
        if len(candles) != EXPECTED_BARS:
            raise RuntimeError(
                f"{inst_id}: expected {EXPECTED_BARS} bars, got {len(candles)}; "
                "refusing to write an incomplete panel"
            )
        expected_open = WINDOW_START
        for candle in candles:
            if candle.open_time != expected_open:
                raise RuntimeError(
                    f"{inst_id}: grid gap at {expected_open.isoformat()} "
                    f"(got {candle.open_time.isoformat()})"
                )
            expected_open += timedelta(days=1)
        pages: list[dict] = []
        for page in fetched.pages:
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
        spec_payload = _fetch_instruments(inst_id)
        spec_record = raw_store.put(
            spec_payload,
            source_id=OKX_SOURCE_ID,
            source_version=OKX_SOURCE_VERSION,
            available_at=fetched_at,
            content_type="application/json",
        )
        spec = json.loads(spec_payload.decode("utf-8"))["data"][0]
        manifest["instruments"][inst_id] = {
            "candle_pages": pages,
            "candle_count": len(candles),
            "first_open": candles[0].open_time.isoformat(),
            "last_open": candles[-1].open_time.isoformat(),
            "last_close": candles[-1].close_time.isoformat(),
            "first_close_price": candles[0].close,
            "last_close_price": candles[-1].close,
            "instruments_record_id": spec_record.record_id,
            "instruments_payload_sha256": spec_record.payload_sha256,
            "contract_value": spec["ctVal"],
            "contract_type": spec["ctType"],
            "tick_size": spec["tickSz"],
            "lot_size": spec["lotSz"],
            "min_size": spec["minSz"],
            "state": spec["state"],
        }
        print(
            f"{inst_id}: {len(candles)} bars, "
            f"{candles[0].open_time.isoformat()} -> "
            f"{candles[-1].close_time.isoformat()}, "
            f"ctVal={spec['ctVal']}, tickSz={spec['tickSz']}"
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
