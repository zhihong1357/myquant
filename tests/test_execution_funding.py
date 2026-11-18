"""Tests for the funding-rate series and series-based funding (offline)."""

from datetime import UTC, datetime

import pytest

from myquant.adapters.okx_funding import OKXFundingRate
from myquant.execution.costs import compute_funding, funding_settlements_between
from myquant.execution.funding import (
    FundingRateRow,
    FundingRateSeries,
    compute_funding_from_series,
)
from myquant.execution.orders import Fill

INST = "BTC-USDT-SWAP"
T0 = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)
T8 = datetime(2026, 11, 18, 8, 0, tzinfo=UTC)
T16 = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
T24 = datetime(2026, 11, 19, 0, 0, tzinfo=UTC)


def _row(when, rate):
    return FundingRateRow(settlement_time=when, funding_rate=rate)


def _series():
    return FundingRateSeries(
        instrument=INST,
        rows=(_row(T0, 0.0001), _row(T8, -0.0002), _row(T16, 0.0003)),
    )


def _fill(order_id, side, when, price, quantity):
    return Fill(
        order_id=order_id,
        side=side,
        fill_time=when,
        price=price,
        quantity=quantity,
        is_maker=False,
        fee=0.0,
    )


def test_row_rejects_off_grid_settlement():
    with pytest.raises(ValueError, match="00:00 / 08:00 / 16:00"):
        _row(datetime(2026, 11, 18, 12, 0, tzinfo=UTC), 0.0001)
    with pytest.raises(ValueError, match="00:00 / 08:00 / 16:00"):
        _row(datetime(2026, 11, 18, 8, 0, 1, tzinfo=UTC), 0.0001)


