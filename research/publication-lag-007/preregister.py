"""Preregister the publication-lag study (H0011, H0012).

Run once, before any study 007 result is computed:

    .venv/bin/python research/publication-lag-007/preregister.py

Registers the FRED, Yahoo Finance, Federal Reserve, BLS and OKX public
sources, the five study 005 instruments plus the CPI month-on-month
macro series and the BTC perpetual, and two hypotheses:

- H0011 (event-study lag sensitivity): study 005's event study re-run
  with all FRED series shifted one trading day (the value dated t is
  only available at t+1 — FRED posts the next business day), Yahoo SPX
  not shifted; does the TYVIX event response survive the lag?
- H0012 (release-day-aligned CPI transmission): does the latest
  published CPI month-on-month value predict next-day SPX returns —
  a real multi-week publication-lag test, with a naive
  reference-month-aligned version as a descriptive lookahead-bias
  control.

The FRED lag (verified before this preregistration, not assumed): at
2026-11-18T06:26Z (01:26 EST, about 9.4 hours after Tuesday's close)
the VIXCLS and DGS10 fredgraph CSVs both end at 2026-11-16 (Monday).
Tuesday's value is not posted yet, which rules out same-evening
posting, while Monday's value is already available, which rules out a
two-business-day posting delay (a two-day lag would have left Monday's
value unposted until Wednesday morning). So a FRED value dated t is
posted on the next business day, and at the close of day t the latest
available FRED value is the previous trading day's: a one-trading-day
availability lag (N=1). The fetch script re-records this check in the
manifest as confirmation.

What the lag does to an event study: a lagged [0,+1] window in
availability terms covers reference-date changes [-1,0] — the
statement-day change plus the day-before change, not the day-after
change. The estimation window shifts back by the same amount ([-60,-11]
availability = [-61,-12] reference), which moves a 50-day mean by one
day and is second-order. The verdict question is whether study 005's
TYVIX finding survives that shift — not whether study 005 was wrong:
both alignments are conditionally correct, under different
availability assumptions.

Data reuse (verified in earlier studies, before this preregistration):
FRED fredgraph CSV without a key (VIXCLS, VXTYN, DGS10, BAA10Y,
CPIAUCSL); Yahoo ^GSPC for the S&P 500; the FOMC calendar from study
005 (research/fomc-event-study-005/fomc_calendar.json, 199 scheduled
meetings, validated here); the CPI calendar from study 006
(research/macro-windows-006/cpi_calendar.json, 71 releases, validated
here); OKX public REST daily candles for BTC-USDT-SWAP. TYVIX (VXTYN)
ends 2020-05-15, so the H0011 sample is 2003-2020 and excludes the
post-2020 hiking cycle. CPIAUCSL is the seasonally adjusted CPI series
(the "S"), the right one for headline month-on-month.

Re-running is safe: identical registrations are left untouched and each
hypothesis is registered only once.
"""

from __future__ import annotations

import hashlib
import json
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
from myquant.studies.macro import load_cpi_calendar, load_fomc_statement_dates

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent

FRED_SOURCE_ID = "fred"
FRED_SOURCE_VERSION = 1
YAHOO_SOURCE_ID = "yahoo-finance"
YAHOO_SOURCE_VERSION = 1
FEDERALRESERVE_SOURCE_ID = "federalreserve"
FEDERALRESERVE_SOURCE_VERSION = 1
BLS_SOURCE_ID = "bls"
BLS_SOURCE_VERSION = 1
OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1

