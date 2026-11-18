"""Paper orders and fill records for the conservative fill model.

A :class:`PaperOrder` is a research instruction, not a live order: it
is never sent anywhere. It carries the three clocks the architecture
requires for anything time-sensitive:

- ``decision_time`` — when the (paper) strategy decided to trade.
- ``available_at`` — when the order instruction was formed and could
  be sent; usually equal to ``decision_time``.
- ``arrival_time`` — when the order reaches the book, computed as
  ``available_at + latency``. Nothing about the order may use market
  data newer than ``decision_time``; nothing may fill before
  ``arrival_time``.

``latency`` is a model parameter, not a measurement: the default
100 ms is a conservative round-trip allowance for REST-based paper
trading from a non-colocated machine, chosen as a round number and
documented as a choice in ``docs/execution.md``. The stress test
scans it (0 / 100 ms / 500 ms / 1 s) so no result depends on the
default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field, model_validator

from myquant.contracts import StrictContract, require_utc

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["filled", "partial", "unfilled", "cancelled"]

#: Default order-to-book latency. A choice, not a measurement; see the
#: module docstring and docs/execution.md.
DEFAULT_LATENCY = timedelta(milliseconds=100)


class PaperOrder(StrictContract):
    """One paper order to replay against a trade tape."""

    order_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(gt=0, allow_inf_nan=False)
    limit_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    decision_time: datetime
    available_at: datetime
    latency: timedelta = DEFAULT_LATENCY
    cancel_time: datetime | None = None

    @model_validator(mode="after")
    def validate_order(self) -> PaperOrder:
        decision = require_utc(self.decision_time)
        available = require_utc(self.available_at)
        if available < decision:
            raise ValueError("available_at cannot precede decision_time")
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit orders require limit_price")
        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("market orders must not carry limit_price")
        if self.latency < timedelta(0):
            raise ValueError("latency must be non-negative")
        cancel = require_utc(self.cancel_time) if self.cancel_time is not None else None
        if cancel is not None and cancel <= decision:
            raise ValueError("cancel_time must be after decision_time")
        object.__setattr__(self, "decision_time", decision)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "cancel_time", cancel)
        return self

    @property
    def arrival_time(self) -> datetime:
        """When the order reaches the book: available_at + latency."""
        return self.available_at + self.latency


class Fill(StrictContract):
    """One paper fill, with its cost decomposition in USDT.

    ``price`` is the execution price actually charged, including any
    adverse slippage/impact adjustment (market fills) or the limit
    price (resting fills). ``crossing_cost`` is measured against the
    arrival-time mid when a valid book snapshot covers the fill; it is
    ``None`` when no valid snapshot was available, and the fill is then
    flagged ``book_unknown`` instead of silently pricing the crossing
    off stale or invented quotes. ``fee`` may be negative: a maker
    rebate is a negative fee, not a zero fee.
    """

    order_id: str = Field(min_length=1)
    side: OrderSide
    fill_time: datetime
    price: float = Field(gt=0, allow_inf_nan=False)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    is_maker: bool
    fee: float = Field(allow_inf_nan=False)
    crossing_cost: float | None = Field(default=None, allow_inf_nan=False)
    slippage_cost: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    impact_cost: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    book_unknown: bool = False
    queue_estimate_unknown: bool = False
    crossed_at_arrival: bool = False
    trade_id: int | None = Field(default=None, ge=0)


class MissedFill(StrictContract):
    """A print that would have filled a limit order had it arrived earlier.

    Recorded, never silently dropped: a missed fill is the visible cost
    of latency for resting orders. ``quantity`` is the print's size —
    an upper bound on what could have filled, not a claim that the
    whole print was available to the paper order.
    """

    order_id: str = Field(min_length=1)
    print_time: datetime
    price: float = Field(gt=0, allow_inf_nan=False)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    trade_id: int = Field(ge=0)


@dataclass(frozen=True)
class OrderResult:
    """Replay outcome for one paper order, with cost totals in USDT.

    ``total_crossing_cost`` is ``None`` when any fill lacked a valid
    book (``crossing_unknown`` is then True): the crossing total is
    unknown, not zero, and must not be summed into a total cost as
    if it were zero.
    """

    order: PaperOrder
    status: OrderStatus
    fills: tuple[Fill, ...]
    missed_fills: tuple[MissedFill, ...]
    filled_quantity: float
    unfilled_quantity: float
    decision_reference_price: float | None

    @property
    def average_fill_price(self) -> float | None:
        """Volume-weighted average fill price, or None when unfilled."""
        if self.filled_quantity == 0:
            return None
        return sum(
            fill.price * fill.quantity for fill in self.fills
        ) / self.filled_quantity

    @property
    def total_fee(self) -> float:
        """Sum of exchange fees (maker rebates are negative fees)."""
        return sum(fill.fee for fill in self.fills)

    @property
    def crossing_unknown(self) -> bool:
        """True when any fill has no crossing cost (no valid book)."""
        return any(fill.crossing_cost is None for fill in self.fills)

    @property
    def total_crossing_cost(self) -> float | None:
        """Sum of crossing costs, or None when any fill lacks one."""
        if self.crossing_unknown:
            return None
        return sum(
            fill.crossing_cost for fill in self.fills if fill.crossing_cost is not None
        )

    @property
    def total_slippage_cost(self) -> float:
        """Sum of adverse slippage costs."""
        return sum(fill.slippage_cost for fill in self.fills)

    @property
    def total_impact_cost(self) -> float:
        """Sum of impact costs."""
        return sum(fill.impact_cost for fill in self.fills)