def test_series_rejects_unordered_and_duplicate_rows():
    with pytest.raises(ValueError, match="strictly increasing"):
        FundingRateSeries(
            instrument=INST, rows=(_row(T8, 0.0), _row(T0, 0.0))
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        FundingRateSeries(
            instrument=INST, rows=(_row(T0, 0.0), _row(T0, 0.0))
        )


def test_series_from_okx_rows_sorts_and_looks_up():
    okx_rows = (
        OKXFundingRate(
            instrument=INST,
            settlement_time=T16,
            funding_rate=0.0003,
            realized_rate=0.0003,
            method="current_period",
            formula_type="withRate",
        ),
        OKXFundingRate(
            instrument=INST,
            settlement_time=T0,
            funding_rate=0.0001,
            realized_rate=0.0001,
            method="current_period",
            formula_type="withRate",
        ),
    )
    series = FundingRateSeries.from_okx_rows(INST, okx_rows)
    assert series.rows[0].settlement_time == T0
    assert series.rows[-1].settlement_time == T16
    assert series.rate_at(T0) == pytest.approx(0.0001)
    assert series.rate_at(T8) is None  # no row: unknown, not zero
    assert series.rate_at(T24) is None


def test_coverage_counts_missing_grid_slots():
    series = FundingRateSeries(
        instrument=INST,
        rows=(_row(T0, 0.0001), _row(T16, 0.0003), _row(T24, 0.0002)),
    )
    coverage = series.coverage()
    assert coverage.first_settlement == T0
    assert coverage.last_settlement == T24
    assert coverage.row_count == 3
    assert coverage.expected_settlements == 4
    assert coverage.missing_settlements == (T8,)


def test_coverage_complete_series_has_no_missing():
    coverage = _series().coverage()
    assert coverage.expected_settlements == 3
    assert coverage.missing_settlements == ()


def test_funding_settlements_between_grid():
    settlements = funding_settlements_between(
        datetime(2026, 11, 18, 1, 0, tzinfo=UTC),
        datetime(2026, 11, 19, 0, 0, tzinfo=UTC),
    )
    assert settlements == (T8, T16, T24)
    # A settlement exactly at start is not crossed.
    assert funding_settlements_between(T8, T16) == (T16,)
    assert funding_settlements_between(T8, T8) == ()


def test_compute_funding_from_series_sign_and_amounts():
    fills = (
        _fill("o1", "buy", datetime(2026, 11, 17, 12, 0, tzinfo=UTC), 90_000.0, 10.0),
    )
    price_at = lambda when: 100_000.0  # noqa: E731
    result = compute_funding_from_series(
        fills,
        _series(),
        start=datetime(2026, 11, 17, 16, 0, tzinfo=UTC),
        end=T16,
        price_at=price_at,
        contract_value=0.01,
    )
    # Position 10 contracts long across T0/T8/T16, priced at 100,000.
    # Notional per settlement: 10 x 100,000 x 0.01 = 10,000 USDT.
    # T0: 10,000 x 0.0001 = 1.00 (long pays); T8: 10,000 x -0.0002 = -2.00
    # (long receives); T16: 10,000 x 0.0003 = 3.00.
    assert [s.amount for s in result.settlements] == pytest.approx([1.0, -2.0, 3.0])
    assert result.total_amount == pytest.approx(2.0)
    assert result.skipped_no_rate == ()
    assert result.skipped_no_price == ()


def test_compute_funding_from_series_short_position_flips_sign():
    fills = (
        _fill("o1", "sell", datetime(2026, 11, 17, 12, 0, tzinfo=UTC), 90_000.0, 5.0),
    )
    result = compute_funding_from_series(
        fills,
        _series(),
        start=datetime(2026, 11, 17, 16, 0, tzinfo=UTC),
        end=T0,
        price_at=lambda when: 100_000.0,
        contract_value=0.01,
    )
    # Short 5 contracts: -5 x 100,000 x 0.01 x 0.0001 = -0.50 (receives).
    assert [s.amount for s in result.settlements] == pytest.approx([-0.5])
    assert result.total_amount == pytest.approx(-0.5)


def test_compute_funding_from_series_skips_unknown_rate_and_price():
    series = FundingRateSeries(
        instrument=INST, rows=(_row(T0, 0.0001), _row(T16, 0.0003))
    )
    fills = (
        _fill("o1", "buy", datetime(2026, 11, 17, 12, 0, tzinfo=UTC), 90_000.0, 10.0),
    )
    result = compute_funding_from_series(
        fills,
        series,
        start=datetime(2026, 11, 17, 16, 0, tzinfo=UTC),
        end=T16,
        price_at=lambda when: 100_000.0,
        contract_value=0.01,
    )
    # T8 has no rate in the series: skipped and reported, not zeroed.
    assert [s.settlement_time for s in result.settlements] == [T0, T16]
    assert result.skipped_no_rate == (T8,)
    assert result.skipped_no_price == ()

    result_no_price = compute_funding_from_series(
        fills,
        _series(),
        start=datetime(2026, 11, 17, 16, 0, tzinfo=UTC),
        end=T0,
        price_at=lambda when: None,
        contract_value=0.01,
    )
    assert result_no_price.settlements == ()
    assert result_no_price.skipped_no_price == (T0,)


def test_compute_funding_from_series_uses_position_before_settlement():
    fills = (
        _fill("o1", "buy", datetime(2026, 11, 18, 2, 0, tzinfo=UTC), 90_000.0, 10.0),
        _fill("o2", "sell", datetime(2026, 11, 18, 10, 0, tzinfo=UTC), 91_000.0, 4.0),
    )
    result = compute_funding_from_series(
        fills,
        _series(),
        start=datetime(2026, 11, 17, 16, 0, tzinfo=UTC),
        end=T16,
        price_at=lambda when: 100_000.0,
        contract_value=0.01,
    )
    # T0: flat (first fill is after T0) -> skipped silently (no position).
    # T8: 10 long -> 10,000 x -0.0002 = -2.00. T16: 6 long -> 6,000 x 0.0003.
    assert [s.settlement_time for s in result.settlements] == [T8, T16]
    assert [s.position_quantity for s in result.settlements] == [10.0, 6.0]
    assert [s.amount for s in result.settlements] == pytest.approx([-2.0, 1.8])


def test_single_rate_fallback_unchanged():
    """The original compute_funding (rate as input) still works."""
    fills = (
        _fill("o1", "buy", datetime(2026, 11, 17, 12, 0, tzinfo=UTC), 90_000.0, 10.0),
    )
    settlements = funding_settlements_between(
        datetime(2026, 11, 17, 16, 0, tzinfo=UTC), T8
    )
    result = compute_funding(
        fills,
        settlements=settlements,
        price_at=lambda when: 100_000.0,
        funding_rate=0.0001,
        contract_value=0.01,
    )
    assert [s.amount for s in result] == pytest.approx([1.0, 1.0])