# instrument_id, name, asset class, type, quote, calendar, metadata
INSTRUMENTS: tuple[
    tuple[str, str, AssetClass, InstrumentType, str, str, dict[str, str]], ...
] = (
    (
        "index:vix",
        "CBOE Volatility Index (VIX)",
        AssetClass.VOLATILITY,
        InstrumentType.INDEX,
        "points",
        "us-equity",
        {"fred_series": "VIXCLS"},
    ),
    (
        "index:tyvix",
        "CBOE/CBOT 10-Year Treasury Note Volatility Index (TYVIX)",
        AssetClass.VOLATILITY,
        InstrumentType.INDEX,
        "points",
        "us-equity",
        {"fred_series": "VXTYN"},
    ),
    (
        "rates:us-10y-yield",
        "Market Yield on US Treasury Securities at 10 Years (DGS10)",
        AssetClass.RATES,
        InstrumentType.RATE,
        "percent",
        "us-equity",
        {"fred_series": "DGS10"},
    ),
    (
        "index:sp500",
        "S&P 500 Index",
        AssetClass.INDEX,
        InstrumentType.INDEX,
        "points",
        "us-equity",
        {"yahoo_symbol": "^GSPC"},
    ),
    (
        "credit:baa-10y-spread",
        "Moody's Seasoned Baa Corporate Bond Yield Relative to "
        "10-Year Treasury (BAA10Y)",
        AssetClass.CREDIT,
        InstrumentType.RATE,
        "percent",
        "us-equity",
        {"fred_series": "BAA10Y"},
    ),
    (
        "macro:cpi-mom",
        "Consumer Price Index for All Urban Consumers, All Items, "
        "month-on-month log change (CPIAUCSL, seasonally adjusted)",
        AssetClass.MACRO,
        InstrumentType.MACRO_SERIES,
        "log-points",
        "us-equity",
        {"fred_series": "CPIAUCSL"},
    ),
    (
        "crypto:btc-usdt-perp",
        "BTC-USDT perpetual swap",
        AssetClass.CRYPTO,
        InstrumentType.PERPETUAL,
        "USDT",
        "crypto-24-7",
        {"okx_inst_id": "BTC-USDT-SWAP"},
    ),
)

# H0011 sample windows (21:00 UTC daily closes), mirroring study 005.
# The binding coverage limit is TYVIX (VXTYN): 2003-01-02 to 2020-05-15.
# For this event study the windows define the sample period, not a
# train/test split: every included event enters the tests. The two-day
# purge gaps match the two-trading-day event window.
H0011_TRAIN_START = datetime(2003, 1, 2, 21, 0, tzinfo=UTC)
H0011_TRAIN_END = datetime(2012, 1, 1, 21, 0, tzinfo=UTC)
H0011_VALIDATION_START = datetime(2012, 1, 3, 21, 0, tzinfo=UTC)
H0011_VALIDATION_END = datetime(2017, 1, 1, 21, 0, tzinfo=UTC)
H0011_HOLDOUT_START = datetime(2017, 1, 3, 21, 0, tzinfo=UTC)
H0011_HOLDOUT_END = datetime(2020, 5, 15, 21, 0, tzinfo=UTC)

# H0012 sample windows (21:00 UTC daily closes). The CPI step
# predictor is undefined before the first calendar release
# (2021-01-13), so the effective sample starts 2021-01-13; the train
# window starts 2021-01-04 to keep the calendar-month boundary clean.
# The BTC robustness test uses the same calendar dates (its OKX bars
# open 16:00 UTC; the 16:00 vs 21:00 UTC mismatch is immaterial since
# no walk-forward runs on BTC).
H0012_TRAIN_START = datetime(2021, 1, 4, 21, 0, tzinfo=UTC)
H0012_TRAIN_END = datetime(2024, 1, 1, 21, 0, tzinfo=UTC)
H0012_VALIDATION_START = datetime(2024, 1, 2, 21, 0, tzinfo=UTC)
H0012_VALIDATION_END = datetime(2025, 1, 1, 21, 0, tzinfo=UTC)
H0012_HOLDOUT_START = datetime(2025, 1, 2, 21, 0, tzinfo=UTC)
H0012_HOLDOUT_END = datetime(2026, 11, 18, 21, 0, tzinfo=UTC)

EVENT_STUDY_COST_ASSUMPTIONS: tuple[str, ...] = (
    "No cost gate applies: an event study measures announcement "
    "responses, not a forecast, and there is no trading rule to cost. "
    "A significant CAR is evidence about how markets respond to "
    "scheduled announcements, not a tradable edge.",
)

CPI_COST_ASSUMPTIONS: tuple[str, ...] = (
    "The S&P 500 index is not directly tradable and no free SPX "
    "futures or ETF price series is used in this study, so the cost "
    "gate is informational, not a verdict criterion; the holdout "
    "out-of-sample incremental R-squared carries the economic weight",
    "The reported gross sign-rule edge applies no costs at all and is "
    "an upper bound on any tradable edge",
)

