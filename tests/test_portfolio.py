"""Tests for the paper portfolio and reconciliation (offline).

Every expected value below is hand-computed from the fills; the
reconciliation checks are the point, so the arithmetic is spelled
out rather than trusted to the module.
"""

from datetime import UTC, datetime, timedelta

import pytest

from myquant.execution.costs import FundingSettlement
from myquant.execution.orders import Fill
from myquant.portfolio.portfolio import PaperPortfolio

BTC = "crypto:btc-usdt-perp"
ETH = "crypto:eth-usdt-perp"
T0 = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
CV_BTC = 0.01
CV_ETH = 0.1


def _fill(
    side: str,
    price: float,
    quantity: float,
    *,
    at: datetime,
    is_maker: bool = False,
    fee: float = 0.0,
) -> Fill:
    return Fill(
        order_id="o1",
        side=side,
        fill_time=at,
        price=price,
        quantity=quantity,
        is_maker=is_maker,
        fee=fee,
    )


def _portfolio() -> PaperPortfolio:
    return PaperPortfolio(
        100_000.0,
        {BTC: CV_BTC, ETH: CV_ETH},
        start_time=T0,
    )


def test_initial_state_and_snapshot():
    portfolio = _portfolio()
    assert portfolio.equity == 100_000.0
    assert portfolio.cash == 100_000.0
    assert portfolio.realized_pnl == 0.0
    assert portfolio.unrealized_pnl == 0.0
    assert portfolio.reconcile().passed
    assert len(portfolio.snapshots) == 1
    assert portfolio.snapshots[0].equity == 100_000.0


def test_buy_and_mark_unrealized():
    portfolio = _portfolio()
    # Buy 100 BTC contracts at 90,000, taker fee 45 USDT
    # (100 x 90,000 x 0.01 x 0.0005).
    portfolio.apply_fill(
        BTC, _fill("buy", 90_000.0, 100.0, at=T0, fee=45.0)
    )
    assert portfolio.cash == pytest.approx(100_000.0 - 45.0)
    assert portfolio.taker_fees == pytest.approx(45.0)
    assert portfolio.maker_fees == 0.0
    # Mark at 91,000: unrealized = 100 x 1,000 x 0.01 = 1,000.
    portfolio.mark({BTC: 91_000.0}, T0 + timedelta(hours=1))
    assert portfolio.unrealized_pnl == pytest.approx(1_000.0)
    assert portfolio.equity == pytest.approx(100_000.0 - 45.0 + 1_000.0)
    assert portfolio.reconcile().passed


def test_partial_close_realizes_and_keeps_average_cost():
    portfolio = _portfolio()
    portfolio.apply_fill(BTC, _fill("buy", 90_000.0, 100.0, at=T0, fee=45.0))
    # Sell 40 at 92,000: realized = 40 x 2,000 x 0.01 = 800.
    # Taker fee on the sell: 40 x 92,000 x 0.01 x 0.0005 = 18.40.
    portfolio.apply_fill(
        BTC, _fill("sell", 92_000.0, 40.0, at=T0 + timedelta(hours=1), fee=18.40)
    )
    position = portfolio.positions[BTC]
    assert position.quantity == 60.0
    assert position.average_cost == 90_000.0
    assert portfolio.realized_pnl == pytest.approx(800.0)
    assert portfolio.cash == pytest.approx(100_000.0 + 800.0 - 45.0 - 18.40)
    # Mark at 91,000: unrealized on the remaining 60 = 60 x 1,000 x 0.01 = 600.
    portfolio.mark({BTC: 91_000.0}, T0 + timedelta(hours=2))
    assert portfolio.unrealized_pnl == pytest.approx(600.0)
    assert portfolio.equity == pytest.approx(
        100_000.0 + 800.0 + 600.0 - 45.0 - 18.40
    )
    reconciliation = portfolio.reconcile()
    assert reconciliation.passed
    assert reconciliation.residual_equity == pytest.approx(0.0, abs=1e-9)
    assert reconciliation.residual_pnl == pytest.approx(0.0, abs=1e-9)


