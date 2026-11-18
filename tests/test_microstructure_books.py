"""Tests for quote normalization. All offline, no network access."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from myquant.adapters.okx_microstructure import OKXBookLevel, OKXBookSnapshot
from myquant.microstructure.books import BookSnapshot, normalize_books_snapshot

INGESTED = datetime(2026, 11, 18, 7, 0, 0, tzinfo=UTC)


def _okx_snapshot(
    asks: list[tuple[float, float, int]],
    bids: list[tuple[float, float, int]],
) -> OKXBookSnapshot:
    return OKXBookSnapshot(
        instrument="BTC-USDT-SWAP",
        snapshot_time=datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC),
        seq_id=987654,
        asks=tuple(
            OKXBookLevel(price=p, size=s, order_count=n) for p, s, n in asks
        ),
        bids=tuple(
            OKXBookLevel(price=p, size=s, order_count=n) for p, s, n in bids
        ),
    )


def _standard_snapshot() -> OKXBookSnapshot:
    return _okx_snapshot(
        asks=[(65000.1, 10.5, 4), (65000.2, 3.0, 2), (65000.3, 1.0, 1)],
        bids=[(65000.0, 20.0, 7), (64999.9, 5.0, 3), (64999.8, 2.5, 1)],
    )


def test_normalize_derives_best_mid_spread() -> None:
    result = normalize_books_snapshot(
        _standard_snapshot(),
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    snap = result.snapshot
    assert result.quality_issues == ()
    assert snap.best_bid == 65000.0
    assert snap.best_ask == 65000.1
    assert snap.mid == pytest.approx(65000.05)
    assert snap.spread == pytest.approx(0.1)
    assert snap.spread_bps == pytest.approx(0.1 / 65000.05 * 10_000)
    assert snap.seq_id == 987654
    assert snap.available_at == snap.snapshot_time


def test_normalize_derives_depth_imbalance_microprice() -> None:
    result = normalize_books_snapshot(
        _standard_snapshot(),
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    snap = result.snapshot
    assert snap.depth_bid(2) == pytest.approx(25.0)
    assert snap.depth_ask(2) == pytest.approx(13.5)
    assert snap.depth_total(2) == pytest.approx(38.5)
    assert snap.imbalance(2) == pytest.approx((25.0 - 13.5) / 38.5)
    assert snap.imbalance(1) == pytest.approx((20.0 - 10.5) / 30.5)
    # Microprice: (bid * ask size + ask * bid size) / total best size.
    expected = (65000.0 * 10.5 + 65000.1 * 20.0) / 30.5
    assert snap.microprice == pytest.approx(expected)
    # Depth beyond the available levels sums what exists.
    assert snap.depth_bid(20) == pytest.approx(27.5)
    assert snap.depth_ask(20) == pytest.approx(14.5)
    with pytest.raises(ValueError, match="levels must be >= 1"):
        snap.depth_bid(0)


def test_normalize_flags_crossed_book_but_keeps_snapshot() -> None:
    result = normalize_books_snapshot(
        _okx_snapshot(
            asks=[(65000.0, 10.0, 1)],
            bids=[(65000.0, 20.0, 1)],
        ),
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert len(result.quality_issues) == 1
    assert "crossed book" in result.quality_issues[0]
    assert result.snapshot.best_bid == 65000.0
    assert result.snapshot.spread == pytest.approx(0.0)


def test_normalize_flags_empty_sides() -> None:
    result = normalize_books_snapshot(
        _okx_snapshot(asks=[(65000.1, 10.0, 1)], bids=[]),
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert "empty bid side" in result.quality_issues
    assert result.snapshot.best_bid is None
    assert result.snapshot.mid is None
    assert result.snapshot.spread is None
    assert result.snapshot.spread_bps is None
    assert result.snapshot.microprice is None
    assert result.snapshot.imbalance(5) == pytest.approx(-1.0)

    both_empty = normalize_books_snapshot(
        _okx_snapshot(asks=[], bids=[]),
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert len(both_empty.quality_issues) == 2
    assert both_empty.snapshot.imbalance(5) is None


def test_imbalance_none_when_both_depths_zero() -> None:
    result = normalize_books_snapshot(
        _okx_snapshot(
            asks=[(65000.1, 0.0, 0)],
            bids=[(65000.0, 0.0, 0)],
        ),
        instrument_id="crypto:btc-usdt-perp",
        venue="okx",
        source_id="okx-public",
        ingested_at=INGESTED,
    )
    assert result.snapshot.imbalance(5) is None
    assert result.snapshot.microprice is None


def test_snapshot_validator_rejects_misordered_levels() -> None:
    from myquant.microstructure.books import BookLevel

    with pytest.raises(ValueError, match="strictly ascending"):
        BookSnapshot(
            instrument_id="crypto:btc-usdt-perp",
            venue="okx",
            snapshot_time=datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC),
            available_at=datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC),
            ingested_at=INGESTED,
            seq_id=1,
            asks=(
                BookLevel(price=65000.2, size=1.0, order_count=1),
                BookLevel(price=65000.1, size=1.0, order_count=1),
            ),
            bids=(BookLevel(price=65000.0, size=1.0, order_count=1),),
            source_id="okx-public",
        )