LAG_VERIFICATION_NOTE = (
    "FRED lag verified 2026-11-18 before preregistration: VIXCLS and "
    "DGS10 fredgraph CSVs fetched at 06:26 UTC (01:26 EST, about 9.4 "
    "hours after Tuesday 2026-11-17's close) both end at 2026-11-16 "
    "(Monday). Tuesday's value is not posted yet (rules out "
    "same-evening posting) and Monday's value is already available "
    "(rules out a two-business-day posting delay), so a FRED value "
    "dated t is posted on the next business day: a one-trading-day "
    "availability lag (N=1)."
)

CONDITIONALLY_CORRECT_NOTE = (
    "Study 005's conclusion is correct under reference-date alignment; "
    "this study asks what a reader or system depending on FRED's "
    "publication rhythm would conclude. Both are conditionally correct "
    "under different availability assumptions — a changed verdict here "
    "does not mean the original conclusion was wrong."
)

CPI_EFFECTIVE_SAMPLE_NOTE = (
    "The CPI step predictor takes only about 70 distinct values over "
    "2021-2026 (one per release); the roughly 1,460 daily regression "
    "rows are NOT the effective sample size. The release-day subsample "
    "test (b) is the cleaner read: each row is a fresh-information "
    "event."
)

CPI_NOT_A_SURPRISE_NOTE = (
    "The predictor is the published CPI month-on-month level, not a "
    "surprise: no consensus data is used (no free source), so this "
    "study does not measure CPI surprises."
)


def verify_calendars() -> dict[str, int]:
    """Assert the reused calendars' counts before any registration.

    Runs before any registration: a calendar change fails loudly here
    instead of silently registering a spec with stale counts. The
    calendars themselves are not re-extracted (study 005's FOMC
    calendar, study 006's CPI calendar).
    """
    fomc_document = json.loads(
        (
            REPO_ROOT
            / "research"
            / "fomc-event-study-005"
            / "fomc_calendar.json"
        ).read_text(encoding="utf-8")
    )
    cpi_document = json.loads(
        (
            REPO_ROOT
            / "research"
            / "macro-windows-006"
            / "cpi_calendar.json"
        ).read_text(encoding="utf-8")
    )
    fomc = load_fomc_statement_dates(fomc_document)
    cpi = load_cpi_calendar(cpi_document)
    if len(fomc) != 199:
        raise ValueError(
            f"FOMC calendar has {len(fomc)} scheduled meetings, expected 199"
        )
    if len(cpi) != 71:
        raise ValueError(f"CPI calendar has {len(cpi)} releases, expected 71")
    return {"fomc_scheduled_meetings": len(fomc), "cpi_releases": len(cpi)}


def build_fred_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=FRED_SOURCE_ID,
        provider="Federal Reserve Bank of St. Louis (FRED)",
        description=(
            "FRED free fredgraph CSV downloads for VIXCLS (VIX), VXTYN "
            "(TYVIX history), DGS10 (10-year Treasury yield), BAA10Y "
            "(Baa minus 10-year Treasury spread) and CPIAUCSL "
            "(seasonally adjusted CPI, monthly)"
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
            "(fixed; DST is not modelled). Monthly CPIAUCSL values are "
            "dated the first of the reference month. " + LAG_VERIFICATION_NOTE
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
            "recorded at 21:00 UTC, matching the FRED convention. Yahoo "
            "market data is knowable at the close and carries no "
            "publication lag in this study."
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


def build_bls_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=BLS_SOURCE_ID,
        provider="U.S. Bureau of Labor Statistics",
        description=(
            "BLS public Consumer Price Index release schedule: Schedule of "
            "Selected Releases annual pages (bls.gov/schedule/{YYYY}/), "
            "the current CPI schedule page "
            "(bls.gov/schedule/news_release/cpi.htm), the archived CPI "
            "news releases page (bls.gov/bls/news-release/cpi.htm) and "
            "the 2025 shutdown impact FAQ"
        ),
        license_status=LicenseStatus.APPROVED,
        permission_basis=(
            "Public release schedule data published by the Bureau of "
            "Labor Statistics, free to use; the pages require no API "
            "key. Used for research only; raw payloads are not "
            "redistributed. BLS returns HTTP 403 to direct programmatic "
            "requests, so the calendar was transcribed from the schedule "
            "pages via text fetch and cross-checked (see "
            "research/macro-windows-006/cpi_calendar.json). This "
            "registry entry is an explicit research-use assertion, not a "
            "legal determination."
        ),
        terms_url="https://www.bls.gov/",
        attribution="Source: U.S. Bureau of Labor Statistics",
        nominal_delay_seconds=0,
        timestamp_basis=(
            "CPI release dates are public in advance (the annual schedule "
            "is announced months ahead); every release is 08:30 Eastern "
            "Time (12:30 UTC in daylight saving time, 13:30 UTC in "
            "standard time), always before the 16:00 ET close, so a "
            "release on date D is knowable at the close of D."
        ),
    )


