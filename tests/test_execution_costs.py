"""Tests for the cost model. All offline, no network access."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from myquant.execution.costs import (
    bps_cost,
    compute_funding,
    funding_settlements_between,
    impact_bps,
    notional_value,
)
from myquant.execution.orders import Fill

T0 = datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)


def test_notional_value_uses_contract_value() -> None:
    # 1 contract of BTC-USDT-SWAP is 0.01 BTC: at 65,000 USDT/BTC the
    # notional is 650 USDT.
    assert notional_value(65000.0, 1.0, 0.01) == pytest.approx(650.0)
    assert notional_value(65000.0, 2.5, 0.01) == pytest.approx(1625.0)


def test_bps_cost() -> None:
    # 1 bp on a 650 USDT notional is 0.065 USDT.
    assert bps_cost(65000.0, 1.0, 1.0, 0.01) == pytest.approx(0.065)
    assert bps_cost(65000.0, 1.0, 0.0, 0.01) == pytest.approx(0.0)


def test_impact_bps_scales_with_size_over_depth() -> None:
    # Half the depth: half the coefficient.
    assert impact_bps(5.0, 10.0, 5.0) == pytest.approx(2.5)
    # Full depth or more: the coefficient, capped.
    assert impact_bps(10.0, 10.0, 5.0) == pytest.approx(5.0)
    assert impact_bps(100.0, 10.0, 5.0) == pytest.approx(5.0)


def test_impact_bps_unknown_without_a_book() -> None:
    assert impact_bps(1.0, None, 5.0) is None


def test_impact_bps_full_coefficient_on_empty_book() -> None:
    assert impact_bps(1.0, 0.0, 5.0) == pytest.approx(5.0)


def test_funding_settlements_on_the_8h_grid() -> None:
    start = datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC)
    assert funding_settlements_between(start, end) == (
        datetime(2026, 11, 18, 8, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 18, 16, 0, 0, tzinfo=UTC),
    )


def test_funding_settlement_at_start_is_not_crossed() -> None:
    # A position opened exactly at 08:00 does not pay the 08:00 funding.
    start = datetime(2026, 11, 18, 8, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 18, 16, 0, 0, tzinfo=UTC)
    assert funding_settlements_between(start, end) == (
        datetime(2026, 11, 18, 16, 0, 0, tzinfo=UTC),
    )


def test_funding_settlements_cross_midnight() -> None:
    start = datetime(2026, 11, 18, 23, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 19, 1, 0, 0, tzinfo=UTC)
    assert funding_settlements_between(start, end) == (
        datetime(2026, 11, 19, 0, 0, 0, tzinfo=UTC),
    )


def test_funding_settlements_empty_when_end_before_start() -> None:
    assert funding_settlements_between(T0, T0) == ()


def _fill(
    side: str, hour: int, quantity: float = 1.0, price: float = 65000.0
) -> Fill:
    return Fill(
        order_id="o1",
        side=side,  # type: ignore[arg-type]
        fill_time=datetime(2026, 11, 18, hour, 0, 0, tzinfo=UTC),
        price=price,
        quantity=quantity,
        is_maker=True,
        fee=0.0,
    )


def test_compute_funding_long_pays_when_rate_positive() -> None:
    fills = (_fill("buy", 7),)
    settlements = (
        datetime(2026, 11, 18, 8, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 18, 16, 0, 0, tzinfo=UTC),
    )
    result = compute_funding(
        fills,
        settlements=settlements,
        price_at=lambda _: 65000.0,
        funding_rate=0.0001,
        contract_value=0.01,
    )
    # 1 contract x 65,000 x 0.01 x 0.0001 = 0.065 USDT per settlement.
    assert [round(s.amount, 9) for s in result] == [0.065, 0.065]
    assert result[0].position_quantity == pytest.approx(1.0)


def test_compute_funding_short_receives_when_rate_positive() -> None:
    fills = (_fill("sell", 7, quantity=2.0),)
    settlements = (datetime(2026, 11, 18, 8, 0, 0, tzinfo=UTC),)
    result = compute_funding(
        fills,
        settlements=settlements,
        price_at=lambda _: 65000.0,
        funding_rate=0.0001,
        contract_value=0.01,
    )
    assert [round(s.amount, 9) for s in result] == [-0.13]
    assert result[0].position_quantity == pytest.approx(-2.0)


def test_compute_funding_skips_settlements_before_any_fill() -> None:
    fills = (_fill("buy", 9),)
    settlements = (
        datetime(2026, 11, 18, 8, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 18, 16, 0, 0, tzinfo=UTC),
    )
    result = compute_funding(
        fills,
        settlements=settlements,
        price_at=lambda _: 65000.0,
        funding_rate=0.0001,
        contract_value=0.01,
    )
    # No position at 08:00 (the fill is at 09:00); only 16:00 pays.
    assert len(result) == 1
    assert result[0].settlement_time.hour == 16


def test_compute_funding_skips_settlements_without_a_price() -> None:
    fills = (_fill("buy", 7),)
    settlements = (datetime(2026, 11, 18, 8, 0, 0, tzinfo=UTC),)
    result = compute_funding(
        fills,
        settlements=settlements,
        price_at=lambda _: None,
        funding_rate=0.0001,
        contract_value=0.01,
    )
    assert result == ()
