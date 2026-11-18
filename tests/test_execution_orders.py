"""Tests for paper orders. All offline, no network access."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from myquant.execution.orders import PaperOrder

T0 = datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)


def _order(**overrides) -> PaperOrder:
    fields: dict = {
        "order_id": "o1",
        "instrument_id": "crypto:btc-usdt-perp",
        "venue": "okx",
        "side": "buy",
        "order_type": "limit",
        "quantity": 1.0,
        "limit_price": 65000.0,
        "decision_time": T0,
        "available_at": T0,
        "latency": timedelta(milliseconds=100),
    }
    fields.update(overrides)
    return PaperOrder(**fields)


def test_arrival_time_is_available_plus_latency() -> None:
    order = _order()
    assert order.arrival_time == T0 + timedelta(milliseconds=100)


def test_zero_quantity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _order(quantity=0.0)


def test_negative_quantity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _order(quantity=-1.0)


def test_limit_order_requires_limit_price() -> None:
    with pytest.raises(ValidationError):
        _order(limit_price=None)


def test_limit_price_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _order(limit_price=0.0)


def test_market_order_must_not_carry_limit_price() -> None:
    with pytest.raises(ValidationError):
        _order(order_type="market", limit_price=65000.0)


def test_market_order_without_limit_price_is_valid() -> None:
    order = _order(order_type="market", limit_price=None)
    assert order.limit_price is None


def test_negative_latency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _order(latency=timedelta(milliseconds=-1))


def test_available_before_decision_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _order(available_at=T0 - timedelta(seconds=1))


def test_cancel_at_or_before_decision_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _order(cancel_time=T0)
    with pytest.raises(ValidationError):
        _order(cancel_time=T0 - timedelta(seconds=1))


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _order(decision_time=datetime(2026, 11, 18, 5, 0, 0))
