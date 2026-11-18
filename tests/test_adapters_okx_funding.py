"""Tests for the OKX funding-rate adapter (offline, frozen fixtures)."""

import json
from datetime import UTC, datetime

import pytest

from myquant.adapters.okx_funding import (
    OKXFundingError,
    fetch_current_funding_rate,
    fetch_funding_history,
    parse_funding_history_response,
    parse_funding_rate_response,
)

INST = "BTC-USDT-SWAP"

# Frozen fixture: the first page of the live response, captured 2026-11-19.
HISTORY_PAYLOAD = json.dumps(
    {
        "code": "0",
        "msg": "",
        "data": [
            {
                "formulaType": "withRate",
                "fundingRate": "0.0000634843947535",
                "fundingTime": "1795017600000",
                "instId": INST,
                "instType": "SWAP",
                "method": "current_period",
                "realizedRate": "0.0000634843947535",
            },
            {
                "formulaType": "withRate",
                "fundingRate": "0.0000239227616186",
                "fundingTime": "1794988800000",
                "instId": INST,
                "instType": "SWAP",
                "method": "current_period",
                "realizedRate": "0.0000239227616186",
            },
            {
                "formulaType": "withRate",
                "fundingRate": "-0.0000108871264091",
                "fundingTime": "1794960000000",
                "instId": INST,
                "instType": "SWAP",
                "method": "current_period",
                "realizedRate": "-0.0000108871264091",
            },
        ],
    }
).encode()

CURRENT_PAYLOAD = json.dumps(
    {
        "code": "0",
        "msg": "",
        "data": [
            {
                "formulaType": "withRate",
                "fundingRate": "0.0000530146093188",
                "fundingTime": "1795046400000",
                "impactValue": "20000.0000000000000000",
                "instId": INST,
                "instType": "SWAP",
                "interestRate": "0.0001000000000000",
                "maxFundingRate": "0.00375",
                "method": "current_period",
                "minFundingRate": "-0.00375",
                "nextFundingRate": "",
                "nextFundingTime": "1795075200000",
                "premium": "-0.0005598130161269",
                "prevFundingTime": "1795017600000",
                "settFundingRate": "0.0000634843947535",
                "settState": "settled",
                "ts": "1795027743781",
            }
        ],
    }
).encode()


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _history_page(rows):
    """Build a history payload from (ms, rate) pairs, newest first."""
    return json.dumps(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "formulaType": "withRate",
                    "fundingRate": str(rate),
                    "fundingTime": str(ms),
                    "instId": INST,
                    "instType": "SWAP",
                    "method": "current_period",
                    "realizedRate": str(rate),
                }
                for ms, rate in rows
            ],
        }
    ).encode()


def test_parse_history_page_oldest_first():
    rates = parse_funding_history_response(HISTORY_PAYLOAD, inst_id=INST)
    assert len(rates) == 3
    # Oldest first after parsing.
    assert rates[0].settlement_time == datetime(2026, 11, 18, 0, 0, tzinfo=UTC)
    assert rates[0].funding_rate == pytest.approx(-0.0000108871264091)
    assert rates[1].settlement_time == datetime(2026, 11, 18, 8, 0, tzinfo=UTC)
    assert rates[2].settlement_time == datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
    assert rates[2].funding_rate == pytest.approx(0.0000634843947535)
    assert rates[2].realized_rate == rates[2].funding_rate
    assert rates[2].method == "current_period"
    assert all(rate.instrument == INST for rate in rates)


def test_parse_history_rejects_error_code():
    payload = json.dumps({"code": "51000", "msg": "boom", "data": []}).encode()
    with pytest.raises(OKXFundingError, match="51000"):
        parse_funding_history_response(payload, inst_id=INST)


def test_parse_history_rejects_wrong_instrument():
    payload = json.dumps(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "formulaType": "withRate",
                    "fundingRate": "0.0001",
                    "fundingTime": "1795017600000",
                    "instId": "ETH-USDT-SWAP",
                    "instType": "SWAP",
                    "method": "current_period",
                    "realizedRate": "0.0001",
                }
            ],
        }
    ).encode()
    with pytest.raises(OKXFundingError, match="ETH-USDT-SWAP"):
        parse_funding_history_response(payload, inst_id=INST)


def test_parse_history_rejects_non_newest_first_order():
    rows = [
        (_ms(datetime(2026, 11, 19, 0, 0, tzinfo=UTC)), 0.0001),
        (_ms(datetime(2026, 11, 19, 8, 0, tzinfo=UTC)), 0.0002),
    ]
    with pytest.raises(OKXFundingError, match="newest-first"):
        parse_funding_history_response(_history_page(rows), inst_id=INST)


def test_parse_history_rejects_duplicate_settlement():
    rows = [
        (_ms(datetime(2026, 11, 19, 8, 0, tzinfo=UTC)), 0.0002),
        (_ms(datetime(2026, 11, 19, 8, 0, tzinfo=UTC)), 0.0002),
    ]
    with pytest.raises(OKXFundingError, match="newest-first|duplicate"):
        parse_funding_history_response(_history_page(rows), inst_id=INST)


