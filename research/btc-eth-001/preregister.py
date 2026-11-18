"""Preregister the BTC/ETH perpetual transmission study (H0001).

Run once, before any result-level analysis:

    .venv/bin/python research/btc-eth-001/preregister.py

Registers the OKX public source, the three perpetual instruments plus the
24/7 crypto calendar, and hypothesis H0001 with its fixed windows,
parameters, test family and acceptance/rejection criteria. Re-running is
safe: identical registrations are left untouched and the hypothesis is
registered only once.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, time
from pathlib import Path

from myquant.canonical import canonical_json
from myquant.catalog import MarketCatalog
from myquant.contracts import MultiplicityCorrection
from myquant.hypotheses import (
    ExpectedDirection,
    HypothesisRegistry,
    HypothesisSpec,
    SampleWindow,
)
from myquant.market import AssetClass, Instrument, InstrumentType, MarketCalendar
from myquant.sources import LicenseStatus, SourceDefinition, SourceRegistry

ROOT = Path(__file__).resolve().parent

SOURCE_ID = "okx-public"
SOURCE_VERSION = 1
HYPOTHESIS_ID = "H0001"

INSTRUMENTS: tuple[tuple[str, str, str], ...] = (
    ("crypto:btc-usdt-perp", "BTC-USDT perpetual swap (OKX)", "BTC-USDT-SWAP"),
    ("crypto:eth-usdt-perp", "ETH-USDT perpetual swap (OKX)", "ETH-USDT-SWAP"),
    ("crypto:sol-usdt-perp", "SOL-USDT perpetual swap (OKX)", "SOL-USDT-SWAP"),
)


def build_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=SOURCE_ID,
        provider="OKX",
        description=(
            "OKX public REST market candles for USDT-margined perpetual swaps "
            "(BTC-USDT-SWAP, ETH-USDT-SWAP, SOL-USDT-SWAP)"
        ),
        license_status=LicenseStatus.APPROVED,
        permission_basis=(
            "Public market data served without authentication by OKX public "
            "REST endpoints (/market/candles, /market/history-candles), used "
            "for research only; raw payloads are not redistributed. OKX Terms "
            "of Service reviewed 2026-11-18. This registry entry is an "
            "explicit research-use assertion, not a legal determination."
        ),
        terms_url="https://www.okx.com/help/terms-of-service",
        attribution="Data: OKX public market data",
        nominal_delay_seconds=0,
        timestamp_basis=(
            "Exchange event time: candle open time in UTC milliseconds; a "
            "candle's values become knowable at its close (open + bar duration)."
        ),
    )


def build_spec() -> HypothesisSpec:
    """The preregistered H0001 research plan.

    Daily bars open at 16:00 UTC (midnight UTC+8), so every daily window
    boundary is a 16:00 UTC bar open. The 1H robustness window is fixed
    in the fixed parameters below.
    """
    train_start = datetime(2023, 1, 1, 16, 0, tzinfo=UTC)
    train_end = datetime(2025, 1, 1, 16, 0, tzinfo=UTC)
    validation_start = datetime(2025, 1, 2, 16, 0, tzinfo=UTC)
    validation_end = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)
    holdout_start = datetime(2026, 1, 2, 16, 0, tzinfo=UTC)
    holdout_end = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
    return HypothesisSpec(
        hypothesis_id=HYPOTHESIS_ID,
        title="BTC perpetual returns lead ETH perpetual returns",
        research_question=(
            "Do daily BTC-USDT perpetual returns at lag 1 contain incremental "
            "information about next-day ETH-USDT perpetual returns beyond "
            "ETH's own history and a common-factor control?"
        ),
        mechanism=(
            "BTC is the largest and most liquid crypto perpetual market; "
            "information and liquidity shocks may reprice BTC first and "
            "transmit to ETH with a lag, so yesterday's BTC return predicts "
            "today's ETH return beyond ETH's own autocorrelation."
        ),
        alternative_hypothesis=(
            "Lagged BTC daily returns explain a positive, out-of-sample "
            "component of next-day ETH returns beyond ETH's own lagged return "
            "and the SOL common-factor control."
        ),
        null_hypothesis=(
            "Lagged BTC daily returns have no incremental predictive value for "
            "next-day ETH returns over ETH's own history and the "
            "common-factor control, after costs and dependence controls."
        ),
        universe=tuple(item[0] for item in INSTRUMENTS),
        source_versions=(f"{SOURCE_ID}@v{SOURCE_VERSION}",),
        observation_frequency="daily",
        horizon_seconds=86_400,
        target_definition="Next-day close-to-close ETH-USDT perpetual log return",
        feature_set=(
            "btc-log-return-lag-1@v1",
            "eth-log-return-lag-1@v1",
            "sol-log-return-lag-0@v1",
        ),
        model_definition=(
            "Partial lead-lag OLS with HAC standard errors",
            "Purged walk-forward out-of-sample evaluation",
            "1H BTC→ETH partial lead-lag as a predeclared robustness check",
        ),
        fixed_parameters=(
            "lag=1",
            "daily_max_hac_lag=5",
            "hourly_max_hac_lag=12",
            "bootstrap_block_length=10",
            "bootstrap_resamples=2000",
            "bootstrap_seed=42",
            "walk_forward_initial_train=365",
            "walk_forward_test_size=90",
            "walk_forward_embargo_days=1",
            "hourly_window_start=2026-08-20T00:00:00Z",
            "hourly_window_end=2026-11-18T00:00:00Z",
            "volatility_split_quantile=0.5",
        ),
        benchmark=(
            "ETH own-history baseline: next-day ETH return predicted from its "
            "own lagged return and the SOL common factor only"
        ),
        cost_model=(
            "Round-trip taker cost 0.10% per position flip (OKX VIP0 taker "
            "0.05% per side, assumed); sign rule on out-of-sample augmented "
            "forecasts, 1x, always invested; funding, slippage and market "
            "impact ignored"
        ),
        cost_assumptions=(
            "OKX VIP0 taker fee 0.05% per side, from the OKX public fee "
            "schedule (okx.com/fees), checked 2026-11-18; treated as an "
            "assumption, not verified for the user's account",
            "Funding rate costs ignored; perpetual funding can exceed taker "
            "fees over holding periods",
            "Slippage and market impact ignored; both would reduce any edge",
        ),
        train_window=SampleWindow(start=train_start, end=train_end),
        validation_window=SampleWindow(start=validation_start, end=validation_end),
        holdout_window=SampleWindow(start=holdout_start, end=holdout_end),
        purge_gap_seconds=86_400,
        minimum_train_observations=200,
        minimum_validation_observations=60,
        minimum_holdout_observations=60,
        primary_metric=(
            "Partial R-squared of lag-1 BTC return in the daily BTC→ETH "
            "partial lead-lag regression"
        ),
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=0.005,
        target_error_rate=0.05,
        multiple_testing_family=(
            "BTC/ETH/SOL perpetual cross-market transmission, daily and 1H "
            "(3 tests: daily BTC→ETH, daily BTC→SOL, 1H BTC→ETH)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=3,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and report "
            "the dropped count"
        ),
        acceptance_criteria=(
            "Holm-adjusted primary p-value below 0.05",
            "Primary partial R-squared at least 0.005",
            "Holdout out-of-sample incremental R-squared above 0",
            "Net daily edge after the 0.10% round-trip taker cost is positive",
        ),
        rejection_criteria=(
            "Holm-adjusted primary p-value at or above 0.05",
            "Primary partial R-squared below 0.005",
            "Holdout out-of-sample incremental R-squared at or below 0",
            "Net daily edge after costs is zero or negative",
        ),
        known_confounders=(
            "SOL common-factor proxy is itself driven by BTC and may absorb "
            "part of the transmission effect; the no-factor result is reported "
            "as an upper-bound control",
            "Common crypto market shocks move BTC, ETH and SOL together; the "
            "partial lead-lag controls for contemporaneous SOL returns only",
            "Daily bars are anchored at 16:00 UTC (midnight UTC+8); the lag-1 "
            "effect is defined on that grid",
        ),
        exclusions=(
            "Unconfirmed (forming) bars are excluded; only confirm=1 candles "
            "enter the panel",
            "Bars after the preregistered window end 2026-11-18T16:00Z are "
            "out of sample",
        ),
        random_seed=42,
    )


def register_source() -> Path:
    registry = SourceRegistry(ROOT / "sources")
    return registry.register(build_source_definition(), version=SOURCE_VERSION)


def register_catalog() -> list[Path]:
    catalog = MarketCatalog(ROOT / "catalog")
    paths = [
        catalog.register_calendar(
            MarketCalendar(
                calendar_id="crypto-24-7",
                timezone_name="UTC",
                weekdays=(0, 1, 2, 3, 4, 5, 6),
                regular_open=time(0, 0),
                regular_close=time(0, 0),
                close_day_offset=1,
            ),
            version=1,
        )
    ]
    for instrument_id, name, okx_inst_id in INSTRUMENTS:
        paths.append(
            catalog.register_instrument(
                Instrument(
                    instrument_id=instrument_id,
                    asset_class=AssetClass.CRYPTO,
                    instrument_type=InstrumentType.PERPETUAL,
                    name=name,
                    quote_currency="USDT",
                    calendar_id="crypto-24-7",
                    metadata={"okx_inst_id": okx_inst_id},
                ),
                version=1,
            )
        )
    return paths


def register_hypothesis() -> tuple[str, str]:
    """Register H0001 once; return (spec fingerprint, registration hash)."""
    registry = HypothesisRegistry(ROOT / "hypotheses")
    spec = build_spec()
    fingerprint = hashlib.sha256(
        canonical_json(spec.model_dump(mode="json"))
    ).hexdigest()
    try:
        existing = registry.get(HYPOTHESIS_ID, version=1)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if existing.spec_fingerprint != fingerprint:
            raise ValueError(
                "H0001 v1 is already registered with a different spec; "
                "amendments need a new version, not a re-run"
            )
        print("H0001 v1 already registered; leaving it untouched.")
        return existing.spec_fingerprint, existing.registration_hash
    registration = registry.register(spec)
    return registration.spec_fingerprint, registration.registration_hash


def main() -> None:
    source_path = register_source()
    print(f"registered source: {source_path}")
    for path in register_catalog():
        print(f"registered catalog entry: {path}")
    fingerprint, registration_hash = register_hypothesis()
    print(f"H0001 v1 spec fingerprint: {fingerprint}")
    print(f"H0001 v1 registration hash: {registration_hash}")
    registry = HypothesisRegistry(ROOT / "hypotheses")
    state = registry.get_state(HYPOTHESIS_ID, 1)
    print(f"H0001 v1 state: {state.value}")
    events = registry.read_events()
    print(f"hypothesis events recorded: {len(events)}")


if __name__ == "__main__":
    main()
