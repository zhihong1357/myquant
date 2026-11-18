"""Preregister the low-volatility transmission study (H0002, H0003).

Run once, before any regime-conditional result is computed:

    .venv/bin/python research/lowvol-002/preregister.py

Registers the OKX and Hyperliquid public sources, the three perpetual
instruments plus the 24/7 crypto calendar, and two hypotheses:

- H0002 (main): regime-conditional transmission on fresh dimensions — a
  new pair (daily BTC→SOL) and a new frequency (1H BTC→ETH). Study 001's
  post-hoc low-volatility observation (BTC→ETH daily, full-sample median
  split) is the hypothesis source, not evidence, and is never re-tested
  on the same data.
- H0003 (forward): the original BTC→ETH daily pair, tested only on bars
  observed after the preregistration date. Preregistered now; the trial
  runs when 60 low-volatility forward rows exist (expected around
  2027-03). No H0003 trial runs in this study.

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
HL_SOURCE_ID = "hyperliquid-public"
HL_SOURCE_VERSION = 1

INSTRUMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("crypto:btc-usdt-perp", "BTC-USDT perpetual swap", "BTC-USDT-SWAP", "BTC"),
    ("crypto:eth-usdt-perp", "ETH-USDT perpetual swap", "ETH-USDT-SWAP", "ETH"),
    ("crypto:sol-usdt-perp", "SOL-USDT perpetual swap", "SOL-USDT-SWAP", "SOL"),
)

# Study 001's daily windows (16:00 UTC bar opens), reused for H0002.
TRAIN_START = datetime(2023, 1, 1, 16, 0, tzinfo=UTC)
TRAIN_END = datetime(2025, 1, 1, 16, 0, tzinfo=UTC)
VALIDATION_START = datetime(2025, 1, 2, 16, 0, tzinfo=UTC)
VALIDATION_END = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)
HOLDOUT_START = datetime(2026, 1, 2, 16, 0, tzinfo=UTC)
HOLDOUT_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)

COST_ASSUMPTIONS: tuple[str, ...] = (
    "OKX VIP0 taker fee 0.05% per side, from the OKX public fee "
    "schedule (okx.com/fees), checked 2026-11-18; treated as an "
    "assumption, not verified for the user's account",
    "Funding rate costs ignored; perpetual funding can exceed taker "
    "fees over holding periods",
    "Slippage and market impact ignored; both would reduce any edge",
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


def build_hyperliquid_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=HL_SOURCE_ID,
        provider="Hyperliquid",
        description=(
            "Hyperliquid public REST candleSnapshot for BTC/ETH/SOL "
            "perpetuals (daily bars)"
        ),
        license_status=LicenseStatus.APPROVED,
        permission_basis=(
            "Public market data served without authentication by "
            "Hyperliquid's public /info endpoint (candleSnapshot), used for "
            "research only; raw payloads are not redistributed. Hyperliquid "
            "Terms of Service reviewed 2026-11-18. This registry entry is an "
            "explicit research-use assertion, not a legal determination."
        ),
        terms_url="https://app.hyperliquid.xyz/terms",
        attribution="Data: Hyperliquid public market data",
        nominal_delay_seconds=0,
        timestamp_basis=(
            "Exchange event time: candle open time in UTC milliseconds; a "
            "candle's values become knowable at its close (open + bar "
            "duration). Daily bars open at 00:00 UTC."
        ),
    )


def build_h0002_spec() -> HypothesisSpec:
    """The preregistered H0002 research plan.

    Regime rule (PIT-correct; study 001's descriptive split used the
    full-sample median, which would leak future information into a test):
    RV30[t] is the sample standard deviation of the target's trailing 30
    returns ending at t; lowvol[t] is RV30[t] below the median of the
    trailing 252 RV30 values strictly before t (daily), or below the
    expanding median of all prior RV30 values with at least 30 of them
    (1H, where RV30 uses 720 hourly returns). Rows without a label are
    excluded: the first 281 daily return rows and the first 749 hourly
    return rows, given study 001's panel sizes.
    """
    return HypothesisSpec(
        hypothesis_id="H0002",
        title="Low-volatility regimes strengthen BTC transmission",
        research_question=(
            "Does lag-1 BTC perpetual return predict the next-bar target "
            "perpetual return more strongly in low-volatility regimes than "
            "in high-volatility regimes, on a fresh pair (daily BTC→SOL) and "
            "a fresh frequency (1H BTC→ETH)?"
        ),
        mechanism=(
            "In low-volatility regimes, orderly price discovery lets "
            "information repriced in the largest, most liquid market (BTC "
            "perpetuals) transmit to smaller markets with a lag, while in "
            "high-volatility regimes simultaneous repricing and "
            "liquidation-driven flows erase the lag. Study 001 found no "
            "unconditional lag-1 transmission; its post-hoc descriptive "
            "split suggested the effect may be concentrated in "
            "low-volatility regimes."
        ),
        alternative_hypothesis=(
            "The lag-1 BTC coefficient is larger in low-volatility regimes "
            "than in high-volatility regimes (positive interaction), and "
            "lag-1 BTC explains a positive out-of-sample component of "
            "next-bar target returns within low-volatility rows."
        ),
        null_hypothesis=(
            "Lag-1 BTC returns have no regime-dependent incremental "
            "predictive value: the interaction coefficient is zero and "
            "lag-1 BTC does not predict target returns within "
            "low-volatility rows, beyond the target's own history and the "
            "common-factor control, after costs and dependence controls."
        ),
        universe=tuple(item[0] for item in INSTRUMENTS),
        source_versions=(
            f"{OKX_SOURCE_ID}@v{OKX_SOURCE_VERSION}",
            f"{HL_SOURCE_ID}@v{HL_SOURCE_VERSION}",
        ),
        observation_frequency="daily",
        horizon_seconds=86_400,
        target_definition=(
            "Next-day close-to-close SOL-USDT perpetual log return (daily "
            "primary); next-hour ETH-USDT perpetual log return (1H secondary)"
        ),
        feature_set=(
            "btc-log-return-lag-1@v1",
            "sol-log-return-lag-1@v1",
            "eth-log-return-lag-0@v1",
            "eth-log-return-lag-1@v1",
            "sol-log-return-lag-0@v1",
            "lowvol-regime-indicator@v1",
            "btc-lowvol-interaction@v1",
        ),
        model_definition=(
            "Interaction OLS with HAC standard errors (daily BTC→SOL, 1H BTC→ETH)",
            "Low-volatility-subsample partial lead-lag with HAC standard errors",
            "Regime-aware purged walk-forward out-of-sample evaluation "
            "(low-volatility holdout rows only)",
            "Hyperliquid daily BTC→ETH low-volatility subsample as a "
            "descriptive cross-venue check (not in the test family)",
        ),
        fixed_parameters=(
            "lag=1",
            "daily_max_hac_lag=5",
            "hourly_max_hac_lag=12",
            "rv_window_days=30",
            "rv_window_hours=720",
            "daily_median_window=252",
            "hourly_median_min_prior=30",
            "bootstrap_block_length=10",
            "bootstrap_resamples=2000",
            "bootstrap_seed=42",
            "walk_forward_initial_train=365",
            "walk_forward_test_size=90",
            "walk_forward_embargo_days=1",
            "hourly_window_start=2026-08-20T00:00:00Z",
            "hourly_window_end=2026-11-18T00:00:00Z",
            "hourly_train_end=2026-10-19T00:00:00Z",
            "hourly_holdout_start=2026-10-19T00:00:00Z",
        ),
        benchmark=(
            "Own-history baseline: next-bar target return predicted from "
            "its own lagged return, the common factor and lag-1 BTC, with "
            "the interaction excluded"
        ),
        cost_model=(
            "Round-trip taker cost 0.10% per position flip (OKX VIP0 taker "
            "0.05% per side, assumed); sign rule on out-of-sample augmented "
            "forecasts on low-volatility holdout rows only, 1x, flat on "
            "high-volatility rows; entry from flat and final exit cost one "
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
            "Partial R-squared of the BTC×lowvol interaction in the daily "
            "BTC→SOL interaction regression"
        ),
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=0.005,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Regime-conditional BTC transmission, daily BTC→SOL and 1H "
            "BTC→ETH (4 tests: A1 daily interaction, A2 daily low-volatility "
            "subsample, B1 1H interaction, B2 1H low-volatility subsample)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=4,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count; rows without a regime label "
            "(warm-up) are excluded and counted"
        ),
        acceptance_criteria=(
            "Holm-adjusted A1 interaction p-value below 0.05",
            "A1 interaction partial R-squared at least 0.005",
            "Holdout out-of-sample incremental R-squared above 0 on "
            "low-volatility holdout rows",
            "Net daily edge after the 0.10% round-trip taker cost is positive",
        ),
        rejection_criteria=(
            "Holm-adjusted A1 interaction p-value at or above 0.05",
            "A1 interaction partial R-squared below 0.005",
            "Holdout out-of-sample incremental R-squared at or below 0 on "
            "low-volatility holdout rows",
            "Net daily edge after costs is zero or negative",
        ),
        known_confounders=(
            "The 30-day volatility window and median-split regime rule "
            "mirror study 001's post-hoc descriptive split; the fresh "
            "dimensions are the pair (BTC→SOL) and the frequency (1H), "
            "not the regime definition",
            "The third-asset common-factor proxy is itself driven by BTC "
            "and may absorb part of the transmission effect; no-factor "
            "controls are reported as upper bounds",
            "Common crypto market shocks move BTC, ETH and SOL together; "
            "the regressions control for the contemporaneous third-asset "
            "return only",
            "Hyperliquid same-period prices are highly correlated with "
            "OKX prices, so the cross-venue check cannot serve as "
            "independent evidence",
            "Daily bars are anchored at 16:00 UTC (OKX) and 00:00 UTC "
            "(Hyperliquid); the lag-1 effect is defined on each venue's "
            "own grid",
        ),
        exclusions=(
            "Unconfirmed (forming) OKX bars are excluded; only confirm=1 "
            "candles enter the panel",
            "Hyperliquid candles that are unclosed or carry zero trades "
            "are excluded",
            "Rows without a regime label are excluded and counted (the "
            "first 281 daily return rows and the first 749 hourly return "
            "rows, given study 001's panel sizes)",
            "Bars after the preregistered window end 2026-11-18T16:00Z "
            "are out of sample",
        ),
        random_seed=42,
    )


def build_h0003_spec() -> HypothesisSpec:
    """The preregistered H0003 forward-test plan.

    The original BTC→ETH daily pair, tested ONLY on rows whose decision
    time is on or after the preregistration date (2026-11-18T16:00Z).
    Earlier bars are used only to compute trailing regime labels. The
    trial runs when 60 low-volatility forward rows exist (about 120 days
    of new bars, expected around 2027-03); the forward sample is too
    small for a walk-forward evaluation, so the confirmatory family is
    the interaction test plus the low-volatility subsample test only,
    with no out-of-sample or cost-gate criterion in this version.
    """
    return HypothesisSpec(
        hypothesis_id="H0003",
        title="Low-volatility BTC→ETH transmission (forward test)",
        research_question=(
            "On daily bars observed after the preregistration date, does "
            "lag-1 BTC perpetual return predict next-day ETH perpetual "
            "return more strongly in low-volatility regimes than in "
            "high-volatility regimes?"
        ),
        mechanism=(
            "Same mechanism as H0002, applied to the original BTC→ETH pair "
            "on strictly forward data: in low-volatility regimes, orderly "
            "price discovery lets information repriced in BTC transmit to "
            "ETH with a lag."
        ),
        alternative_hypothesis=(
            "On forward daily bars, the lag-1 BTC coefficient is larger in "
            "low-volatility regimes than in high-volatility regimes "
            "(positive interaction), and lag-1 BTC explains a positive "
            "component of next-day ETH returns within low-volatility rows."
        ),
        null_hypothesis=(
            "On forward daily bars, lag-1 BTC returns have no "
            "regime-dependent incremental predictive value for next-day "
            "ETH returns beyond ETH's own history and the common-factor "
            "control."
        ),
        universe=tuple(item[0] for item in INSTRUMENTS),
        source_versions=(f"{OKX_SOURCE_ID}@v{OKX_SOURCE_VERSION}",),
        observation_frequency="daily",
        horizon_seconds=86_400,
        target_definition=(
            "Next-day close-to-close ETH-USDT perpetual log return on bars "
            "after 2026-11-18T16:00Z"
        ),
        feature_set=(
            "btc-log-return-lag-1@v1",
            "eth-log-return-lag-1@v1",
            "sol-log-return-lag-0@v1",
            "lowvol-regime-indicator@v1",
            "btc-lowvol-interaction@v1",
        ),
        model_definition=(
            "Interaction OLS with HAC standard errors (forward daily BTC→ETH)",
            "Low-volatility-subsample partial lead-lag with HAC standard errors",
        ),
        fixed_parameters=(
            "lag=1",
            "daily_max_hac_lag=5",
            "rv_window_days=30",
            "daily_median_window=252",
            "bootstrap_block_length=10",
            "bootstrap_resamples=2000",
            "bootstrap_seed=42",
            "forward_window_start=2026-11-18T16:00:00Z",
            "minimum_lowvol_rows=60",
        ),
        benchmark=(
            "Own-history baseline: next-day ETH return predicted from its "
            "own lagged return, the SOL common factor and lag-1 BTC, with "
            "the interaction excluded"
        ),
        cost_model=(
            "No cost gate in this version: the forward sample is too small "
            "for a walk-forward evaluation, so costs are not assessed until "
            "the sample supports it"
        ),
        cost_assumptions=COST_ASSUMPTIONS,
        train_window=SampleWindow(start=TRAIN_START, end=TRAIN_END),
        validation_window=SampleWindow(start=VALIDATION_START, end=VALIDATION_END),
        holdout_window=SampleWindow(
            start=datetime(2026, 11, 19, 16, 0, tzinfo=UTC),
            end=datetime(2027, 3, 31, 16, 0, tzinfo=UTC),
        ),
        purge_gap_seconds=86_400,
        minimum_train_observations=200,
        minimum_validation_observations=60,
        minimum_holdout_observations=60,
        primary_metric=(
            "Partial R-squared of the BTC×lowvol interaction in the "
            "forward BTC→ETH interaction regression"
        ),
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=0.005,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Forward low-volatility BTC→ETH daily transmission (2 tests: "
            "interaction, low-volatility subsample)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=2,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count; rows without a regime label "
            "(warm-up) are excluded and counted"
        ),
        acceptance_criteria=(
            "Holm-adjusted interaction p-value below 0.05",
            "Interaction partial R-squared at least 0.005",
        ),
        rejection_criteria=(
            "Holm-adjusted interaction p-value at or above 0.05",
            "Interaction partial R-squared below 0.005",
        ),
        known_confounders=(
            "The hypothesis was generated from this pair's historical "
            "data; the forward sample is fresh but the pair is not",
            "The 30-day volatility window and median-split regime rule "
            "mirror study 001's post-hoc descriptive split",
            "The SOL common-factor proxy is itself driven by BTC and may "
            "absorb part of the transmission effect",
            "The forward sample is small (minimum 60 low-volatility "
            "rows); the test has limited power against small effects",
        ),
        exclusions=(
            "Unconfirmed (forming) OKX bars are excluded; only confirm=1 "
            "candles enter the panel",
            "Rows without a regime label are excluded and counted",
            "Rows with decision time before 2026-11-18T16:00Z are not in "
            "the test sample; earlier bars are used only to compute "
            "trailing regime labels",
        ),
        random_seed=42,
    )


def register_sources() -> list[Path]:
    registry = SourceRegistry(ROOT / "sources")
    return [
        registry.register(build_okx_source_definition(), version=OKX_SOURCE_VERSION),
        registry.register(
            build_hyperliquid_source_definition(), version=HL_SOURCE_VERSION
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
    for instrument_id, name, okx_inst_id, hl_coin in INSTRUMENTS:
        paths.append(
            catalog.register_instrument(
                Instrument(
                    instrument_id=instrument_id,
                    asset_class=AssetClass.CRYPTO,
                    instrument_type=InstrumentType.PERPETUAL,
                    name=name,
                    quote_currency="USDT",
                    calendar_id="crypto-24-7",
                    metadata={
                        "okx_inst_id": okx_inst_id,
                        "hyperliquid_coin": hl_coin,
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
    for spec in (build_h0002_spec(), build_h0003_spec()):
        fingerprint, registration_hash = register_hypothesis(spec)
        print(f"{spec.hypothesis_id} v1 spec fingerprint: {fingerprint}")
        print(f"{spec.hypothesis_id} v1 registration hash: {registration_hash}")
    registry = HypothesisRegistry(ROOT / "hypotheses")
    for hypothesis_id in ("H0002", "H0003"):
        state = registry.get_state(hypothesis_id, 1)
        print(f"{hypothesis_id} v1 state: {state.value}")
    events = registry.read_events()
    print(f"hypothesis events recorded: {len(events)}")


if __name__ == "__main__":
    main()
