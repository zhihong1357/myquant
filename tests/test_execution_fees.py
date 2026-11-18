"""Tests for the OKX fee schedule. All offline, no network access.

The rate table is pinned to the OKX notice cited in
``myquant.execution.fees`` (effective 2026-09-09, read 2026-11-18);
any change to the table must come with a re-check of the source.
"""

from __future__ import annotations

import pytest

from myquant.execution.fees import OKX_FUTURES_FEES

# (tier, maker rate, taker rate) as published in the OKX notice.
EXPECTED_RATES = (
    ("Regular", 0.0002, 0.0005),
    ("VIP 1", 0.00016, 0.00045),
    ("VIP 2", 0.00015, 0.00036),
    ("VIP 3", 0.0001, 0.00028),
    ("VIP 4", 0.00008, 0.00027),
    ("VIP 5", 0.00005, 0.00026),
    ("VIP 6", 0.0, 0.00025),
    ("VIP 7", -0.00001, 0.00023),
    ("VIP 8", -0.000025, 0.0002),
    ("VIP 9", -0.00005, 0.00015),
)


def test_fee_table_matches_the_okx_notice() -> None:
    assert len(OKX_FUTURES_FEES.tiers) == len(EXPECTED_RATES)
    for name, maker, taker in EXPECTED_RATES:
        tier = OKX_FUTURES_FEES.tier(name)
        assert tier.maker_rate == pytest.approx(maker)
        assert tier.taker_rate == pytest.approx(taker)


def test_regular_tier_is_vip0() -> None:
    assert OKX_FUTURES_FEES.rate_for("Regular", maker=True) == pytest.approx(0.0002)
    assert OKX_FUTURES_FEES.rate_for("Regular", maker=False) == pytest.approx(0.0005)


def test_fee_is_charged_on_notional() -> None:
    # A 10,000 USDT notional at Regular rates: 2.00 maker, 5.00 taker.
    assert OKX_FUTURES_FEES.fee_for("Regular", maker=True, notional=10_000.0) == (
        pytest.approx(2.0)
    )
    assert OKX_FUTURES_FEES.fee_for("Regular", maker=False, notional=10_000.0) == (
        pytest.approx(5.0)
    )


def test_maker_rebate_is_a_negative_fee() -> None:
    # VIP 7 makers earn a rebate of 0.001%: a 10,000 USDT maker fill
    # returns 0.10 USDT instead of costing a fee.
    assert OKX_FUTURES_FEES.fee_for("VIP 7", maker=True, notional=10_000.0) == (
        pytest.approx(-0.1)
    )


def test_unknown_tier_raises() -> None:
    with pytest.raises(ValueError, match="unknown fee tier"):
        OKX_FUTURES_FEES.rate_for("VIP 10", maker=True)


def test_negative_notional_raises() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        OKX_FUTURES_FEES.fee_for("Regular", maker=True, notional=-1.0)


def test_schedule_carries_its_provenance() -> None:
    assert "okx.com" in OKX_FUTURES_FEES.source_url
    assert OKX_FUTURES_FEES.effective_date.isoformat() == "2026-09-09"
    assert OKX_FUTURES_FEES.checked_date.isoformat() == "2026-11-18"
    assert OKX_FUTURES_FEES.version >= 1
