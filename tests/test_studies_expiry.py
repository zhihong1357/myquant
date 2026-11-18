"""Offline tests for the Deribit expiry calendar and window flags."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from myquant.studies.expiry import (
    ExpiryEvent,
    expiry_window_indicator,
    is_quarterly_month,
    last_friday,
    monthly_expiries,
    quarterly_window_indicator,
    verify_calendar_against_listed,
    window_dates,
)


class TestLastFriday:
    def test_known_months(self) -> None:
        assert last_friday(2026, 11) == date(2026, 11, 27)
        assert last_friday(2026, 12) == date(2026, 12, 25)
        assert last_friday(2027, 1) == date(2027, 1, 29)
        assert last_friday(2027, 3) == date(2027, 3, 26)
        assert last_friday(2021, 1) == date(2021, 1, 29)

    def test_month_ending_on_friday(self) -> None:
        # 2021-04-30 is itself a Friday.
        assert last_friday(2021, 4) == date(2021, 4, 30)

    def test_month_starting_on_friday(self) -> None:
        # 2021-10-01 is a Friday; the last Friday is 2021-10-29.
        assert last_friday(2021, 10) == date(2021, 10, 29)

    def test_february_leap_and_common(self) -> None:
        assert last_friday(2024, 2) == date(2024, 2, 23)
        assert last_friday(2023, 2) == date(2023, 2, 24)

    def test_year_end_boundary(self) -> None:
        assert last_friday(2026, 12) == date(2026, 12, 25)
        assert last_friday(2027, 1) == date(2027, 1, 29)


class TestMonthlyExpiries:
    def test_range_and_quarterly_flags(self) -> None:
        expiries = monthly_expiries(date(2026, 11, 1), date(2027, 3, 31))
        assert [event.expiry_date for event in expiries] == [
            date(2026, 11, 27),
            date(2026, 12, 25),
            date(2027, 1, 29),
            date(2027, 2, 26),
            date(2027, 3, 26),
        ]
        assert [event.is_quarterly for event in expiries] == [
            False,
            True,
            False,
            False,
            True,
        ]

    def test_partial_month_boundaries(self) -> None:
        # Start after November's expiry: November is excluded.
        expiries = monthly_expiries(date(2026, 11, 28), date(2026, 12, 31))
        assert [event.expiry_date for event in expiries] == [date(2026, 12, 25)]
        # End before December's expiry: December is excluded.
        expiries = monthly_expiries(date(2026, 11, 1), date(2026, 12, 24))
        assert [event.expiry_date for event in expiries] == [date(2026, 11, 27)]

    def test_inverted_range_raises(self) -> None:
        with pytest.raises(ValueError):
            monthly_expiries(date(2026, 12, 1), date(2026, 11, 1))

    def test_full_year_has_twelve_expiries(self) -> None:
        expiries = monthly_expiries(date(2021, 1, 1), date(2021, 12, 31))
        assert len(expiries) == 12
        assert sum(event.is_quarterly for event in expiries) == 4

    def test_settlement_is_0800_utc(self) -> None:
        event = ExpiryEvent(expiry_date=date(2026, 11, 27), is_quarterly=False)
        assert event.settlement == datetime(2026, 11, 27, 8, 0, tzinfo=UTC)


class TestWindowDates:
    def test_default_window_is_t_minus_3_to_t(self) -> None:
        expiries = (ExpiryEvent(date(2026, 11, 27), False),)
        assert window_dates(expiries) == {
            date(2026, 11, 24),
            date(2026, 11, 25),
            date(2026, 11, 26),
            date(2026, 11, 27),
        }

    def test_wide_window(self) -> None:
        expiries = (ExpiryEvent(date(2026, 11, 27), False),)
        assert window_dates(expiries, days_before=5, days_after=1) == {
            date(2026, 11, 22),
            date(2026, 11, 23),
            date(2026, 11, 24),
            date(2026, 11, 25),
            date(2026, 11, 26),
            date(2026, 11, 27),
            date(2026, 11, 28),
        }

    def test_negative_offsets_raise(self) -> None:
        expiries = (ExpiryEvent(date(2026, 11, 27), False),)
        with pytest.raises(ValueError):
            window_dates(expiries, days_before=-1)


class TestWindowIndicator:
    def test_flags_bar_open_dates_in_window(self) -> None:
        expiries = (ExpiryEvent(date(2026, 11, 27), False),)
        index = pd.DatetimeIndex(
            [
                datetime(2026, 11, 23, 16, 0, tzinfo=UTC),
                datetime(2026, 11, 24, 16, 0, tzinfo=UTC),
                datetime(2026, 11, 27, 16, 0, tzinfo=UTC),
                datetime(2026, 11, 28, 16, 0, tzinfo=UTC),
            ]
        )
        flags = expiry_window_indicator(index, expiries)
        assert flags.tolist() == [False, True, True, False]
        assert flags.dtype == bool

    def test_hourly_bars_share_the_calendar_day_rule(self) -> None:
        expiries = (ExpiryEvent(date(2026, 11, 27), False),)
        index = pd.date_range(
            datetime(2026, 11, 26, 0, 0, tzinfo=UTC),
            datetime(2026, 11, 27, 23, 0, tzinfo=UTC),
            freq="h",
        )
        flags = expiry_window_indicator(index, expiries)
        # Both days are in the window, so all 48 hours are flagged.
        assert flags.all()

    def test_quarterly_indicator_only(self) -> None:
        expiries = (
            ExpiryEvent(date(2026, 11, 27), False),
            ExpiryEvent(date(2026, 12, 25), True),
        )
        index = pd.DatetimeIndex(
            [
                datetime(2026, 11, 27, 16, 0, tzinfo=UTC),
                datetime(2026, 12, 25, 16, 0, tzinfo=UTC),
            ]
        )
        flags = quarterly_window_indicator(index, expiries)
        assert flags.tolist() == [False, True]

    def test_empty_expiries_flags_nothing(self) -> None:
        index = pd.DatetimeIndex([datetime(2026, 11, 27, 16, 0, tzinfo=UTC)])
        assert expiry_window_indicator(index, ()).tolist() == [False]


class TestVerifyCalendarAgainstListed:
    def test_listed_expiries_from_2026_11_18_pass(self) -> None:
        # The actual listed BTC/ETH expiry sets observed 2026-11-18.
        listed = {
            date(2026, 11, 18),
            date(2026, 11, 19),
            date(2026, 11, 20),
            date(2026, 11, 21),
            date(2026, 11, 27),
            date(2026, 12, 4),
            date(2026, 12, 25),
            date(2027, 1, 29),
            date(2027, 3, 26),
            date(2027, 6, 25),
            date(2027, 9, 24),
        }
        record = verify_calendar_against_listed(
            listed,
            as_of=date(2026, 11, 18),
            btc_expiry_dates=listed,
            eth_expiry_dates=set(listed),
        )
        assert record["all_checks_passed"] is True
        assert record["monthly_check_passed"] is True
        assert record["quarterly_check_passed"] is True
        assert record["currencies_match"] is True
        assert record["listed_quarterly_expiries"] == [
            "2026-12-25",
            "2027-03-26",
            "2027-06-25",
            "2027-09-24",
        ]

    def test_missing_monthly_fails(self) -> None:
        listed = {
            date(2026, 11, 27),
            date(2026, 12, 25),
            date(2027, 3, 26),
            date(2027, 6, 25),
            date(2027, 9, 24),
        }
        record = verify_calendar_against_listed(listed, as_of=date(2026, 11, 18))
        assert record["all_checks_passed"] is False
        assert record["monthly_check_passed"] is False
        assert record["missing_monthlies_within_listing_lead"] == ["2027-01-29"]

    def test_currency_mismatch_fails(self) -> None:
        listed = {
            date(2026, 11, 27),
            date(2026, 12, 25),
            date(2027, 1, 29),
            date(2027, 3, 26),
            date(2027, 6, 25),
            date(2027, 9, 24),
        }
        record = verify_calendar_against_listed(
            listed,
            as_of=date(2026, 11, 18),
            btc_expiry_dates=listed,
            eth_expiry_dates=listed - {date(2027, 9, 24)},
        )
        assert record["currencies_match"] is False
        assert record["all_checks_passed"] is False


def test_quarterly_months() -> None:
    assert is_quarterly_month(3) is True
    assert is_quarterly_month(6) is True
    assert is_quarterly_month(9) is True
    assert is_quarterly_month(12) is True
    assert is_quarterly_month(11) is False
