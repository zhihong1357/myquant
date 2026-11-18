"""Preregister the FOMC event study (H0007, H0008).

Run once, before any event-study result is computed:

    .venv/bin/python research/fomc-event-study-005/preregister.py

Registers the FRED, Yahoo Finance and Federal Reserve public sources,
the five study instruments plus the US equity calendar, and two
hypotheses:

- H0007 (event response): scheduled FOMC statement days produce
  significant cumulative abnormal returns in the [0,+1] event window
  across the rates, credit, equity and volatility legs (VIX CAR < 0
  primary: the post-announcement volatility drop).
- H0008 (cross-event transmission): across FOMC events, the SPX
  event-window CAR is negatively related to the DGS10 event-window CAR
  (a rates-up surprise coincides with equities down).

Events are scheduled FOMC meetings only: the statement day (t=0) is the
last day of the meeting; the statement is released at about 14:00 ET
and the daily close (16:00 ET) already contains the reaction.
Unscheduled meetings, cancelled meetings, conference calls and notation
votes are excluded. The calendar is extracted from the Fed's own pages
(fomchistorical{YYYY}.htm for 2003-2020, fomccalendars.htm for 2021
onwards) and cross-checked (see the fetch script and the study report).

Mechanism red lines: the DGS10 event-window move is only a PROXY for
the policy surprise, not the surprise itself — there is no free federal
funds futures surprise series (a Kuttner-style surprise needs futures
data), so H0008 tests the cross-sectional association between the rates
leg and the equity leg, not a causal "surprise effect". An event study
measures announcement responses, not tradable alpha: a significant CAR
is not a trading strategy, and no cost gate applies.

Data reuse (verified in study 003, before this preregistration): FRED
fredgraph CSV without a key (VIXCLS, VXTYN, DGS10, BAA10Y); Yahoo
^GSPC for the S&P 500. TYVIX (VXTYN) ends 2020-05-15, so the main
sample is 2003-2020 and excludes the post-2020 hiking cycle; the
descriptive extended sample (non-TYVIX legs to 2026) is predeclared
below. No new FRED series is introduced.

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

FRED_SOURCE_ID = "fred"
FRED_SOURCE_VERSION = 1
YAHOO_SOURCE_ID = "yahoo-finance"
YAHOO_SOURCE_VERSION = 1
FEDERALRESERVE_SOURCE_ID = "federalreserve"
FEDERALRESERVE_SOURCE_VERSION = 1

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

# Sample windows (21:00 UTC daily closes), mirroring study 003. The
# binding coverage limit is TYVIX (VXTYN): 2003-01-02 to 2020-05-15.
# For this event study the windows define the sample period, not a
# train/test split: every included event enters the tests, and H0008's
# chronological split-half is the out-of-sample-style validation. The
# two-day purge gaps match the two-trading-day event window.
TRAIN_START = datetime(2003, 1, 2, 21, 0, tzinfo=UTC)
TRAIN_END = datetime(2012, 1, 1, 21, 0, tzinfo=UTC)
VALIDATION_START = datetime(2012, 1, 3, 21, 0, tzinfo=UTC)
VALIDATION_END = datetime(2017, 1, 1, 21, 0, tzinfo=UTC)
HOLDOUT_START = datetime(2017, 1, 3, 21, 0, tzinfo=UTC)
HOLDOUT_END = datetime(2020, 5, 15, 21, 0, tzinfo=UTC)

COST_ASSUMPTIONS: tuple[str, ...] = (
    "No cost gate applies: an event study measures announcement "
    "responses, not a forecast, and there is no trading rule to cost. "
    "A significant CAR is evidence about how markets respond to "
    "scheduled announcements, not a tradable edge.",
)

POLICY_SURPRISE_NOTE = (
    "The DGS10 event-window move is only a proxy for the policy "
    "surprise, not the surprise itself: there is no free federal funds "
    "futures surprise series (a Kuttner-style surprise needs futures "
    "data). This study tests the cross-sectional association between "
    "the rates leg and the other legs, not a causal surprise effect."
)


def build_fred_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=FRED_SOURCE_ID,
        provider="Federal Reserve Bank of St. Louis (FRED)",
        description=(
            "FRED free fredgraph CSV downloads for VIXCLS (VIX), VXTYN "
            "(TYVIX history), DGS10 (10-year Treasury yield) and BAA10Y "
            "(Baa minus 10-year Treasury spread)"
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


def build_federalreserve_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=FEDERALRESERVE_SOURCE_ID,
        provider="Board of Governors of the Federal Reserve System",
        description=(
            "Federal Reserve public FOMC meeting calendar pages: "
            "fomchistorical{YYYY}.htm (2003-2020) and fomccalendars.htm "
            "(2021 onwards), plus the 2003 schedule press release and the "
            "2020 minutes publication page used as cross-checks"
        ),
        license_status=LicenseStatus.APPROVED,
        permission_basis=(
            "Public meeting schedule data published by the Board of "
            "Governors, free to use; the pages require no API key. Used "
            "for research only; raw payloads are not redistributed. This "
            "registry entry is an explicit research-use assertion, not a "
            "legal determination."
        ),
        terms_url="https://www.federalreserve.gov/",
        attribution="Source: Board of Governors of the Federal Reserve System",
        nominal_delay_seconds=0,
        timestamp_basis=(
            "Scheduled meeting dates are public in advance (the annual "
            "schedule is announced months ahead); the statement day is "
            "the last day of the meeting and the statement is released "
            "at about 14:00 ET on that day."
        ),
    )


def build_h0007_spec() -> HypothesisSpec:
    """The preregistered H0007 research plan.

    Events are scheduled FOMC meetings; t=0 is the statement day (the
    last meeting day). The event window is [0,+1] trading days and the
    estimation window is [-60,-11] (50 trading days); the expected
    return is the constant mean over the estimation window, estimated
    separately for each event and each leg. The estimator is the repo's
    event_study() with its overlap-clustering inference; scheduled
    meetings are at least four weeks apart, so [0,+1] windows never
    overlap and each event is its own cluster. One-sided p-values are
    derived from the estimator's z-statistic as Phi(z) for the
    "less than" direction. Effect size is the standardized mean CAR
    (mean CAR divided by the cross-event standard deviation of CARs);
    the 0.3 threshold is a small-to-medium standardized effect — with
    about 135 events the design is well powered for it (the standard
    error of the standardized mean is about 1/sqrt(135) = 0.086, so
    0.3 is about 3.5 standard errors).
    """
    return HypothesisSpec(
        hypothesis_id="H0007",
        title="FOMC statements move rates, credit, equity and volatility",
        research_question=(
            "Do scheduled FOMC statement days produce significant "
            "cumulative abnormal returns in the [0,+1] event window "
            "across the rates (DGS10), credit (BAA10Y spread), equity "
            "(SPX) and volatility (VIX, TYVIX) legs?"
        ),
        mechanism=(
            "Scheduled announcements resolve policy uncertainty: implied "
            "volatility should fall after the statement as uncertainty "
            "is removed (the post-announcement volatility drop), while "
            "the rates leg reprices on the policy news and the repricing "
            "transmits to equities and credit. " + POLICY_SURPRISE_NOTE
        ),
        alternative_hypothesis=(
            "Mean CAR[0,+1] is negative for VIX (primary) and TYVIX and "
            "non-zero for SPX, DGS10 and BAA10Y, with the VIX "
            "standardized mean CAR at or below -0.3."
        ),
        null_hypothesis=(
            "Mean CAR[0,+1] around scheduled FOMC statement days is "
            "zero on every leg; announcement days are indistinguishable "
            "from ordinary days after the constant-mean benchmark."
        ),
        universe=tuple(item[0] for item in INSTRUMENTS),
        source_versions=(
            f"{FRED_SOURCE_ID}@v{FRED_SOURCE_VERSION}",
            f"{YAHOO_SOURCE_ID}@v{YAHOO_SOURCE_VERSION}",
            f"{FEDERALRESERVE_SOURCE_ID}@v{FEDERALRESERVE_SOURCE_VERSION}",
        ),
        observation_frequency="daily",
        horizon_seconds=172_800,
        target_definition=(
            "Per-leg cumulative abnormal return over the [0,+1] event "
            "window around scheduled FOMC statement days (VIX and TYVIX "
            "log changes, SPX log return, DGS10 and BAA10Y level changes "
            "in basis points)"
        ),
        feature_set=(
            "baa10y-car-0-1@v1",
            "dgs10-car-0-1@v1",
            "spx-car-0-1@v1",
            "tyvix-car-0-1@v1",
            "vix-car-0-1@v1",
        ),
        model_definition=(
            "Constant-mean event study via the repo event_study() "
            "estimator (estimation window [-60,-11], event window "
            "[0,+1], overlap-cluster inference)",
            "One-sided p-values for the volatility legs derived from the "
            "estimator z-statistic as Phi(z) for the 'less than' "
            "direction; two-sided p-values for SPX, DGS10 and BAA10Y",
            "Holm family of 5 tests (a VIX, b SPX, c DGS10, d BAA10Y, "
            "e TYVIX); effect size is the standardized mean CAR",
            "Descriptive [-1,+1] window, descriptive extended sample "
            "(non-TYVIX legs to 2026-11-16) and descriptive policy-cycle "
            "splits (hiking / cutting / unchanged, no p-values)",
        ),
        fixed_parameters=(
            "cycle_cutting_1=2007-09-18:2008-12-16",
            "cycle_cutting_2=2019-07-31:2020-03-15",
            "cycle_hiking_1=2004-06-30:2006-06-29",
            "cycle_hiking_2=2015-12-17:2018-12-19",
            "estimation_end_steps=11",
            "estimation_start_steps=60",
            "event_post_steps=1",
            "event_pre_steps=0",
            "event_source=federalreserve fomchistorical pages 2003-2020 "
            "and fomccalendars.htm 2021 onwards",
            "extended_sample_end=2026-11-16",
            "sample_end=2020-05-15",
            "sample_start=2003-01-02",
            "standardized_effect_threshold=0.3",
            "statement_time=14:00 ET on the last meeting day",
            "transform_baa10y=level-change-bp",
            "transform_dgs10=level-change-bp",
            "transform_spx=log-change",
            "transform_tyvix=log-change",
            "transform_vix=log-change",
            "wide_event_post_steps=1",
            "wide_event_pre_steps=1",
        ),
        benchmark=(
            "Constant-mean expected return: the mean observed change "
            "over each event's own estimation window [-60,-11], "
            "estimated separately per event and per leg"
        ),
        cost_model=(
            "No cost gate: an event study measures announcement "
            "responses, not a forecast; there is no trading rule to cost"
        ),
        cost_assumptions=COST_ASSUMPTIONS,
        train_window=SampleWindow(start=TRAIN_START, end=TRAIN_END),
        validation_window=SampleWindow(start=VALIDATION_START, end=VALIDATION_END),
        holdout_window=SampleWindow(start=HOLDOUT_START, end=HOLDOUT_END),
        purge_gap_seconds=172_800,
        minimum_train_observations=1000,
        minimum_validation_observations=500,
        minimum_holdout_observations=300,
        primary_metric=(
            "Standardized mean VIX CAR[0,+1] (mean CAR divided by the "
            "cross-event standard deviation of CARs)"
        ),
        expected_direction=ExpectedDirection.NEGATIVE,
        minimum_effect_size=0.3,
        target_error_rate=0.05,
        multiple_testing_family=(
            "FOMC event-window CARs (5 tests: a VIX CAR[0,+1] < 0, "
            "b SPX CAR[0,+1] != 0, c DGS10 CAR[0,+1] != 0, "
            "d BAA10Y CAR[0,+1] != 0, e TYVIX CAR[0,+1] < 0)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=5,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count. Events whose t=0 is absent from "
            "the panel or whose estimation or event window does not fit "
            "inside the panel are excluded and counted."
        ),
        acceptance_criteria=(
            "Holm-adjusted VIX CAR p-value below 0.05 (one-sided, "
            "negative direction)",
            "Standardized mean VIX CAR at or below -0.3",
        ),
        rejection_criteria=(
            "Holm-adjusted VIX CAR p-value at or above 0.05 (one-sided, "
            "negative direction)",
            "Standardized mean VIX CAR above -0.3",
        ),
        known_confounders=(
            "The DGS10 event-window move is only a proxy for the policy "
            "surprise, not the surprise itself: no free federal funds "
            "futures surprise series exists.",
            "An event study measures announcement responses, not "
            "tradable alpha; a significant CAR is not a trading strategy.",
            "Estimation windows may contain a prior meeting's event "
            "window (2 of 50 days when meetings are five weeks apart); "
            "the contamination is small and the simple [-60,-11] rule "
            "is kept as preregistered.",
            "FRED publication lag is not modelled; available_at equals "
            "the close.",
            "TYVIX was discontinued in May 2020; the main sample ends "
            "2020-05-15 and excludes the post-2020 hiking cycle.",
            "Other macro releases occasionally coincide with FOMC "
            "statement days; they are not excluded — the event window "
            "is defined by the FOMC calendar only.",
            "The calendar is extracted from the Fed's own pages, not "
            "rule-constructed; the residual risk is a parsing error, "
            "guarded by the per-year count checks and the cross-checks.",
        ),
        exclusions=(
            "Unscheduled meetings, cancelled meetings, conference calls "
            "and notation votes are excluded (listed in the report).",
            "FOMC minutes releases are not events in this study.",
            "Events with an incomplete estimation window ([-60,-11]) or "
            "event window ([0,+1]) are excluded and counted.",
            "Bars outside the sample (2003-01-02 to 2020-05-15) are out "
            "of sample for the main tests; the extended sample "
            "(non-TYVIX legs to 2026-11-16) is descriptive only.",
            "The [-1,+1] window and the policy-cycle splits are "
            "descriptive only and are not in the test family.",
        ),
        random_seed=42,
    )


def build_h0008_spec() -> HypothesisSpec:
    """The preregistered H0008 research plan.

    Cross-event OLS of one leg's [0,+1] CAR on the DGS10 [0,+1] CAR,
    with heteroskedasticity-consistent (HC0) standard errors via
    newey_west_hac with max_lag=0. The CARs are the same ones H0007
    computes (same events, same windows, same benchmark). The
    one-sided primary p-value is derived from the HAC t-statistic as
    Phi(t) for the "less than" direction. The R-squared threshold of
    0.05 means the rates leg explains at least 5% of the cross-event
    variance in SPX CARs — a material single-factor association for a
    cross-event regression, where R-squared values are typically low.
    The split-half rule: events ordered chronologically, the first half
    is the first floor(n/2) events and the second half is the rest;
    replication requires the second-half slope to be negative with a
    one-sided HC0 p-value below 0.05, and the first-half slope to be
    negative with a one-sided HC0 p-value below 0.05.
    """
    return HypothesisSpec(
        hypothesis_id="H0008",
        title="Across FOMC events, rates and equity CARs move oppositely",
        research_question=(
            "Across scheduled FOMC events, is the SPX event-window CAR "
            "negatively related to the DGS10 event-window CAR (a "
            "rates-up surprise coinciding with equities down), and do "
            "the VIX and BAA10Y CARs co-move with the DGS10 CAR?"
        ),
        mechanism=(
            "A hawkish policy surprise raises the discount rate and "
            "tightens financial conditions, so equities fall when rates "
            "rise on announcement days; the cross-event slope captures "
            "that transmission. " + POLICY_SURPRISE_NOTE
        ),
        alternative_hypothesis=(
            "The SPX CAR on DGS10 CAR cross-event slope is negative, "
            "with R-squared at least 0.05 and a split-half replication "
            "in the second half of events."
        ),
        null_hypothesis=(
            "The SPX CAR is unrelated to the DGS10 CAR across FOMC "
            "events: the cross-event slope is zero."
        ),
        universe=(
            "index:sp500",
            "rates:us-10y-yield",
            "index:vix",
            "credit:baa-10y-spread",
        ),
        source_versions=(
            f"{FRED_SOURCE_ID}@v{FRED_SOURCE_VERSION}",
            f"{YAHOO_SOURCE_ID}@v{YAHOO_SOURCE_VERSION}",
            f"{FEDERALRESERVE_SOURCE_ID}@v{FEDERALRESERVE_SOURCE_VERSION}",
        ),
        observation_frequency="daily",
        horizon_seconds=172_800,
        target_definition=(
            "Cross-event regression targets: SPX CAR[0,+1] (primary), "
            "VIX CAR[0,+1] and BAA10Y CAR[0,+1], each regressed on the "
            "DGS10 CAR[0,+1] across scheduled FOMC events"
        ),
        feature_set=(
            "baa10y-car-0-1@v1",
            "dgs10-car-0-1@v1",
            "spx-car-0-1@v1",
            "vix-car-0-1@v1",
        ),
        model_definition=(
            "Cross-event OLS of the target leg's CAR[0,+1] on the "
            "DGS10 CAR[0,+1], heteroskedasticity-consistent (HC0) "
            "standard errors via newey_west_hac with max_lag=0",
            "One-sided primary p-value derived from the HAC t-statistic "
            "as Phi(t) for the 'less than' direction; two-sided "
            "p-values for the VIX and BAA10Y slopes",
            "Holm family of 3 tests (a SPX on DGS10, b VIX on DGS10, "
            "c BAA10Y on DGS10)",
            "Split-half replication: events ordered chronologically, "
            "first half = first floor(n/2) events, second half = the "
            "rest; replication requires both halves to show a negative "
            "slope with a one-sided HC0 p-value below 0.05",
            "Descriptive extended-sample regressions (non-TYVIX legs to "
            "2026-11-16), not in the test family",
        ),
        fixed_parameters=(
            "cross_section_max_lag=0",
            "estimation_end_steps=11",
            "estimation_start_steps=60",
            "event_post_steps=1",
            "event_pre_steps=0",
            "event_source=federalreserve fomchistorical pages 2003-2020 "
            "and fomccalendars.htm 2021 onwards",
            "extended_sample_end=2026-11-16",
            "r_squared_threshold=0.05",
            "sample_end=2020-05-15",
            "sample_start=2003-01-02",
            "split_half_rule=chronological median split (first half = "
            "first floor(n/2) events)",
            "statement_time=14:00 ET on the last meeting day",
            "transform_baa10y=level-change-bp",
            "transform_dgs10=level-change-bp",
            "transform_spx=log-change",
            "transform_vix=log-change",
        ),
        benchmark=(
            "Zero-slope null: the target leg's CAR is unrelated to the "
            "DGS10 CAR across events (intercept-only model)"
        ),
        cost_model=(
            "No cost gate: an event study measures announcement "
            "responses, not a forecast; there is no trading rule to cost"
        ),
        cost_assumptions=COST_ASSUMPTIONS,
        train_window=SampleWindow(start=TRAIN_START, end=TRAIN_END),
        validation_window=SampleWindow(start=VALIDATION_START, end=VALIDATION_END),
        holdout_window=SampleWindow(start=HOLDOUT_START, end=HOLDOUT_END),
        purge_gap_seconds=172_800,
        minimum_train_observations=1000,
        minimum_validation_observations=500,
        minimum_holdout_observations=300,
        primary_metric=(
            "R-squared of the SPX CAR on DGS10 CAR cross-event regression"
        ),
        expected_direction=ExpectedDirection.NEGATIVE,
        minimum_effect_size=0.05,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Cross-event CAR transmission (3 tests: a SPX CAR on DGS10 "
            "CAR slope < 0, b VIX CAR on DGS10 CAR slope != 0, "
            "c BAA10Y CAR on DGS10 CAR slope != 0)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=3,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count. Events whose t=0 is absent from "
            "the panel or whose estimation or event window does not fit "
            "inside the panel are excluded and counted (same event set "
            "as H0007)."
        ),
        acceptance_criteria=(
            "Holm-adjusted SPX-on-DGS10 slope p-value below 0.05 "
            "(one-sided, negative direction)",
            "SPX-on-DGS10 regression R-squared at least 0.05",
            "Split-half replication: the first-half and second-half "
            "slopes are both negative with one-sided HC0 p-values below "
            "0.05",
        ),
        rejection_criteria=(
            "Holm-adjusted SPX-on-DGS10 slope p-value at or above 0.05 "
            "(one-sided, negative direction)",
            "SPX-on-DGS10 regression R-squared below 0.05",
            "Split-half replication fails (either half's slope is "
            "non-negative or its one-sided HC0 p-value is at or above "
            "0.05)",
        ),
        known_confounders=(
            "The DGS10 CAR is only a proxy for the policy surprise, not "
            "the surprise itself: no free federal funds futures surprise "
            "series exists.",
            "The two CARs are measured over the same event window: the "
            "regression is contemporaneous, not a lead-lag claim, and "
            "common shocks on FOMC days move both legs.",
            "Cross-event association is not causal identification.",
            "The cross-section is small (about 135 events); each "
            "split-half has about 67 events.",
            "TYVIX was discontinued in May 2020; the main sample ends "
            "2020-05-15 and excludes the post-2020 hiking cycle.",
            "FRED publication lag is not modelled; available_at equals "
            "the close.",
        ),
        exclusions=(
            "Unscheduled meetings, cancelled meetings, conference calls "
            "and notation votes are excluded (same event set as H0007).",
            "FOMC minutes releases are not events in this study.",
            "Events with an incomplete estimation window ([-60,-11]) or "
            "event window ([0,+1]) are excluded and counted.",
            "Bars outside the sample (2003-01-02 to 2020-05-15) are out "
            "of sample for the main tests; the extended-sample "
            "regressions (to 2026-11-16) are descriptive only.",
        ),
        random_seed=42,
    )


def register_sources() -> list[Path]:
    registry = SourceRegistry(ROOT / "sources")
    return [
        registry.register(build_fred_source_definition(), version=FRED_SOURCE_VERSION),
        registry.register(
            build_yahoo_source_definition(), version=YAHOO_SOURCE_VERSION
        ),
        registry.register(
            build_federalreserve_source_definition(),
            version=FEDERALRESERVE_SOURCE_VERSION,
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


def main() -> None:
    for path in register_sources():
        print(f"registered source: {path}")
    for path in register_catalog():
        print(f"registered catalog entry: {path}")
    for spec in (build_h0007_spec(), build_h0008_spec()):
        fingerprint, registration_hash = register_hypothesis(spec)
        print(f"{spec.hypothesis_id} v1 spec fingerprint: {fingerprint}")
        print(f"{spec.hypothesis_id} v1 registration hash: {registration_hash}")
    registry = HypothesisRegistry(ROOT / "hypotheses")
    for hypothesis_id in ("H0007", "H0008"):
        state = registry.get_state(hypothesis_id, 1)
        print(f"{hypothesis_id} v1 state: {state.value}")
    events = registry.read_events()
    print(f"hypothesis events recorded: {len(events)}")


if __name__ == "__main__":
    main()
