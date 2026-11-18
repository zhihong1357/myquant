"""Macro release calendar and macro-window features (study 006).

The macro window is the union of FOMC statement days and CPI release
days, one OKX daily bar per event: the bar whose return interval
contains the release moment. OKX daily bars open at 16:00 UTC, so which
bar contains a release depends on the release's time of day in UTC:

- **CPI** is released at 08:30 Eastern Time: 12:30 UTC in daylight
  saving time, 13:30 UTC in standard time. Both are **before** 16:00
  UTC, so the release always falls inside the bar that opened at 16:00
  UTC on the **day before** the release date. The CPI window bar is the
  release date minus one day.
- **FOMC statements** are released at about 14:00 Eastern Time: 18:00
  UTC in daylight saving time, 19:00 UTC in standard time. Both are
  **after** 16:00 UTC, so the statement always falls inside the bar that
  opened at 16:00 UTC on the **statement day itself**. The FOMC window
  bar is the statement date.
- **Treasury auction results** (descriptive only) are announced shortly
  after the competitive-bidding close, 1:00 PM ET for notes and bonds
  (11:30 AM ET for bills, which are not used here): 17:00 UTC in
  daylight saving time, 18:00 UTC in standard time. Both are **after**
  16:00 UTC, so the auction window bar is the auction date itself.

Both offsets are DST-independent: CPI is always before 16:00 UTC and
FOMC/auction results are always after it, in both DST and standard time.
No timezone conversion is needed anywhere in this module — the mapping
is a fixed day offset per event type, which is exactly why it can be
locked by tests on known dates.

The window indicator for a bar is known at the bar's open: FOMC and CPI
schedules are public months in advance. What is NOT known at the bar's
open is the release *content* (whether the print surprised); this study
tests the release-day effect, not the surprise effect.

Calendar sources:

- FOMC statement days come from study 005's committed calendar file
  (``research/fomc-event-study-005/fomc_calendar.json``), extracted from
  federalreserve.gov pages and cross-checked there. This module only
  loads the statement dates; it does not re-parse the Fed's pages.
- CPI release days come from study 006's committed calendar file
  (``research/macro-windows-006/cpi_calendar.json``), transcribed from
  the BLS Schedule of Selected Releases pages via text fetch (BLS
  returns HTTP 403 to direct programmatic requests). The October 2025
  CPI was never published (2025 lapse in appropriations), so no event
  exists for that reference month.
- Treasury auction dates (descriptive only) come from study 006's
  committed calendar file
  (``research/macro-windows-006/treasury_auction_calendar.json``),
  fetched from the U.S. Treasury Fiscal Data API (auctions_query) and
  cross-checked against the TreasuryDirect auctioned-securities service.

This module is pure calendar arithmetic plus window flags (no network,
no market data). Fetching and verification live in the study 006 fetch
script; the verification records live in the study manifest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Any

import pandas as pd

#: CPI release time, Eastern Time (08:30 ET = 12:30/13:30 UTC).
CPI_RELEASE_TIME_ET = time(8, 30)

#: FOMC statement release time, Eastern Time (about 14:00 ET = 18:00/19:00 UTC).
FOMC_STATEMENT_TIME_ET = time(14, 0)

#: Treasury note/bond auction competitive-bidding close, Eastern Time
#: (1:00 PM ET = 17:00/18:00 UTC; results follow shortly after).
AUCTION_CLOSE_TIME_ET = time(13, 0)

#: OKX daily bar open, UTC. The release-time argument above is stated
#: against this boundary.
BAR_OPEN_TIME_UTC = time(16, 0)


@dataclass(frozen=True)
class CPIRelease:
    """One CPI release: its date and the reference month it reports."""

    release_date: date
    reference_month: str  # "YYYY-MM", always the month before the release


@dataclass(frozen=True)
class MacroWindow:
    """The macro window as sets of OKX daily bar-open dates.

    ``window_bars`` is the union of the CPI and FOMC window bars (the
    main window used by the test family). ``overlap_bars`` are bars
    that are both a CPI window bar and an FOMC window bar: a CPI
    release the day after an FOMC statement lands in the same bar as
    the statement. The union counts each bar once.
    """

    window_bars: frozenset[date]
    cpi_bars: frozenset[date]
    fomc_bars: frozenset[date]
    overlap_bars: frozenset[date]


def cpi_window_bar(release_date: date) -> date:
    """The OKX daily bar-open date containing a CPI release.

    CPI releases at 08:30 ET (12:30 UTC in DST, 13:30 UTC in standard
    time), always before the 16:00 UTC bar open, so the release falls
    inside the bar opened the day before the release date.
    """
    return release_date - timedelta(days=1)


def fomc_window_bar(statement_date: date) -> date:
    """The OKX daily bar-open date containing an FOMC statement.

    Statements release at about 14:00 ET (18:00 UTC in DST, 19:00 UTC
    in standard time), always after the 16:00 UTC bar open, so the
    statement falls inside the bar opened on the statement day itself.
    """
    return statement_date


def auction_window_bar(auction_date: date) -> date:
    """The OKX daily bar-open date containing a Treasury auction result.

    Note/bond auction results are announced shortly after the 1:00 PM
    ET competitive close (17:00 UTC in DST, 18:00 UTC in standard
    time), always after the 16:00 UTC bar open, so the result falls
    inside the bar opened on the auction day itself. Descriptive only.
    """
    return auction_date


def build_macro_window(
    cpi_release_dates: list[date] | tuple[date, ...],
    fomc_statement_dates: list[date] | tuple[date, ...],
) -> MacroWindow:
    """Build the macro window (union of CPI and FOMC window bars).

    Pure set arithmetic: each event maps to exactly one window bar via
    its fixed offset, and the union deduplicates bars that contain both
    a CPI release and an FOMC statement.
    """
    cpi_bars = frozenset(cpi_window_bar(item) for item in cpi_release_dates)
    fomc_bars = frozenset(fomc_window_bar(item) for item in fomc_statement_dates)
    return MacroWindow(
        window_bars=cpi_bars | fomc_bars,
        cpi_bars=cpi_bars,
        fomc_bars=fomc_bars,
        overlap_bars=cpi_bars & fomc_bars,
    )


def wide_window_dates(
    window_bars: frozenset[date] | set[date],
    *,
    days_before: int = 1,
    days_after: int = 1,
) -> frozenset[date]:
    """Expand each window bar by ±1 bar (descriptive wide window).

    The wide window is event bar ±1 bar, as a set union: overlapping
    expansions of nearby events deduplicate.
    """
    if days_before < 0 or days_after < 0:
        raise ValueError("wide-window offsets must be non-negative")
    dates: set[date] = set()
    for bar in window_bars:
        for offset in range(-days_before, days_after + 1):
            dates.add(bar + timedelta(days=offset))
    return frozenset(dates)


def macro_window_indicator(
    index: pd.DatetimeIndex,
    window_bars: frozenset[date] | set[date],
) -> pd.Series:
    """Flag bars whose UTC bar-open date falls in the macro window.

    The flag depends only on the bar-open date and the public release
    calendar, so it is known at the bar's open (point-in-time correct).
    Hourly bars share the calendar-day rule: every hourly bar on a
    window date is flagged, including the hour containing the release.
    """
    bars = set(window_bars)
    flags = [ts.date() in bars for ts in index]
    return pd.Series(flags, index=index, dtype=bool)


def _parse_date(value: object, *, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO date: {value!r}") from exc


def load_cpi_calendar(document: dict[str, Any]) -> tuple[CPIRelease, ...]:
    """Parse and validate the committed CPI calendar document.

    Structural checks: every release has a release date and a reference
    month; dates are unique and sorted; every reference month is exactly
    the calendar month before the release month (true for all 71
    releases, including the two shutdown-affected 2025 releases). The
    file's own verification record (annual counts, archive cross-check,
    second-source spot checks) is the provenance; this loader checks
    the structure, not the provenance claims.
    """
    releases = document.get("releases")
    if not isinstance(releases, list) or not releases:
        raise ValueError("CPI calendar document has no releases list")
    parsed: list[CPIRelease] = []
    for entry in releases:
        if not isinstance(entry, dict):
            raise ValueError(f"CPI release entry is not an object: {entry!r}")
        release_date = _parse_date(entry.get("release_date"), field="release_date")
        reference_month = entry.get("reference_month")
        if not isinstance(reference_month, str):
            raise ValueError(
                f"CPI release {release_date} has no reference_month string"
            )
        try:
            ref_year, ref_month = (
                int(part) for part in reference_month.split("-")
            )
        except ValueError as exc:
            raise ValueError(
                f"CPI release {release_date} has a malformed reference_month: "
                f"{reference_month!r}"
            ) from exc
        expected_year, expected_month = (
            (release_date.year - 1, 12)
            if release_date.month == 1
            else (release_date.year, release_date.month - 1)
        )
        if (ref_year, ref_month) != (expected_year, expected_month):
            raise ValueError(
                f"CPI release {release_date} reports reference month "
                f"{reference_month}, expected {expected_year:04d}-{expected_month:02d}"
            )
        parsed.append(
            CPIRelease(release_date=release_date, reference_month=reference_month)
        )
    dates = [item.release_date for item in parsed]
    if dates != sorted(dates):
        raise ValueError("CPI releases are not sorted by release date")
    if len(set(dates)) != len(dates):
        raise ValueError("CPI calendar has duplicate release dates")
    return tuple(parsed)


def load_fomc_statement_dates(document: dict[str, Any]) -> tuple[date, ...]:
    """Parse the statement dates from study 005's FOMC calendar file.

    The file was extracted and cross-checked by study 005; this loader
    only reads the scheduled meetings' statement dates, sorted, with a
    duplicate check. It does not re-derive the calendar.
    """
    meetings = document.get("scheduled_meetings")
    if not isinstance(meetings, list) or not meetings:
        raise ValueError("FOMC calendar document has no scheduled_meetings list")
    dates: list[date] = []
    for entry in meetings:
        if not isinstance(entry, dict):
            raise ValueError(f"FOMC meeting entry is not an object: {entry!r}")
        dates.append(
            _parse_date(entry.get("statement_date"), field="statement_date")
        )
    if len(set(dates)) != len(dates):
        raise ValueError("FOMC calendar has duplicate statement dates")
    return tuple(sorted(dates))


def load_auction_calendar(document: dict[str, Any]) -> tuple[date, ...]:
    """Parse the coupon auction dates from the auction calendar file.

    The file lists distinct Treasury note/bond auction (competitive
    close) dates; bills are excluded by construction (weekly cash
    management, not event days). Dates must be unique and sorted.
    """
    dates_value = document.get("coupon_auction_dates")
    if not isinstance(dates_value, list) or not dates_value:
        raise ValueError("auction calendar document has no coupon_auction_dates list")
    dates = [
        _parse_date(value, field="coupon_auction_dates entry")
        for value in dates_value
    ]
    if dates != sorted(dates):
        raise ValueError("auction dates are not sorted")
    if len(set(dates)) != len(dates):
        raise ValueError("auction calendar has duplicate dates")
    return tuple(dates)


def load_verified_auction_dates(
    document: dict[str, Any],
) -> tuple[date, ...] | None:
    """Auction dates, but only when the calendar is verified.

    The preregistered conditional: auction-day splits are descriptive
    and run only when the auction calendar's verification passed (the
    Fiscal Data API vs TreasuryDirect cross-check agreed and the
    annual-count bounds held). Returns None when `verified` is not
    exactly True, so trial scripts omit the splits and record why
    instead of silently using an unverified calendar. A verified
    calendar still goes through the structural loader, so a malformed
    verified document raises rather than returning partial dates.
    """
    if document.get("verified") is not True:
        return None
    return load_auction_calendar(document)


def annual_counts(dates: list[date] | tuple[date, ...]) -> dict[int, int]:
    """Event counts per calendar year."""
    counts: dict[int, int] = {}
    for item in dates:
        counts[item.year] = counts.get(item.year, 0) + 1
    return counts
