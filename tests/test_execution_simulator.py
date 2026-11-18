"""Tests for the conservative fill simulator. All offline.

Every expectation below is hand-computed from the fill rules in
``myquant.execution.simulator``; see ``docs/execution.md`` for the
rules and the reasoning behind each one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from myquant.execution.costs import CostConfig
from myquant.execution.orders import PaperOrder
from myquant.execution.simulator import SimulationConfig, simulate_orders
from myquant.microstructure.books import BookLevel, BookSnapshot
from myquant.microstructure.trades import Trade

T0 = datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)


def _trade(
    trade_id: int,
    second: int,
    side: str = "sell",
    price: float = 65000.0,
    size: float = 0.5,
) -> Trade:
    event = T0 + timedelta(seconds=second)
    return Trade(
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        event_time=event,
        available_at=event,
        ingested_at=event,
        trade_id=trade_id,
        price=price,
        size=size,
        aggressor_side=side,  # type: ignore[arg-type]
        source_id="okx-public",
    )


def _snapshot(
    second: int,
    bid: float = 65000.0,
    bid_size: float = 10.0,
    ask: float = 65000.1,
    ask_size: float = 10.0,
) -> BookSnapshot:
    event = T0 + timedelta(seconds=second)
    return BookSnapshot(
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        snapshot_time=event,
        available_at=event,
        ingested_at=event,
        seq_id=1000 + second,
        asks=(BookLevel(price=ask, size=ask_size, order_count=5),),
        bids=(BookLevel(price=bid, size=bid_size, order_count=5),),
        source_id="okx-public",
    )


def _order(
    order_id: str = "o1",
    side: str = "buy",
    order_type: str = "limit",
    quantity: float = 1.0,
    limit_price: float | None = 65000.0,
    decision_second: int = 0,
    latency_ms: int = 0,
    cancel_second: int | None = None,
) -> PaperOrder:
    decision = T0 + timedelta(seconds=decision_second)
    return PaperOrder(
        order_id=order_id,
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        side=side,  # type: ignore[arg-type]
        order_type=order_type,  # type: ignore[arg-type]
        quantity=quantity,
        limit_price=limit_price if order_type == "limit" else None,
        decision_time=decision,
        available_at=decision,
        latency=timedelta(milliseconds=latency_ms),
        cancel_time=(
            T0 + timedelta(seconds=cancel_second)
            if cancel_second is not None
            else None
        ),
    )


def test_limit_buy_fills_on_opposite_prints_at_limit() -> None:
    tape = (
        _trade(1, 1, "sell", 65000.0, 0.5),
        _trade(2, 2, "sell", 65000.0, 0.3),
        _trade(3, 3, "buy", 65000.0, 1.0),  # same side: must not fill
    )
    result = simulate_orders((_order(),), tape)
    (order_result,) = result.order_results
    assert order_result.status == "partial"
    assert order_result.filled_quantity == pytest.approx(0.8)
    assert order_result.unfilled_quantity == pytest.approx(0.2)
    assert [fill.price for fill in order_result.fills] == [65000.0, 65000.0]
    assert all(fill.is_maker for fill in order_result.fills)
    assert [fill.trade_id for fill in order_result.fills] == [1, 2]
    # Maker fee on 0.8 contracts: 65,000 x 0.8 x 0.01 x 0.0002 = 0.104.
    assert order_result.total_fee == pytest.approx(0.104)
    # No snapshot: crossing is unknown, not zero.
    assert order_result.crossing_unknown
    assert order_result.total_crossing_cost is None
    assert result.fills_queue_unknown == 2


def test_limit_sell_fills_on_buy_prints() -> None:
    tape = (_trade(1, 1, "buy", 65000.0, 1.0),)
    result = simulate_orders(
        (_order(side="sell", quantity=1.0),), tape
    )
    (order_result,) = result.order_results
    assert order_result.status == "filled"
    assert order_result.filled_quantity == pytest.approx(1.0)


def test_same_side_prints_never_fill_a_resting_order() -> None:
    # A buy-aggressor print below the bid: the ask was there, but the
    # paper bid may not have been the counterparty. Conservative: no fill.
    tape = (_trade(1, 1, "buy", 64999.0, 5.0),)
    result = simulate_orders((_order(),), tape)
    (order_result,) = result.order_results
    assert order_result.status == "unfilled"
    assert order_result.fills == ()


def test_queue_ahead_is_consumed_before_the_paper_order_fills() -> None:
    snapshot = _snapshot(0, bid=65000.0, bid_size=2.0, ask=65000.1, ask_size=1.0)
    tape = (
        _trade(1, 1, "sell", 65000.0, 1.5),  # queue 2.0 -> 0.5, no fill
        _trade(2, 2, "sell", 65000.0, 1.0),  # queue 0.5 -> 0, fill 0.5
        _trade(3, 3, "sell", 65000.0, 1.0),  # fill 0.5
    )
    result = simulate_orders((_order(),), tape, (snapshot,))
    (order_result,) = result.order_results
    assert order_result.status == "filled"
    assert [fill.quantity for fill in order_result.fills] == [0.5, 0.5]
    assert [fill.trade_id for fill in order_result.fills] == [2, 3]
    assert result.fills_queue_unknown == 0
    # Crossing vs the arrival mid 65,000.05: (65,000 - 65,000.05) x 0.01.
    assert order_result.total_crossing_cost == pytest.approx(-0.0005)


def test_through_print_clears_the_queue() -> None:
    snapshot = _snapshot(0, bid=65000.0, bid_size=2.0, ask=65000.1, ask_size=1.0)
    tape = (
        _trade(1, 1, "sell", 64999.9, 0.4),  # through: queue gone, fill 0.4
        _trade(2, 2, "sell", 65000.0, 0.8),  # fill the remaining 0.6
    )
    result = simulate_orders((_order(),), tape, (snapshot,))
    (order_result,) = result.order_results
    assert order_result.status == "filled"
    assert [fill.quantity for fill in order_result.fills] == [0.4, 0.6]
    assert all(fill.price == 65000.0 for fill in order_result.fills)


def test_print_exactly_at_arrival_does_not_fill() -> None:
    tape = (
        _trade(1, 2, "sell", 65000.0, 1.0),  # exactly at arrival: no fill
        _trade(2, 3, "sell", 65000.0, 1.0),  # strictly after: fills
    )
    result = simulate_orders((_order(latency_ms=2000),), tape)
    (order_result,) = result.order_results
    assert [fill.trade_id for fill in order_result.fills] == [2]
    assert order_result.missed_fills == ()


def test_latency_creates_missed_fills() -> None:
    tape = (
        _trade(1, 1, "sell", 65000.0, 1.0),  # in [decision, arrival): missed
        _trade(2, 3, "sell", 65000.0, 1.0),  # after arrival: fills
    )
    result = simulate_orders((_order(latency_ms=2000),), tape)
    (order_result,) = result.order_results
    assert order_result.status == "filled"
    assert len(order_result.missed_fills) == 1
    assert order_result.missed_fills[0].trade_id == 1
    assert order_result.missed_fills[0].price == 65000.0
    assert result.missed_fills == 1


def test_cancel_stops_resting_fills() -> None:
    tape = (
        _trade(1, 1, "sell", 65000.0, 1.0),  # fills
        _trade(2, 6, "sell", 65000.0, 1.0),  # after cancel: no fill
        _trade(3, 7, "sell", 65000.0, 0.1),  # tape extends past cancel
    )
    result = simulate_orders((_order(quantity=2.0, cancel_second=5),), tape)
    (order_result,) = result.order_results
    assert order_result.status == "cancelled"
    assert order_result.filled_quantity == pytest.approx(1.0)
    assert order_result.unfilled_quantity == pytest.approx(1.0)


def test_cancel_before_arrival_never_activates() -> None:
    tape = (_trade(1, 3, "sell", 65000.0, 1.0),)
    result = simulate_orders((_order(latency_ms=2000, cancel_second=1),), tape)
    (order_result,) = result.order_results
    assert order_result.status == "cancelled"
    assert order_result.fills == ()


def test_market_buy_fills_at_ask_plus_slippage_and_impact() -> None:
    snapshot = _snapshot(0)
    result = simulate_orders((_order(order_type="market"),), (), (snapshot,))
    (order_result,) = result.order_results
    assert order_result.status == "filled"
    (fill,) = order_result.fills
    # Ask 65,000.1; slippage 1 bp + impact 5 x (1/10) = 0.5 bp.
    assert fill.price == pytest.approx(65000.1 * 1.00015)
    assert not fill.is_maker
    assert not fill.book_unknown
    # Taker fee on the filled notional.
    assert fill.fee == pytest.approx(65009.850015 * 0.01 * 0.0005)
    # Crossing: half the 0.1 spread on 1 contract.
    assert fill.crossing_cost == pytest.approx(0.0005)
    assert fill.slippage_cost == pytest.approx(0.0650001)
    assert fill.impact_cost == pytest.approx(0.03250005)


def test_market_sell_fills_at_bid() -> None:
    snapshot = _snapshot(0)
    result = simulate_orders(
        (_order(order_type="market", side="sell"),), (), (snapshot,)
    )
    (order_result,) = result.order_results
    (fill,) = order_result.fills
    # Bid 65,000.0; adverse move is downward for a sell.
    assert fill.price == pytest.approx(65000.0 * (1.0 - 0.00015))
    assert fill.crossing_cost == pytest.approx(0.0005)


def test_market_order_without_book_falls_back_to_first_print() -> None:
    tape = (_trade(1, 1, "buy", 65010.0, 0.5),)
    result = simulate_orders((_order(order_type="market"),), tape)
    (order_result,) = result.order_results
    (fill,) = order_result.fills
    # First print 65,010.0 + 1 bp slippage; impact unknown (no book).
    assert fill.price == pytest.approx(65010.0 * 1.0001)
    assert fill.book_unknown
    assert fill.crossing_cost is None
    assert fill.impact_cost == pytest.approx(0.0)
    assert fill.slippage_cost == pytest.approx(65010.0 * 0.01 * 0.0001)


def test_market_order_with_no_print_after_arrival_does_not_fill() -> None:
    tape = (_trade(1, 1, "buy", 65010.0, 0.5),)
    result = simulate_orders(
        (_order(order_type="market", decision_second=10),), tape
    )
    (order_result,) = result.order_results
    assert order_result.status == "unfilled"
    assert order_result.fills == ()


def test_crossed_limit_fills_as_taker_at_arrival() -> None:
    snapshot = _snapshot(0)
    # Limit 65,020 is above the ask (crossed) and above the modelled
    # adverse price 65,009.85, so the cap does not bind here.
    result = simulate_orders(
        (_order(limit_price=65020.0),), (), (snapshot,)
    )
    (order_result,) = result.order_results
    assert order_result.status == "filled"
    (fill,) = order_result.fills
    assert fill.crossed_at_arrival
    assert not fill.is_maker
    assert fill.price == pytest.approx(65000.1 * 1.00015)


def test_crossed_limit_fill_price_is_capped_at_the_limit() -> None:
    snapshot = _snapshot(0)
    result = simulate_orders(
        (_order(limit_price=65000.2),), (), (snapshot,)
    )
    (order_result,) = result.order_results
    (fill,) = order_result.fills
    # Modelled adverse price would be 65,009.85; the limit caps it.
    assert fill.price == pytest.approx(65000.2)
    # The decomposition reconciles: slip + impact = (fill - book) x qty.
    assert fill.slippage_cost + fill.impact_cost == pytest.approx(0.001)


def test_crossed_limit_without_book_rests() -> None:
    # No snapshot: the model cannot know the book is crossed, so the
    # order rests instead of fabricating a taker fill.
    tape = (_trade(1, 1, "sell", 65000.0, 1.0),)
    result = simulate_orders((_order(limit_price=65000.5),), tape)
    (order_result,) = result.order_results
    (fill,) = order_result.fills
    assert not fill.crossed_at_arrival
    assert fill.is_maker
    assert fill.price == pytest.approx(65000.5)


def test_stale_snapshot_is_unknown() -> None:
    snapshot = _snapshot(0)
    tape = (_trade(1, 11, "buy", 65010.0, 0.5),)
    # Arrival at 05:00:10; the snapshot is 10 s old, past the 5 s max age.
    result = simulate_orders(
        (_order(order_type="market", decision_second=10),), tape, (snapshot,)
    )
    (order_result,) = result.order_results
    (fill,) = order_result.fills
    assert fill.book_unknown
    assert fill.price == pytest.approx(65010.0 * 1.0001)


def test_fresh_snapshot_is_used() -> None:
    snapshot = _snapshot(9)
    result = simulate_orders(
        (_order(order_type="market", decision_second=10),), (), (snapshot,)
    )
    (order_result,) = result.order_results
    (fill,) = order_result.fills
    assert not fill.book_unknown
    assert fill.price == pytest.approx(65000.1 * 1.00015)


def test_snapshot_max_age_is_configurable() -> None:
    snapshot = _snapshot(0)
    config = SimulationConfig(
        cost=CostConfig(snapshot_max_age=timedelta(seconds=30))
    )
    result = simulate_orders(
        (_order(order_type="market", decision_second=10),),
        (),
        (snapshot,),
        config=config,
    )
    (order_result,) = result.order_results
    assert not order_result.fills[0].book_unknown


def test_empty_tape_fills_nothing_and_does_not_crash() -> None:
    result = simulate_orders(
        (_order(), _order(order_id="o2", order_type="market")),
        (),
    )
    assert result.orders_unfilled == 2
    assert all(r.fills == () for r in result.order_results)
    assert all(r.decision_reference_price is None for r in result.order_results)


def test_decision_reference_price_is_last_print_before_decision() -> None:
    tape = (
        _trade(1, 1, "buy", 64999.0, 0.5),
        _trade(2, 3, "buy", 65001.0, 0.5),
        _trade(3, 7, "buy", 65002.0, 0.5),
    )
    result = simulate_orders((_order(decision_second=5),), tape)
    (order_result,) = result.order_results
    assert order_result.decision_reference_price == pytest.approx(65001.0)


def test_unsorted_tape_raises() -> None:
    tape = (_trade(2, 2), _trade(1, 1))
    with pytest.raises(ValueError, match="sorted by \\(event_time, trade_id\\)"):
        simulate_orders((_order(),), tape)


def test_unsorted_snapshots_raise() -> None:
    with pytest.raises(ValueError, match="sorted by snapshot_time"):
        simulate_orders((_order(),), (), (_snapshot(5), _snapshot(1)))


def test_average_fill_price_and_totals() -> None:
    tape = (
        _trade(1, 1, "sell", 65000.0, 0.5),
        _trade(2, 2, "sell", 65000.0, 0.5),
    )
    result = simulate_orders((_order(),), tape)
    (order_result,) = result.order_results
    assert order_result.average_fill_price == pytest.approx(65000.0)
    assert order_result.total_slippage_cost == pytest.approx(0.0)
    assert order_result.total_impact_cost == pytest.approx(0.0)
    assert result.orders_filled == 1
    assert result.total_fee == pytest.approx(0.13)


def test_vip_tier_changes_the_fee() -> None:
    config = SimulationConfig(fee_tier="VIP 1")
    tape = (_trade(1, 1, "sell", 65000.0, 1.0),)
    result = simulate_orders((_order(),), tape, config=config)
    (order_result,) = result.order_results
    # VIP 1 maker rate is 0.016%: 650 x 0.00016 = 0.104.
    assert order_result.total_fee == pytest.approx(0.104)
