"""Paper portfolio and reconciliation (Stage 5a).

A perpetuals paper portfolio: positions in contracts with an
average-cost basis, cash that moves only on fees, funding, and
realized PnL (buying does not deduct notional from cash), and an
equity curve sampled at every event. Fills come from the Stage 4b
conservative simulator (``apply_order_result``) or from a stated
close-fill convention in validation; the portfolio never invents a
fill and never places an order.

Cash model (perpetuals, USDT-margined):

- equity = cash + unrealized PnL
- cash = initial_cash + realized PnL − fees − funding paid
- unrealized PnL = Σ quantity × (mark − average cost) × contract value

Fees are split maker/taker by the fill's ``is_maker`` flag; funding
is applied as settlements computed by ``compute_funding_from_series``
(positive amount = paid) and tracked separately from fees. A mark is
the latest known price per instrument; an instrument's mark
initializes to its first fill price (unrealized is then zero at that
instant, which is exactly right) and moves only on ``mark`` calls.

Reconciliation (``reconcile``) is three-way and reports exact
residuals:

1. equity from cash + unrealized vs equity from the ledger
   (initial + realized − fees − funding + unrealized);
2. book PnL (realized + unrealized, average-cost basis) vs an
   independent PnL from raw fill cash flows plus current position
   values at mark — method-independent, it never touches average
   cost;
3. the equity-change identity is (1) rearranged and reported with it.

``passed`` requires every |residual| ≤ ``RECONCILIATION_TOLERANCE``
(1e-9 USDT), a floating-point tolerance, not a rounding: the
reported residuals are the exact floats. A residual above the
tolerance is a bug to fix, never a parameter to tune.

Events (fills, funding, marks) must arrive in non-decreasing time
order; the portfolio raises on an out-of-order event rather than
silently re-ordering a ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from myquant.contracts import require_utc
from myquant.execution.costs import FundingSettlement
from myquant.execution.orders import Fill, OrderResult
from myquant.portfolio.risk import ExposureSnapshot, aggregate_exposure

#: Floating-point tolerance for reconciliation residuals, in USDT.
#: Far below any economically meaningful amount; the reported
#: residuals themselves are never rounded.
RECONCILIATION_TOLERANCE = 1e-9


@dataclass
class Position:
    """One instrument's paper position (average-cost basis)."""

    instrument_id: str
    quantity: float = 0.0  # signed contracts (+ long, - short)
    average_cost: float | None = None  # entry price; None when flat
    contract_value: float = 0.0
    mark_price: float | None = None
    realized_pnl: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        """Mark-to-market PnL on the open position (0 when flat)."""
        if self.quantity == 0 or self.average_cost is None or self.mark_price is None:
            return 0.0
        return self.quantity * (self.mark_price - self.average_cost) * self.contract_value

    @property
    def notional(self) -> float:
        """Signed notional at mark (0 when unmarked)."""
        if self.mark_price is None:
            return 0.0
        return self.quantity * self.mark_price * self.contract_value


@dataclass(frozen=True)
class EquitySnapshot:
    """Portfolio state at one event time (mark-time-sampled)."""

    time: datetime
    equity: float
    cash: float
    realized_pnl: float
    unrealized_pnl: float
    maker_fees: float
    taker_fees: float
    funding_paid: float
    gross_notional: float
    mark_time: datetime | None  # when marks were last updated (None = fill-price marks)


@dataclass(frozen=True)
class AppliedFill:
    """A fill as recorded in the portfolio ledger (for the audit trail)."""

    instrument_id: str
    side: str
    fill_time: datetime
    price: float
    quantity: float
    is_maker: bool
    fee: float
    contract_value: float


@dataclass(frozen=True)
class Reconciliation:
    """Three-way reconciliation result, with exact residuals."""

    equity: float
    equity_from_ledger: float
    residual_equity: float
    pnl_book: float
    pnl_independent: float
    residual_pnl: float
    passed: bool


