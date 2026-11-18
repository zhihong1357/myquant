"""Offline tests for the macro release calendar and window flags."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from myquant.studies.macro import (
    annual_counts,
    auction_window_bar,
    build_macro_window,
    cpi_window_bar,
    fomc_window_bar,
    load_auction_calendar,
    load_cpi_calendar,
    load_fomc_statement_dates,
    load_verified_auction_dates,
    macro_window_indicator,
    wide_window_dates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CPI_CALENDAR_PATH = REPO_ROOT / "research" / "macro-windows-006" / "cpi_calendar.json"
FOMC_CALENDAR_PATH = (
    REPO_ROOT / "research" / "fomc-event-study-005" / "fomc_calendar.json"
)


class TestCpiWindowBar:
    def test_known_dates(self) -> None:
        # CPI releases at 08:30 ET, always before the 16:00 UTC bar open,
        # so the window bar opened the day before the release date.
        assert cpi_window_bar(date(2026, 11, 10)) == date(2026, 11, 9)
        assert cpi_window_bar(date(2021, 1, 13)) == date(2021, 1, 12)
        assert cpi_window_bar(date(2022, 6, 10)) == date(2022, 6, 9)

    def test_shutdown_delayed_release(self) -> None:
        # The September 2025 CPI was released 2025-10-24 (delayed from
        # 2025-10-15 by the lapse in appropriations); the offset applies
        # to the actual release date.
        assert cpi_window_bar(date(2025, 10, 24)) == date(2025, 10, 23)

    def test_dst_and_standard_time_agree(self) -> None:
        # 08:30 ET is 12:30 UTC in DST and 13:30 UTC in standard time;
        # both are before 16:00 UTC, so the offset is DST-independent.
        # June (DST) and January (standard) releases map the same way.
        assert cpi_window_bar(date(2023, 6, 13)) == date(2023, 6, 12)
        assert cpi_window_bar(date(2023, 1, 12)) == date(2023, 1, 11)

    def test_month_boundary(self) -> None:
        assert cpi_window_bar(date(2024, 5, 15)) == date(2024, 5, 14)
        assert cpi_window_bar(date(2025, 4, 10)) == date(2025, 4, 9)


class TestFomcWindowBar:
    def test_known_dates(self) -> None:
        # Statements release at about 14:00 ET, always after the 16:00
        # UTC bar open, so the window bar opened on the statement day.
        assert fomc_window_bar(date(2021, 1, 27)) == date(2021, 1, 27)
        assert fomc_window_bar(date(2026, 10, 28)) == date(2026, 10, 28)
        assert fomc_window_bar(date(2022, 6, 15)) == date(2022, 6, 15)

    def test_dst_and_standard_time_agree(self) -> None:
        # 14:00 ET is 18:00 UTC in DST and 19:00 UTC in standard time;
        # both are after 16:00 UTC, so the offset is DST-independent.
        assert fomc_window_bar(date(2023, 6, 14)) == date(2023, 6, 14)
        assert fomc_window_bar(date(2023, 2, 1)) == date(2023, 2, 1)


class TestAuctionWindowBar:
    def test_same_day(self) -> None:
        # Note/bond results follow the 1:00 PM ET close (17:00/18:00
        # UTC), always after the 16:00 UTC bar open.
        assert auction_window_bar(date(2026, 1, 12)) == date(2026, 1, 12)


class TestBuildMacroWindow:
    def test_union_and_overlap(self) -> None:
        # A CPI release the day after an FOMC statement shares the
        # statement's window bar; the union counts it once and records
        # the overlap.
        window = build_macro_window(
            [date(2026, 12, 10)], [date(2026, 12, 9)]
        )
        assert window.cpi_bars == frozenset({date(2026, 12, 9)})
        assert window.fomc_bars == frozenset({date(2026, 12, 9)})
        assert window.window_bars == frozenset({date(2026, 12, 9)})
        assert window.overlap_bars == frozenset({date(2026, 12, 9)})

    def test_no_overlap_when_events_are_apart(self) -> None:
        window = build_macro_window(
            [date(2026, 11, 10)], [date(2026, 10, 28)]
        )
        assert window.window_bars == frozenset(
            {date(2026, 11, 9), date(2026, 10, 28)}
        )
        assert window.overlap_bars == frozenset()

    def test_empty_inputs(self) -> None:
        window = build_macro_window([], [])
        assert window.window_bars == frozenset()
        assert window.overlap_bars == frozenset()

    def test_committed_calendars_union(self) -> None:
        cpi = load_cpi_calendar(
            json.loads(CPI_CALENDAR_PATH.read_text(encoding="utf-8"))
        )
        fomc = load_fomc_statement_dates(
            json.loads(FOMC_CALENDAR_PATH.read_text(encoding="utf-8"))
        )
        fomc_2021_2026 = tuple(d for d in fomc if 2021 <= d.year <= 2026)
        window = build_macro_window(
            [item.release_date for item in cpi], fomc_2021_2026
        )
        assert len(window.cpi_bars) == 71
        assert len(window.fomc_bars) == 48
        # Exactly one overlap: the 2026-12-09 bar holds both the Dec 9
        # FOMC statement and the Dec 10 CPI release (out of sample).
        assert window.overlap_bars == frozenset({date(2026, 12, 9)})
        assert len(window.window_bars) == 71 + 48 - 1
        # In-sample (daily panel 2021-01-21 .. 2026-11-16): 116 bars,
        # 69 CPI + 47 FOMC, no overlap in-sample.
        in_sample = {
            bar
            for bar in window.window_bars
            if date(2021, 1, 21) <= bar <= date(2026, 11, 16)
        }
        assert len(in_sample) == 116
        assert len(
            [bar for bar in window.cpi_bars
             if date(2021, 1, 21) <= bar <= date(2026, 11, 16)]
        ) == 69
        assert len(
            [bar for bar in window.fomc_bars
             if date(2021, 1, 21) <= bar <= date(2026, 11, 16)]
        ) == 47


class TestWideWindowDates:
    def test_event_bar_plus_minus_one(self) -> None:
        assert wide_window_dates(frozenset({date(2026, 11, 9)})) == frozenset(
            {date(2026, 11, 8), date(2026, 11, 9), date(2026, 11, 10)}
        )

    def test_overlapping_expansions_deduplicate(self) -> None:
        assert wide_window_dates(
            frozenset({date(2026, 11, 9), date(2026, 11, 10)})
        ) == frozenset(
            {
                date(2026, 11, 8),
                date(2026, 11, 9),
                date(2026, 11, 10),
                date(2026, 11, 11),
            }
        )

    def test_negative_offsets_raise(self) -> None:
        with pytest.raises(ValueError):
            wide_window_dates(frozenset({date(2026, 11, 9)}), days_before=-1)


class TestMacroWindowIndicator:
    def test_flags_bar_open_dates(self) -> None:
        bars = frozenset({date(2026, 11, 9), date(2026, 10, 28)})
        index = pd.DatetimeIndex(
            [
                datetime(2026, 10, 28, 16, 0, tzinfo=UTC),
                datetime(2026, 11, 9, 16, 0, tzinfo=UTC),
                datetime(2026, 11, 10, 16, 0, tzinfo=UTC),
            ]
        )
        flags = macro_window_indicator(index, bars)
        assert flags.tolist() == [True, True, False]
        assert flags.dtype == bool

    def test_hourly_bars_share_the_calendar_day_rule(self) -> None:
        bars = frozenset({date(2026, 11, 9)})
        index = pd.date_range(
            datetime(2026, 11, 9, 0, 0, tzinfo=UTC),
            datetime(2026, 11, 9, 23, 0, tzinfo=UTC),
            freq="h",
        )
        flags = macro_window_indicator(index, bars)
        # All 24 hourly bars on the window date are flagged, including
        # the hour containing the 08:30 ET (13:30 UTC) CPI release.
        assert flags.all()

    def test_empty_window_flags_nothing(self) -> None:
        index = pd.DatetimeIndex([datetime(2026, 11, 9, 16, 0, tzinfo=UTC)])
        assert macro_window_indicator(index, frozenset()).tolist() == [False]


class TestLoadCpiCalendar:
    def test_committed_calendar(self) -> None:
        document = json.loads(CPI_CALENDAR_PATH.read_text(encoding="utf-8"))
        releases = load_cpi_calendar(document)
        assert len(releases) == 71
        assert annual_counts([item.release_date for item in releases]) == {
            2021: 12,
            2022: 12,
            2023: 12,
            2024: 12,
            2025: 11,
            2026: 12,
        }
        assert releases[0].release_date == date(2021, 1, 13)
        assert releases[0].reference_month == "2020-12"
        assert releases[-1].release_date == date(2026, 12, 10)
        assert releases[-1].reference_month == "2026-11"
        # The October 2025 CPI was never published: no release reports
        # reference month 2025-10, and the file records it as such.
        assert "2025-10" not in {
            item.reference_month for item in releases
        }
        assert document["not_published"][0]["reference_month"] == "2025-10"
        # Known dates.
        by_ref = {item.reference_month: item.release_date for item in releases}
        assert by_ref["2026-10"] == date(2026, 11, 10)
        assert by_ref["2025-09"] == date(2025, 10, 24)
        assert by_ref["2022-05"] == date(2022, 6, 10)
        assert by_ref["2023-12"] == date(2024, 1, 11)

    def test_wrong_reference_month_raises(self) -> None:
        document = {
            "releases": [
                {"release_date": "2026-11-10", "reference_month": "2026-09"}
            ]
        }
        with pytest.raises(ValueError):
            load_cpi_calendar(document)

    def test_unsorted_releases_raise(self) -> None:
        document = {
            "releases": [
                {"release_date": "2026-11-10", "reference_month": "2026-10"},
                {"release_date": "2026-10-14", "reference_month": "2026-09"},
            ]
        }
        with pytest.raises(ValueError):
            load_cpi_calendar(document)

    def test_duplicate_release_dates_raise(self) -> None:
        document = {
            "releases": [
                {"release_date": "2026-11-10", "reference_month": "2026-10"},
                {"release_date": "2026-11-10", "reference_month": "2026-10"},
            ]
        }
        with pytest.raises(ValueError):
            load_cpi_calendar(document)

    def test_missing_releases_raise(self) -> None:
        with pytest.raises(ValueError):
            load_cpi_calendar({})


class TestLoadFomcStatementDates:
    def test_committed_calendar_2021_2026(self) -> None:
        document = json.loads(FOMC_CALENDAR_PATH.read_text(encoding="utf-8"))
        statements = load_fomc_statement_dates(document)
        assert len(statements) == 199
        in_range = tuple(d for d in statements if 2021 <= d.year <= 2026)
        assert len(in_range) == 48
        assert annual_counts(in_range) == {year: 8 for year in range(2021, 2027)}
        assert in_range[0] == date(2021, 1, 27)
        assert in_range[-1] == date(2026, 12, 9)

    def test_missing_meetings_raise(self) -> None:
        with pytest.raises(ValueError):
            load_fomc_statement_dates({})


class TestLoadAuctionCalendar:
    def test_valid_document(self) -> None:
        document = {"coupon_auction_dates": ["2026-01-12", "2026-01-13"]}
        assert load_auction_calendar(document) == (
            date(2026, 1, 12),
            date(2026, 1, 13),
        )

    def test_unsorted_dates_raise(self) -> None:
        with pytest.raises(ValueError):
            load_auction_calendar(
                {"coupon_auction_dates": ["2026-01-13", "2026-01-12"]}
            )

    def test_missing_dates_raise(self) -> None:
        with pytest.raises(ValueError):
            load_auction_calendar({})


class TestLoadVerifiedAuctionDates:
    def test_verified_true_returns_dates(self) -> None:
        document = {
            "verified": True,
            "coupon_auction_dates": ["2026-01-12", "2026-01-13"],
        }
        assert load_verified_auction_dates(document) == (
            date(2026, 1, 12),
            date(2026, 1, 13),
        )

    def test_verified_false_returns_none(self) -> None:
        document = {
            "verified": False,
            "coupon_auction_dates": ["2026-01-12", "2026-01-13"],
        }
        assert load_verified_auction_dates(document) is None

    def test_verified_missing_returns_none(self) -> None:
        document = {"coupon_auction_dates": ["2026-01-12", "2026-01-13"]}
        assert load_verified_auction_dates(document) is None

    def test_verified_true_but_malformed_raises(self) -> None:
        document = {
            "verified": True,
            "coupon_auction_dates": ["2026-01-13", "2026-01-12"],
        }
        with pytest.raises(ValueError):
            load_verified_auction_dates(document)


def test_annual_counts() -> None:
    assert annual_counts(
        [date(2021, 1, 13), date(2021, 2, 10), date(2022, 1, 12)]
    ) == {2021: 2, 2022: 1}
    assert annual_counts([]) == {}