def test_parse_history_rejects_bad_fields():
    payload = json.dumps(
        {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "formulaType": "withRate",
                    "fundingRate": "not-a-number",
                    "fundingTime": "1795017600000",
                    "instId": INST,
                    "instType": "SWAP",
                    "method": "current_period",
                    "realizedRate": "0.0001",
                }
            ],
        }
    ).encode()
    with pytest.raises(OKXFundingError, match="bad fields"):
        parse_funding_history_response(payload, inst_id=INST)


def test_parse_current_funding_rate():
    current, _ = (
        parse_funding_rate_response(CURRENT_PAYLOAD, inst_id=INST),
        None,
    )
    assert current.instrument == INST
    assert current.funding_rate == pytest.approx(0.0000530146093188)
    assert current.funding_time == datetime(2026, 11, 19, 0, 0, tzinfo=UTC)
    assert current.next_funding_time == datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
    assert current.prev_funding_time == datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
    # The settled rate for the interval ending 16:00 on 2026-11-18 matches
    # the history row at that settlement time exactly.
    assert current.settled_funding_rate == pytest.approx(0.0000634843947535)
    assert current.max_funding_rate == pytest.approx(0.00375)
    assert current.min_funding_rate == pytest.approx(-0.00375)


def test_fetch_current_funding_rate_uses_transport():
    seen: list[str] = []

    def transport(url: str) -> bytes:
        seen.append(url)
        return CURRENT_PAYLOAD

    current, page = fetch_current_funding_rate(INST, transport=transport)
    assert current.instrument == INST
    assert "funding-rate?instId=BTC-USDT-SWAP" in seen[0]
    assert page.payload == CURRENT_PAYLOAD


def _fake_transport(pages_by_after):
    """Transport serving canned pages keyed by the `after` cursor."""

    def transport(url: str) -> bytes:
        if "after=" in url:
            cursor = int(url.split("after=")[1].split("&")[0])
        else:
            cursor = None
        return pages_by_after[cursor]

    return transport


def test_fetch_history_pages_backwards_with_after():
    t16 = _ms(datetime(2026, 11, 19, 16, 0, tzinfo=UTC))
    t08 = _ms(datetime(2026, 11, 19, 8, 0, tzinfo=UTC))
    t00 = _ms(datetime(2026, 11, 19, 0, 0, tzinfo=UTC))
    t_prev16 = _ms(datetime(2026, 11, 18, 16, 0, tzinfo=UTC))
    t_prev08 = _ms(datetime(2026, 11, 18, 8, 0, tzinfo=UTC))
    pages = {
        None: _history_page([(t16, 0.0003), (t08, 0.0002), (t00, 0.0001)]),
        t00: _history_page([(t_prev16, 0.0004), (t_prev08, 0.0005)]),
        t_prev08: _history_page([]),
    }
    fetched = fetch_funding_history(
        INST, transport=_fake_transport(pages), delay_seconds=0.0
    )
    assert [r.funding_rate for r in fetched.rates] == [
        0.0005,
        0.0004,
        0.0001,
        0.0002,
        0.0003,
    ]
    assert len(fetched.pages) == 3


def test_fetch_history_respects_start_and_end():
    t16 = _ms(datetime(2026, 11, 19, 16, 0, tzinfo=UTC))
    t08 = _ms(datetime(2026, 11, 19, 8, 0, tzinfo=UTC))
    t00 = _ms(datetime(2026, 11, 19, 0, 0, tzinfo=UTC))
    pages = {
        None: _history_page([(t16, 0.0003), (t08, 0.0002), (t00, 0.0001)]),
    }
    fetched = fetch_funding_history(
        INST,
        start=datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        end=datetime(2026, 11, 19, 16, 0, tzinfo=UTC),
        transport=_fake_transport(pages),
        delay_seconds=0.0,
    )
    # [start, end): only the 08:00 row.
    assert len(fetched.rates) == 1
    assert fetched.rates[0].settlement_time == datetime(
        2026, 11, 19, 8, 0, tzinfo=UTC
    )


def test_fetch_history_stops_at_start():
    t16 = _ms(datetime(2026, 11, 19, 16, 0, tzinfo=UTC))
    t08 = _ms(datetime(2026, 11, 19, 8, 0, tzinfo=UTC))
    calls: list[str] = []

    def transport(url: str) -> bytes:
        calls.append(url)
        return _history_page([(t16, 0.0003), (t08, 0.0002)])

    fetched = fetch_funding_history(
        INST,
        start=datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        transport=transport,
        delay_seconds=0.0,
    )
    # Oldest row (08:00) is at start, so paging stops after one page.
    assert len(calls) == 1
    assert len(fetched.rates) == 2


def test_fetch_history_rejects_non_advancing_cursor():
    t16 = _ms(datetime(2026, 11, 19, 16, 0, tzinfo=UTC))

    def transport(url: str) -> bytes:
        return _history_page([(t16, 0.0003)])

    with pytest.raises(OKXFundingError, match="did not advance"):
        fetch_funding_history(INST, transport=transport, delay_seconds=0.0)


def test_fetch_history_validates_arguments():
    with pytest.raises(ValueError, match="page_size"):
        fetch_funding_history(INST, page_size=101)
    with pytest.raises(ValueError, match="end must be after start"):
        fetch_funding_history(
            INST,
            start=datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
            end=datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        )