def test_short_position_and_flip():
    portfolio = _portfolio()
    # Short 50 ETH at 3,000 (maker fill, fee 3 USDT: 50 x 3,000 x 0.1 x 0.0002).
    portfolio.apply_fill(
        ETH, _fill("sell", 3_000.0, 50.0, at=T0, is_maker=True, fee=3.0)
    )
    assert portfolio.maker_fees == pytest.approx(3.0)
    # Mark at 2,900: unrealized = -50 x (2,900 - 3,000) x 0.1 = +500.
    portfolio.mark({ETH: 2_900.0}, T0 + timedelta(hours=1))
    assert portfolio.unrealized_pnl == pytest.approx(500.0)
    # Buy 80 at 2,800: closes the 50 short (realized 50 x 200 x 0.1 = 1,000)
    # and flips to a 30 long at 2,800.
    portfolio.apply_fill(
        ETH, _fill("buy", 2_800.0, 80.0, at=T0 + timedelta(hours=2), fee=11.20)
    )
    position = portfolio.positions[ETH]
    assert position.quantity == 30.0
    assert position.average_cost == 2_800.0
    assert portfolio.realized_pnl == pytest.approx(1_000.0)
    assert portfolio.reconcile().passed
    # Mark at 2,900: unrealized on the 30 long = 30 x 100 x 0.1 = 300.
    portfolio.mark({ETH: 2_900.0}, T0 + timedelta(hours=3))
    assert portfolio.unrealized_pnl == pytest.approx(300.0)
    assert portfolio.equity == pytest.approx(
        100_000.0 + 1_000.0 + 300.0 - 3.0 - 11.20
    )
    assert portfolio.reconcile().passed


def test_funding_paid_and_received():
    portfolio = _portfolio()
    portfolio.apply_fill(BTC, _fill("buy", 90_000.0, 100.0, at=T0, fee=45.0))
    # Funding settlement: long 100 contracts, rate +0.0001 at 90,000
    # -> pays 100 x 90,000 x 0.01 x 0.0001 = 9.00.
    portfolio.apply_funding(
        FundingSettlement(
            settlement_time=T0 + timedelta(hours=8),
            position_quantity=100.0,
            price=90_000.0,
            amount=9.0,
        )
    )
    assert portfolio.funding_paid == pytest.approx(9.0)
    assert portfolio.cash == pytest.approx(100_000.0 - 45.0 - 9.0)
    # Negative rate: receives 4.50.
    portfolio.apply_funding(
        FundingSettlement(
            settlement_time=T0 + timedelta(hours=16),
            position_quantity=100.0,
            price=90_000.0,
            amount=-4.50,
        )
    )
    assert portfolio.funding_paid == pytest.approx(4.50)
    assert portfolio.cash == pytest.approx(100_000.0 - 45.0 - 4.50)
    assert portfolio.reconcile().passed


def test_independent_pnl_cross_check_catches_no_error_on_mixed_book():
    """A mixed long/short book reconciles exactly both ways."""
    portfolio = _portfolio()
    portfolio.apply_fill(BTC, _fill("buy", 90_000.0, 100.0, at=T0, fee=45.0))
    portfolio.apply_fill(
        ETH, _fill("sell", 3_000.0, 50.0, at=T0 + timedelta(minutes=1), fee=7.50)
    )
    portfolio.apply_fill(
        BTC, _fill("sell", 91_000.0, 100.0, at=T0 + timedelta(hours=1), fee=45.50)
    )
    portfolio.apply_fill(
        ETH, _fill("buy", 2_900.0, 20.0, at=T0 + timedelta(hours=2), fee=2.90)
    )
    portfolio.mark(
        {BTC: 91_500.0, ETH: 2_850.0}, T0 + timedelta(hours=3)
    )
    # Realized: BTC 100 x 1,000 x 0.01 = 1,000; ETH 20 x 100 x 0.1 = 200.
    assert portfolio.realized_pnl == pytest.approx(1_200.0)
    # Unrealized: ETH short 30 at 2,850 vs avg 3,000: -30 x (-150) x 0.1 = 450.
    assert portfolio.unrealized_pnl == pytest.approx(450.0)
    # Independent PnL: fill flows + position values.
    # BTC flows: -100 x 90,000 x 0.01 + 100 x 91,000 x 0.01 = 1,000.
    # ETH flows: +50 x 3,000 x 0.1 - 20 x 2,900 x 0.1 = 15,000 - 5,800 = 9,200.
    # ETH position value: -30 x 2,850 x 0.1 = -8,550. Total: 1,650.
    reconciliation = portfolio.reconcile()
    assert reconciliation.pnl_book == pytest.approx(1_650.0)
    assert reconciliation.pnl_independent == pytest.approx(1_650.0)
    assert reconciliation.residual_pnl == pytest.approx(0.0, abs=1e-9)
    assert reconciliation.passed


