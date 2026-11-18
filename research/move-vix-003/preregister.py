"""Preregister the MOVE/VIX/VXN conditional repricing study (H0004).

Run once, before any result-level analysis:

    .venv/bin/python research/move-vix-003/preregister.py

Registers the FRED and Yahoo Finance public sources, the six study
instruments plus the US equity calendar, and one hypothesis:

- H0004 (main): lag-1 log change in rates implied volatility predicts
  next-day VIX log change beyond VIX's own history and the SPX
  common-factor control (thesis 001, H2).

v2 amendment (pre-trial, before any result-level analysis): v1's
known_confounders said the SPX factor is contemporaneous with the
target (day t+1), but the preregistered partial_lead_lag interface
requires every predictor to be known at the forecast time (day t), and
the walk-forward evaluation cannot use a t+1 control without leaking
the future into the forecasts. v2 pins the factor to the predictor day
(SPX[t]) and predeclares a descriptive factor-timing sensitivity. No
change to the test family, acceptance criteria, sample windows, or
hypotheses.

Rate-volatility source (verified 2026-11-18, coverage only — no
lead-lag, regression or p-value was computed before preregistration):

- The ICE BofA MOVE index has no free source: Yahoo ``^MOVE`` is a
  Northern Trust ETF, not the index; Stooq serves a JS anti-scrape page;
  FRED has no MOVE series.
- The CBOE TYVIX history CSV returns 403, Yahoo ``^TYVIX`` is delisted
  and FRED has no ``TYVIX`` series — but FRED series ``VXTYN`` is the
  TYVIX history (2003-01-02 to 2020-05-15, 4,532 rows, zero missing
  values). TYVIX is used as the rates implied-volatility source.
- TYVIX measures expected 30-day volatility of 10-year Treasury
  futures *prices* (percent); MOVE measures expected volatility of
  Treasury *yields* (basis points). Both are rates implied volatility;
  the substitution is approximate and is stated as a limitation. TYVIX
  was discontinued in May 2020, so the sample ends 2020-05-15.

Re-running is safe: identical registrations are left untouched and the
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

FRED_SOURCE_ID = "fred"
FRED_SOURCE_VERSION = 1
YAHOO_SOURCE_ID = "yahoo-finance"
YAHOO_SOURCE_VERSION = 1

# instrument_id, name, asset class, type, quote, metadata
INSTRUMENTS: tuple[tuple[str, str, AssetClass, InstrumentType, str, dict[str, str]], ...] = (
    (
        "index:vix",
        "CBOE Volatility Index (VIX)",
        AssetClass.VOLATILITY,
        InstrumentType.INDEX,
        "points",
        {"fred_series": "VIXCLS"},
    ),
    (
        "index:vxn",
        "CBOE Nasdaq-100 Volatility Index (VXN)",
        AssetClass.VOLATILITY,
        InstrumentType.INDEX,
        "points",
        {"fred_series": "VXNCLS"},
    ),
    (
        "index:tyvix",
        "CBOE/CBOT 10-Year Treasury Note Volatility Index (TYVIX)",
        AssetClass.VOLATILITY,
        InstrumentType.INDEX,
        "points",
        {"fred_series": "VXTYN"},
    ),
    (
        "rates:us-10y-yield",
        "Market Yield on US Treasury Securities at 10 Years (DGS10)",
        AssetClass.RATES,
        InstrumentType.RATE,
        "percent",
        {"fred_series": "DGS10"},
    ),
    (
        "index:sp500",
        "S&P 500 Index",
        AssetClass.INDEX,
        InstrumentType.INDEX,
        "points",
        {"yahoo_symbol": "^GSPC"},
    ),
    (
        "credit:baa-10y-spread",
        "Moody's Seasoned Baa Corporate Bond Yield Relative to "
        "10-Year Treasury (BAA10Y)",
        AssetClass.CREDIT,
        InstrumentType.RATE,
        "percent",
        {"fred_series": "BAA10Y"},
    ),
)

# Sample windows (21:00 UTC daily closes). The binding coverage limit is
# TYVIX (VXTYN): 2003-01-02 to 2020-05-15.
TRAIN_START = datetime(2003, 1, 2, 21, 0, tzinfo=UTC)
TRAIN_END = datetime(2012, 1, 1, 21, 0, tzinfo=UTC)
VALIDATION_START = datetime(2012, 1, 2, 21, 0, tzinfo=UTC)
VALIDATION_END = datetime(2017, 1, 1, 21, 0, tzinfo=UTC)
HOLDOUT_START = datetime(2017, 1, 2, 21, 0, tzinfo=UTC)
HOLDOUT_END = datetime(2020, 5, 15, 21, 0, tzinfo=UTC)

COST_ASSUMPTIONS: tuple[str, ...] = (
    "Volatility indices are not tradable; VIX exposure requires VIX "
    "futures, and futures roll costs cannot be measured from free data: "
    "Yahoo VX=F returns no data (verified 2026-11-18) and no other "
    "reliable free VIX futures series was found",
    "The cost gate is therefore informational, not a verdict criterion; "
    "the holdout out-of-sample incremental R-squared carries the "
    "economic weight",
    "The reported gross sign-rule edge applies no costs at all and is "
    "an upper bound on any tradable edge",
)


def build_fred_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=FRED_SOURCE_ID,
        provider="Federal Reserve Bank of St. Louis (FRED)",
        description=(
            "FRED free fredgraph CSV downloads for VIXCLS (VIX), VXNCLS "
            "(VXN), VXTYN (TYVIX history), DGS10 (10-year Treasury yield) "
            "and BAA10Y (Baa minus 10-year Treasury spread)"
        ),
        license_status=LicenseStatus.APPROVED,
        permission_basis=(
            "Public economic data published by the Federal Reserve Bank "
            "of St. Louis, free to use with attribution; the fredgraph.csv "
            "endpoint requires no API key. Used for research only; raw "
            "payloads are not redistributed. FRED terms of use reviewed "
            "2026-11-18. This registry entry is an explicit research-use "
            "assertion, not a legal determination."
        ),
        terms_url="https://fred.stlouisfed.org/docs/api/terms_of_use.html",
        attribution="Source: Federal Reserve Bank of St. Louis",
        nominal_delay_seconds=0,
        timestamp_basis=(
            "Daily closing values dated observation_date; the event time "
            "is the US equity close (16:00 ET) recorded as 21:00 UTC "
            "(fixed; DST is not modelled) and available_at equals the "
            "event time. FRED's actual publication lag is not modelled."
        ),
    )


def build_yahoo_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=YAHOO_SOURCE_ID,
        provider="Yahoo Finance",
        description=(
            "Yahoo Finance public chart endpoint (query2.finance.yahoo.com) "
            "daily bars for the S&P 500 index (^GSPC)"
        ),
        license_status=LicenseStatus.APPROVED,
        permission_basis=(
            "Public market data served without authentication by Yahoo's "
            "chart endpoint, used for research only; raw payloads are not "
            "redistributed. Yahoo Terms of Service reviewed 2026-11-18. "
            "This registry entry is an explicit research-use assertion, "
            "not a legal determination."
        ),
        terms_url="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
        attribution="Data: Yahoo Finance",
        nominal_delay_seconds=0,
        timestamp_basis=(
            "Daily bars timestamped at the market open (09:30 ET); the "
            "trading date is derived in America/New_York and the close is "
            "recorded at 21:00 UTC, matching the FRED convention."
        ),
    )


def build_h0004_spec() -> HypothesisSpec:
    """The preregistered H0004 research plan.

    Variables are log changes: volatility levels are mean-reverting and
    thesis H2 concerns standardized moves. The common-factor control is
    the contemporaneous SPX daily log return. The test family has 3
    tests: (a) daily TYVIX→VIX (primary), (b) daily TYVIX→VXN, (c)
    weekly TYVIX→VIX (Friday-close to Friday-close log changes; the
    weekly test is an in-sample partial lead-lag over the full weekly
    sample, with no separate walk-forward). The reverse placebo
    (VIX→TYVIX), the rolling-percentile descriptive, the sub-period
    stability split and the z-scored robustness are descriptive only
    and are not in the test family.
    """
    return HypothesisSpec(
        hypothesis_id="H0004",
        title="Rates volatility leads equity volatility",
        research_question=(
            "Does the lag-1 log change in rates implied volatility "
            "(TYVIX, via FRED VXTYN) predict the next-day VIX log change "
            "beyond VIX's own history and the contemporaneous SPX "
            "common-factor control?"
        ),
        mechanism=(
            "Rates volatility repricing (rate-expectation and "
            "term-premium shocks) transmits to equity volatility with a "
            "lag: rate moves reprice equity discount rates and risk "
            "appetite, and the rates market — larger and more "
            "policy-sensitive — reprices first. Thesis 001 H2: a large "
            "standardized move in one volatility market may precede a "
            "move in another."
        ),
        alternative_hypothesis=(
            "The lag-1 TYVIX log change has a positive coefficient in the "
            "daily TYVIX→VIX partial lead-lag regression (rates "
            "volatility up predicts equity volatility up the next day), "
            "with partial R-squared at least 0.005 and a positive "
            "holdout out-of-sample incremental R-squared."
        ),
        null_hypothesis=(
            "Lag-1 TYVIX log changes have no incremental predictive value "
            "for next-day VIX log changes beyond VIX's own history and "
            "the SPX common-factor control, after dependence controls."
        ),
        universe=tuple(item[0] for item in INSTRUMENTS),
        source_versions=(
            f"{FRED_SOURCE_ID}@v{FRED_SOURCE_VERSION}",
            f"{YAHOO_SOURCE_ID}@v{YAHOO_SOURCE_VERSION}",
        ),
        observation_frequency="daily",
        horizon_seconds=86_400,
        target_definition=(
            "Next-day close-to-close VIX log change (daily primary and "
            "weekly robustness); next-day VXN log change (daily secondary)"
        ),
        feature_set=(
            "tyvix-log-change-lag-1@v1",
            "vix-log-change-lag-1@v1",
            "vxn-log-change-lag-1@v1",
            "spx-log-return-lag-0@v1",
            "tyvix-log-change-lag-1-weekly@v1",
            "vix-log-change-lag-1-weekly@v1",
            "spx-log-return-lag-0-weekly@v1",
        ),
        model_definition=(
            "Partial lead-lag OLS with HAC standard errors "
            "(daily TYVIX→VIX, daily TYVIX→VXN, weekly TYVIX→VIX)",
            "Purged walk-forward out-of-sample evaluation of the daily "
            "primary model (baseline: own history plus SPX factor; "
            "augmented: plus lag-1 TYVIX)",
            "Naive lead-lag scan (lags 0-5, raw Pearson correlations) as "
            "a descriptive upper bound (not in the test family)",
        ),
        fixed_parameters=(
            "lag=1",
            "daily_max_hac_lag=5",
            "weekly_max_hac_lag=4",
            "bootstrap_block_length=10",
            "bootstrap_resamples=2000",
            "bootstrap_seed=42",
            "walk_forward_initial_train=1000",
            "walk_forward_test_size=126",
            "walk_forward_embargo_days=1",
            "weekly_anchor=friday-close",
            "rate_vol_source=fred:VXTYN (TYVIX)",
            "sample_start=2003-01-02",
            "sample_end=2020-05-15",
            "subperiods=2003-2007,2008-2012,2013-2017,2018-2020",
            "percentile_window_days=252",
            "zscore_window_days=252",
        ),
        benchmark=(
            "Own-history baseline: next-day VIX log change predicted "
            "from its own lagged log change and the contemporaneous SPX "
            "log return, without lag-1 TYVIX"
        ),
        cost_model=(
            "Informational only: volatility indices are not tradable; "
            "VIX exposure requires VIX futures and roll costs cannot be "
            "measured from free data (no reliable free VIX futures "
            "series — Yahoo VX=F returns no data). The trial reports the "
            "gross sign-rule edge on holdout out-of-sample forecasts "
            "(no costs applied) as an informational assessment, not a "
            "verdict criterion; the out-of-sample incremental R-squared "
            "criterion carries the economic weight."
        ),
        cost_assumptions=COST_ASSUMPTIONS,
        train_window=SampleWindow(start=TRAIN_START, end=TRAIN_END),
        validation_window=SampleWindow(start=VALIDATION_START, end=VALIDATION_END),
        holdout_window=SampleWindow(start=HOLDOUT_START, end=HOLDOUT_END),
        purge_gap_seconds=86_400,
        minimum_train_observations=1000,
        minimum_validation_observations=500,
        minimum_holdout_observations=300,
        primary_metric=(
            "Partial R-squared of lag-1 TYVIX log change in the daily "
            "TYVIX→VIX partial lead-lag regression"
        ),
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=0.005,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Rates-volatility transmission to equity volatility (3 tests: "
            "a daily TYVIX→VIX, b daily TYVIX→VXN, c weekly TYVIX→VIX)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=3,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count. FRED '.' missing values and Yahoo "
            "null closes are excluded at fetch time and counted."
        ),
        acceptance_criteria=(
            "Holm-adjusted primary p-value below 0.05",
            "Primary partial R-squared at least 0.005",
            "Holdout out-of-sample incremental R-squared above 0",
        ),
        rejection_criteria=(
            "Holm-adjusted primary p-value at or above 0.05",
            "Primary partial R-squared below 0.005",
            "Holdout out-of-sample incremental R-squared at or below 0",
        ),
        known_confounders=(
            "TYVIX measures expected volatility of 10-year Treasury "
            "futures prices, not yields; MOVE measures yield volatility. "
            "Both are rates implied volatility, but the substitution is "
            "approximate.",
            "TYVIX was discontinued in May 2020; the sample ends "
            "2020-05-15 and excludes the post-2020 rate-hiking cycle.",
            "FRED publication lag is not modelled; available_at equals "
            "the close, so the lag-1 design assumes the previous day's "
            "close is usable at the next day's close.",
            "The SPX factor is contemporaneous with the target; it "
            "controls the common equity-market driver but cannot absorb "
            "rate-driven common shocks that move both vol indices.",
            "Volatility indices are mean-reverting; log changes are used, "
            "but residual autocorrelation is handled with HAC standard "
            "errors only.",
            "The weekly test resamples the daily synchronized panel; "
            "weekly rows are not independent of the daily rows.",
        ),
        exclusions=(
            "Bars outside the TYVIX coverage window (2003-01-02 to "
            "2020-05-15) are out of sample.",
            "Incomplete synchronized rows are excluded and counted.",
            "FRED '.' missing values and Yahoo null closes are excluded "
            "at fetch time and counted.",
            "The reverse placebo (VIX→TYVIX), the rolling-percentile "
            "descriptive, the sub-period stability split and the "
            "z-scored robustness are descriptive only and are not in "
            "the test family.",
        ),
        random_seed=42,
    )


H0004_AMENDMENT_REASON = (
    "Correct the SPX factor alignment: v1's known_confounders said the "
    "factor is contemporaneous with the target (day t+1), but the "
    "preregistered partial_lead_lag interface requires every predictor "
    "to be known at the forecast time (day t), and the walk-forward "
    "evaluation cannot use a t+1 control without leaking the future "
    "into the forecasts. v2 pins the factor to the predictor day "
    "(SPX[t]) and predeclares a descriptive factor-timing sensitivity. "
    "No change to the test family, acceptance criteria, sample "
    "windows, or hypotheses. Made before any result-level analysis."
)


def build_h0004_spec_v2() -> HypothesisSpec:
    """H0004 v2: v1 with the factor alignment corrected (wording only).

    The test family, acceptance criteria, sample windows and hypotheses
    are unchanged. The changes pin the SPX factor to the predictor day
    and predeclare the factor-timing sensitivity as descriptive.
    """
    spec_v1 = build_h0004_spec()
    confounders = tuple(
        (
            "The SPX factor is measured on the predictor day t (the same "
            "day as the TYVIX move), as required by the partial_lead_lag "
            "interface (every predictor must be known at the forecast "
            "time) and by the leakage-free walk-forward evaluation. It "
            "controls the day-t common equity-market shock; it cannot "
            "absorb the day-t+1 common shock that moves VIX and SPX "
            "together on the target day. The day-t+1 shock is future "
            "news at t and is orthogonal to TYVIX[t], so omitting it "
            "costs power, not unbiasedness. A descriptive sensitivity "
            "re-runs the primary test with the SPX factor measured on "
            "the target day (t+1); it is not in the test family and "
            "cannot be used for forecasting."
        )
        if item.startswith("The SPX factor is contemporaneous")
        else item
        for item in spec_v1.known_confounders
    )
    copied = spec_v1.model_copy(
        update={
            "research_question": (
                "Does the lag-1 log change in rates implied volatility "
                "(TYVIX, via FRED VXTYN) predict the next-day VIX log "
                "change beyond VIX's own history and the same-day SPX "
                "common-factor control (SPX log return on the predictor "
                "day t, known at the forecast time)?"
            ),
            "benchmark": (
                "Own-history baseline: next-day VIX log change predicted "
                "from its own lagged log change and the same-day SPX log "
                "return (day t), without lag-1 TYVIX"
            ),
            "fixed_parameters": spec_v1.fixed_parameters
            + (
                "factor_alignment=predictor-day (SPX[t])",
                "factor_timing_sensitivity=descriptive "
                "(SPX[t+1] control, not in family)",
            ),
            "known_confounders": confounders,
            "exclusions": spec_v1.exclusions
            + (
                "The factor-timing sensitivity (primary test with the "
                "SPX factor measured on the target day) is descriptive "
                "only and is not in the test family.",
            ),
        }
    )
    # Re-validate through a JSON round-trip: model_copy skips validation,
    # so the appended fixed_parameters would stay unsorted, while the
    # registry's fingerprint check re-validates (and re-sorts) on load.
    # Without this the stored fingerprint would not match the stored spec.
    return HypothesisSpec.model_validate(copied.model_dump(mode="json"))


def register_sources() -> list[Path]:
    registry = SourceRegistry(ROOT / "sources")
    return [
        registry.register(build_fred_source_definition(), version=FRED_SOURCE_VERSION),
        registry.register(
            build_yahoo_source_definition(), version=YAHOO_SOURCE_VERSION
        ),
    ]


def register_catalog() -> list[Path]:
    catalog = MarketCatalog(ROOT / "catalog")
    paths = [
        catalog.register_calendar(
            MarketCalendar(
                calendar_id="us-equity",
                timezone_name="America/New_York",
                weekdays=(0, 1, 2, 3, 4),
                regular_open=time(9, 30),
                regular_close=time(16, 0),
            ),
            version=1,
        )
    ]
    for instrument_id, name, asset_class, instrument_type, quote, metadata in INSTRUMENTS:
        paths.append(
            catalog.register_instrument(
                Instrument(
                    instrument_id=instrument_id,
                    asset_class=asset_class,
                    instrument_type=instrument_type,
                    name=name,
                    quote_currency=quote,
                    calendar_id="us-equity",
                    metadata=metadata,
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


def register_amendment(spec: HypothesisSpec, reason: str) -> tuple[str, str]:
    """Register the v2 amendment once; return (fingerprint, hash)."""
    registry = HypothesisRegistry(ROOT / "hypotheses")
    hypothesis_id = spec.hypothesis_id
    fingerprint = hashlib.sha256(
        canonical_json(spec.model_dump(mode="json"))
    ).hexdigest()
    try:
        existing = registry.get(hypothesis_id, version=2)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if existing.spec_fingerprint != fingerprint:
            raise ValueError(
                f"{hypothesis_id} v2 is already registered with a different "
                "spec; amendments need a new version, not a re-run"
            )
        print(f"{hypothesis_id} v2 already registered; leaving it untouched.")
        return existing.spec_fingerprint, existing.registration_hash
    registration = registry.register(spec, amendment_reason=reason)
    return registration.spec_fingerprint, registration.registration_hash


def main() -> None:
    for path in register_sources():
        print(f"registered source: {path}")
    for path in register_catalog():
        print(f"registered catalog entry: {path}")
    spec = build_h0004_spec()
    fingerprint, registration_hash = register_hypothesis(spec)
    print(f"{spec.hypothesis_id} v1 spec fingerprint: {fingerprint}")
    print(f"{spec.hypothesis_id} v1 registration hash: {registration_hash}")
    spec_v2 = build_h0004_spec_v2()
    fingerprint_v2, registration_hash_v2 = register_amendment(
        spec_v2, H0004_AMENDMENT_REASON
    )
    print(f"{spec_v2.hypothesis_id} v2 spec fingerprint: {fingerprint_v2}")
    print(f"{spec_v2.hypothesis_id} v2 registration hash: {registration_hash_v2}")
    registry = HypothesisRegistry(ROOT / "hypotheses")
    for version in (1, 2):
        state = registry.get_state(spec.hypothesis_id, version)
        print(f"{spec.hypothesis_id} v{version} state: {state.value}")
    events = registry.read_events()
    print(f"hypothesis events recorded: {len(events)}")


if __name__ == "__main__":
    main()
