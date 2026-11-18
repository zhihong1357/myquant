"""Fetch OKX candles and Deribit data for the options-expiry study.

Run after preregistration, from the repo root:

    .venv/bin/python research/options-expiry-004/fetch_data.py

Pulls daily candles (2021-01-21 to 2026-11-18) for BTC/ETH/SOL and 1H
candles (2025-01-02 to 2026-11-18) for BTC/ETH/SOL from OKX public REST;
Deribit option instrument listings (listed + recently expired) and DVOL
daily index points for BTC/ETH from Deribit public REST. Raw response
pages go to the gitignored cache under data/cache/options-expiry-004/raw/
(content-addressed RawStore); parsed confirmed candles become
observations in data/cache/options-expiry-004/pit-1d/, pit-1h/ and
pit-dvol/ (ParquetPITStore, one store per frequency/grid — daily and
hourly observations share event times but carry different values, and
DVOL points sit on a 00:00 UTC grid, so the stores must stay separate).

The daily panel starts at SOL's first confirmed OKX bar
(2021-01-21T16:00Z); BTC and ETH history goes back further, but the
synchronized three-instrument panel cannot start earlier.

The expiry calendar is rule-constructed (last Friday of each month,
08:00 UTC) and cross-checked here against the listed Deribit expiries;
the verification record is written into the manifest. Deribit's
``get_instruments`` with ``expired=true`` returns only the most recent
batch of expired contracts, so the expired listing is recorded only to
document that limitation, not to build the calendar.

Only the manifest (endpoints, parameters, date ranges, payload SHA-256,
calendar verification) and the panel summary (counts only, no raw
prices) are written into this research directory for commit. Raw
payloads and parquet never leave the local cache.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from myquant.adapters.deribit import (
    dvol_to_observations,
    fetch_instruments,
    fetch_volatility_index,
)
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
from myquant.studies.expiry import monthly_expiries, verify_calendar_against_listed

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "options-expiry-004"

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
DERIBIT_SOURCE_ID = "deribit"
DERIBIT_SOURCE_VERSION = 1
OKX_VENUE = "okx"
DERIBIT_VENUE = "deribit"

# Instrument ids match research/options-expiry-004/preregister.py (single
# source of truth is the committed catalog under
# research/options-expiry-004/catalog/).
INSTRUMENTS: dict[str, str] = {
    "crypto:btc-usdt-perp": "BTC-USDT-SWAP",
    "crypto:eth-usdt-perp": "ETH-USDT-SWAP",
    "crypto:sol-usdt-perp": "SOL-USDT-SWAP",
}

DVOL_INSTRUMENTS: dict[str, str] = {
    "index:btc-dvol": "BTC",
    "index:eth-dvol": "ETH",
}

DAILY_START = datetime(2021, 1, 21, 16, 0, tzinfo=UTC)
DAILY_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
HOURLY_START = datetime(2025, 1, 2, 0, 0, tzinfo=UTC)
HOURLY_END = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)
DVOL_START = datetime(2021, 1, 1, 0, 0, tzinfo=UTC)
DVOL_END = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)

OKX_FETCH_PLAN: tuple[tuple[str, str, datetime, datetime], ...] = (
    ("crypto:btc-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:eth-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:sol-usdt-perp", "1D", DAILY_START, DAILY_END),
    ("crypto:btc-usdt-perp", "1H", HOURLY_START, HOURLY_END),
    ("crypto:eth-usdt-perp", "1H", HOURLY_START, HOURLY_END),
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


def pit_store_for(name: str, source_registry: SourceRegistry) -> ParquetPITStore:
    """One PIT store per frequency/grid.

    Daily and hourly observations share event times (every daily bar opens
    at 16:00 UTC, which is also an hourly bar open) but carry different
    values, so they must never sit in the same store: PIT revision
    resolution keys on (instrument, venue, field, event_time, source,
    version) and would silently collapse the hourly value into the daily
    one. DVOL points sit on a 00:00 UTC grid and are close-only. Frequency
    and grid are part of the dataset identity, not the observation.
    """
    return ParquetPITStore(CACHE_ROOT / name, source_registry)


def fetch_okx_one(
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


def fetch_deribit_instruments(
    *,
    raw_store: RawStore,
    fetched_at: datetime,
) -> dict:
    """Fetch listed and recently-expired option listings for BTC/ETH.

    Returns the manifest entry including the calendar verification
    record. The expired listing documents the API's limitation (only the
    most recent expired batch is returned); it is not used to build the
    calendar.
    """
    entries: list[dict] = []
    listed_by_currency: dict[str, set[date]] = {}
    expired_by_currency: dict[str, set[date]] = {}
    for currency in ("BTC", "ETH"):
        for expired in (False, True):
            result = fetch_instruments(
                currency, kind="option", expired=expired
            )
            page_entries: list[dict[str, str]] = []
            for page in result.pages:
                record = raw_store.put(
                    page.payload,
                    source_id=DERIBIT_SOURCE_ID,
                    available_at=fetched_at,
                    content_type="application/json",
                    source_version=DERIBIT_SOURCE_VERSION,
                    event_time=None,
                    ingested_at=fetched_at,
                )
                page_entries.append(
                    {
                        "url": page.url,
                        "payload_sha256": record.payload_sha256,
                        "record_id": record.record_id,
                    }
                )
            expiry_dates = sorted(
                {item.expiration_timestamp.date() for item in result.instruments}
            )
            if expired:
                expired_by_currency[currency] = set(expiry_dates)
            else:
                listed_by_currency[currency] = set(expiry_dates)
            entries.append(
                {
                    "currency": currency,
                    "kind": "option",
                    "expired": expired,
                    "endpoint": "https://www.deribit.com/api/v2/public/get_instruments",
                    "instruments": len(result.instruments),
                    "distinct_expiry_dates": [
                        item.isoformat() for item in expiry_dates
                    ],
                    "pages": page_entries,
                }
            )
    listed_union = listed_by_currency["BTC"] | listed_by_currency["ETH"]
    verification = verify_calendar_against_listed(
        listed_union,
        as_of=fetched_at.date(),
        btc_expiry_dates=listed_by_currency["BTC"],
        eth_expiry_dates=listed_by_currency["ETH"],
    )
    return {
        "listings": entries,
        "calendar_verification": verification,
        "expired_listing_note": (
            "The expired=true listing returns only the most recent batch "
            "of expired contracts (see distinct_expiry_dates for "
            "expired=true); it cannot reconstruct the historical expiry "
            "calendar, which is why the calendar is rule-constructed."
        ),
        "expired_expiry_dates": {
            currency: sorted(item.isoformat() for item in dates)
            for currency, dates in expired_by_currency.items()
        },
    }


def fetch_dvol_one(
    instrument_id: str,
    *,
    raw_store: RawStore,
    pit_store: ParquetPITStore,
    fetched_at: datetime,
) -> dict:
    currency = DVOL_INSTRUMENTS[instrument_id]
    result = fetch_volatility_index(
        currency,
        start=DVOL_START,
        end=DVOL_END,
        delay_seconds=0.2,
    )
    page_entries: list[dict[str, str]] = []
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
        page_entries.append(
            {
                "url": page.url,
                "payload_sha256": record.payload_sha256,
                "record_id": record.record_id,
            }
        )
    observations = dvol_to_observations(
        result.points,
        instrument_id=instrument_id,
        venue=DERIBIT_VENUE,
        source_id=DERIBIT_SOURCE_ID,
        source_version=DERIBIT_SOURCE_VERSION,
        ingested_at=fetched_at,
    )
    parquet_path = pit_store.write_batch(observations)
    return {
        "instrument_id": instrument_id,
        "deribit_currency": currency,
        "endpoint": "https://www.deribit.com/api/v2/public/get_volatility_index_data",
        "window_start": DVOL_START.isoformat(),
        "window_end": DVOL_END.isoformat(),
        "points": len(result.points),
        "first_point": result.points[0].timestamp.isoformat() if result.points else None,
        "last_point": (
            result.points[-1].timestamp.isoformat() if result.points else None
        ),
        "pages": page_entries,
        "pit_store": "pit-dvol",
        "pit_parquet": parquet_path.name,
        "pit_parquet_sha256": parquet_path.stem,
        "observation_rows": len(observations),
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
    source_registry.require_research_permission(
        OKX_SOURCE_ID, version=OKX_SOURCE_VERSION
    )
    source_registry.require_research_permission(
        DERIBIT_SOURCE_ID, version=DERIBIT_SOURCE_VERSION
    )
    pit_stores = {
        "pit-1d": pit_store_for("pit-1d", source_registry),
        "pit-1h": pit_store_for("pit-1h", source_registry),
        "pit-dvol": pit_store_for("pit-dvol", source_registry),
    }

    okx_fetches: list[dict] = []
    for instrument_id, bar, start, end in OKX_FETCH_PLAN:
        entry = fetch_okx_one(
            instrument_id,
            bar,
            start,
            end,
            raw_store=raw_store,
            pit_store=pit_stores[f"pit-{bar.lower()}"],
            fetched_at=fetched_at,
        )
        okx_fetches.append(entry)
        print(
            f"{instrument_id} {bar}: {entry['candles']} candles, "
            f"{entry['missing_bars']} missing, {len(entry['pages'])} pages"
        )

    deribit_instruments = fetch_deribit_instruments(
        raw_store=raw_store, fetched_at=fetched_at
    )
    for listing in deribit_instruments["listings"]:
        print(
            f"Deribit {listing['currency']} options expired={listing['expired']}: "
            f"{listing['instruments']} instruments, "
            f"{len(listing['distinct_expiry_dates'])} distinct expiries"
        )
    verification = deribit_instruments["calendar_verification"]
    print(f"calendar verification passed: {verification['all_checks_passed']}")

    dvol_fetches: list[dict] = []
    for instrument_id in DVOL_INSTRUMENTS:
        entry = fetch_dvol_one(
            instrument_id,
            raw_store=raw_store,
            pit_store=pit_stores["pit-dvol"],
            fetched_at=fetched_at,
        )
        dvol_fetches.append(entry)
        print(
            f"{instrument_id}: {entry['points']} DVOL points, "
            f"{entry['first_point']} .. {entry['last_point']}"
        )

    # The constructed expiry calendar for the daily sample period
    # (coverage only: counts and range, no result-level information).
    expiries = monthly_expiries(DAILY_START.date(), DAILY_END.date())
    calendar_record = {
        "rule": "last Friday of each calendar month, 08:00 UTC",
        "sample_start": DAILY_START.date().isoformat(),
        "sample_end": DAILY_END.date().isoformat(),
        "monthly_expiries": len(expiries),
        "quarterly_expiries": sum(event.is_quarterly for event in expiries),
        "first_expiry": expiries[0].expiry_date.isoformat() if expiries else None,
        "last_expiry": expiries[-1].expiry_date.isoformat() if expiries else None,
        "source": (
            "Rule-constructed from the public Deribit rule; verified "
            "against listed expiries (calendar_verification) and the "
            "official Deribit Contract Introduction Policy. Not pulled "
            "from historical contracts: the public API returns only the "
            "most recent expired batch."
        ),
    }

    quality: dict[str, dict] = {}
    for store_name in ("pit-1d", "pit-1h"):
        expected_series: set[SeriesKey] = {
            (instrument_id, OKX_VENUE, field, OKX_SOURCE_ID, OKX_SOURCE_VERSION)
            for instrument_id in INSTRUMENTS
            for field in FIELDS
        }
        quality[store_name] = inspect_store(
            pit_stores[store_name], expected_series, as_of=fetched_at
        )
    dvol_expected: set[SeriesKey] = {
        (
            instrument_id,
            DERIBIT_VENUE,
            "close",
            DERIBIT_SOURCE_ID,
            DERIBIT_SOURCE_VERSION,
        )
        for instrument_id in DVOL_INSTRUMENTS
    }
    quality["pit-dvol"] = inspect_store(
        pit_stores["pit-dvol"], dvol_expected, as_of=fetched_at
    )

    manifest = {
        "study": "options-expiry-004",
        "fetched_at": fetched_at.isoformat(),
        "cache_root": "data/cache/options-expiry-004",
        "okx_fetches": okx_fetches,
        "deribit_instruments": deribit_instruments,
        "dvol_fetches": dvol_fetches,
        "expiry_calendar": calendar_record,
        "quality": quality,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    print(f"manifest written: {manifest_path}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()}")
    summary = {
        "study": "options-expiry-004",
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
            for entry in okx_fetches
        ],
        "deribit_listings": [
            {
                "currency": listing["currency"],
                "expired": listing["expired"],
                "instruments": listing["instruments"],
                "distinct_expiry_dates": listing["distinct_expiry_dates"],
            }
            for listing in deribit_instruments["listings"]
        ],
        "calendar_verification": verification,
        "expiry_calendar": calendar_record,
        "dvol_panels": [
            {
                "instrument_id": entry["instrument_id"],
                "points": entry["points"],
                "first_point": entry["first_point"],
                "last_point": entry["last_point"],
            }
            for entry in dvol_fetches
        ],
        "quality_row_count": {
            name: report["row_count"] for name, report in quality.items()
        },
        "quality_issues": {
            name: report["issues"] for name, report in quality.items()
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
