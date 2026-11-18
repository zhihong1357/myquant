"""Preregister the macro-windows study (H0009, H0010).

Run once, before any macro-window result is computed:

    .venv/bin/python research/macro-windows-006/preregister.py

Registers the OKX, Federal Reserve, BLS and Fiscal Data public sources,
the three perpetual instruments and the 24/7 crypto calendar, and two
hypotheses:

- H0009 (transmission): BTC→ETH daily transmission is stronger inside
  macro windows (one OKX daily bar per FOMC statement / CPI release:
  the bar whose return interval contains the release moment) than
  outside them.
- H0010 (volatility level): mean daily absolute log return is higher
  on macro-window days than on non-window days (BTC primary, ETH
  secondary).

Macro-window definition (fixed here, locked by tests in
tests/test_studies_macro.py). OKX daily bars open at 16:00 UTC:

- CPI releases at 08:30 ET (12:30 UTC in DST, 13:30 UTC in standard
  time), always BEFORE 16:00 UTC, so the CPI window bar is the bar
  opened the day BEFORE the release date.
- FOMC statements release at about 14:00 ET (18:00 UTC in DST, 19:00
  UTC in standard time), always AFTER 16:00 UTC, so the FOMC window
  bar is the bar opened ON the statement day itself.
- Both offsets are DST-independent (CPI always before 16:00 UTC, FOMC
  always after). The window indicator is known at the bar's open
  because the schedules are public in advance (point-in-time correct).

Window counts over the preregistered sample (daily bars 2021-01-21 ..
2026-11-16): 116 window bars (69 CPI + 47 FOMC), no in-sample overlap.
The single overlap bar (2026-12-09: the Dec 9 FOMC statement and the
Dec 10 CPI release share one bar) is out of sample, as is the first CPI
bar (2021-01-12, before the panel) and the last FOMC bar (2026-12-09).
This script asserts these counts from the committed calendars before
registering anything, so a calendar change fails loudly here instead of
silently registering a spec with stale counts.

Calendars:

- FOMC: study 005's committed file
  (research/fomc-event-study-005/fomc_calendar.json), 48 statements in
  2021-2026, extracted from federalreserve.gov and cross-checked there.
- CPI: study 006's committed file
  (research/macro-windows-006/cpi_calendar.json), 71 releases
  2021-01-13..2026-12-10, transcribed from the BLS Schedule of
  Selected Releases pages via text fetch (BLS returns HTTP 403 to
  direct programmatic requests) and cross-checked against the BLS
  archived releases page and second sources. The October 2025 CPI was
  never published (2025 lapse in appropriations), so no event exists
  for that reference month.
- Treasury auctions (descriptive only, conditional): the auction
  calendar is fetched from the U.S. Treasury Fiscal Data API
  (auctions_query) and cross-checked against the TreasuryDirect
  auctioned-securities service. If the calendar cannot be verified,
  the auction-day descriptive splits are omitted and the report says
  why. Auction days never enter the main window (FOMC + CPI only).

Red lines:

- The window indicator is known at t, but the release CONTENT (whether
  the print surprised) is NOT known at t. This study tests the
  release-day effect, not the surprise effect; it does not claim to
  measure macro surprises or their transmission. Surprise measurement
  needs consensus/actuals data, which is out of scope.
- A window effect must not be default-attributed to any mechanism
  (e.g. "institutional rebalancing"). The report writes only to
  "consistent/inconsistent with ..." for any mechanism story.
- The CPI calendar's sourcing limitation is stated honestly: BLS
  direct connection is walled (HTTP 403); the calendar was extracted
  via text fetch and cross-checked, not from structured BLS API output.

Re-running is safe: identical registrations are left untouched and each
hypothesis is registered only once.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
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
from myquant.studies.macro import (
    build_macro_window,
    load_cpi_calendar,
    load_fomc_statement_dates,
)

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent

OKX_SOURCE_ID = "okx-public"
OKX_SOURCE_VERSION = 1
FEDERALRESERVE_SOURCE_ID = "federalreserve"
FEDERALRESERVE_SOURCE_VERSION = 1
BLS_SOURCE_ID = "bls"
BLS_SOURCE_VERSION = 1
FISCALDATA_SOURCE_ID = "fiscaldata"
FISCALDATA_SOURCE_VERSION = 1

INSTRUMENTS: tuple[tuple[str, str, str], ...] = (
    ("crypto:btc-usdt-perp", "BTC-USDT perpetual swap", "BTC-USDT-SWAP"),
    ("crypto:eth-usdt-perp", "ETH-USDT perpetual swap", "ETH-USDT-SWAP"),
    ("crypto:sol-usdt-perp", "SOL-USDT perpetual swap", "SOL-USDT-SWAP"),
)

# Daily windows (16:00 UTC bar opens), mirroring study 004. The daily
# panel starts at SOL's first confirmed OKX bar (2021-01-21T16:00Z);
# BTC and ETH history goes back further, but the synchronized
# three-instrument panel cannot start earlier. One-day purge gaps
# separate the windows.
TRAIN_START = datetime(2021, 1, 21, 16, 0, tzinfo=UTC)
TRAIN_END = datetime(2024, 1, 1, 16, 0, tzinfo=UTC)
VALIDATION_START = datetime(2024, 1, 2, 16, 0, tzinfo=UTC)
VALIDATION_END = datetime(2025, 1, 1, 16, 0, tzinfo=UTC)
HOLDOUT_START = datetime(2025, 1, 2, 16, 0, tzinfo=UTC)
HOLDOUT_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)

# 1H window (00:00 UTC bar opens), aligned with the daily holdout start;
# it covers about 22 months and is used for the H0009 1H robustness
# test only.
HOURLY_START = datetime(2025, 1, 2, 0, 0, tzinfo=UTC)
HOURLY_END = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)

# Preregistered sample bounds for the window-count assertion (daily
# bar-open dates; the panel's effective end is the last confirmed bar,
# 2026-11-16, two days short of the holdout end, as in study 004).
PANEL_FIRST_BAR = date(2021, 1, 21)
PANEL_LAST_BAR = date(2026, 11, 16)
EXPECTED_WINDOW_BARS = 116
EXPECTED_CPI_BARS = 69
EXPECTED_FOMC_BARS = 47
EXPECTED_OVERLAP_BARS = 1

COST_ASSUMPTIONS: tuple[str, ...] = (
    "OKX VIP0 taker fee 0.05% per side, from the OKX public fee "
    "schedule (okx.com/fees), checked 2026-11-18; treated as an "
    "assumption, not verified for the user's account",
    "Funding rate costs ignored; perpetual funding can exceed taker "
    "fees over holding periods",
    "Slippage and market impact ignored; both would reduce any edge",
)

MACRO_MECHANISM_NOTE = (
    "The window indicator is known at t (release schedules are public "
    "in advance), but the release content — whether the print surprised "
    "— is NOT known at t. This study tests the release-day effect, not "
    "the surprise effect, and does not claim to measure macro surprises "
    "or their transmission. A window effect must not be "
    "default-attributed to any mechanism (e.g. institutional "
    "rebalancing); the report writes only to 'consistent/inconsistent "
    "with ...' for any mechanism story."
)

CPI_SOURCING_NOTE = (
    "The CPI calendar was transcribed from the BLS Schedule of Selected "
    "Releases pages via text fetch and cross-checked against the BLS "
    "archived releases page and second sources; BLS returns HTTP 403 to "
    "direct programmatic requests, so the calendar is not structured BLS "
    "API output. The October 2025 CPI was never published (2025 lapse "
    "in appropriations), so no event exists for that reference month."
)

AUCTION_CONDITIONAL_NOTE = (
    "Treasury auction-day splits are descriptive only, conditional on "
    "the auction calendar being verifiable from the U.S. Treasury "
    "Fiscal Data API (auctions_query) with a TreasuryDirect cross-check; "
    "if the calendar cannot be verified, the auction splits are omitted "
    "and the report says why. Auction days never enter the main window "
    "(FOMC + CPI only)."
)


def verify_window_counts() -> dict[str, int]:
    """Assert the preregistered macro-window counts from the calendars.

    Runs before any registration: a calendar change fails loudly here
    instead of silently registering a spec with stale counts.
    """
    cpi_document = json.loads(
        (ROOT / "cpi_calendar.json").read_text(encoding="utf-8")
    )
    fomc_document = json.loads(
        (
            REPO_ROOT
            / "research"
            / "fomc-event-study-005"
            / "fomc_calendar.json"
        ).read_text(encoding="utf-8")
    )
    cpi = load_cpi_calendar(cpi_document)
    fomc = load_fomc_statement_dates(fomc_document)
    fomc_2021_2026 = tuple(d for d in fomc if 2021 <= d.year <= 2026)
    if len(cpi) != 71:
        raise ValueError(f"CPI calendar has {len(cpi)} releases, expected 71")
    if len(fomc_2021_2026) != 48:
        raise ValueError(
            f"FOMC calendar has {len(fomc_2021_2026)} statements in "
            "2021-2026, expected 48"
        )
    window = build_macro_window(
        [item.release_date for item in cpi], fomc_2021_2026
    )
    if len(window.overlap_bars) != EXPECTED_OVERLAP_BARS:
        raise ValueError(
            f"macro-window overlap bars: {sorted(window.overlap_bars)}, "
            f"expected {EXPECTED_OVERLAP_BARS}"
        )
    in_sample = {
        bar
        for bar in window.window_bars
        if PANEL_FIRST_BAR <= bar <= PANEL_LAST_BAR
    }
    cpi_in_sample = {
        bar
        for bar in window.cpi_bars
        if PANEL_FIRST_BAR <= bar <= PANEL_LAST_BAR
    }
    fomc_in_sample = {
        bar
        for bar in window.fomc_bars
        if PANEL_FIRST_BAR <= bar <= PANEL_LAST_BAR
    }
    counts = {
        "window_bars_in_sample": len(in_sample),
        "cpi_bars_in_sample": len(cpi_in_sample),
        "fomc_bars_in_sample": len(fomc_in_sample),
        "overlap_bars_total": len(window.overlap_bars),
        "overlap_bars_in_sample": len(
            window.overlap_bars
            & {bar for bar in in_sample}
        ),
    }
    if counts["window_bars_in_sample"] != EXPECTED_WINDOW_BARS:
        raise ValueError(
            f"in-sample window bars: {counts['window_bars_in_sample']}, "
            f"expected {EXPECTED_WINDOW_BARS}"
        )
    if counts["cpi_bars_in_sample"] != EXPECTED_CPI_BARS:
        raise ValueError(
            f"in-sample CPI bars: {counts['cpi_bars_in_sample']}, "
            f"expected {EXPECTED_CPI_BARS}"
        )
    if counts["fomc_bars_in_sample"] != EXPECTED_FOMC_BARS:
        raise ValueError(
            f"in-sample FOMC bars: {counts['fomc_bars_in_sample']}, "
            f"expected {EXPECTED_FOMC_BARS}"
        )
    return counts


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
            "standard time), always before the 16:00 UTC OKX daily bar open."
        ),
    )


def build_fiscaldata_source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id=FISCALDATA_SOURCE_ID,
        provider=(
            "U.S. Department of the Treasury, Bureau of the Fiscal Service"
        ),
        description=(
            "Fiscal Data API auctions_query dataset: Treasury auction "
            "results by CUSIP, including auction_date, security_type and "
            "security_term, for the descriptive Treasury auction-day "
            "splits only (auction days never enter the main window)"
        ),
        license_status=LicenseStatus.APPROVED,
        permission_basis=(
            "Public auction data served without authentication by the "
            "Fiscal Data API "
            "(api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
            "accounting/od/auctions_query), used for research only; raw "
            "payloads are not redistributed. This registry entry is an "
            "explicit research-use assertion, not a legal determination."
        ),
        terms_url="https://fiscaldata.treasury.gov/",
        attribution="Source: U.S. Department of the Treasury, Fiscal Data",
        nominal_delay_seconds=0,
        timestamp_basis=(
            "auction_date is the competitive-bidding close date; "
            "note/bond results are announced shortly after the 1:00 PM "
            "ET close (17:00 UTC in daylight saving time, 18:00 UTC in "
            "standard time), always after the 16:00 UTC OKX daily bar open."
        ),
    )


def build_h0009_spec() -> HypothesisSpec:
    """The preregistered H0009 research plan.

    Window definition: the macro window is the union of FOMC statement
    days and CPI release days, one OKX daily bar per event (the bar
    whose return interval contains the release moment). CPI releases at
    08:30 ET, always before the 16:00 UTC bar open, so the CPI window
    bar is the bar opened the day BEFORE the release date; FOMC
    statements release at about 14:00 ET, always after the 16:00 UTC
    bar open, so the FOMC window bar is the bar opened ON the statement
    day. Both offsets are DST-independent. The window indicator is
    known at the bar's open because the schedules are public in advance.
    """
    return HypothesisSpec(
        hypothesis_id="H0009",
        title="Macro windows strengthen BTC→ETH transmission",
        research_question=(
            "Does lag-1 BTC perpetual return predict the next-day ETH "
            "perpetual return more strongly inside macro windows (one OKX "
            "daily bar per FOMC statement / CPI release: the bar whose "
            "return interval contains the release moment) than outside "
            "them?"
        ),
        mechanism=(
            "Scheduled macro releases concentrate information flow on "
            "release days, so price discovery in the largest market (BTC "
            "perpetuals) may transmit to ETH with a stronger lag inside "
            "the window. " + MACRO_MECHANISM_NOTE
        ),
        alternative_hypothesis=(
            "The lag-1 BTC coefficient for next-day ETH returns is larger "
            "inside macro windows than outside them (positive "
            "interaction), and lag-1 BTC explains a positive "
            "out-of-sample component of next-day ETH returns within "
            "macro-window rows."
        ),
        null_hypothesis=(
            "Lag-1 BTC returns have no macro-window-dependent incremental "
            "predictive value: the interaction coefficient is zero and "
            "lag-1 BTC does not predict ETH returns within macro-window "
            "rows, beyond ETH's own history and the common-factor "
            "control, after costs and dependence controls."
        ),
        universe=tuple(item[0] for item in INSTRUMENTS),
        source_versions=(
            f"{OKX_SOURCE_ID}@v{OKX_SOURCE_VERSION}",
            f"{FEDERALRESERVE_SOURCE_ID}@v{FEDERALRESERVE_SOURCE_VERSION}",
            f"{BLS_SOURCE_ID}@v{BLS_SOURCE_VERSION}",
            f"{FISCALDATA_SOURCE_ID}@v{FISCALDATA_SOURCE_VERSION}",
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
            "macro-window-indicator@v1",
            "btc-macro-window-interaction@v1",
        ),
        model_definition=(
            "Interaction OLS with HAC standard errors (daily BTC→ETH, 1H BTC→ETH)",
            "Macro-window-subsample partial lead-lag with HAC standard errors",
            "Window-aware purged walk-forward out-of-sample evaluation "
            "(macro-window holdout rows only)",
            "Macro-window counts over the preregistered sample (daily "
            "bars 2021-01-21..2026-11-16): 116 window bars (69 CPI, 47 "
            "FOMC), no in-sample overlap; the single overlap bar "
            "(2026-12-09) is out of sample",
            "Wide-window (event bar ±1 bar), FOMC-only vs CPI-only and "
            "subperiod splits as descriptive checks (not in the test family)",
            AUCTION_CONDITIONAL_NOTE,
        ),
        fixed_parameters=(
            "lag=1",
            "daily_max_hac_lag=5",
            "hourly_max_hac_lag=12",
            "wide_window_days_before=1",
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
            "forecasts on macro-window holdout rows only, 1x, flat on "
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
            "Partial R-squared of the BTC×macro-window interaction in "
            "the daily BTC→ETH interaction regression"
        ),
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=0.005,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Macro-window BTC→ETH daily transmission (3 tests: A daily "
            "interaction, B daily macro-window subsample, C 1H interaction)"
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
            "macro-window holdout rows",
            "Net daily edge after the 0.10% round-trip taker cost is positive",
        ),
        rejection_criteria=(
            "Holm-adjusted A interaction p-value at or above 0.05",
            "A interaction partial R-squared below 0.005",
            "Holdout out-of-sample incremental R-squared at or below 0 on "
            "macro-window holdout rows",
            "Net daily edge after costs is zero or negative",
        ),
        known_confounders=(
            "The release content (whether the print surprised) is not "
            "known at t; this study tests the release-day effect, not "
            "the surprise effect, and must not be read as evidence about "
            "macro surprises or their transmission",
            "A window effect must not be default-attributed to any "
            "mechanism (e.g. institutional rebalancing); the report "
            "writes only to 'consistent/inconsistent with ...'",
            CPI_SOURCING_NOTE,
            "Macro windows are scarce (about 20 events per year); the "
            "daily window sample is 116 rows of about 2,100, so power "
            "against small effects is limited",
            "The SOL common-factor proxy is itself driven by BTC and may "
            "absorb part of the transmission effect; no-factor controls "
            "are reported as upper bounds",
            "Common crypto market shocks move BTC, ETH and SOL together; "
            "the regressions control for the contemporaneous third-asset "
            "return only",
            "The CPI window bar opened the day before the release date "
            "and the FOMC window bar opened on the statement day; both "
            "offsets are fixed by the release times against the 16:00 "
            "UTC bar open and are DST-independent",
        ),
        exclusions=(
            "Unconfirmed (forming) OKX bars are excluded; only confirm=1 "
            "candles enter the panel",
            "The first daily return row has no lag-1 predictor and is "
            "excluded; the same warm-up rule applies to the 1H panel",
            "Bars after the preregistered window end 2026-11-18T16:00Z "
            "are out of sample",
            "The October 2025 CPI was never published, so no window bar "
            "exists for that reference month",
        ),
        random_seed=42,
    )


def build_h0010_spec() -> HypothesisSpec:
    """The preregistered H0010 research plan.

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
    of window to non-window mean |log return|; the 1.15 threshold is
    reused from H0006 with the same justification — macro release days
    are known high-volatility days, and 15% is the smallest uplift worth
    noticing for a first-order calendar effect rather than a marginal one.
    """
    return HypothesisSpec(
        hypothesis_id="H0010",
        title="Macro windows raise realized volatility",
        research_question=(
            "Is mean daily absolute log return (|log return|, a robust "
            "realized-volatility proxy) higher on macro-window days (one "
            "OKX daily bar per FOMC statement / CPI release) than on "
            "non-window days, for BTC (primary) and ETH (secondary) "
            "perpetuals?"
        ),
        mechanism=(
            "Scheduled macro releases concentrate information flow on "
            "release days, which may raise realized volatility on window "
            "days. " + MACRO_MECHANISM_NOTE
        ),
        alternative_hypothesis=(
            "Mean daily absolute log return is higher on macro-window "
            "days than on non-window days (positive window coefficient), "
            "with a window/non-window mean ratio of at least 1.15 for BTC."
        ),
        null_hypothesis=(
            "Mean daily absolute log return is the same on macro-window "
            "and non-window days; the window coefficient is zero."
        ),
        universe=("crypto:btc-usdt-perp", "crypto:eth-usdt-perp"),
        source_versions=(
            f"{OKX_SOURCE_ID}@v{OKX_SOURCE_VERSION}",
            f"{FEDERALRESERVE_SOURCE_ID}@v{FEDERALRESERVE_SOURCE_VERSION}",
            f"{BLS_SOURCE_ID}@v{BLS_SOURCE_VERSION}",
            f"{FISCALDATA_SOURCE_ID}@v{FISCALDATA_SOURCE_VERSION}",
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
            "macro-window-indicator@v1",
        ),
        model_definition=(
            "Mean comparison by OLS of |log return| on the window "
            "indicator with HAC standard errors (max lag 10)",
            "Block-bootstrap confidence interval for the window minus "
            "non-window mean difference (block 10, 2000 resamples, seed 42)",
            "The mean comparison uses all daily rows in the sample "
            "period (train + validation + holdout); the windows define "
            "the sample period, not a train/test split for this hypothesis",
            "Macro-window counts over the preregistered sample (daily "
            "bars 2021-01-21..2026-11-16): 116 window bars (69 CPI, 47 "
            "FOMC), no in-sample overlap; the single overlap bar "
            "(2026-12-09) is out of sample",
            "Wide-window (event bar ±1 bar), FOMC-only vs CPI-only and "
            "subperiod splits as descriptive checks (not in the test family)",
            AUCTION_CONDITIONAL_NOTE,
        ),
        fixed_parameters=(
            "wide_window_days_before=1",
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
            "No cost gate: H0010 is a volatility-level comparison, not a "
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
            "Ratio of mean daily |log return| on macro-window days to "
            "mean daily |log return| on non-window days (BTC primary)"
        ),
        expected_direction=ExpectedDirection.POSITIVE,
        minimum_effect_size=1.15,
        target_error_rate=0.05,
        multiple_testing_family=(
            "Macro-window realized-volatility level (2 tests: BTC mean "
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
            "The release content (whether the print surprised) is not "
            "known at t; this study tests the release-day effect, not "
            "the surprise effect",
            CPI_SOURCING_NOTE,
            "Macro windows are scarce (about 20 events per year); the "
            "daily window sample is 116 rows of about 2,100",
            "The CPI window bar opened the day before the release date "
            "and the FOMC window bar opened on the statement day; both "
            "offsets are fixed by the release times against the 16:00 "
            "UTC bar open and are DST-independent",
        ),
        exclusions=(
            "Unconfirmed (forming) OKX bars are excluded; only confirm=1 "
            "candles enter the panel",
            "The first daily return row has no lag-1 predictor and is "
            "excluded",
            "Bars after the preregistered window end 2026-11-18T16:00Z "
            "are out of sample",
            "The October 2025 CPI was never published, so no window bar "
            "exists for that reference month",
        ),
        random_seed=42,
    )


def register_sources() -> list[Path]:
    registry = SourceRegistry(ROOT / "sources")
    return [
        registry.register(build_okx_source_definition(), version=OKX_SOURCE_VERSION),
        registry.register(
            build_federalreserve_source_definition(),
            version=FEDERALRESERVE_SOURCE_VERSION,
        ),
        registry.register(build_bls_source_definition(), version=BLS_SOURCE_VERSION),
        registry.register(
            build_fiscaldata_source_definition(),
            version=FISCALDATA_SOURCE_VERSION,
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
    counts = verify_window_counts()
    print(f"macro-window counts verified: {counts}")
    for path in register_sources():
        print(f"registered source: {path}")
    for path in register_catalog():
        print(f"registered catalog entry: {path}")
    for spec in (build_h0009_spec(), build_h0010_spec()):
        fingerprint, registration_hash = register_hypothesis(spec)
        print(f"{spec.hypothesis_id} v1 spec fingerprint: {fingerprint}")
        print(f"{spec.hypothesis_id} v1 registration hash: {registration_hash}")
    registry = HypothesisRegistry(ROOT / "hypotheses")
    for hypothesis_id in ("H0009", "H0010"):
        state = registry.get_state(hypothesis_id, 1)
        print(f"{hypothesis_id} v1 state: {state.value}")
    events = registry.read_events()
    print(f"hypothesis events recorded: {len(events)}")


if __name__ == "__main__":
    main()
