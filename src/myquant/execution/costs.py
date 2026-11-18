"""Cost model: crossing, slippage, impact and funding.

Every number in :class:`CostConfig` is a modelling choice, not a
finding. Each default below carries its reason in one sentence, and
``docs/execution.md`` repeats the table with the same reasons. None
of these assumptions has been calibrated against real executions;
the stress test exists precisely so results can be re-read under
different assumptions.

Verified venue facts used here (not assumptions):

- BTC-USDT-SWAP contract value is 0.01 BTC per contract
  (``ctVal`` from OKX ``/api/v5/public/instruments``, read
  2026-11-18; tick size 0.1 USDT, minimum size 0.01 contracts).
- Funding settles every 8 hours on the 00:00 / 08:00 / 16:00 UTC
  grid (next ``fundingTime`` read live from OKX
  ``/api/v5/public/funding-rate`` on 2026-11-18 was
  2026-11-18T16:00:00Z; the funding-rate cap/floor is +/-0.375% per
  interval, ``maxFundingRate``/``minFundingRate`` from the same
  endpoint).

What is NOT in this module: the funding-rate *series*. The funding
rate is an input parameter (``funding_rate_per_interval``); no
historical funding sequence is pulled, so funding cost is computed
only when the caller supplies a rate. That is a documented data gap,
not a default of zero cost — the default rate of 0.0 means "no
funding input supplied", and any report using it must say so.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from pydantic import Field

from myquant.contracts import StrictContract
from myquant.execution.orders import Fill

#: BTC-USDT-SWAP contract value in BTC per contract (OKX instruments
#: endpoint, verified 2026-11-18). Other instruments differ; pass the
#: right value in CostConfig.
DEFAULT_CONTRACT_VALUE_BTC = 0.01

#: OKX perpetual funding settles on this UTC grid (verified live,
#: see the module docstring).
FUNDING_SETTLEMENT_HOURS = (0, 8, 16)


class CostConfig(StrictContract):
    """Configurable cost assumptions with conservative defaults."""

    contract_value: float = Field(
        default=DEFAULT_CONTRACT_VALUE_BTC, gt=0, allow_inf_nan=False
    )
    market_slippage_bps: float = Field(default=1.0, ge=0, allow_inf_nan=False)
    impact_coefficient_bps: float = Field(default=5.0, ge=0, allow_inf_nan=False)
    impact_depth_levels: int = Field(default=5, ge=1)
    snapshot_max_age: timedelta = Field(default=timedelta(seconds=5))
    queue_ahead_fallback: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    funding_rate_per_interval: float = Field(default=0.0, allow_inf_nan=False)
    funding_interval_hours: int = Field(default=8, ge=1)

    @property
    def market_slippage_rate(self) -> float:
        """Market slippage as a decimal fraction."""
        return self.market_slippage_bps / 10_000.0

    @property
    def impact_coefficient_rate(self) -> float:
        """Impact coefficient as a decimal fraction."""
        return self.impact_coefficient_bps / 10_000.0


def notional_value(
    price: float, quantity: float, contract_value: float
) -> float:
    """Notional value in USDT: price x contracts x BTC-per-contract."""
    return price * quantity * contract_value


def bps_cost(
    price: float,
    quantity: float,
    bps: float,
    contract_value: float,
) -> float:
    """Cost in USDT of an adverse move of ``bps`` basis points (>= 0).

    Shared by the slippage and impact terms: both are adverse price
    moves priced on the same notional.
    """
    return price * quantity * contract_value * bps / 10_000.0


def impact_bps(
    order_quantity: float,
    depth: float | None,
    coefficient_bps: float,
) -> float | None:
    """Linear impact in bps: coefficient x min(order / depth, 1).

    ``None`` depth means no valid book was available, so impact is
    unknown — the caller must flag the fill rather than invent a
    depth. A zero depth (empty side) is the worst case: the full
    coefficient applies.
    """
    if depth is None:
        return None
    if depth <= 0:
        return coefficient_bps
    return coefficient_bps * min(order_quantity / depth, 1.0)


def funding_settlements_between(
    start: datetime, end: datetime
) -> tuple[datetime, ...]:
    """Funding settlement times in (start, end] on the 00/08/16 UTC grid.

    A position held across a settlement pays (or receives) funding at
    that settlement; a settlement exactly at ``start`` is not crossed
    by a position opened at ``start``.
    """
    if end <= start:
        return ()
    settlements: list[datetime] = []
    day = start.date()
    last_day = end.date() + timedelta(days=1)
    while day <= last_day:
        for hour in FUNDING_SETTLEMENT_HOURS:
            settlement = datetime.combine(day, time(hour=hour), tzinfo=UTC)
            if start < settlement <= end:
                settlements.append(settlement)
        day += timedelta(days=1)
    return tuple(settlements)


@dataclass(frozen=True)
class FundingSettlement:
    """One funding payment: position held across one settlement."""

    settlement_time: datetime
    position_quantity: float  # signed contracts (+ long, - short)
    price: float  # reference price at settlement (last print at/before it)
    amount: float  # USDT paid (> 0) or received (< 0)


def compute_funding(
    fills: Sequence[Fill],
    *,
    settlements: tuple[datetime, ...],
    price_at: Callable[[datetime], float | None],
    funding_rate: float,
    contract_value: float,
) -> tuple[FundingSettlement, ...]:
    """Funding due on the position built by a set of fills.

    For each settlement, the position is the signed sum of fills
    strictly before the settlement time, valued at the last print
    price at or before the settlement. A positive funding rate means
    longs pay shorts. ``price_at`` returns ``None`` when no print
    precedes the settlement; such settlements are skipped and must be
    disclosed by the caller (a skipped settlement is missing data,
    not zero funding).
    """
    results: list[FundingSettlement] = []
    for settlement in settlements:
        position = sum(
            fill.quantity if fill.side == "buy" else -fill.quantity
            for fill in fills
            if fill.fill_time < settlement
        )
        if position == 0:
            continue
        price = price_at(settlement)
        if price is None:
            continue
        results.append(
            FundingSettlement(
                settlement_time=settlement,
                position_quantity=position,
                price=price,
                amount=position * price * contract_value * funding_rate,
            )
        )
    return tuple(results)
