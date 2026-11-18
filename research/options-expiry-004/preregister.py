"""Preregister the options-expiry study (H0005, H0006).

Run once, before any expiry-window result is computed:

    .venv/bin/python research/options-expiry-004/preregister.py

Registers the OKX and Deribit public sources, the three perpetual
instruments plus the BTC/ETH DVOL indices and the 24/7 crypto calendar,
and two hypotheses:

- H0005 (transmission): BTC→ETH daily transmission is stronger inside
  Deribit monthly option expiry windows (bar-open dates T-3..T) than
  outside them.
- H0006 (volatility level): mean daily absolute log return is higher
  on expiry-window days than on non-window days (BTC primary, ETH
  secondary).

Expiry calendar: monthly expiries are the last Friday of each calendar
month at 08:00 UTC, per the public Deribit rule. The rule was
cross-checked two ways on 2026-11-18: (a) the listed forward
monthly/quarterly expiries all fall on last Fridays and the BTC and ETH
expiry sets are identical; (b) the official Deribit Contract
Introduction Policy states the same last-Friday rule. The calendar is
rule-constructed, not pulled from historical contracts: Deribit's
``get_instruments`` with ``expired=true`` returns only the most recent
batch of expired contracts and cannot reconstruct the historical
calendar.

Mechanism red line: the expiry window is only a PROXY for
dealer-hedging intensity. Deribit public data reports whole-market
per-contract open interest and Greeks, not dealer positions, so no
claim about dealer net gamma, dealer positions or hedging flow can be
verified from public data. This study tests the expiry-window effect
itself (whether volatility and transmission differ inside the window);
any hedging interpretation is inference, not observation. In crypto,
forced buying and selling are dominated by perpetual liquidations, open
interest and funding rates; options gamma is only an environment
variable.

Time convention: Deribit settles Friday 08:00 UTC; OKX daily bars open
16:00 UTC, so the T-day daily return spans the settlement moment. Under
the close-to-close convention the return indexed at bar open t measures
the price change over [t, t + 24h): the T-1 bar's interval contains the
settlement moment and the T bar is the first full post-settlement bar.

Re-running is safe: identical registrations are left untouched and each
hypothesis is registered only once.
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

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
DERIBIT_SOURCE_ID = "deribit"
DERIBIT_SOURCE_VERSION = 1

INSTRUMENTS: tuple[tuple[str, str, str], ...] = (
    ("crypto:btc-usdt-perp", "BTC-USDT perpetual swap", "BTC-USDT-SWAP"),
    ("crypto:eth-usdt-perp", "ETH-USDT perpetual swap", "ETH-USDT-SWAP"),
    ("crypto:sol-usdt-perp", "SOL-USDT perpetual swap", "SOL-USDT-SWAP"),
)

DVOL_INDICES: tuple[tuple[str, str, str, str], ...] = (
    ("index:btc-dvol", "Deribit Volatility Index (BTC DVOL)", "btc_vol", "BTC"),
    ("index:eth-dvol", "Deribit Volatility Index (ETH DVOL)", "eth_vol", "ETH"),
)

# Daily windows (16:00 UTC bar opens). The daily panel starts at SOL's
# first confirmed OKX bar (2021-01-21T16:00Z); BTC and ETH history goes
# back further, but the synchronized three-instrument panel cannot start
# earlier. One-day purge gaps separate the windows.
TRAIN_START = datetime(2021, 1, 21, 16, 0, tzinfo=UTC)
TRAIN_END = datetime(2024, 1, 1, 16, 0, tzinfo=UTC)
VALIDATION_START = datetime(2024, 1, 2, 16, 0, tzinfo=UTC)
VALIDATION_END = datetime(2025, 1, 1, 16, 0, tzinfo=UTC)
HOLDOUT_START = datetime(2025, 1, 2, 16, 0, tzinfo=UTC)
HOLDOUT_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)

# 1H window (00:00 UTC bar opens), aligned with the daily holdout start;
# it covers about 22 monthly expiries and is used for the H0005 1H
# robustness test only.
HOURLY_START = datetime(2025, 1, 2, 0, 0, tzinfo=UTC)
HOURLY_END = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)

COST_ASSUMPTIONS: tuple[str, ...] = (
    "OKX VIP0 taker fee 0.05% per side, from the OKX public fee "
    "schedule (okx.com/fees), checked 2026-11-18; treated as an "
    "assumption, not verified for the user's account",
    "Funding rate costs ignored; perpetual funding can exceed taker "
    "fees over holding periods",
    "Slippage and market impact ignored; both would reduce any edge",
)

EXPIRY_MECHANISM_NOTE = (
    "The expiry window is only a proxy for dealer-hedging intensity, "
    "not a measurement of it. Deribit public data reports whole-market "
    "per-contract open interest and Greeks, not dealer positions, so "
    "dealer net gamma, dealer positions and hedging flow cannot be "
    "verified from public data. This study tests the expiry-window "
    "effect itself; any hedging interpretation is inference, not "
    "observation. In crypto, forced buying and selling are dominated "
    "by perpetual liquidations, open interest and funding rates, and "
    "options gamma is only an environment variable."
)


def build_okx_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=OKX_SOURCE_ID,
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


def build_deribit_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=DERIBIT_SOURCE_ID,
        provider="Deribit",
        description=(
            "Deribit public REST option instrument listings "
            "(get_instruments, listed and recently expired) and DVOL "
            "volatility index data (get_volatility_index_data) for BTC and ETH"
        ),
        license_status=LicenseStatus.APPROVED,
        permission_basis=(
            "Public market data served without authentication by Deribit "
            "public REST endpoints (/public/get_instruments, "
            "/public/get_volatility_index_data), used for research only; "
            "raw payloads are not redistributed. Deribit Terms of Service "
            "and API documentation reviewed 2026-11-18. This registry "
            "entry is an explicit research-use assertion, not a legal "
            "determination."
        ),
        terms_url="https://www.deribit.com/pages/terms",
        attribution="Data: Deribit public market data",
        nominal_delay_seconds=0,
        timestamp_basis=(
            "Instrument expiration_timestamp is the settlement moment in "
            "UTC milliseconds (08:00 UTC on the expiry date). DVOL daily "
            "points are timestamped at 00:00 UTC; a daily point's close "
            "becomes knowable at the next day's 00:00 UTC."
        ),
    )


def build_h0005_spec() -> HypothesisSpec:
    """The preregistered H0005 research plan.

    Window definition: the expiry window for monthly expiry T (last
    Friday of the month, settlement 08:00 UTC) is the set of OKX
    bar-open dates in [T-3, T] (four calendar days; crypto trades every
    calendar day). The window indicator is known at the bar's open
    because the expiry calendar is public in advance (point-in-time
    correct). The T-day daily return spans the settlement moment: the
    T-1 bar's interval contains the settlement and the T bar is the
    first full post-settlement bar.
    """
    return HypothesisSpec(
        hypothesis_id="H0005",
        title="Expiry windows strengthen BTC→ETH transmission",
        research_question=(
            "Does lag-1 BTC perpetual return predict the next-day ETH "
            "perpetual return more strongly inside Deribit monthly option "
            "expiry windows (bar-open dates T-3..T, T the last Friday of "
            "the month, settlement 08:00 UTC) than outside them?"
        ),
        mechanism=(
            "Expiry-related position management (dealer hedging, "
            "position closing and repositioning around settlement) may "
            "concentrate information flow in the days before expiry, so "
            "price discovery in the largest market (BTC perpetuals) "
            "transmits to ETH with a stronger lag inside the window. "
            + EXPIRY_MECHANISM_NOTE
        ),
        alternative_hypothesis=(
            "The lag-1 BTC coefficient for next-day ETH returns is larger "
            "inside expiry windows than outside them (positive "
            "interaction), and lag-1 BTC explains a positive "
            "out-of-sample component of next-day ETH returns within "
            "expiry-window rows."
        ),
        null_hypothesis=(
            "Lag-1 BTC returns have no expiry-window-dependent "
            "incremental predictive value: the interaction coefficient is "
            "zero and lag-1 BTC does not predict ETH returns within "
            "expiry-window rows, beyond ETH's own history and the "
            "common-factor control, after costs and dependence controls."
        ),
        universe=tuple(item[0] for item in INSTRUMENTS),
        source_versions=(
            f"{OKX_SOURCE_ID}@v{OKX_SOURCE_VERSION}",
            f"{DERIBIT_SOURCE_ID}@v{DERIBIT_SOURCE_VERSION}",
        ),
        observation_frequency="daily",
        horizon_seconds=86_400,
        target_definition=(
            "Next-day close-to-close ETH-USDT perpetual log return (daily "
            "primary); next-hour ETH-USDT perpetual log return (1H secondary)"
        ),
        feature_set=(
            "btc-log-return-lag-1@v1",
            "eth-log-return-lag-1@v1",
            "sol-log-return-lag-0@v1",
            "expiry-window-indicator@v1",
            "btc-expiry-window-interaction@v1",
        ),
        model_definition=(
            "Interaction OLS with HAC standard errors (daily BTC→ETH, 1H BTC→ETH)",
            "Expiry-window-subsample partial lead-lag with HAC standard errors",
            "Window-aware purged walk-forward out-of-sample evaluation "
            "(expiry-window holdout rows only)",
            "Wide-window (T-5..T+1), quarterly-vs-monthly and subperiod "
            "splits as descriptive checks (not in the test family)",
            "DVOL around expiry as a descriptive check (not in the test family)",
        ),
        fixed_parameters=(
            "lag=1",
            "daily_max_hac_lag=5",
            "hourly_max_hac_lag=12",
            "window_days_before=3",
            "window_days_after=0",
            "wide_window_days_before=5",
            "wide_window_days_after=1",
            "bootstrap_block_length=10",
            "bootstrap_resamples=2000",
            "bootstrap_seed=42",
            "walk_forward_initial_train=365",
            "walk_forward_test_size=90",
            "walk_forward_embargo_days=1",
            "hourly_window_start=2025-01-02T00:00:00Z",
            "hourly_window_end=2026-11-18T00:00:00Z",
        ),
        benchmark=(
            "Own-history baseline: next-bar ETH return predicted from its "
            "own lagged return, the SOL common factor and lag-1 BTC, with "
            "the interaction excluded"
        ),
        cost_model=(
            "Round-trip taker cost 0.10% per position flip (OKX VIP0 taker "
            "0.05% per side, assumed); sign rule on out-of-sample augmented "
            "forecasts on expiry-window holdout rows only, 1x, flat on "
            "non-window rows; entry from flat and final exit cost one "
            "taker side each; funding, slippage and market impact ignored"
        ),
        cost_assumptions=COST_ASSUMPTIONS,
        train_window=SampleWindow(start=TRAIN_START, end=TRAIN_END),
        validation_window=SampleWindow(start=VALIDATION_START, end=VALIDATION_END),
        holdout_window=SampleWindow(start=HOLDOUT_START, end=HOLDOUT_END),
        purge_gap_seconds=86_400,
        minimum_train_observations=200,
        minimum_validation_observations=60,
        minimum_holdout_observations=60,
        primary_metric=(
            "Partial R-squared of the BTC×expiry-window interaction in "
            "the daily BTC→ETH interaction regression"
        ),
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=0.005,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Expiry-window BTC→ETH daily transmission (3 tests: A daily "
            "interaction, B daily expiry-window subsample, C 1H interaction)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=3,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count"
        ),
        acceptance_criteria=(
            "Holm-adjusted A interaction p-value below 0.05",
            "A interaction partial R-squared at least 0.005",
            "Holdout out-of-sample incremental R-squared above 0 on "
            "expiry-window holdout rows",
            "Net daily edge after the 0.10% round-trip taker cost is positive",
        ),
        rejection_criteria=(
            "Holm-adjusted A interaction p-value at or above 0.05",
            "A interaction partial R-squared below 0.005",
            "Holdout out-of-sample incremental R-squared at or below 0 on "
            "expiry-window holdout rows",
            "Net daily edge after costs is zero or negative",
        ),
        known_confounders=(
            "The expiry window is only a proxy for dealer-hedging "
            "intensity; Deribit public data gives whole-market OI and "
            "Greeks, not dealer positions, so dealer gamma exposure "
            "cannot be verified",
            "In crypto, forced buying and selling are dominated by "
            "perpetual liquidations, open interest and funding rates; "
            "options gamma is only an environment variable, so a window "
            "effect must not be default-attributed to gamma",
            "Monthly expiries are scarce (about 12 per year); the daily "
            "window sample is roughly 280 rows of about 2,100, so power "
            "against small effects is limited",
            "The SOL common-factor proxy is itself driven by BTC and may "
            "absorb part of the transmission effect; no-factor controls "
            "are reported as upper bounds",
            "Common crypto market shocks move BTC, ETH and SOL together; "
            "the regressions control for the contemporaneous third-asset "
            "return only",
            "The T-day daily return spans the Friday 08:00 UTC "
            "settlement (bars open 16:00 UTC); the T-1 bar's interval "
            "contains the settlement moment and the T bar is the first "
            "full post-settlement bar",
        ),
        exclusions=(
            "Unconfirmed (forming) OKX bars are excluded; only confirm=1 "
            "candles enter the panel",
            "The first daily return row has no lag-1 predictor and is "
            "excluded; the same warm-up rule applies to the 1H panel",
            "Bars after the preregistered window end 2026-11-18T16:00Z "
            "are out of sample",
        ),
        random_seed=42,
    )


def build_h0006_spec() -> HypothesisSpec:
    """The preregistered H0006 research plan.

    The mean comparison uses all daily rows in the sample period (train
    + validation + holdout); the windows define the sample period, not a
    train/test split for this hypothesis, because the test is a single
    predeclared level comparison with no model selection and no
    out-of-sample evaluation. Inference: OLS of |log return| on the
    window indicator with Newey-West HAC standard errors (max lag 10;
    absolute returns are more persistent than returns). The
    block-bootstrap interval (block 10, 2000 resamples, seed 42) for the
    window-minus-non-window mean difference is computed on the weighted
    series whose mean is the difference of means. Effect size: the ratio
    of window to non-window mean |log return|; the 1.15 threshold means
    window days are at least 15% more volatile in absolute-return terms,
    a material level difference rather than a statistically detectable
    but economically negligible one.
    """
    return HypothesisSpec(
        hypothesis_id="H0006",
        title="Expiry windows raise realized volatility",
        research_question=(
            "Is mean daily absolute log return (|log return|, a robust "
            "realized-volatility proxy) higher on Deribit monthly option "
            "expiry-window days (bar-open dates T-3..T) than on "
            "non-window days, for BTC (primary) and ETH (secondary) "
            "perpetuals?"
        ),
        mechanism=(
            "Option expiry concentrates position management (dealer "
            "hedging, position closing and repositioning around "
            "settlement) in the days before expiry, which may raise "
            "realized volatility on window days. " + EXPIRY_MECHANISM_NOTE
        ),
        alternative_hypothesis=(
            "Mean daily absolute log return is higher on expiry-window "
            "days than on non-window days (positive window coefficient), "
            "with a window/non-window mean ratio of at least 1.15 for BTC."
        ),
        null_hypothesis=(
            "Mean daily absolute log return is the same on expiry-window "
            "and non-window days; the window coefficient is zero."
        ),
        universe=("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        source_versions=(
            f"{OKX_SOURCE_ID}@v{OKX_SOURCE_VERSION}",
            f"{DERIBIT_SOURCE_ID}@v{DERIBIT_SOURCE_VERSION}",
        ),
        observation_frequency="daily",
        horizon_seconds=86_400,
        target_definition=(
            "Daily absolute close-to-close log return (|log return|) of "
            "the BTC-USDT perpetual (primary) and ETH-USDT perpetual "
            "(secondary)"
        ),
        feature_set=(
            "btc-abs-log-return@v1",
            "eth-abs-log-return@v1",
            "expiry-window-indicator@v1",
        ),
        model_definition=(
            "Mean comparison by OLS of |log return| on the window "
            "indicator with HAC standard errors (max lag 10)",
            "Block-bootstrap confidence interval for the window minus "
            "non-window mean difference (block 10, 2000 resamples, seed 42)",
            "The mean comparison uses all daily rows in the sample "
            "period (train + validation + holdout); the windows define "
            "the sample period, not a train/test split for this hypothesis",
            "Wide-window (T-5..T+1), quarterly-vs-monthly and subperiod "
            "splits as descriptive checks (not in the test family)",
        ),
        fixed_parameters=(
            "window_days_before=3",
            "window_days_after=0",
            "wide_window_days_before=5",
            "wide_window_days_after=1",
            "effect_ratio_threshold=1.15",
            "abs_return_hac_max_lag=10",
            "bootstrap_block_length=10",
            "bootstrap_resamples=2000",
            "bootstrap_seed=42",
        ),
        benchmark=(
            "Non-window mean daily absolute log return: the window "
            "effect is the window mean minus the non-window mean"
        ),
        cost_model=(
            "No cost gate: H0006 is a volatility-level comparison, not a "
            "forecast; there is no trading rule to cost"
        ),
        cost_assumptions=COST_ASSUMPTIONS,
        train_window=SampleWindow(start=TRAIN_START, end=TRAIN_END),
        validation_window=SampleWindow(start=VALIDATION_START, end=VALIDATION_END),
        holdout_window=SampleWindow(start=HOLDOUT_START, end=HOLDOUT_END),
        purge_gap_seconds=86_400,
        minimum_train_observations=200,
        minimum_validation_observations=60,
        minimum_holdout_observations=60,
        primary_metric=(
            "Ratio of mean daily |log return| on expiry-window days to "
            "mean daily |log return| on non-window days (BTC primary)"
        ),
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=1.15,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Expiry-window realized-volatility level (2 tests: BTC mean "
            "|log return| comparison, ETH mean |log return| comparison)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=2,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count"
        ),
        acceptance_criteria=(
            "Holm-adjusted BTC mean-comparison p-value below 0.05",
            "BTC window/non-window mean |log return| ratio at least 1.15",
        ),
        rejection_criteria=(
            "Holm-adjusted BTC mean-comparison p-value at or above 0.05",
            "BTC window/non-window mean |log return| ratio below 1.15",
        ),
        known_confounders=(
            "Absolute returns are strongly autocorrelated (volatility "
            "clustering); HAC standard errors (max lag 10) and a "
            "block-bootstrap interval account for dependence",
            "The expiry window is only a proxy for dealer-hedging "
            "intensity; no dealer position or gamma exposure is measured",
            "Monthly expiries are scarce (about 12 per year); the daily "
            "window sample is roughly 280 rows of about 2,100",
            "The T-day daily return spans the Friday 08:00 UTC "
            "settlement (bars open 16:00 UTC); the T-1 bar's interval "
            "contains the settlement moment and the T bar is the first "
            "full post-settlement bar",
        ),
        exclusions=(
            "Unconfirmed (forming) OKX bars are excluded; only confirm=1 "
            "candles enter the panel",
            "The first daily return row has no lag-1 predictor and is "
            "excluded",
            "Bars after the preregistered window end 2026-11-18T16:00Z "
            "are out of sample",
        ),
        random_seed=42,
    )


def register_sources() -> list[Path]:
    registry = SourceRegistry(ROOT / "sources")
    return [
        registry.register(build_okx_source_definition(), version=OKX_SOURCE_VERSION),
        registry.register(
            build_deribit_source_definition(), version=DERIBIT_SOURCE_VERSION
        ),
    ]


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
    for instrument_id, name, index_name, currency in DVOL_INDICES:
        paths.append(
            catalog.register_instrument(
                Instrument(
                    instrument_id=instrument_id,
                    asset_class=AssetClass.VOLATILITY,
                    instrument_type=InstrumentType.INDEX,
                    name=name,
                    quote_currency="percent",
                    calendar_id="crypto-24-7",
                    metadata={
                        "deribit_index_name": index_name,
                        "deribit_currency": currency,
                    },
                ),
                version=1,
            )
        )
    return paths


def register_hypothesis(spec: HypothesisSpec) -> tuple[str, str]:
    """Register one hypothesis once; return (spec fingerprint, registration hash)."""
    registry = HypothesisRegistry(ROOT / "hypotheses")
    hypothesis_id = spec.hypothesis_id
    fingerprint = hashlib.sha256(
        canonical_json(spec.model_dump(mode="json"))
    ).hexdigest()
    try:
        existing = registry.get(hypothesis_id, version=1)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if existing.spec_fingerprint != fingerprint:
            raise ValueError(
                f"{hypothesis_id} v1 is already registered with a different "
                "spec; amendments need a new version, not a re-run"
            )
        print(f"{hypothesis_id} v1 already registered; leaving it untouched.")
        return existing.spec_fingerprint, existing.registration_hash
    registration = registry.register(spec)
    return registration.spec_fingerprint, registration.registration_hash


def main() -> None:
    for path in register_sources():
        print(f"registered source: {path}")
    for path in register_catalog():
        print(f"registered catalog entry: {path}")
    for spec in (build_h0005_spec(), build_h0006_spec()):
        fingerprint, registration_hash = register_hypothesis(spec)
        print(f"{spec.hypothesis_id} v1 spec fingerprint: {fingerprint}")
        print(f"{spec.hypothesis_id} v1 registration hash: {registration_hash}")
    registry = HypothesisRegistry(ROOT / "hypotheses")
    for hypothesis_id in ("H0005", "H0006"):
        state = registry.get_state(hypothesis_id, 1)
        print(f"{hypothesis_id} v1 state: {state.value}")
    events = registry.read_events()
    print(f"hypothesis events recorded: {len(events)}")


if __name__ == "__main__":
    main()