def build_okx_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=OKX_SOURCE_ID,
        provider="OKX",
        description=(
            "OKX public REST market candles for the USDT-margined BTC "
            "perpetual swap (BTC-USDT-SWAP), daily bars"
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
            "candle's values become knowable at its close (open + bar duration). "
            "Daily bars open at 16:00 UTC."
        ),
    )


def build_h0011_spec() -> HypothesisSpec:
    """The preregistered H0011 research plan.

    Events, estimation window [-60,-11], event window [0,+1] and the
    constant-mean benchmark all mirror study 005 (H0007). The only
    change is the availability alignment: every FRED leg's changes are
    shifted one trading day on the series' own dates (diff-then-join,
    with the shift between diff and join), so the lagged change at
    availability date t is the original change at the previous own
    date; Yahoo SPX is not shifted (market data is knowable at the
    close). The lagged panel drops its first return row (2003-01-03),
    which has no lagged change; the SPX control runs on the same
    truncated index and must reproduce study 005's SPX CAR exactly
    (+0.000669, p=0.634) as an internal correctness check.

    The lagged [0,+1] window covers reference-date changes [-1,0]:
    the statement-day change plus the day-before change. The
    estimation window shifts back by the same amount ([-60,-11]
    availability = [-61,-12] reference), which moves a 50-day mean by
    one day and is second-order. The per-day abnormal-return
    decomposition (day -1, 0, +1 contributions, unlagged) is reported
    descriptively to explain how the lag changes the conclusion.
    """
    return HypothesisSpec(
        hypothesis_id="H0011",
        title="The FOMC TYVIX event response survives a one-day FRED lag",
        research_question=(
            "Does study 005's TYVIX event response (CAR[0,+1] = -0.0381, "
            "Holm p = 5.0e-08) survive when every FRED series is shifted "
            "one trading day to match FRED's publication rhythm — that "
            "is, when the reader sees each FRED value only the next "
            "trading day?"
        ),
        mechanism=(
            "FRED posts a value dated t on the next business day "
            "(verified 2026-11-18: one-trading-day availability lag), so "
            "a reader or system depending on FRED's publication rhythm "
            "sees the statement-day change only at t+1. The lagged "
            "[0,+1] window therefore covers reference-date changes "
            "[-1,0]: the statement-day change plus the day-before "
            "change. If the TYVIX drop is concentrated on day 0, the "
            "lagged CAR stays negative; if it is concentrated on day "
            "+1, the lagged CAR collapses toward the day -1 noise. "
            + CONDITIONALLY_CORRECT_NOTE
        ),
        alternative_hypothesis=(
            "The lagged TYVIX CAR[0,+1] is negative, with a Holm-adjusted "
            "one-sided p-value below 0.05 and a standardized mean CAR "
            "at or below -0.3."
        ),
        null_hypothesis=(
            "The lagged TYVIX CAR[0,+1] is zero: under FRED's "
            "publication rhythm the statement-day response is not "
            "visible in the [0,+1] availability window."
        ),
        universe=(
            "index:vix",
            "index:tyvix",
            "rates:us-10y-yield",
            "index:sp500",
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
            "Per-leg cumulative abnormal return over the lagged [0,+1] "
            "event window around scheduled FOMC statement days (FRED "
            "legs lagged one trading day: VIX and TYVIX log changes, "
            "DGS10 and BAA10Y level changes in basis points; SPX log "
            "return unlagged as an internal correctness control)"
        ),
        feature_set=(
            "baa10y-lagged-car-0-1@v1",
            "dgs10-lagged-car-0-1@v1",
            "spx-car-0-1@v1",
            "tyvix-lagged-car-0-1@v1",
            "vix-lagged-car-0-1@v1",
        ),
        model_definition=(
            "Constant-mean event study via the repo event_study() "
            "estimator (estimation window [-60,-11], event window "
            "[0,+1], overlap-cluster inference), mirroring study 005",
            "FRED legs lagged one trading day on their own dates "
            "(diff-then-join, shift between diff and join); Yahoo SPX "
            "not shifted",
            "One-sided p-values for the lagged volatility legs derived "
            "from the estimator z-statistic as Phi(z) for the 'less "
            "than' direction; two-sided p-values for lagged DGS10, "
            "lagged BAA10Y and the SPX control",
            "Holm family of 5 tests (a lagged TYVIX, b lagged VIX, "
            "c lagged DGS10, d lagged BAA10Y, e SPX unlagged control); "
            "effect size is the standardized mean CAR",
            "Descriptive per-day abnormal-return decomposition (day -1, "
            "0, +1 contributions, unlagged) and descriptive unlagged "
            "replication on the truncated panel index (no p-values)",
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
            "lag_steps=1",
            "lag_verification=2026-11-18 VIXCLS/DGS10 fredgraph CSVs "
            "fetched 06:26 UTC end 2026-11-16 (Monday); Tuesday "
            "2026-11-17 not yet posted, Monday already available",
            "lagged_reference_window=-1:0",
            "sample_end=2020-05-15",
            "sample_start=2003-01-02",
            "spx_control_expected_car=0.000669",
            "spx_control_expected_p=0.634",
            "standardized_effect_threshold=0.3",
            "statement_time=14:00 ET on the last meeting day",
            "transform_baa10y=level-change-bp",
            "transform_dgs10=level-change-bp",
            "transform_spx=log-change",
            "transform_tyvix=log-change",
            "transform_vix=log-change",
        ),
        benchmark=(
            "Constant-mean expected return: the mean observed change "
            "over each event's own estimation window [-60,-11], "
            "estimated separately per event and per leg, on the lagged "
            "changes for the FRED legs"
        ),
        cost_model=(
            "No cost gate: an event study measures announcement "
            "responses, not a forecast; there is no trading rule to cost"
        ),
        cost_assumptions=EVENT_STUDY_COST_ASSUMPTIONS,
        train_window=SampleWindow(start=H0011_TRAIN_START, end=H0011_TRAIN_END),
        validation_window=SampleWindow(
            start=H0011_VALIDATION_START, end=H0011_VALIDATION_END
        ),
        holdout_window=SampleWindow(
            start=H0011_HOLDOUT_START, end=H0011_HOLDOUT_END
        ),
        purge_gap_seconds=172_800,
        minimum_train_observations=1000,
        minimum_validation_observations=500,
        minimum_holdout_observations=300,
        primary_metric=(
            "Standardized mean lagged TYVIX CAR[0,+1] (mean CAR divided "
            "by the cross-event standard deviation of CARs)"
        ),
        expected_direction=ExpectedDirection.NEGATIVE,
        minimum_effect_size=0.3,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Lagged FOMC event-window CARs (5 tests: a lagged TYVIX "
            "CAR[0,+1] < 0, b lagged VIX CAR[0,+1] < 0, c lagged DGS10 "
            "CAR[0,+1] != 0, d lagged BAA10Y CAR[0,+1] != 0, e SPX "
            "CAR[0,+1] != 0 unlagged control)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=5,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count. Events whose t=0 is absent from "
            "the panel or whose estimation or event window does not fit "
            "inside the panel are excluded and counted (same event set "
            "as study 005: 135 included, 3 excluded). The first panel "
            "return row (2003-01-03) has no lagged change and is dropped."
        ),
        acceptance_criteria=(
            "Holm-adjusted lagged TYVIX CAR p-value below 0.05 "
            "(one-sided, negative direction)",
            "Standardized mean lagged TYVIX CAR at or below -0.3",
        ),
        rejection_criteria=(
            "Holm-adjusted lagged TYVIX CAR p-value at or above 0.05 "
            "(one-sided, negative direction)",
            "Standardized mean lagged TYVIX CAR above -0.3",
        ),
        known_confounders=(
            "The lagged test answers a different question than study "
            "005: the lagged [0,+1] window covers reference-date "
            "changes [-1,0], so a changed verdict does not mean the "
            "original conclusion was wrong; both are conditionally "
            "correct under different availability assumptions.",
            "The FRED posting lag is verified by behaviour on "
            "2026-11-18 only; the residual risk is a historical change "
            "in FRED's posting behaviour, which cannot be verified from "
            "current data.",
            "The estimation window also shifts back one day in "
            "reference terms ([-61,-12]); the effect on a 50-day mean "
            "is second-order.",
            "A partial holiday in one FRED leg is handled per series on "
            "its own dates: a lagged change at t is the original change "
            "at the previous own date, even when that date is not in "
            "the panel index.",
            "TYVIX was discontinued in May 2020; the main sample ends "
            "2020-05-15 and excludes the post-2020 hiking cycle.",
            "Estimation windows may contain a prior meeting's event "
            "window (2 of 50 days when meetings are five weeks apart); "
            "the contamination is small and the simple [-60,-11] rule "
            "is kept as preregistered, mirroring study 005.",
            "Other macro releases occasionally coincide with FOMC "
            "statement days; they are not excluded — the event window "
            "is defined by the FOMC calendar only.",
            "The SPX control must reproduce study 005's SPX CAR "
            "(+0.000669, p=0.634) exactly; a mismatch would indicate a "
            "machinery error, not a market finding.",
        ),
        exclusions=(
            "Unscheduled meetings, cancelled meetings, conference calls "
            "and notation votes are excluded (same event set as study "
            "005).",
            "FOMC minutes releases are not events in this study.",
            "Events with an incomplete estimation window ([-60,-11]) or "
            "event window ([0,+1]) are excluded and counted.",
            "The first panel return row (2003-01-03) is dropped: it has "
            "no lagged change.",
            "Bars outside the sample (2003-01-02 to 2020-05-15) are out "
            "of sample for the main tests.",
            "The per-day abnormal-return decomposition and the unlagged "
            "replication on the truncated index are descriptive only "
            "and are not in the test family.",
        ),
        random_seed=42,
    )


