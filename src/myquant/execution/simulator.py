"""Conservative paper fill simulator: replay paper orders on a tape.

The simulator replays :class:`PaperOrder` records against a tape of
normalized :class:`Trade` records and a (possibly sparse) list of
:class:`BookSnapshot` records. It is a research cost model, not an
execution system: it never places orders, and every fill it reports
is a modelled fill under stated assumptions, not an observed one.

Fill rules (conservative by design; see ``docs/execution.md`` for the
reasoning behind each rule and the direction of its bias):

- **Limit orders** rest after arrival. A resting buy (sell) fills
  only on prints with the opposite aggressor side (sell prints fill
  bids, buy prints fill asks) at or through the limit price. The
  fill price is the limit price, never better. Same-side prints
  never fill a resting order, even at or through the limit: a
  same-side print at the limit price means the opposite side of the
  book was there, and the paper order may or may not have been the
  counterparty — assuming it was not is the conservative choice.
- **Queue.** The paper order is last in the queue at its price. At
  the limit price, prints first consume ``queue_ahead`` — the
  resting size at that price in the arrival-time snapshot, or the
  configured fallback when no valid snapshot covers the arrival
  (flagged ``queue_estimate_unknown``). A print strictly *through*
  the limit price proves the whole level was swept, so it clears
  the queue and fills at the limit price, bounded by the print size.
- **Crossed at arrival.** A limit order that crosses a valid
  arrival-time book (buy limit >= best ask, sell limit <= best bid)
  fills immediately as a taker at the best price plus slippage and
  impact, capped at the limit price (a limit is the worst price the
  order accepts). With no valid book at arrival the order rests:
  the model never fabricates a taker fill from an unknown book.
- **Market orders** fill at arrival against a valid book snapshot
  (best ask for buys, best bid for sells) plus adverse slippage and
  impact. With no valid book, they fill at the first subsequent
  print price (flagged ``book_unknown``) plus slippage and impact;
  impact is then unknown too, so it is 0 with the same flag. A
  market order with no subsequent print does not fill.
- **Snapshots between.** A snapshot is usable only within
  ``snapshot_max_age`` of its snapshot time (default 5 s). Older
  snapshots are unknown, never held: the book between snapshots is
  unknown, and the model says so instead of interpolating or
  holding stale quotes.
- **Latency.** Nothing fills before ``arrival_time``. Prints in
  [decision_time, arrival_time) that would have filled a limit
  order are recorded as :class:`MissedFill` entries, not silently
  dropped. Market orders record the last print price before the
  decision as the decision reference.
- **Cancel.** A resting remainder is cancelled at ``cancel_time``
  (prints at or after it do not fill). An order cancelled before
  arrival never becomes active.
- **Independence.** Orders are replayed independently: each order
  sees the full tape, and paper fills do not consume tape volume
  for other orders. This is a simplification, valid only while
  paper sizes are small relative to tape volume; it is stated here
  so it is not mistaken for a modelled interaction.
- **Ordering.** The tape must be sorted by (event_time, trade_id)
  and the snapshots by snapshot_time; an unsorted input raises
  instead of being silently re-sorted, because ordering is
  load-bearing for the replay.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime

from myquant.contracts import StrictContract
from myquant.execution.costs import (
    CostConfig,
    bps_cost,
    impact_bps,
    notional_value,
)
from myquant.execution.fees import (
    OKX_FUTURES_FEES,
    REGULAR_TIER,
    FeeSchedule,
)
from myquant.execution.orders import (
    Fill,
    MissedFill,
    OrderResult,
    OrderStatus,
    PaperOrder,
)
from myquant.microstructure.books import BookSnapshot
from myquant.microstructure.trades import Trade


class SimulationConfig(StrictContract):
    """Simulator configuration: cost assumptions + fee schedule + tier."""

    cost: CostConfig = CostConfig()
    fee_schedule: FeeSchedule = OKX_FUTURES_FEES
    fee_tier: str = REGULAR_TIER


@dataclass(frozen=True)
class SimulationResult:
    """Replay outcome for a set of orders, with aggregate counters."""

    order_results: tuple[OrderResult, ...]
    orders_filled: int
    orders_partial: int
    orders_unfilled: int
    orders_cancelled: int
    fills_book_unknown: int
    fills_queue_unknown: int
    missed_fills: int

    @property
    def total_fee(self) -> float:
        """Sum of exchange fees over all fills (rebates negative)."""
        return sum(result.total_fee for result in self.order_results)

    @property
    def total_slippage_cost(self) -> float:
        """Sum of adverse slippage costs over all fills."""
        return sum(result.total_slippage_cost for result in self.order_results)

    @property
    def total_impact_cost(self) -> float:
        """Sum of impact costs over all fills."""
        return sum(result.total_impact_cost for result in self.order_results)


def _check_sorted_trades(trades: tuple[Trade, ...]) -> None:
    previous: tuple[datetime, int] | None = None
    for trade in trades:
        key = (trade.event_time, trade.trade_id)
        if previous is not None and key < previous:
            raise ValueError(
                "tape must be sorted by (event_time, trade_id); "
                "refusing to replay an out-of-order tape"
            )
        previous = key


def _check_sorted_snapshots(snapshots: tuple[BookSnapshot, ...]) -> None:
    previous: datetime | None = None
    for snapshot in snapshots:
        if previous is not None and snapshot.snapshot_time < previous:
            raise ValueError(
                "snapshots must be sorted by snapshot_time; "
                "refusing to replay out-of-order snapshots"
            )
        previous = snapshot.snapshot_time


def _snapshot_at(
    snapshots: tuple[BookSnapshot, ...],
    snapshot_times: tuple[datetime, ...],
    when: datetime,
    max_age_seconds: float,
) -> BookSnapshot | None:
    """Latest snapshot at or before ``when`` within ``max_age_seconds``.

    Returns ``None`` when no snapshot covers ``when`` — the book is
    then unknown, never held past its age.
    """
    index = bisect.bisect_right(snapshot_times, when) - 1
    if index < 0:
        return None
    snapshot = snapshots[index]
    age = (when - snapshot.snapshot_time).total_seconds()
    if age > max_age_seconds:
        return None
    return snapshot


def _queue_ahead_at(
    snapshot: BookSnapshot | None,
    order: PaperOrder,
    fallback: float,
) -> tuple[float, bool]:
    """Resting size ahead of the paper order at its limit price.

    From the arrival-time snapshot when one is valid (the size at
    the exact limit-price level; 0.0 when the level is absent, since
    the paper order would then be alone at that price). Falls back
    to the configured parameter — flagged — when no valid snapshot
    covers the arrival.
    """
    if snapshot is None or order.limit_price is None:
        return fallback, True
    levels = snapshot.bids if order.side == "buy" else snapshot.asks
    for level in levels:
        if level.price == order.limit_price:
            return level.size, False
    return 0.0, False


def _print_fills_limit(order: PaperOrder, trade: Trade) -> bool:
    """Whether one print can fill a resting limit order.

    Only opposite-aggressor prints at or through the limit price:
    sell prints fill bids, buy prints fill asks. Same-side prints
    never fill (see the module docstring).
    """
    if order.limit_price is None:
        return False
    if trade.aggressor_side == order.side:
        return False
    if order.side == "buy":
        return trade.price <= order.limit_price
    return trade.price >= order.limit_price


def _print_through_limit(order: PaperOrder, trade: Trade) -> bool:
    """Whether a print is strictly through the limit price (level swept)."""
    if order.limit_price is None:
        return False
    if order.side == "buy":
        return trade.price < order.limit_price
    return trade.price > order.limit_price


@dataclass
class _OrderReplay:
    """Mutable per-order replay state."""

    order: PaperOrder
    fills: list[Fill]
    missed_fills: list[MissedFill]
    remaining: float
    queue_ahead: float
    queue_estimate_unknown: bool
    decision_reference_price: float | None = None
    cancelled: bool = False


def _crossing_vs_mid(
    order: PaperOrder,
    fill_price: float,
    fill_quantity: float,
    snapshot: BookSnapshot | None,
    contract_value: float,
) -> float | None:
    """Crossing cost vs the arrival-time mid, or None without a book.

    Positive means the fill paid worse than mid; negative means price
    improvement (a resting buy below mid, or a resting sell above mid).
    """
    if snapshot is None or snapshot.mid is None:
        return None
    mid = snapshot.mid
    if order.side == "buy":
        return (fill_price - mid) * fill_quantity * contract_value
    return (mid - fill_price) * fill_quantity * contract_value


def _taker_fill(
    order: PaperOrder,
    *,
    fill_time: datetime,
    book_price: float,
    snapshot: BookSnapshot | None,
    book_unknown: bool,
    config: SimulationConfig,
    crossed_at_arrival: bool,
) -> Fill:
    """Build one taker fill (market order, or crossed limit at arrival).

    The execution price is the book price plus adverse slippage and
    impact, capped at the limit price for limit orders (a limit is
    the worst price the order accepts). The slippage/impact costs
    are split from the adverse move actually paid, proportional to
    their modelled shares, so the decomposition always reconciles
    with the fill price even when the cap binds.
    """
    cost = config.cost
    slippage = cost.market_slippage_bps
    depth: float | None = None
    if snapshot is not None:
        depth = (
            snapshot.depth_ask(cost.impact_depth_levels)
            if order.side == "buy"
            else snapshot.depth_bid(cost.impact_depth_levels)
        )
    impact = impact_bps(order.quantity, depth, cost.impact_coefficient_bps)
    impact_bps_value = impact if impact is not None else 0.0
    raw_bps = slippage + impact_bps_value
    if order.side == "buy":
        uncapped = book_price * (1.0 + raw_bps / 10_000.0)
        price = uncapped if order.limit_price is None else min(uncapped, order.limit_price)
    else:
        uncapped = book_price * (1.0 - raw_bps / 10_000.0)
        price = uncapped if order.limit_price is None else max(uncapped, order.limit_price)
    adverse_bps_paid = abs(price - book_price) / book_price * 10_000.0
    if raw_bps > 0:
        slip_share = slippage / raw_bps
        impact_share = impact_bps_value / raw_bps
    else:
        slip_share = impact_share = 0.0
    notional = notional_value(price, order.quantity, cost.contract_value)
    fee = config.fee_schedule.fee_for(config.fee_tier, maker=False, notional=notional)
    return Fill(
        order_id=order.order_id,
        side=order.side,
        fill_time=fill_time,
        price=price,
        quantity=order.quantity,
        is_maker=False,
        fee=fee,
        crossing_cost=_crossing_vs_mid(
            order, book_price, order.quantity, snapshot, cost.contract_value
        ),
        slippage_cost=bps_cost(
            book_price,
            order.quantity,
            adverse_bps_paid * slip_share,
            cost.contract_value,
        ),
        impact_cost=bps_cost(
            book_price,
            order.quantity,
            adverse_bps_paid * impact_share,
            cost.contract_value,
        ),
        book_unknown=book_unknown,
        queue_estimate_unknown=False,
        crossed_at_arrival=crossed_at_arrival,
        trade_id=None,
    )


def _maker_fill(
    order: PaperOrder,
    *,
    fill_time: datetime,
    fill_quantity: float,
    snapshot: BookSnapshot | None,
    queue_estimate_unknown: bool,
    trade_id: int,
    config: SimulationConfig,
) -> Fill:
    """Build one resting-limit fill at the limit price (maker fee)."""
    assert order.limit_price is not None
    cost = config.cost
    notional = notional_value(order.limit_price, fill_quantity, cost.contract_value)
    fee = config.fee_schedule.fee_for(config.fee_tier, maker=True, notional=notional)
    return Fill(
        order_id=order.order_id,
        side=order.side,
        fill_time=fill_time,
        price=order.limit_price,
        quantity=fill_quantity,
        is_maker=True,
        fee=fee,
        crossing_cost=_crossing_vs_mid(
            order, order.limit_price, fill_quantity, snapshot, cost.contract_value
        ),
        slippage_cost=0.0,
        impact_cost=0.0,
        book_unknown=snapshot is None,
        queue_estimate_unknown=queue_estimate_unknown,
        crossed_at_arrival=False,
        trade_id=trade_id,
    )


def _replay_market_order(
    replay: _OrderReplay,
    trades: tuple[Trade, ...],
    trade_times: tuple[datetime, ...],
    snapshots: tuple[BookSnapshot, ...],
    snapshot_times: tuple[datetime, ...],
    config: SimulationConfig,
) -> None:
    """Fill a market order at arrival, or leave it unfilled."""
    order = replay.order
    arrival = order.arrival_time
    snapshot = _snapshot_at(
        snapshots, snapshot_times, arrival, config.cost.snapshot_max_age.total_seconds()
    )
    book_price: float | None = None
    if snapshot is not None:
        book_price = (
            snapshot.best_ask if order.side == "buy" else snapshot.best_bid
        )
    if book_price is not None:
        replay.fills.append(
            _taker_fill(
                order,
                fill_time=arrival,
                book_price=book_price,
                snapshot=snapshot,
                book_unknown=False,
                config=config,
                crossed_at_arrival=False,
            )
        )
        replay.remaining = 0.0
        return
    # No valid book (or an empty side): fall back to the first print at
    # or after arrival, flagged. No subsequent print means no fill, and
    # a first print at or after the cancel time means the order was
    # cancelled before any price was observable.
    index = bisect.bisect_left(trade_times, arrival)
    if index >= len(trades):
        return
    first_print = trades[index]
    if order.cancel_time is not None and first_print.event_time >= order.cancel_time:
        replay.cancelled = True
        return
    replay.fills.append(
        _taker_fill(
            order,
            fill_time=first_print.event_time,
            book_price=first_print.price,
            snapshot=None,
            book_unknown=True,
            config=config,
            crossed_at_arrival=False,
        )
    )
    replay.remaining = 0.0


def _replay_limit_order(
    replay: _OrderReplay,
    trades: tuple[Trade, ...],
    trade_times: tuple[datetime, ...],
    snapshots: tuple[BookSnapshot, ...],
    snapshot_times: tuple[datetime, ...],
    config: SimulationConfig,
) -> None:
    """Rest a limit order and fill it against subsequent prints."""
    order = replay.order
    arrival = order.arrival_time
    assert order.limit_price is not None
    snapshot = _snapshot_at(
        snapshots, snapshot_times, arrival, config.cost.snapshot_max_age.total_seconds()
    )
    # Crossed at arrival: immediate taker fill at the best price.
    if snapshot is not None:
        best = snapshot.best_ask if order.side == "buy" else snapshot.best_bid
        if best is not None:
            crossed = (
                order.limit_price >= best
                if order.side == "buy"
                else order.limit_price <= best
            )
            if crossed:
                replay.fills.append(
                    _taker_fill(
                        order,
                        fill_time=arrival,
                        book_price=best,
                        snapshot=snapshot,
                        book_unknown=False,
                        config=config,
                        crossed_at_arrival=True,
                    )
                )
                replay.remaining = 0.0
                return
    queue_ahead, queue_unknown = _queue_ahead_at(
        snapshot, order, config.cost.queue_ahead_fallback
    )
    replay.queue_ahead = queue_ahead
    replay.queue_estimate_unknown = queue_unknown
    # Prints strictly after arrival can fill; a print at exactly the
    # arrival instant is simultaneous with the order reaching the book
    # and is not counted as a fill (conservative).
    index = bisect.bisect_right(trade_times, arrival)
    while index < len(trades) and replay.remaining > 0:
        trade = trades[index]
        index += 1
        if order.cancel_time is not None and trade.event_time >= order.cancel_time:
            break
        if not _print_fills_limit(order, trade):
            continue
        if _print_through_limit(order, trade):
            # The whole level was swept: the queue ahead is gone.
            replay.queue_ahead = 0.0
            fill_quantity = min(replay.remaining, trade.size)
        elif replay.queue_ahead >= trade.size:
            replay.queue_ahead -= trade.size
            continue
        else:
            fill_quantity = min(replay.remaining, trade.size - replay.queue_ahead)
            replay.queue_ahead = 0.0
        replay.fills.append(
            _maker_fill(
                order,
                fill_time=trade.event_time,
                fill_quantity=fill_quantity,
                snapshot=snapshot,
                queue_estimate_unknown=queue_unknown,
                trade_id=trade.trade_id,
                config=config,
            )
        )
        replay.remaining -= fill_quantity


def _decision_reference_price(
    trades: tuple[Trade, ...],
    trade_times: tuple[datetime, ...],
    decision_time: datetime,
) -> float | None:
    """Last print price strictly before the decision time, if any."""
    index = bisect.bisect_left(trade_times, decision_time) - 1
    if index < 0:
        return None
    return trades[index].price


def _record_missed_fills(
    replay: _OrderReplay,
    trades: tuple[Trade, ...],
    trade_times: tuple[datetime, ...],
) -> None:
    """Record prints in [decision, arrival) that would have filled the order."""
    order = replay.order
    if order.order_type != "limit":
        return
    start = bisect.bisect_left(trade_times, order.decision_time)
    end = bisect.bisect_left(trade_times, order.arrival_time)
    for trade in trades[start:end]:
        if _print_fills_limit(order, trade):
            replay.missed_fills.append(
                MissedFill(
                    order_id=order.order_id,
                    print_time=trade.event_time,
                    price=trade.price,
                    quantity=trade.size,
                    trade_id=trade.trade_id,
                )
            )


def _finish_replay(replay: _OrderReplay) -> OrderResult:
    order = replay.order
    filled = order.quantity - replay.remaining
    if replay.cancelled:
        status: OrderStatus = "cancelled"
    elif filled == 0:
        status = "unfilled"
    elif replay.remaining == 0:
        status = "filled"
    else:
        status = "partial"
    return OrderResult(
        order=order,
        status=status,
        fills=tuple(replay.fills),
        missed_fills=tuple(replay.missed_fills),
        filled_quantity=filled,
        unfilled_quantity=replay.remaining,
        decision_reference_price=replay.decision_reference_price,
    )


def simulate_orders(
    orders: tuple[PaperOrder, ...] | list[PaperOrder],
    trades: tuple[Trade, ...] | list[Trade],
    snapshots: tuple[BookSnapshot, ...] | list[BookSnapshot] = (),
    *,
    config: SimulationConfig | None = None,
) -> SimulationResult:
    """Replay paper orders against a tape (and optional snapshots).

    Orders are independent (see the module docstring): each order
    sees the full tape. The tape and snapshots must be sorted (see
    ``_check_sorted_trades`` / ``_check_sorted_snapshots``).
    """
    cfg = config or SimulationConfig()
    tape = tuple(trades)
    books = tuple(snapshots)
    _check_sorted_trades(tape)
    _check_sorted_snapshots(books)
    trade_times = tuple(trade.event_time for trade in tape)
    snapshot_times = tuple(snapshot.snapshot_time for snapshot in books)

    results: list[OrderResult] = []
    for order in orders:
        replay = _OrderReplay(
            order=order,
            fills=[],
            missed_fills=[],
            remaining=order.quantity,
            queue_ahead=0.0,
            queue_estimate_unknown=False,
            decision_reference_price=_decision_reference_price(
                tape, trade_times, order.decision_time
            ),
        )
        _record_missed_fills(replay, tape, trade_times)
        if order.cancel_time is not None and order.cancel_time <= order.arrival_time:
            replay.cancelled = True
        elif order.order_type == "market":
            _replay_market_order(
                replay, tape, trade_times, books, snapshot_times, cfg
            )
        else:
            _replay_limit_order(
                replay, tape, trade_times, books, snapshot_times, cfg
            )
            if (
                order.cancel_time is not None
                and replay.remaining > 0
                and (not tape or tape[-1].event_time >= order.cancel_time)
            ):
                replay.cancelled = True
        results.append(_finish_replay(replay))

    return SimulationResult(
        order_results=tuple(results),
        orders_filled=sum(1 for r in results if r.status == "filled"),
        orders_partial=sum(1 for r in results if r.status == "partial"),
        orders_unfilled=sum(1 for r in results if r.status == "unfilled"),
        orders_cancelled=sum(1 for r in results if r.status == "cancelled"),
        fills_book_unknown=sum(
            1 for r in results for fill in r.fills if fill.book_unknown
        ),
        fills_queue_unknown=sum(
            1 for r in results for fill in r.fills if fill.queue_estimate_unknown
        ),
        missed_fills=sum(len(r.missed_fills) for r in results),
    )
