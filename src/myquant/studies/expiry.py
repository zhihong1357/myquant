"""Deribit option expiry calendar and expiry-window features.

The calendar is constructed from the public Deribit rule — monthly
options expire on the last Friday of each calendar month and quarterly
options on the last Friday of each calendar quarter, both at 08:00 UTC
— because the public ``get_instruments`` endpoint returns only the most
recent batch of expired contracts and cannot reconstruct the historical
calendar. The rule was cross-checked two ways on 2026-11-18: (a) the
listed forward monthly/quarterly expiries all fall on last Fridays,
and the BTC and ETH expiry sets are identical; (b) the official Deribit
Contract Introduction Policy states the same last-Friday rule. The
verification record lives in the study 004 manifest, not in this
module: this module is pure calendar arithmetic plus window flags.

Window conventions (fixed by the study 004 preregistration):

- An expiry ``T`` is a calendar date (a Friday); settlement is 08:00 UTC
  on that date.
- The expiry window is the set of OKX bar-open dates in [T-3, T] (four
  calendar days; crypto trades every calendar day). The window flag for
  a bar is known at the bar's open: the expiry calendar is public in
  advance, so the flag is point-in-time correct.
- Under the close-to-close convention the return indexed at bar open
  ``t`` measures the price change over [t, t + 24h). The T-1 bar's
  interval contains the settlement moment (Friday 08:00 UTC) and the
  T bar is the first full post-settlement bar.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pandas as pd

#: Deribit option settlement time (UTC) on every expiry date.
SETTLEMENT_TIME = time(8, 0)

#: Months whose last-Friday expiry is also a quarterly expiry.
QUARTERLY_MONTHS = frozenset({3, 6, 9, 12})

#: How far ahead of an expiry Deribit lists its monthly contracts
#: (the Contract Introduction Policy lists three monthly expiries).
MONTHLY_LISTING_LEAD_DAYS = 92


@dataclass(frozen=True)
class ExpiryEvent:
    """One monthly option expiry (a last Friday, 08:00 UTC)."""

    expiry_date: date
    is_quarterly: bool

    @property
    def settlement(self) -> datetime:
        """Settlement moment (08:00 UTC on the expiry date)."""
        return datetime.combine(self.expiry_date, SETTLEMENT_TIME, tzinfo=UTC)


def last_friday(year: int, month: int) -> date:
    """Return the last Friday of the given calendar month."""
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    # Friday is weekday 4; walk back at most six days.
    return last_day - timedelta(days=(last_day.weekday() - 4) % 7)


def is_quarterly_month(month: int) -> bool:
    """Whether a month's last-Friday expiry is also a quarterly expiry."""
    return month in QUARTERLY_MONTHS


def monthly_expiries(start: date, end: date) -> tuple[ExpiryEvent, ...]:
    """Construct monthly expiries with dates in [start, end].

    Pure calendar arithmetic: every expiry is the last Friday of its
    month at 08:00 UTC, per the Deribit rule. No network access.
    """
    if end < start:
        raise ValueError("expiry range end must not precede start")
    events: list[ExpiryEvent] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        expiry = last_friday(year, month)
        if start <= expiry <= end:
            events.append(
                ExpiryEvent(expiry_date=expiry, is_quarterly=is_quarterly_month(month))
            )
        month += 1
        if month > 12:
            month = 1
            year += 1
    return tuple(events)


def window_dates(
    expiries: list[ExpiryEvent] | tuple[ExpiryEvent, ...],
    *,
    days_before: int = 3,
    days_after: int = 0,
) -> frozenset[date]:
    """Calendar dates inside any expiry window.

    The window for expiry T is [T - days_before, T + days_after].
    Windows never overlap for monthly expiries (they are at least 28
    days apart and the window is at most a week), so the set is a plain
    union; the function still deduplicates defensively.
    """
    if days_before < 0 or days_after < 0:
        raise ValueError("window offsets must be non-negative")
    dates: set[date] = set()
    for expiry in expiries:
        for offset in range(-days_before, days_after + 1):
            dates.add(expiry.expiry_date + timedelta(days=offset))
    return frozenset(dates)