def build_h0012_spec() -> HypothesisSpec:
    """The preregistered H0012 research plan.

    Predictor: the FRED CPIAUCSL month-on-month log change, aligned by
    release date as a step function — each trading day's value is the
    most recent published CPI MoM as of that day (release dates from
    study 006's calendar, 71 releases). A release on date D is knowable
    at the close of D (08:30 ET release, 16:00 ET close), so release-day
    rows carry the fresh print. The step is evaluated at each bar's
    close date: for SPX the close date is the trading date; for OKX
    daily bars (open 16:00 UTC) the close date is the open date plus
    one day.

    HAC lags are fixed here, not tuned afterwards: the daily tests use
    max lag 21 because the step predictor's run length is about 21
    trading days (one release per month), so the regression residuals
    inherit roughly monthly autocorrelation; the release-day subsample
    uses max lag 5 because its rows are about 21 trading days apart
    and only short-range dependence remains. The expected direction is
    negative (a higher CPI MoM tightens policy expectations and should
    weigh on next-day equities), but the tests are two-sided and the
    sign is not a verdict criterion — the verdict rests on the
    Holm-adjusted p-value, the partial R-squared and the out-of-sample
    incremental R-squared, mirroring studies 001 and 003.
    """
    return HypothesisSpec(
        hypothesis_id="H0012",
        title="The latest published CPI MoM predicts next-day returns",
        research_question=(
            "Does the latest published CPI month-on-month value (FRED "
            "CPIAUCSL, aligned by release date as a step function) "
            "predict next-day S&P 500 returns, and does the same "
            "predictor work on release days only and for next-day BTC "
            "returns?"
        ),
        mechanism=(
            "The latest published CPI print is public information; if "
            "markets under-react to the level of the latest print "
            "(rather than only to its surprise component), the print "
            "should carry incremental predictive value for next-day "
            "returns. The expected direction is negative: a higher CPI "
            "MoM tightens policy expectations and should weigh on "
            "next-day equities. " + CPI_NOT_A_SURPRISE_NOTE
        ),
        alternative_hypothesis=(
            "The CPI step predictor has incremental predictive value "
            "for next-day SPX returns beyond SPX's own lagged return, "
            "with a Holm-adjusted p-value below 0.05, a partial "
            "R-squared of at least 0.005 and a positive holdout "
            "out-of-sample incremental R-squared."
        ),
        null_hypothesis=(
            "The latest published CPI MoM has no incremental predictive "
            "value for next-day returns: the step coefficient is zero "
            "and the predictor does not improve out-of-sample forecasts."
        ),
        universe=(
            "macro:cpi-mom",
            "index:sp500",
            "crypto:btc-usdt-perp",
        ),
        source_versions=(
            f"{FRED_SOURCE_ID}@v{FRED_SOURCE_VERSION}",
            f"{YAHOO_SOURCE_ID}@v{YAHOO_SOURCE_VERSION}",
            f"{BLS_SOURCE_ID}@v{BLS_SOURCE_VERSION}",
            f"{OKX_SOURCE_ID}@v{OKX_SOURCE_VERSION}",
        ),
        observation_frequency="daily",
        horizon_seconds=86_400,
        target_definition=(
            "Next-day close-to-close S&P 500 log return (daily primary "
            "and release-day subsample); next-day BTC-USDT perpetual "
            "log return (robustness)"
        ),
        feature_set=(
            "cpi-step-mom@v1",
            "spx-log-return-lag-1@v1",
            "btc-log-return-lag-1@v1",
            "cpi-release-day@v1",
            "cpi-naive-mom@v1",
        ),
        model_definition=(
            "Partial lead-lag OLS with HAC standard errors (daily SPX, "
            "release-day SPX subsample, daily BTC)",
            "Purged walk-forward out-of-sample evaluation (initial "
            "train 365 days, test 90 days, 1-day embargo), mirroring "
            "study 006",
            "Cost gate informational only: the gross sign-rule edge on "
            "holdout out-of-sample forecasts (no costs applied), with a "
            "block-bootstrap confidence interval; not a verdict "
            "criterion",
            "Descriptive naive alignment: the same three regressions "
            "with the CPI MoM aligned by reference month (the month's "
            "value treated as known during the month, 2-6 weeks of "
            "lookahead), compared against the PIT step to quantify the "
            "lookahead bias; not in the test family",
        ),
        fixed_parameters=(
            "lag=1",
            "daily_max_hac_lag=21",
            "subsample_max_hac_lag=5",
            "btc_max_hac_lag=21",
            "bootstrap_block_length=10",
            "bootstrap_resamples=2000",
            "bootstrap_seed=42",
            "walk_forward_initial_train=365",
            "walk_forward_test_size=90",
            "walk_forward_embargo_days=1",
            "cpi_series=CPIAUCSL",
            "cpi_calendar=research/macro-windows-006/cpi_calendar.json "
            "(71 releases, 2021-01-13 to 2026-12-10)",
            "cpi_fetch_start=2020-11-01",
            "sample_start=2021-01-04",
            "sample_end=2026-11-18",
        ),
        benchmark=(
            "Own-history baseline: next-day SPX return predicted from "
            "its own lagged return only (BTC: its own lagged return)"
        ),
        cost_model=(
            "Informational only: the S&P 500 index is not directly "
            "tradable and no free SPX futures or ETF price series is "
            "used in this study. The trial reports the gross sign-rule "
            "edge on holdout out-of-sample forecasts (no costs applied) "
            "as an informational assessment, not a verdict criterion; "
            "the out-of-sample incremental R-squared criterion carries "
            "the economic weight."
        ),
        cost_assumptions=CPI_COST_ASSUMPTIONS,
        train_window=SampleWindow(start=H0012_TRAIN_START, end=H0012_TRAIN_END),
        validation_window=SampleWindow(
            start=H0012_VALIDATION_START, end=H0012_VALIDATION_END
        ),
        holdout_window=SampleWindow(
            start=H0012_HOLDOUT_START, end=H0012_HOLDOUT_END
        ),
        purge_gap_seconds=86_400,
        minimum_train_observations=200,
        minimum_validation_observations=60,
        minimum_holdout_observations=60,
        primary_metric=(
            "Partial R-squared of the CPI step predictor in the daily "
            "SPX lead-lag regression"
        ),
        expected_direction=ExpectedDirection.NEGATIVE,
        minimum_effect_size=0.005,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Release-day-aligned CPI transmission (3 tests: A CPI step "
            "-> next-day SPX return, B CPI step -> next-day SPX return "
            "on release-day rows only, C CPI step -> next-day BTC "
            "return)"
        ),
        multiple_testing_method=MultiplicityCorrection.HOLM,
        planned_test_count=3,
        missing_data_policy=(
            "No forward filling; drop incomplete synchronized rows and "
            "report the dropped count. Rows before the first calendar "
            "release (2021-01-13) have an undefined predictor and are "
            "dropped."
        ),
        acceptance_criteria=(
            "Holm-adjusted A p-value below 0.05",
            "A partial R-squared at least 0.005",
            "Holdout out-of-sample incremental R-squared above 0",
        ),
        rejection_criteria=(
            "Holm-adjusted A p-value at or above 0.05",
            "A partial R-squared below 0.005",
            "Holdout out-of-sample incremental R-squared at or below 0",
        ),
        known_confounders=(
            CPI_EFFECTIVE_SAMPLE_NOTE,
            CPI_NOT_A_SURPRISE_NOTE,
            "CPIAUCSL is the current vintage: seasonal factors are "
            "revised annually, so the historical values differ slightly "
            "from the as-released prints; as-released values would need "
            "ALFRED (API key required) and the revision effect is "
            "small, but it is a stated limitation.",
            "FRED's own posting lag for CPIAUCSL relative to the BLS "
            "release date is a second-order effect and is not modelled: "
            "the step uses the BLS release date, not the FRED posting "
            "date.",
            "The CPI step predictor is highly autocorrelated (about "
            "21-trading-day runs); the HAC lags are fixed in this "
            "preregistration (21 for the daily tests, 5 for the "
            "release-day subsample) and are not tuned afterwards.",
            "Common shocks move CPI expectations and equities together; "
            "the regressions control for SPX's own lagged return only.",
            "The BTC robustness test uses the same calendar dates as "
            "the SPX tests; the OKX bar convention (16:00 UTC open, "
            "close date = open date + 1) is handled by evaluating the "
            "step at each bar's close date.",
            "The October 2025 CPI was never published, so the step "
            "holds the September 2025 value from 2025-10-24 until the "
            "November 2025 release on 2025-12-18 — the longest single "
            "step in the calendar, about eight weeks.",
        ),
        exclusions=(
            "Rows before the first calendar release (2021-01-13) have "
            "an undefined predictor and are excluded.",
            "Unconfirmed (forming) OKX bars are excluded; only "
            "confirm=1 candles enter the BTC panel.",
            "The first return row of each panel has no lag-1 predictor "
            "and is excluded.",
            "Bars after the preregistered window end 2026-11-18 are "
            "out of sample.",
            "The naive reference-month alignment is descriptive only "
            "and is not in the test family.",
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
        registry.register(build_bls_source_definition(), version=BLS_SOURCE_VERSION),
        registry.register(build_okx_source_definition(), version=OKX_SOURCE_VERSION),
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
        ),
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
        ),
    ]
    for (
        instrument_id,
        name,
        asset_class,
        instrument_type,
        quote,
        calendar_id,
        metadata,
    ) in INSTRUMENTS:
        paths.append(
            catalog.register_instrument(
                Instrument(
                    instrument_id=instrument_id,
                    asset_class=asset_class,
                    instrument_type=instrument_type,
                    name=name,
                    quote_currency=quote,
                    calendar_id=calendar_id,
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
    counts = verify_calendars()
    print(f"calendar counts verified: {counts}")
    for path in register_sources():
        print(f"registered source: {path}")
    for path in register_catalog():
        print(f"registered catalog entry: {path}")
    for spec in (build_h0011_spec(), build_h0012_spec()):
        fingerprint, registration_hash = register_hypothesis(spec)
        print(f"{spec.hypothesis_id} v1 spec fingerprint: {fingerprint}")
        print(f"{spec.hypothesis_id} v1 registration hash: {registration_hash}")
    registry = HypothesisRegistry(ROOT / "hypotheses")
    for hypothesis_id in ("H0011", "H0012"):
        state = registry.get_state(hypothesis_id, 1)
        print(f"{hypothesis_id} v1 state: {state.value}")
    events = registry.read_events()
    print(f"hypothesis events recorded: {len(events)}")


if __name__ == "__main__":
    main()
