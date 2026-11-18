"""OKX perpetual-futures fee schedule, verified from OKX's own notice.

Source: OKX, "Advance Notice: Spot and Futures Trading Fee
Adjustment", published 2026-08-21, updated 2026-08-25, effective
2026-09-09 15:00-17:00 (UTC+8), Futures Standard Group pairs, read
2026-11-18 from
https://www.okx.com/en-br/help/advance-notice-spot-and-futures-trading-fee-adjustment-eea

The notice's thresholds are in EUR (EEA publication); the rates are
identical to the global USD schedule, corroborated by independent
reads of okx.com's fee page (2026-09-14, 2026-09-23, 2026-10-11,
2026-11-16). A direct read of https://www.okx.com/fees from this
machine returns the OKX US schedule instead (spot only, Regular
0.20% / 0.35%, no futures table), so the notice — not the geo-
redirected fee page — is the cited source. Fees are charged on the
notional value of the position, not on margin. Maker rates at VIP 7+
are negative: a rebate for adding liquidity, not an error.

Fees change; this table is versioned (``version`` + ``effective_date``
+ ``checked_date``) and must be re-checked before any reuse past its
checked date. Regional schedules differ (US, EEA, SG); this table is
the global/EEA Standard Group schedule for perpetual and expiry
futures. BTC-USDT-SWAP is a Standard Group pair.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from myquant.contracts import StrictContract

#: OKX notice carrying the full futures fee table (see module docstring).
OKX_FEE_SOURCE_URL = (
    "https://www.okx.com/en-br/help/"
    "advance-notice-spot-and-futures-trading-fee-adjustment-eea"
)
OKX_FEE_SOURCE_DESCRIPTION = (
    "OKX, 'Advance Notice: Spot and Futures Trading Fee Adjustment', "
    "Futures Standard Group pairs (perpetual and expiry futures)"
)
#: The notice's rates took effect 2026-09-09 (VIP 7/8 adjusted then;
#: all other tiers unchanged from the prior schedule).
OKX_FEE_EFFECTIVE_DATE = date(2026, 9, 9)
#: Date the table below was read from the OKX notice.
OKX_FEE_CHECKED_DATE = date(2026, 11, 18)

#: Threshold currency as published in the cited notice.
OKX_FEE_THRESHOLD_CURRENCY = "EUR"

REGULAR_TIER = "Regular"


class FeeTier(StrictContract):
    """One VIP tier's maker/taker rates (decimals, e.g. 0.0002 = 0.02%).

    ``maker_rate`` may be negative: VIP 7+ makers earn a rebate.
    Thresholds are the qualification minima as published in the cited
    notice (EUR); ``None`` means the tier has no minimum (Regular).
    The simulator selects a tier by name, never by threshold.
    """

    name: str = Field(min_length=1)
    maker_rate: float = Field(allow_inf_nan=False)
    taker_rate: float = Field(ge=0, allow_inf_nan=False)
    min_assets: float | None = Field(default=None, ge=0)
    min_volume_30d: float | None = Field(default=None, ge=0)


class FeeSchedule(StrictContract):
    """A versioned fee table with its provenance."""

    source_url: str = Field(min_length=1)
    source_description: str = Field(min_length=1)
    effective_date: date
    checked_date: date
    version: int = Field(ge=1)
    threshold_currency: str = Field(min_length=1)
    tiers: tuple[FeeTier, ...] = Field(min_length=1)

    def tier(self, name: str) -> FeeTier:
        """Return one tier by name, or raise for an unknown tier."""
        for candidate in self.tiers:
            if candidate.name == name:
                return candidate
        known = ", ".join(tier.name for tier in self.tiers)
        raise ValueError(f"unknown fee tier {name!r}; known tiers: {known}")

    def rate_for(self, tier_name: str, *, maker: bool) -> float:
        """Maker or taker rate (decimal) for one tier."""
        tier = self.tier(tier_name)
        return tier.maker_rate if maker else tier.taker_rate

    def fee_for(
        self, tier_name: str, *, maker: bool, notional: float
    ) -> float:
        """Exchange fee in USDT on a notional value.

        The fee is charged on notional, not on margin. A negative
        maker rate yields a negative fee (a rebate).
        """
        if notional < 0:
            raise ValueError("notional must be non-negative")
        return notional * self.rate_for(tier_name, maker=maker)


#: OKX futures Standard Group schedule, verified 2026-11-18 (see the
#: module docstring for the source). Default tier is Regular (VIP 0).
OKX_FUTURES_FEES = FeeSchedule(
    source_url=OKX_FEE_SOURCE_URL,
    source_description=OKX_FEE_SOURCE_DESCRIPTION,
    effective_date=OKX_FEE_EFFECTIVE_DATE,
    checked_date=OKX_FEE_CHECKED_DATE,
    version=1,
    threshold_currency=OKX_FEE_THRESHOLD_CURRENCY,
    tiers=(
        FeeTier(name="Regular", maker_rate=0.0002, taker_rate=0.0005),
        FeeTier(
            name="VIP 1",
            maker_rate=0.00016,
            taker_rate=0.00045,
            min_assets=100_000,
            min_volume_30d=5_000_000,
        ),
        FeeTier(
            name="VIP 2",
            maker_rate=0.00015,
            taker_rate=0.00036,
            min_assets=200_000,
            min_volume_30d=10_000_000,
        ),
        FeeTier(
            name="VIP 3",
            maker_rate=0.0001,
            taker_rate=0.00028,
            min_assets=2_000_000,
            min_volume_30d=50_000_000,
        ),
        FeeTier(
            name="VIP 4",
            maker_rate=0.00008,
            taker_rate=0.00027,
            min_assets=5_000_000,
            min_volume_30d=200_000_000,
        ),
        FeeTier(
            name="VIP 5",
            maker_rate=0.00005,
            taker_rate=0.00026,
            min_assets=20_000_000,
            min_volume_30d=600_000_000,
        ),
        FeeTier(
            name="VIP 6",
            maker_rate=0.0,
            taker_rate=0.00025,
            min_assets=50_000_000,
            min_volume_30d=1_000_000_000,
        ),
        FeeTier(
            name="VIP 7",
            maker_rate=-0.00001,
            taker_rate=0.00023,
            min_assets=100_000_000,
            min_volume_30d=1_500_000_000,
        ),
        FeeTier(
            name="VIP 8",
            maker_rate=-0.000025,
            taker_rate=0.0002,
            min_assets=250_000_000,
            min_volume_30d=2_000_000_000,
        ),
        FeeTier(
            name="VIP 9",
            maker_rate=-0.00005,
            taker_rate=0.00015,
            min_assets=500_000_000,
            min_volume_30d=20_000_000_000,
        ),
    ),
)
