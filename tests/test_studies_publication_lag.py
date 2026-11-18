"""Offline tests for publication-lag alignment and CPI step functions."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from myquant.contracts import Observation
from myquant.studies.macro import CPIRelease, load_cpi_calendar
from myquant.studies.publication_lag import (
    build_cpi_naive_function,
    build_cpi_step_function,
    cpi_mom_log_changes,
    cpi_release_day_flags,
    cpi_releases_without_mom,
    lagged_changes_on_index,
    lagged_panel_index,
    reference_window_for_lagged,
    shift_changes_by_positions,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CPI_CALENDAR_PATH = REPO_ROOT / "research" / "macro-windows-006" / "cpi_calendar.json"

CLOSE_UTC = datetime(2021, 1, 4, 21, 0, tzinfo=UTC)


def _observation(
    instrument_id: str,
    event_time: datetime,
    value: float,
) -> Observation:
    return Observation(
        instrument_id=instrument_id,
        venue="fred",
        event_time=event_time,
        available_at=event_time,
        ingested_at=datetime(2026, 11, 18, 6, 0, tzinfo=UTC),
        field="close",
        value=value,
        unit="points",
        source_id="fred",
        source_version=1,
    )


def _daily_observations(
    instrument_id: str,
    closes: list[float],
    *,
    start: datetime = CLOSE_UTC,
) -> list[Observation]:
    """One close per calendar day (a trading-day stand-in for tests)."""
    return [
        _observation(
            instrument_id,
            start + pd.Timedelta(days=offset),
            value,
        )
        for offset, value in enumerate(closes)
    ]


def _mom_series(months: list[str], values: list[float]) -> pd.Series:
    index = pd.DatetimeIndex(
        [datetime(int(m[:4]), int(m[5:7]), 1, 21, 0, tzinfo=UTC) for m in months]
    )
    return pd.Series(values, index=index, dtype=float)


class TestShiftChangesByPositions:
    def test_shift_one_moves_each_change_to_the_next_date(self) -> None:
        index = pd.date_range("2021-01-04", periods=4, freq="D", tz="UTC")
        changes = pd.Series([0.01, -0.02, 0.03, 0.0], index=index)
        shifted = shift_changes_by_positions(changes, 1)
        assert np.isnan(shifted.iloc[0])
        assert shifted.iloc[1] == pytest.approx(0.01)
        assert shifted.iloc[2] == pytest.approx(-0.02)
        assert shifted.iloc[3] == pytest.approx(0.03)

    def test_shift_zero_is_identity(self) -> None:
        index = pd.date_range("2021-01-04", periods=3, freq="D", tz="UTC")
        changes = pd.Series([0.01, -0.02, 0.03], index=index)
        pd.testing.assert_series_equal(
            shift_changes_by_positions(changes, 0), changes
        )

    def test_negative_steps_raise(self) -> None:
        index = pd.date_range("2021-01-04", periods=3, freq="D", tz="UTC")
        changes = pd.Series([0.01, -0.02, 0.03], index=index)
        with pytest.raises(ValueError, match="non-negative"):
            shift_changes_by_positions(changes, -1)

    def test_unsorted_index_raises(self) -> None:
        index = pd.DatetimeIndex(
            [
                datetime(2021, 1, 5, 21, 0, tzinfo=UTC),
                datetime(2021, 1, 4, 21, 0, tzinfo=UTC),
            ]
        )
        changes = pd.Series([0.01, -0.02], index=index)
        with pytest.raises(ValueError, match="sorted"):
            shift_changes_by_positions(changes, 1)


class TestLaggedPanelIndex:
    def test_drops_leading_rows(self) -> None:
        index = pd.date_range("2021-01-04", periods=5, freq="D", tz="UTC")
        assert list(lagged_panel_index(index, 1)) == list(index[1:])
        assert list(lagged_panel_index(index, 0)) == list(index)

    def test_lag_not_smaller_than_index_raises(self) -> None:
        index = pd.date_range("2021-01-04", periods=2, freq="D", tz="UTC")
        with pytest.raises(ValueError, match="smaller than the index"):
            lagged_panel_index(index, 2)


class TestReferenceWindowForLagged:
    def test_main_window_lag_one_covers_minus_one_to_zero(self) -> None:
        # The lagged [0,+1] availability window covers reference-date
        # changes [-1,0]: the statement-day change plus the day-before
        # change, not the day-after change.
        assert reference_window_for_lagged(0, 1, 1) == (-1, 0)

    def test_no_lag_is_identity(self) -> None:
        assert reference_window_for_lagged(0, 1, 0) == (0, 1)
        assert reference_window_for_lagged(1, 1, 0) == (-1, 1)

    def test_wide_window_lag_one(self) -> None:
        assert reference_window_for_lagged(1, 1, 1) == (-2, 0)

    def test_negative_steps_raise(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            reference_window_for_lagged(0, 1, -1)


class TestLaggedChangesOnIndex:
    def test_log_lag_one_equals_previous_day_change(self) -> None:
        # Closes 100, 101, 102, 104, 103: log changes on own dates are
        # log(101/100), log(102/101), log(104/102), log(103/104).
        # Lagged by one, the change at day t is the original change at
        # day t-1.
        observations = _daily_observations("index:vix", [100, 101, 102, 104, 103])
        full_index = pd.date_range(
            "2021-01-05 21:00", periods=4, freq="D", tz="UTC"
        )
        index = lagged_panel_index(full_index, 1)
        frame = lagged_changes_on_index(
            observations,
            instruments=("index:vix",),
            index=index,
            lag_steps=1,
            transform="log",
        )
        expected = [
            np.log(101 / 100),
            np.log(102 / 101),
            np.log(104 / 102),
        ]
        assert frame["index:vix"].to_list() == pytest.approx(expected)

    def test_level_lag_one_scales_to_basis_points(self) -> None:
        observations = _daily_observations(
            "rates:us-10y-yield", [4.00, 4.10, 4.05, 4.20]
        )
        full_index = pd.date_range(
            "2021-01-05 21:00", periods=3, freq="D", tz="UTC"
        )
        index = lagged_panel_index(full_index, 1)
        frame = lagged_changes_on_index(
            observations,
            instruments=("rates:us-10y-yield",),
            index=index,
            lag_steps=1,
            transform="level",
        )
        # Level changes (percent) are 0.10, -0.05, 0.15; lagged by one,
        # the frame holds 10bp and -5bp.
        assert frame["rates:us-10y-yield"].to_list() == pytest.approx([10.0, -5.0])

    def test_full_index_raises_on_the_first_row(self) -> None:
        # The first panel row has no lagged change (nothing shifted into
        # it); passing the untruncated index must fail loudly.
        observations = _daily_observations("index:vix", [100, 101, 102, 104])
        full_index = pd.date_range(
            "2021-01-05 21:00", periods=3, freq="D", tz="UTC"
        )
        with pytest.raises(ValueError, match="unavailable at some index"):
            lagged_changes_on_index(
                observations,
                instruments=("index:vix",),
                index=full_index,
                lag_steps=1,
                transform="log",
            )

    def test_partial_holiday_uses_own_dates(self) -> None:
        # The series trades on a day the panel does not (a partial
        # holiday for the other legs): own dates Mon, Tue (partial),
        # Wed, Thu with closes 100, 101, 102, 104. The panel index is
        # Mon, Wed, Thu. The lagged change at Wed is the own-dates
        # change at Tue (log(101/100)) — the value available at Wed's
        # close is Tuesday's, not Monday's.
        observations = _daily_observations("index:vix", [100, 101, 102, 104])
        panel_index = pd.DatetimeIndex(
            [
                datetime(2021, 1, 4, 21, 0, tzinfo=UTC),  # Mon
                datetime(2021, 1, 6, 21, 0, tzinfo=UTC),  # Wed
                datetime(2021, 1, 7, 21, 0, tzinfo=UTC),  # Thu
            ]
        )
        # The return index starts at the first change (Tue); the panel
        # return rows are Wed and Thu, so the truncated index is [Thu].
        # Use the Wed/Thu return rows and drop the leading one.
        return_index = panel_index[1:]
        index = lagged_panel_index(return_index, 1)
        frame = lagged_changes_on_index(
            observations,
            instruments=("index:vix",),
            index=index,
            lag_steps=1,
            transform="log",
        )
        assert frame.index[0] == datetime(2021, 1, 7, 21, 0, tzinfo=UTC)
        # Lagged change at Thu = own-dates change at Wed = log(102/101).
        assert frame["index:vix"].iloc[0] == pytest.approx(np.log(102 / 101))

    def test_nonpositive_levels_raise_for_log(self) -> None:
        observations = _daily_observations("index:vix", [100, 0, 102, 104])
        full_index = pd.date_range(
            "2021-01-05 21:00", periods=3, freq="D", tz="UTC"
        )
        with pytest.raises(ValueError, match="positive levels"):
            lagged_changes_on_index(
                observations,
                instruments=("index:vix",),
                index=lagged_panel_index(full_index, 1),
                lag_steps=1,
                transform="log",
            )

    def test_unknown_transform_raises(self) -> None:
        observations = _daily_observations("index:vix", [100, 101, 102])
        with pytest.raises(ValueError, match="transform"):
            lagged_changes_on_index(
                observations,
                instruments=("index:vix",),
                index=pd.date_range("2021-01-06", periods=1, freq="D", tz="UTC"),
                lag_steps=1,
                transform="sqrt",
            )


class TestCpiMomLogChanges:
    def test_consecutive_months(self) -> None:
        levels = _mom_series(
            ["2020-11", "2020-12", "2021-01"],
            [260.0, 261.0, 262.0],
        )
        changes = cpi_mom_log_changes(levels)
        assert np.isnan(changes.iloc[0])
        assert changes.iloc[1] == pytest.approx(np.log(261 / 260))
        assert changes.iloc[2] == pytest.approx(np.log(262 / 261))

    def test_gap_leaves_two_months_undefined(self) -> None:
        # A missing month (the October 2025 CPI was never published)
        # leaves the MoM undefined for that month and for the month
        # after it (no comparison base); other months are unaffected.
        levels = _mom_series(
            ["2020-11", "2020-12", "2021-02", "2021-03"],
            [260.0, 261.0, 263.0, 264.0],
        )
        changes = cpi_mom_log_changes(levels)
        assert changes.index.strftime("%Y-%m").to_list() == [
            "2020-11",
            "2020-12",
            "2021-01",
            "2021-02",
            "2021-03",
        ]
        assert np.isnan(changes.iloc[0])  # first month, no base
        assert changes.iloc[1] == pytest.approx(np.log(261 / 260))
        assert np.isnan(changes.iloc[2])  # 2021-01 level missing
        assert np.isnan(changes.iloc[3])  # 2021-02 has no base month
        assert changes.iloc[4] == pytest.approx(np.log(264 / 263))

    def test_nonpositive_raises(self) -> None:
        levels = _mom_series(["2020-11", "2020-12"], [260.0, 0.0])
        with pytest.raises(ValueError, match="positive"):
            cpi_mom_log_changes(levels)

    def test_duplicate_month_raises(self) -> None:
        index = pd.DatetimeIndex(
            [
                datetime(2020, 12, 1, 21, 0, tzinfo=UTC),
                datetime(2020, 12, 15, 21, 0, tzinfo=UTC),
            ]
        )
        levels = pd.Series([260.0, 261.0], index=index)
        with pytest.raises(ValueError, match="more than one observation"):
            cpi_mom_log_changes(levels)


class TestCpiStepFunction:
    def _releases(self) -> tuple[CPIRelease, ...]:
        return (
            CPIRelease(release_date=date(2021, 1, 13), reference_month="2020-12"),
            CPIRelease(release_date=date(2021, 2, 10), reference_month="2021-01"),
            CPIRelease(release_date=date(2021, 3, 10), reference_month="2021-02"),
        )

    def _mom(self) -> pd.Series:
        changes = _mom_series(
            ["2020-11", "2020-12", "2021-01", "2021-02"],
            [260.0, 261.0, 262.0, 263.0],
        )
        return cpi_mom_log_changes(changes)

    def test_step_jumps_on_release_dates(self) -> None:
        close_dates = pd.DatetimeIndex(
            [
                datetime(2021, 1, 12, 21, 0, tzinfo=UTC),
                datetime(2021, 1, 13, 21, 0, tzinfo=UTC),
                datetime(2021, 2, 9, 21, 0, tzinfo=UTC),
                datetime(2021, 2, 10, 21, 0, tzinfo=UTC),
                datetime(2021, 3, 9, 21, 0, tzinfo=UTC),
                datetime(2021, 3, 10, 21, 0, tzinfo=UTC),
            ]
        )
        step = build_cpi_step_function(self._releases(), self._mom(), close_dates)
        # Before the first release: no CPI value is available yet.
        assert np.isnan(step.iloc[0])
        # Release-day rows carry the fresh print (08:30 ET release,
        # 16:00 ET close).
        assert step.iloc[1] == pytest.approx(np.log(261 / 260))
        assert step.iloc[2] == pytest.approx(np.log(261 / 260))
        assert step.iloc[3] == pytest.approx(np.log(262 / 261))
        assert step.iloc[4] == pytest.approx(np.log(262 / 261))
        assert step.iloc[5] == pytest.approx(np.log(263 / 262))

    def test_release_without_mom_is_skipped_and_reported(self) -> None:
        # The February 2021 release has no MoM (its reference month is
        # missing from the MoM series): the step keeps holding the
        # December 2020 value, and cpi_releases_without_mom reports
        # the skipped release for the caller to assert on.
        mom = cpi_mom_log_changes(
            _mom_series(["2020-11", "2020-12"], [260.0, 261.0])
        )
        close_dates = pd.DatetimeIndex(
            [
                datetime(2021, 2, 9, 21, 0, tzinfo=UTC),
                datetime(2021, 2, 10, 21, 0, tzinfo=UTC),
                datetime(2021, 3, 10, 21, 0, tzinfo=UTC),
            ]
        )
        step = build_cpi_step_function(self._releases(), mom, close_dates)
        assert step.iloc[0] == pytest.approx(np.log(261 / 260))
        assert step.iloc[1] == pytest.approx(np.log(261 / 260))
        assert step.iloc[2] == pytest.approx(np.log(261 / 260))
        skipped = cpi_releases_without_mom(self._releases(), mom)
        assert [item.reference_month for item in skipped] == ["2021-01", "2021-02"]

    def test_real_calendar_shutdown_hold(self) -> None:
        # The October 2025 CPI was never published: the step function
        # holds the September 2025 value (released 2025-10-24, delayed
        # by the shutdown) until the December 2025 release (2026-01-13)
        # — the November 2025 release (2025-12-18) carries no usable
        # MoM because its base month is missing, so it does not move
        # the step. The hold runs about eleven weeks.
        document = json.loads(CPI_CALENDAR_PATH.read_text(encoding="utf-8"))
        releases = load_cpi_calendar(document)
        assert len(releases) == 71
        months = [
            f"{year:04d}-{month:02d}"
            for year in (2020, 2021, 2022, 2023, 2024, 2025, 2026)
            for month in range(1, 13)
        ]
        months = ["2020-11", "2020-12"] + [m for m in months if m >= "2021-01"]
        # The October 2025 level is missing (never published).
        months = [m for m in months if m != "2025-10"]
        levels = _mom_series(months, [260.0 + i for i in range(len(months))])
        mom = cpi_mom_log_changes(levels)
        assert np.isnan(mom.loc["2025-10-01"])
        assert np.isnan(mom.loc["2025-11-01"])
        skipped = cpi_releases_without_mom(releases, mom)
        assert [item.reference_month for item in skipped] == ["2025-11"]
        close_dates = pd.DatetimeIndex(
            [
                datetime(2025, 10, 23, 21, 0, tzinfo=UTC),
                datetime(2025, 10, 24, 21, 0, tzinfo=UTC),
                datetime(2025, 12, 17, 21, 0, tzinfo=UTC),
                datetime(2025, 12, 18, 21, 0, tzinfo=UTC),
                datetime(2026, 1, 13, 21, 0, tzinfo=UTC),
            ]
        )
        step = build_cpi_step_function(releases, mom, close_dates)
        aug_2025_mom = np.log(
            (260.0 + months.index("2025-08")) / (260.0 + months.index("2025-07"))
        )
        sep_2025_mom = np.log(
            (260.0 + months.index("2025-09")) / (260.0 + months.index("2025-08"))
        )
        dec_2025_mom = np.log(
            (260.0 + months.index("2025-12")) / (260.0 + months.index("2025-11"))
        )
        assert step.iloc[0] == pytest.approx(aug_2025_mom)
        # The delayed September release lands 2025-10-24.
        assert step.iloc[1] == pytest.approx(sep_2025_mom)
        # No October release exists, so the September value still holds
        # on 2025-12-17 — seven weeks after its release.
        assert step.iloc[2] == pytest.approx(sep_2025_mom)
        # The November 2025 release (2025-12-18) carries no usable MoM
        # (its base month was never published), so the step does not move.
        assert step.iloc[3] == pytest.approx(sep_2025_mom)
        # The December 2025 release (2026-01-13) steps to the December MoM.
        assert step.iloc[4] == pytest.approx(dec_2025_mom)


class TestCpiNaiveFunction:
    def test_naive_uses_the_containing_month(self) -> None:
        mom = cpi_mom_log_changes(
            _mom_series(
                ["2020-11", "2020-12", "2021-01", "2021-02"],
                [260.0, 261.0, 262.0, 263.0],
            )
        )
        close_dates = pd.DatetimeIndex(
            [
                datetime(2021, 1, 5, 21, 0, tzinfo=UTC),
                datetime(2021, 1, 13, 21, 0, tzinfo=UTC),
                datetime(2021, 2, 1, 21, 0, tzinfo=UTC),
            ]
        )
        naive = build_cpi_naive_function(mom, close_dates)
        # January closes carry the January MoM (released 2021-02-10):
        # lookahead. February closes carry the February MoM.
        assert naive.iloc[0] == pytest.approx(np.log(262 / 261))
        assert naive.iloc[1] == pytest.approx(np.log(262 / 261))
        assert naive.iloc[2] == pytest.approx(np.log(263 / 262))

    def test_month_without_mom_is_nan(self) -> None:
        mom = cpi_mom_log_changes(
            _mom_series(["2020-11", "2020-12"], [260.0, 261.0])
        )
        close_dates = pd.DatetimeIndex(
            [datetime(2021, 1, 5, 21, 0, tzinfo=UTC)]
        )
        naive = build_cpi_naive_function(mom, close_dates)
        assert np.isnan(naive.iloc[0])


class TestCpiReleaseDayFlags:
    def test_flags_release_dates_only(self) -> None:
        close_dates = pd.DatetimeIndex(
            [
                datetime(2021, 1, 12, 21, 0, tzinfo=UTC),
                datetime(2021, 1, 13, 21, 0, tzinfo=UTC),
                datetime(2021, 1, 14, 21, 0, tzinfo=UTC),
            ]
        )
        flags = cpi_release_day_flags(close_dates, [date(2021, 1, 13)])
        assert flags.to_list() == [False, True, False]