def test_out_of_order_event_rejected():
    portfolio = _portfolio()
    portfolio.apply_fill(BTC, _fill("buy", 90_000.0, 100.0, at=T0 + timedelta(hours=1)))
    with pytest.raises(ValueError, match="non-decreasing time order"):
        portfolio.apply_fill(BTC, _fill("sell", 91_000.0, 10.0, at=T0))


def test_mark_requires_price_for_open_positions():
    portfolio = _portfolio()
    portfolio.apply_fill(BTC, _fill("buy", 90_000.0, 100.0, at=T0))
    with pytest.raises(ValueError, match="no mark price"):
        portfolio.mark({ETH: 3_000.0}, T0 + timedelta(hours=1))


def test_unknown_instrument_and_bad_inputs():
    with pytest.raises(ValueError, match="no contract value"):
        _portfolio().apply_fill(
            "crypto:sol-usdt-perp", _fill("buy", 150.0, 10.0, at=T0)
        )
    with pytest.raises(ValueError, match="initial_cash"):
        PaperPortfolio(-1.0, {BTC: CV_BTC}, start_time=T0)
    with pytest.raises(ValueError, match="contract value"):
        PaperPortfolio(100_000.0, {BTC: 0.0}, start_time=T0)


def test_exposure_uses_risk_module():
    portfolio = _portfolio()
    portfolio.apply_fill(BTC, _fill("buy", 90_000.0, 100.0, at=T0, fee=45.0))
    portfolio.apply_fill(
        ETH, _fill("sell", 3_000.0, 50.0, at=T0 + timedelta(minutes=1), fee=7.50)
    )
    portfolio.mark({BTC: 90_000.0, ETH: 3_000.0}, T0 + timedelta(hours=1))
    exposure = portfolio.exposure()
    # BTC long 100 x 90,000 x 0.01 = 90,000; ETH short 50 x 3,000 x 0.1 = 15,000.
    assert exposure.long_notional == pytest.approx(90_000.0)
    assert exposure.short_notional == pytest.approx(15_000.0)
    assert exposure.gross_notional == pytest.approx(105_000.0)
    assert exposure.max_single_share == pytest.approx(90_000.0 / 105_000.0)
    assert exposure.leverage == pytest.approx(
        105_000.0 / (100_000.0 - 45.0 - 7.50)
    )


def test_equity_curve_sampled_at_each_event():
    portfolio = _portfolio()
    portfolio.apply_fill(BTC, _fill("buy", 90_000.0, 100.0, at=T0, fee=45.0))
    portfolio.mark({BTC: 91_000.0}, T0 + timedelta(hours=1))
    portfolio.apply_funding(
        FundingSettlement(
            settlement_time=T0 + timedelta(hours=8),
            position_quantity=100.0,
            price=91_000.0,
            amount=9.10,
        )
    )
    # Initial + fill + mark + funding = 4 snapshots.
    assert len(portfolio.snapshots) == 4
    assert portfolio.snapshots[1].equity == pytest.approx(100_000.0 - 45.0)
    assert portfolio.snapshots[2].equity == pytest.approx(100_000.0 - 45.0 + 1_000.0)
    assert portfolio.snapshots[3].equity == pytest.approx(
        100_000.0 - 45.0 + 1_000.0 - 9.10
    )
    assert portfolio.snapshots[3].mark_time == T0 + timedelta(hours=1)
