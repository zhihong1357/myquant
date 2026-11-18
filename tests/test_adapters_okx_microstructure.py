"""Tests for the OKX microstructure adapter (trades, books, ticker).

All tests run offline against frozen fixtures; no test touches the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from myquant.adapters.okx_microstructure import (
    OKXMicrostructureError,
    fetch_books_snapshot,
    fetch_ticker,
    fetch_trades_history,
    parse_books_response,
    parse_ticker_response,
    parse_trades_response,
)

INST = "BTC-USDT-SWAP"


def _ms(year: int, month: int, day: int, hour: int, minute: int, second: int) -> int:
    return int(
        datetime(year, month, day, hour, minute, second, tzinfo=UTC).timestamp() * 1000
    )


def _trade_row(
    trade_id: int,
    ms: int,
    price: str = "65000",
    size: str = "0.5",
    side: str = "buy",
    inst_id: str = INST,
) -> dict[str, str]:
    return {
        "instId": inst_id,
        "tradeId": str(trade_id),
        "px": price,
        "sz": size,
        "side": side,
        "ts": str(ms),
        "source": "0",
    }


def _payload(rows: list) -> bytes:
    return json.dumps({"code": "0", "msg": "", "data": rows}).encode("utf-8")


# Frozen trades page: newest first, as the API returns it.
TRADES_FIXTURE = _payload(
    [
        _trade_row(103, _ms(2026, 11, 18, 5, 0, 3), "65000", "0.5", "buy"),
        _trade_row(102, _ms(2026, 11, 18, 5, 0, 2), "64999", "0.2", "sell"),
        _trade_row(101, _ms(2026, 11, 18, 5, 0, 1), "65001", "1.0", "buy"),
    ]
)


def test_parse_trades_returns_oldest_first() -> None:
    page = parse_trades_response(TRADES_FIXTURE, inst_id=INST)
    assert [t.trade_id for t in page.trades] == [101, 102, 103]
    assert page.trades[0].event_time == datetime(2026, 11, 18, 5, 0, 1, tzinfo=UTC)
    assert page.trades[0].price == 65001.0
    assert page.trades[0].size == 1.0
    assert page.trades[1].side == "sell"
    assert page.trades[2].source == "0"
    assert page.rejected == ()


def test_parse_trades_same_millisecond_keeps_id_order() -> None:
    # Two trades in the same millisecond: trade-ID order decides.
    payload = _payload(
        [
            _trade_row(202, _ms(2026, 11, 18, 5, 0, 0), "65000", "0.1", "buy"),
            _trade_row(201, _ms(2026, 11, 18, 5, 0, 0), "65000", "0.1", "sell"),
        ]
    )
    page = parse_trades_response(payload, inst_id=INST)
    assert [t.trade_id for t in page.trades] == [201, 202]


def test_parse_trades_rejects_bad_rows_and_counts_them() -> None:
    payload = _payload(
        [
            _trade_row(110, _ms(2026, 11, 18, 5, 0, 10), "65000", "0.5", "buy"),
            _trade_row(109, _ms(2026, 11, 18, 5, 0, 9), "65000", "0.5", "hold"),
            _trade_row(108, _ms(2026, 11, 18, 5, 0, 8), "0", "0.5", "buy"),
            _trade_row(107, _ms(2026, 11, 18, 5, 0, 7), "65000", "-1", "sell"),
            _trade_row(106, _ms(2026, 11, 18, 5, 0, 6), "65000", "0.5", "buy"),
            _trade_row(106, _ms(2026, 11, 18, 5, 0, 6), "65000", "0.5", "buy"),
            _trade_row(
                105, _ms(2026, 11, 18, 5, 0, 5), "65000", "0.5", "buy",
                inst_id="ETH-USDT-SWAP",
            ),
            {"instId": INST, "tradeId": "104", "px": "65000"},
        ]
    )
    page = parse_trades_response(payload, inst_id=INST)
    assert [t.trade_id for t in page.trades] == [106, 110]
    assert len(page.rejected) == 6
    reasons = " | ".join(r.reason for r in page.rejected)
    assert "bad side" in reasons
    assert "duplicate trade_id 106" in reasons
    assert "ETH-USDT-SWAP" in reasons


def test_parse_trades_rejects_broken_page_order() -> None:
    payload = _payload(
        [
            _trade_row(101, _ms(2026, 11, 18, 5, 0, 1)),
            _trade_row(102, _ms(2026, 11, 18, 5, 0, 2)),
        ]
    )
    with pytest.raises(OKXMicrostructureError, match="newest-first"):
        parse_trades_response(payload, inst_id=INST)


def test_parse_trades_rejects_error_code_and_bad_json() -> None:
    payload = json.dumps({"code": "50001", "msg": "rate limited", "data": []})
    with pytest.raises(OKXMicrostructureError, match="50001"):
        parse_trades_response(payload.encode(), inst_id=INST)
    with pytest.raises(OKXMicrostructureError, match="not valid JSON"):
        parse_trades_response(b"{not json", inst_id=INST)
    with pytest.raises(OKXMicrostructureError, match="no 'data' list"):
        parse_trades_response(
            json.dumps({"code": "0", "msg": "", "data": {}}).encode(), inst_id=INST
        )


class _FakeTradesTransport:
    """Simulates history-trades pagination over a fixed trade list."""

    def __init__(self, rows_newest_first: list[dict[str, str]]) -> None:
        self.rows = rows_newest_first
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        after = None
        if "after=" in url:
            after = int(url.split("after=")[1].split("&")[0])
        limit = int(url.split("limit=")[1].split("&")[0])
        pool = self.rows
        if after is not None:
            pool = [r for r in pool if int(r["tradeId"]) < after]
        return _payload(pool[:limit])


def _trades_rows_newest_first() -> list[dict[str, str]]:
    # 12 trades, one per second, 05:00:00..05:00:11, ids 200..211.
    rows = [
        _trade_row(
            200 + i,
            _ms(2026, 11, 18, 5, 0, i),
            "65000",
            "0.1",
            "buy" if i % 2 == 0 else "sell",
        )
        for i in range(12)
    ]
    return list(reversed(rows))


def test_fetch_trades_history_pages_backwards_and_filters_window() -> None:
    transport = _FakeTradesTransport(_trades_rows_newest_first())
    result = fetch_trades_history(
        INST,
        start=datetime(2026, 11, 18, 5, 0, 3, tzinfo=UTC),
        end=datetime(2026, 11, 18, 5, 0, 9, tzinfo=UTC),
        page_size=5,
        delay_seconds=0.0,
        transport=transport,
    )
    assert [t.trade_id for t in result.trades] == [203, 204, 205, 206, 207, 208]
    assert result.skipped_after_end == 3  # trades 209, 210, 211
    assert result.rejected == ()
    assert len(result.pages) == 2  # page 2's oldest trade predates start, so it stops
    assert "after=" not in result.pages[0].url
    assert "after=207" in result.pages[1].url


def test_fetch_trades_history_calls_on_page_per_page() -> None:
    transport = _FakeTradesTransport(_trades_rows_newest_first())
    seen: list[str] = []
    fetch_trades_history(
        INST,
        start=datetime(2026, 11, 18, 5, 0, 3, tzinfo=UTC),
        end=datetime(2026, 11, 18, 5, 0, 9, tzinfo=UTC),
        page_size=5,
        delay_seconds=0.0,
        transport=transport,
        on_page=lambda page: seen.append(page.url),
    )
    assert len(seen) == 2
    assert "after=" not in seen[0]
    assert "after=207" in seen[1]


def test_fetch_trades_history_stops_on_empty_page() -> None:
    transport = _FakeTradesTransport(_trades_rows_newest_first())
    result = fetch_trades_history(
        INST,
        start=datetime(2026, 11, 18, 4, 0, 0, tzinfo=UTC),
        end=datetime(2026, 11, 18, 5, 0, 12, tzinfo=UTC),
        page_size=5,
        delay_seconds=0.0,
        transport=transport,
    )
    assert len(result.trades) == 12
    assert result.pages[-1].payload == _payload([])


def test_fetch_trades_history_validates_arguments() -> None:
    with pytest.raises(ValueError, match="end must be after start"):
        fetch_trades_history(
            INST,
            start=datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC),
            end=datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC),
            transport=_FakeTradesTransport([]),
        )
    with pytest.raises(ValueError, match="page_size"):
        fetch_trades_history(
            INST,
            start=datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC),
            end=datetime(2026, 11, 18, 6, 0, 0, tzinfo=UTC),
            page_size=500,
            transport=_FakeTradesTransport([]),
        )


BOOKS_FIXTURE = json.dumps(
    {
        "code": "0",
        "msg": "",
        "data": [
            {
                "asks": [
                    ["65000.1", "10.5", "0", "4"],
                    ["65000.2", "3.0", "0", "2"],
                    ["65000.3", "1.0", "0", "1"],
                ],
                "bids": [
                    ["65000.0", "20.0", "0", "7"],
                    ["64999.9", "5.0", "0", "3"],
                    ["64999.8", "2.5", "0", "1"],
                ],
                "ts": str(_ms(2026, 11, 18, 5, 0, 0)),
                "seqId": "987654",
            }
        ],
    }
).encode("utf-8")


def test_parse_books_snapshot() -> None:
    snap = parse_books_response(BOOKS_FIXTURE, inst_id=INST)
    assert snap.snapshot_time == datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)
    assert snap.seq_id == 987654
    assert [level.price for level in snap.asks] == [65000.1, 65000.2, 65000.3]
    assert snap.asks[0].size == 10.5
    assert snap.asks[0].order_count == 4
    assert [level.price for level in snap.bids] == [65000.0, 64999.9, 64999.8]
    assert snap.bids[0].order_count == 7


def test_parse_books_rejects_malformed_levels() -> None:
    def _books_with(asks: list, bids: list) -> bytes:
        return json.dumps(
            {
                "code": "0",
                "msg": "",
                "data": [
                    {
                        "asks": asks,
                        "bids": bids,
                        "ts": str(_ms(2026, 11, 18, 5, 0, 0)),
                        "seqId": "1",
                    }
                ],
            }
        ).encode("utf-8")

    with pytest.raises(OKXMicrostructureError, match="4 elements"):
        parse_books_response(
            _books_with([["65000.1", "10.5", "0"]], [["65000.0", "20.0", "0", "7"]]),
            inst_id=INST,
        )
    with pytest.raises(OKXMicrostructureError, match="deprecated"):
        parse_books_response(
            _books_with(
                [["65000.1", "10.5", "3", "4"]],
                [["65000.0", "20.0", "0", "7"]],
            ),
            inst_id=INST,
        )
    with pytest.raises(OKXMicrostructureError, match="strictly ascending"):
        parse_books_response(
            _books_with(
                [["65000.2", "3.0", "0", "2"], ["65000.1", "10.5", "0", "4"]],
                [["65000.0", "20.0", "0", "7"]],
            ),
            inst_id=INST,
        )
    with pytest.raises(OKXMicrostructureError, match="strictly descending"):
        parse_books_response(
            _books_with(
                [["65000.1", "10.5", "0", "4"]],
                [["64999.9", "5.0", "0", "3"], ["65000.0", "20.0", "0", "7"]],
            ),
            inst_id=INST,
        )
    with pytest.raises(OKXMicrostructureError, match="exactly one snapshot"):
        parse_books_response(
            json.dumps({"code": "0", "msg": "", "data": []}).encode(), inst_id=INST
        )


def test_fetch_books_snapshot_uses_transport() -> None:
    transport = lambda url: BOOKS_FIXTURE  # noqa: E731
    snap, page = fetch_books_snapshot(INST, depth=3, transport=transport)
    assert snap.asks[0].price == 65000.1
    assert "sz=3" in page.url
    with pytest.raises(ValueError, match="depth"):
        fetch_books_snapshot(INST, depth=401, transport=transport)


TICKER_FIXTURE = json.dumps(
    {
        "code": "0",
        "msg": "",
        "data": [
            {
                "bidPx": "65000.0",
                "bidSz": "20.0",
                "askPx": "65000.1",
                "askSz": "10.5",
                "last": "65000.0",
                "ts": str(_ms(2026, 11, 18, 5, 0, 0)),
            }
        ],
    }
).encode("utf-8")


def test_parse_ticker_response() -> None:
    ticker = parse_ticker_response(TICKER_FIXTURE, inst_id=INST)
    assert ticker.bid_price == 65000.0
    assert ticker.ask_price == 65000.1
    assert ticker.bid_size == 20.0
    assert ticker.ask_size == 10.5
    assert ticker.last_price == 65000.0
    assert ticker.ticker_time == datetime(2026, 11, 18, 5, 0, 0, tzinfo=UTC)


def test_fetch_ticker_uses_transport() -> None:
    transport = lambda url: TICKER_FIXTURE  # noqa: E731
    ticker, page = fetch_ticker(INST, transport=transport)
    assert ticker.bid_price == 65000.0
    assert "/ticker?instId=BTC-USDT-SWAP" in page.url