class PaperPortfolio:
    """A paper perpetuals portfolio with an auditable ledger."""

    def __init__(
        self,
        initial_cash: float,
        contract_values: dict[str, float],
        *,
        start_time: datetime,
    ) -> None:
        if initial_cash < 0:
            raise ValueError("initial_cash must be non-negative")
        if not contract_values:
            raise ValueError("at least one contract value is required")
        for instrument_id, value in contract_values.items():
            if value <= 0:
                raise ValueError(
                    f"contract value must be positive for {instrument_id}"
                )
        self.initial_cash = initial_cash
        self.contract_values = dict(contract_values)
        self.start_time = require_utc(start_time)
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._maker_fees = 0.0
        self._taker_fees = 0.0
        self._funding_paid = 0.0
        self._realized_pnl = 0.0
        self._fills: list[AppliedFill] = []
        self._funding_events: list[FundingSettlement] = []
        self._last_event_time = self.start_time
        self._last_mark_time: datetime | None = None
        self._snapshots: list[EquitySnapshot] = []
        self._snapshot(self.start_time)

    # -- state -----------------------------------------------------

    @property
    def cash(self) -> float:
        """Cash balance: initial + realized − fees − funding."""
        return self._cash

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self._positions.values())

    @property
    def equity(self) -> float:
        """Equity = cash + unrealized PnL."""
        return self._cash + self.unrealized_pnl

    @property
    def maker_fees(self) -> float:
        return self._maker_fees

    @property
    def taker_fees(self) -> float:
        return self._taker_fees

    @property
    def total_fees(self) -> float:
        return self._maker_fees + self._taker_fees

    @property
    def funding_paid(self) -> float:
        """Net funding paid (> 0) or received (< 0)."""
        return self._funding_paid

    @property
    def positions(self) -> dict[str, Position]:
        """Live positions (a copy; the ledger owns the originals)."""
        return dict(self._positions)

    @property
    def snapshots(self) -> tuple[EquitySnapshot, ...]:
        return tuple(self._snapshots)

    @property
    def fills(self) -> tuple[AppliedFill, ...]:
        return tuple(self._fills)

    @property
    def funding_events(self) -> tuple[FundingSettlement, ...]:
        return tuple(self._funding_events)

    # -- events ----------------------------------------------------

    def apply_fill(self, instrument_id: str, fill: Fill) -> None:
        """Apply one fill to the position and cash (average-cost basis)."""
        if instrument_id not in self.contract_values:
            raise ValueError(f"no contract value for {instrument_id}")
        fill_time = require_utc(fill.fill_time)
        self._check_order(fill_time)
        contract_value = self.contract_values[instrument_id]
        position = self._positions.setdefault(
            instrument_id,
            Position(instrument_id=instrument_id, contract_value=contract_value),
        )
        signed_qty = fill.quantity if fill.side == "buy" else -fill.quantity
        if position.mark_price is None:
            # First fill for this instrument: mark at the fill price.
            position.mark_price = fill.price
        if position.quantity == 0:
            position.quantity = signed_qty
            position.average_cost = fill.price
        elif (position.quantity > 0) == (signed_qty > 0):
            # Adding to the position: re-weight the average cost.
            total = abs(position.quantity) + fill.quantity
            assert position.average_cost is not None
            position.average_cost = (
                abs(position.quantity) * position.average_cost
                + fill.quantity * fill.price
            ) / total
            position.quantity += signed_qty
        else:
            # Reducing or flipping: realize PnL on the closed part.
            closed = min(abs(position.quantity), fill.quantity)
            direction = 1.0 if position.quantity > 0 else -1.0
            assert position.average_cost is not None
            realized = (
                closed
                * (fill.price - position.average_cost)
                * direction
                * contract_value
            )
            position.realized_pnl += realized
            self._realized_pnl += realized
            self._cash += realized
            position.quantity += signed_qty
            if position.quantity == 0:
                position.average_cost = None
            elif (position.quantity > 0) != (direction > 0):
                # Flipped: the remainder opens at the fill price.
                position.average_cost = fill.price
        if fill.is_maker:
            self._maker_fees += fill.fee
        else:
            self._taker_fees += fill.fee
        self._cash -= fill.fee
        self._fills.append(
            AppliedFill(
                instrument_id=instrument_id,
                side=fill.side,
                fill_time=fill_time,
                price=fill.price,
                quantity=fill.quantity,
                is_maker=fill.is_maker,
                fee=fill.fee,
                contract_value=contract_value,
            )
        )
        self._last_event_time = fill_time
        self._snapshot(fill_time)

    def apply_order_result(self, result: OrderResult) -> None:
        """Apply every fill of one simulated order (in fill order)."""
        for fill in result.fills:
            self.apply_fill(result.order.instrument_id, fill)

    def apply_funding(self, settlement: FundingSettlement) -> None:
        """Apply one funding settlement (amount > 0 = paid)."""
        settlement_time = require_utc(settlement.settlement_time)
        self._check_order(settlement_time)
        self._funding_paid += settlement.amount
        self._cash -= settlement.amount
        self._funding_events.append(settlement)
        self._last_event_time = settlement_time
        self._snapshot(settlement_time)

    def mark(self, prices: dict[str, float], at: datetime) -> None:
        """Update mark prices; every open position must be marked."""
        mark_time = require_utc(at)
        self._check_order(mark_time)
        for instrument_id, position in self._positions.items():
            if position.quantity == 0:
                continue
            if instrument_id not in prices:
                raise ValueError(
                    f"no mark price for open position {instrument_id}"
                )
            if prices[instrument_id] <= 0:
                raise ValueError(
                    f"mark price must be positive for {instrument_id}"
                )
        for instrument_id, price in prices.items():
            if instrument_id in self._positions:
                self._positions[instrument_id].mark_price = price
        self._last_mark_time = mark_time
        self._last_event_time = mark_time
        self._snapshot(mark_time)

    # -- reporting -------------------------------------------------

    def exposure(self) -> ExposureSnapshot:
        """Exposure snapshot via the risk module (descriptive)."""
        positions = {
            instrument_id: (
                position.quantity,
                position.mark_price or 0.0,
                position.contract_value,
            )
            for instrument_id, position in self._positions.items()
            if position.quantity != 0 and position.mark_price is not None
        }
        return aggregate_exposure(positions, equity=self.equity)

    def reconcile(self) -> Reconciliation:
        """Three-way reconciliation; see the module docstring."""
        equity = self.equity
        equity_from_ledger = (
            self.initial_cash
            + self._realized_pnl
            - self.total_fees
            - self._funding_paid
            + self.unrealized_pnl
        )
        residual_equity = equity - equity_from_ledger
        # Independent PnL: raw fill cash flows + current position
        # values at mark. Buys pay cash (negative flow), sells receive
        # it; the open position is worth quantity x mark x contract
        # value. No average cost anywhere in this computation.
        fill_flows = sum(
            (-fill.price if fill.side == "buy" else fill.price)
            * fill.quantity
            * fill.contract_value
            for fill in self._fills
        )
        position_values = sum(
            position.quantity
            * (position.mark_price or 0.0)
            * position.contract_value
            for position in self._positions.values()
        )
        pnl_independent = fill_flows + position_values
        pnl_book = self._realized_pnl + self.unrealized_pnl
        residual_pnl = pnl_book - pnl_independent
        passed = (
            abs(residual_equity) <= RECONCILIATION_TOLERANCE
            and abs(residual_pnl) <= RECONCILIATION_TOLERANCE
        )
        return Reconciliation(
            equity=equity,
            equity_from_ledger=equity_from_ledger,
            residual_equity=residual_equity,
            pnl_book=pnl_book,
            pnl_independent=pnl_independent,
            residual_pnl=residual_pnl,
            passed=passed,
        )

    # -- internals -------------------------------------------------

    def _check_order(self, event_time: datetime) -> None:
        if event_time < self._last_event_time:
            raise ValueError(
                "events must arrive in non-decreasing time order: "
                f"{event_time.isoformat()} precedes "
                f"{self._last_event_time.isoformat()}"
            )

    def _snapshot(self, at: datetime) -> None:
        gross = sum(
            abs(position.notional) for position in self._positions.values()
        )
        self._snapshots.append(
            EquitySnapshot(
                time=at,
                equity=self.equity,
                cash=self._cash,
                realized_pnl=self._realized_pnl,
                unrealized_pnl=self.unrealized_pnl,
                maker_fees=self._maker_fees,
                taker_fees=self._taker_fees,
                funding_paid=self._funding_paid,
                gross_notional=gross,
                mark_time=self._last_mark_time,
            )
        )