def expiry_window_indicator(
    index: pd.DatetimeIndex,
    expiries: list[ExpiryEvent] | tuple[ExpiryEvent, ...],
    *,
    days_before: int = 3,
    days_after: int = 0,
) -> pd.Series:
    """Flag bars whose UTC bar-open date falls in an expiry window.

    The flag depends only on the bar-open date and the public expiry
    calendar, so it is known at the bar's open (point-in-time correct).
    """
    window = window_dates(expiries, days_before=days_before, days_after=days_after)
    flags = [ts.date() in window for ts in index]
    return pd.Series(flags, index=index, dtype=bool)


def quarterly_window_indicator(
    index: pd.DatetimeIndex,
    expiries: list[ExpiryEvent] | tuple[ExpiryEvent, ...],
    *,
    days_before: int = 3,
    days_after: int = 0,
) -> pd.Series:
    """Flag bars inside a *quarterly* expiry window only."""
    quarterly = tuple(event for event in expiries if event.is_quarterly)
    return expiry_window_indicator(
        index, quarterly, days_before=days_before, days_after=days_after
    )


def verify_calendar_against_listed(
    listed_expiry_dates: set[date] | frozenset[date],
    *,
    as_of: date,
    btc_expiry_dates: set[date] | frozenset[date] | None = None,
    eth_expiry_dates: set[date] | frozenset[date] | None = None,
) -> dict[str, object]:
    """Cross-check the constructed calendar against listed expiries.

    Check (a): every constructed monthly expiry within the monthly
    listing lead window (``as_of`` .. ``as_of`` + 92 days) must appear
    among the listed expiry dates. Monthlies further out are not yet
    introduced, so their absence is expected, not a failure.
    Check (b): every listed expiry date that is a quarterly month's
    last Friday must match the constructed quarterly expiry.
    Check (c): when both currency sets are given, the BTC and ETH
    listed expiry sets must be identical.

    Returns a JSON-serializable verification record with a boolean
    ``all_checks_passed`` flag and per-check detail.
    """
    listed = set(listed_expiry_dates)
    horizon_end = as_of + timedelta(days=MONTHLY_LISTING_LEAD_DAYS)
    expected_monthlies = monthly_expiries(as_of, horizon_end)
    missing_monthlies = [
        event.expiry_date.isoformat()
        for event in expected_monthlies
        if event.expiry_date not in listed
    ]
    monthly_check = len(missing_monthlies) == 0

    listed_quarterlies = sorted(
        expiry
        for expiry in listed
        if is_quarterly_month(expiry.month) and expiry == last_friday(expiry.year, expiry.month)
    )
    constructed_quarterlies = sorted(
        event.expiry_date
        for event in monthly_expiries(as_of, max(listed) if listed else as_of)
        if event.is_quarterly
    )
    quarterly_check = all(
        expiry in listed_quarterlies for expiry in constructed_quarterlies
    ) and all(
        expiry in constructed_quarterlies for expiry in listed_quarterlies
    )

    currencies_match: bool | None = None
    if btc_expiry_dates is not None and eth_expiry_dates is not None:
        currencies_match = set(btc_expiry_dates) == set(eth_expiry_dates)

    all_passed = monthly_check and quarterly_check and (currencies_match is not False)
    return {
        "all_checks_passed": all_passed,
        "monthly_check_passed": monthly_check,
        "missing_monthlies_within_listing_lead": missing_monthlies,
        "listing_lead_days": MONTHLY_LISTING_LEAD_DAYS,
        "horizon_end": horizon_end.isoformat(),
        "quarterly_check_passed": quarterly_check,
        "listed_quarterly_expiries": [d.isoformat() for d in listed_quarterlies],
        "constructed_quarterly_expiries": [
            d.isoformat() for d in constructed_quarterlies
        ],
        "currencies_match": currencies_match,
        "listed_expiry_count": len(listed),
    }
