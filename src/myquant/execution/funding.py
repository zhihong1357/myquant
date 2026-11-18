"""Historical funding-rate series for perpetuals (Stage 5a).

Closes the Stage 4b data gap: the funding rate is no longer only an
input parameter. A :class:`FundingRateSeries` is a validated,
settlement-time-indexed series of settled funding rates (one row per
8-hour settlement on the 00:00 / 08:00 / 16:00 UTC grid), built from
OKX ``/public/funding-rate-history`` rows by
``research/funding-history/fetch_data.py``.

Sign convention (same as ``myquant.execution.costs.compute_funding``):
a positive rate means longs pay shorts at settlement. The funding
amount for a signed position held across a settlement is
``position x price x contract_value x rate`` — positive means the
holder pays, negative means the holder receives. The rate is the
settled rate for the interval *ending* at the settlement time: a
position held across the settlement pays the rate settled then.

What this module does NOT do: interpolate or extrapolate. A
settlement with no row in the series has an unknown rate, and
``compute_funding_from_series`` skips it (reporting the skip) rather
than inventing a rate. A series that does not cover a window cannot
price funding for that window; the caller must say so.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from pydantic import Field, model_validator

from myquant.adapters.okx_funding import OKXFundingRate
from myquant.contracts import StrictContract, require_utc
from myquant.execution.costs import (
    FUNDING_SETTLEMENT_HOURS,
    FundingSettlement,
    funding_settlements_between,
)
from myquant.execution.orders import Fill


class FundingRateRow(StrictContract):
    """One settled funding rate, indexed by settlement time."""

    settlement_time: datetime
    funding_rate: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_row(self) -> FundingRateRow:
        settlement = require_utc(self.settlement_time)
        if (
            settlement.hour not in FUNDING_SETTLEMENT_HOURS
            or settlement.minute != 0
            or settlement.second != 0
            or settlement.microsecond != 0
        ):
            raise ValueError(
                "settlement_time must fall on the 00:00 / 08:00 / 16:00 UTC grid: "
                f"{settlement.isoformat()}"
            )
        object.__setattr__(self, "settlement_time", settlement)
        return self


@dataclass(frozen=True)
class FundingCoverage:
    """Coverage of a series over the settlement grid.

    ``expected_settlements`` counts every grid slot in
    [first, last]; ``missing_settlements`` lists the grid slots with
    no row. A complete series has no missing slots; anything else is
    a data limitation the caller must report, not fill in.
    """

    first_settlement: datetime
    last_settlement: datetime
    row_count: int
    expected_settlements: int
    missing_settlements: tuple[datetime, ...]


class FundingRateSeries(StrictContract):
    """A validated, settlement-indexed funding-rate series.

    Rows must be strictly increasing in settlement time (duplicates
    are rejected) and every row must sit on the funding grid (checked
    by :class:`FundingRateRow`). The series is immutable; lookups are
    exact-match only.
    """

    instrument: str = Field(min_length=1)
    rows: tuple[FundingRateRow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_series(self) -> FundingRateSeries:
        previous: datetime | None = None
        for row in self.rows:
            if previous is not None and row.settlement_time <= previous:
                raise ValueError(
                    "funding rows must be strictly increasing in settlement time"
                )
            previous = row.settlement_time
        return self

    @classmethod
    def from_okx_rows(
        cls, instrument: str, rows: Sequence[OKXFundingRate]
    ) -> FundingRateSeries:
        """Build a series from adapter rows (any order; sorted here)."""
        ordered = sorted(rows, key=lambda row: row.settlement_time)
        return cls(
            instrument=instrument,
            rows=tuple(
                FundingRateRow(
                    settlement_time=row.settlement_time,
                    funding_rate=row.funding_rate,
                )
                for row in ordered
            ),
        )

    def rate_at(self, settlement: datetime) -> float | None:
        """The settled rate at one settlement, or None when unknown."""
        target = require_utc(settlement)
        for row in self.rows:
            if row.settlement_time == target:
                return row.funding_rate
        return None

    def coverage(self) -> FundingCoverage:
        """Grid completeness over [first, last] settlement."""
        first = self.rows[0].settlement_time
        last = self.rows[-1].settlement_time
        known = {row.settlement_time for row in self.rows}
        missing: list[datetime] = []
        day = first.date()
        expected = 0
        while day <= last.date():
            for hour in FUNDING_SETTLEMENT_HOURS:
                slot = datetime.combine(day, time(hour=hour), tzinfo=UTC)
                if first <= slot <= last:
                    expected += 1
                    if slot not in known:
                        missing.append(slot)
            day += timedelta(days=1)
        return FundingCoverage(
            first_settlement=first,
            last_settlement=last,
            row_count=len(self.rows),
            expected_settlements=expected,
            missing_settlements=tuple(missing),
        )


@dataclass(frozen=True)
class FundingFromSeriesResult:
    """Funding computed from a series, with the skipped settlements."""

    settlements: tuple[FundingSettlement, ...]
    skipped_no_rate: tuple[datetime, ...]
    skipped_no_price: tuple[datetime, ...]

    @property
    def total_amount(self) -> float:
        """Net funding paid (> 0) or received (< 0) in USDT."""
        return sum(item.amount for item in self.settlements)


def compute_funding_from_series(
    fills: Sequence[Fill],
    series: FundingRateSeries,
    *,
    start: datetime,
    end: datetime,
    price_at: Callable[[datetime], float | None],
    contract_value: float,
) -> FundingFromSeriesResult:
    """Funding due on the position built by fills, at historical rates.

    For each settlement in (start, end] on the funding grid, the
    position is the signed sum of fills strictly before the
    settlement, valued at the last print price at or before the
    settlement (``price_at`` — a callable taking a datetime and
    returning a price or None). Settlements with no rate in the
    series, or no price, are skipped and listed in the result: a
    skipped settlement is missing data, not zero funding. The
    single-rate fallback in ``costs.compute_funding`` is unchanged
    and stays available when no series exists.
    """
    settlements = funding_settlements_between(start, end)
    computed: list[FundingSettlement] = []
    skipped_no_rate: list[datetime] = []
    skipped_no_price: list[datetime] = []
    for settlement in settlements:
        position = sum(
            fill.quantity if fill.side == "buy" else -fill.quantity
            for fill in fills
            if fill.fill_time < settlement
        )
        if position == 0:
            continue
        rate = series.rate_at(settlement)
        if rate is None:
            skipped_no_rate.append(settlement)
            continue
        price = price_at(settlement)
        if price is None:
            skipped_no_price.append(settlement)
            continue
        computed.append(
            FundingSettlement(
                settlement_time=settlement,
                position_quantity=position,
                price=float(price),
                amount=position * float(price) * contract_value * rate,
            )
        )
    return FundingFromSeriesResult(
        settlements=tuple(computed),
        skipped_no_rate=tuple(skipped_no_rate),
        skipped_no_price=tuple(skipped_no_price),
    )
