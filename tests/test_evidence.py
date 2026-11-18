"""Tests for the evidence analyst (Stage 6b).

All offline: every check runs against recorded fixtures, and no
test imports the fetch layer. Network behaviour is the probe
script's job, not the tests'.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from myquant.evidence import (
    CheckKind,
    CheckResult,
    CheckStatus,
    EvidenceRegistry,
    EvidenceReport,
    FreshnessResult,
    FreshnessStatus,
    LagKind,
    PanelFreshnessConfig,
    ProbeKind,
    RecordedOnlyItem,
    SourceProbeResult,
    check_deribit_dvol,
    check_deribit_instruments,
    check_discontinued_series_end,
    check_fed_page,
    check_fiscal_api,
    check_fred_csv,
    check_hyperliquid_mids,
    check_okx_candles,
    check_panel_freshness,
    check_probe,
    check_reachable,
    check_skipped,
    check_yahoo_chart,
    expected_latest_cpi_month,
    expected_latest_dvol,
    expected_latest_fred,
    expected_latest_okx_daily,
    expected_latest_yahoo,
    previous_trading_day,
    render_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Fixtures: recorded payloads (small, hand-built).
# ---------------------------------------------------------------------------


def _okx_payload(*, code: str = "0", confirmed: bool = True) -> bytes:
    # Two 1D rows, newest first: the forming bar (today 16:00 UTC)
    # and the latest confirmed bar (yesterday 16:00 UTC).
    rows = [
        [
            str(_ms(datetime(2026, 11, 18, 16, 0, tzinfo=UTC))),
            "90000",
            "91000",
            "89000",
            "90500",
            "100",
            "9000000",
            "9000000",
            "0",
        ],
        [
            str(_ms(datetime(2026, 11, 17, 16, 0, tzinfo=UTC))),
            "88000",
            "90000",
            "87000",
            "89500",
            "120",
            "10740000",
            "10740000",
            "1" if confirmed else "0",
        ],
    ]
    return json.dumps({"code": code, "msg": "", "data": rows}).encode()


def _deribit_instruments_payload(*, expiries: tuple[datetime, ...]) -> bytes:
    rows = []
    for index, expiry in enumerate(expiries):
        rows.append(
            {
                "instrument_name": f"BTC-27NOV26-{90000 + index * 1000}-C",
                "base_currency": "BTC",
                "kind": "option",
                "option_type": "call",
                "strike": 90000 + index * 1000,
                "expiration_timestamp": _ms(expiry),
            }
        )
    return json.dumps({"result": rows}).encode()


def _dvol_payload() -> bytes:
    return json.dumps(
        {
            "result": {
                "data": [
                    [_ms(datetime(2026, 11, 16, tzinfo=UTC)), 55.0, 57.0, 54.0, 56.0],
                    [_ms(datetime(2026, 11, 17, tzinfo=UTC)), 56.0, 58.0, 55.0, 57.0],
                ]
            }
        }
    ).encode()


def _fred_payload(*, series_id: str = "VIXCLS") -> bytes:
    # 2026-11-17 carries an empty field (missing), not ".".
    text = (
        f"observation_date,{series_id}\n"
        "2026-11-16,18.50\n"
        "2026-11-17,\n"
        "2026-11-18,19.20\n"
    )
    return text.encode()


def _yahoo_payload(*, symbol: str = "^GSPC", meta_symbol: str = "^GSPC") -> bytes:
    return json.dumps(
        {
            "chart": {
                "error": None,
                "result": [
                    {
                        "meta": {"symbol": meta_symbol, "longName": "S&P 500"},
                        "timestamp": [
                            int(datetime(2026, 11, 16, 14, 30, tzinfo=UTC).timestamp()),
                            int(datetime(2026, 11, 17, 14, 30, tzinfo=UTC).timestamp()),
                            int(datetime(2026, 11, 18, 14, 30, tzinfo=UTC).timestamp()),
                        ],
                        "indicators": {
                            "quote": [
                                {"close": [6700.0, None, 6720.0]},
                            ]
                        },
                    }
                ],
            }
        }
    ).encode()


def _fed_payload(*, markers: bool = True) -> bytes:
    body = (
        "<html><body><h1>Federal Open Market Committee</h1>"
        "<p>FOMC meeting calendar 2026</p></body></html>"
        if markers
        else "<html><body><p>unrelated page</p></body></html>"
    )
    return body.encode()


def _fiscal_payload() -> bytes:
    return json.dumps(
        {
            "data": [
                {"auction_date": "2026-10-20", "security_type": "Note"},
                {"auction_date": "2026-10-22", "security_type": "Bond"},
            ],
            "meta": {"total-count": 2},
        }
    ).encode()


def _hyperliquid_payload() -> bytes:
    # Live shape (observed 2026-11-19): a flat symbol -> price map,
    # not a {"mids": [...]} wrapper.
    return json.dumps(
        {"BTC": "62460.5", "ETH": "1764.05", "SOL": "73.1605"}
    ).encode()


def _registry_dict(*, duplicate: bool = False) -> dict:
    source = {
        "source_id": "fred",
        "provider": "Federal Reserve Bank of St. Louis",
        "description": "FRED free fredgraph CSV",
        "base_url": "https://fred.stlouisfed.org/graph/fredgraph.csv",
        "auth": "none — public, no key",
        "used_by": ["move-vix-003"],
        "endpoints": [
            {
                "path": "/graph/fredgraph.csv?id=<SERIES>",
                "used_for": "daily series values",
                "expected_structure": "CSV with DATE and value columns",
            }
        ],
        "quirks": [
            {
                "statement": "Missing values are empty fields.",
                "verified_by": "study 003 (move-vix-003)",
                "verified_date": "2026-11-18",
                "recheck": None,
                "recorded_only": False,
            }
        ],
        "retention": "Full history served; current vintage.",
        "probe_kind": "automatic",
        "probes": [
            {
                "key": "fred:VIXCLS",
                "method": "GET",
                "url_template": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS",
                "user_agent": None,
                "timeout_seconds": 30.0,
                "check_kind": "fred_csv",
                "check_params": {"series_id": "VIXCLS"},
                "body_template": None,
            }
        ],
        "manual_check": None,
        "last_verified": "2026-11-18",
    }
    sources = [source, dict(source)] if duplicate else [source]
    return {"schema_version": 1, "sources": sources}


# ---------------------------------------------------------------------------
# Registry validation.
# ---------------------------------------------------------------------------


def test_registry_duplicate_id_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        EvidenceRegistry.model_validate(_registry_dict(duplicate=True))


def test_registry_unknown_source_rejected() -> None:
    registry = EvidenceRegistry.model_validate(_registry_dict())
    with pytest.raises(ValueError, match="unknown source id"):
        registry.source("no-such-source")


def test_registry_unknown_probe_rejected() -> None:
    registry = EvidenceRegistry.model_validate(_registry_dict())
    with pytest.raises(ValueError, match="unknown probe"):
        registry.probe("fred", "fred:NOPE")


def test_registry_manual_only_with_probes_rejected() -> None:
    data = _registry_dict()
    data["sources"][0]["probe_kind"] = "manual-only"
    with pytest.raises(ValidationError, match="manual-only"):
        EvidenceRegistry.model_validate(data)


def test_registry_manual_only_without_method_rejected() -> None:
    data = _registry_dict()
    data["sources"][0]["probe_kind"] = "manual-only"
    data["sources"][0]["probes"] = []
    with pytest.raises(ValidationError, match="manual_check"):
        EvidenceRegistry.model_validate(data)


def test_registry_automatic_without_probes_rejected() -> None:
    data = _registry_dict()
    data["sources"][0]["probes"] = []
    with pytest.raises(ValidationError, match="at least one probe"):
        EvidenceRegistry.model_validate(data)


def test_panel_freshness_discontinued_needs_series_end() -> None:
    with pytest.raises(ValidationError, match="series_end"):
        PanelFreshnessConfig.model_validate(
            {
                "schema_version": 1,
                "panels": [
                    {
                        "instrument_id": "index:tyvix",
                        "source_id": "fred",
                        "lag_kind": "discontinued",
                        "latest_from": "fred:VXTYN",
                        "series_end": None,
                        "notes": "",
                    }
                ],
            }
        )


def test_panel_freshness_unknown_panel_rejected() -> None:
    config = PanelFreshnessConfig.model_validate(
        {"schema_version": 1, "panels": []}
    )
    with pytest.raises(ValueError, match="unknown panel"):
        config.rule("index:nope")


# ---------------------------------------------------------------------------
# Reachability and SKIP.
# ---------------------------------------------------------------------------


def test_reachability_pass_fail() -> None:
    ok = check_reachable("fred", "fred:VIXCLS:reachability", status=200, error=None)
    assert ok.status is CheckStatus.PASS
    denied = check_reachable(
        "fred", "fred:VIXCLS:reachability", status=403, error="HTTPError 403"
    )
    assert denied.status is CheckStatus.FAIL
    assert denied.reason is not None and "403" in denied.reason
    down = check_reachable(
        "fred",
        "fred:VIXCLS:reachability",
        status=None,
        error="URLError: timed out",
    )
    assert down.status is CheckStatus.FAIL
    assert down.reason is not None and "timed out" in down.reason


def test_skip_verdict() -> None:
    skipped = check_skipped(
        "bls",
        "bls:manual",
        evidence="Manual-only: re-check the BLS schedule page by hand",
    )
    assert skipped.status is CheckStatus.SKIP
    assert "Manual-only" in skipped.evidence


def test_fail_requires_reason() -> None:
    with pytest.raises(ValidationError, match="reason"):
        CheckResult(
            check_id="x",
            source_id="fred",
            status=CheckStatus.FAIL,
            evidence="something",
            reason=None,
        )


# ---------------------------------------------------------------------------
# Per-source checks: PASS, FAIL, boundaries.
# ---------------------------------------------------------------------------


def test_okx_candles_pass() -> None:
    result = check_okx_candles(
        _okx_payload(),
        source_id="okx-public",
        check_id="okx:BTC-1D:payload",
        instrument="BTC-USDT-SWAP",
    )
    assert result.status is CheckStatus.PASS
    assert result.latest_date == date(2026, 11, 17)
    assert "1 forming" in result.evidence


def test_okx_candles_nonzero_code_fails() -> None:
    result = check_okx_candles(
        _okx_payload(code="50001"),
        source_id="okx-public",
        check_id="okx:BTC-1D:payload",
        instrument="BTC-USDT-SWAP",
    )
    assert result.status is CheckStatus.FAIL
    assert result.reason is not None and "50001" in result.reason


def test_okx_candles_no_confirmed_bar_fails() -> None:
    result = check_okx_candles(
        _okx_payload(confirmed=False),
        source_id="okx-public",
        check_id="okx:BTC-1D:payload",
        instrument="BTC-USDT-SWAP",
    )
    assert result.status is CheckStatus.FAIL
    assert result.reason is not None and "no confirmed bar" in result.reason


def test_okx_candles_malformed_fails() -> None:
    result = check_okx_candles(
        b"not json",
        source_id="okx-public",
        check_id="okx:BTC-1D:payload",
        instrument="BTC-USDT-SWAP",
    )
    assert result.status is CheckStatus.FAIL


def test_okx_candles_non_1600_open_fails() -> None:
    # 1D bars open at 16:00 UTC by the recorded convention; a bar
    # opening at midnight means the convention no longer holds.
    rows = [
        [
            str(_ms(datetime(2026, 11, 18, 0, 0, tzinfo=UTC))),
            "90000",
            "91000",
            "89000",
            "90500",
            "100",
            "9000000",
            "9000000",
            "0",
        ],
        [
            str(_ms(datetime(2026, 11, 17, 16, 0, tzinfo=UTC))),
            "88000",
            "90000",
            "87000",
            "89500",
            "120",
            "10740000",
            "10740000",
            "1",
        ],
    ]
    result = check_okx_candles(
        json.dumps({"code": "0", "msg": "", "data": rows}).encode(),
        source_id="okx-public",
        check_id="okx:BTC-1D:payload",
        instrument="BTC-USDT-SWAP",
    )
    assert result.status is CheckStatus.FAIL
    assert result.reason is not None and "16:00 UTC" in result.reason


def test_deribit_expired_single_batch_pass() -> None:
    result = check_deribit_instruments(
        _deribit_instruments_payload(
            expiries=(
                datetime(2026, 11, 18, 8, 0, tzinfo=UTC),
                datetime(2026, 11, 18, 8, 0, tzinfo=UTC),
            )
        ),
        source_id="deribit",
        check_id="deribit:expired:payload",
        expired=True,
    )
    assert result.status is CheckStatus.PASS
    assert "single batch" in result.evidence


def test_deribit_expired_multiple_batches_fails() -> None:
    result = check_deribit_instruments(
        _deribit_instruments_payload(
            expiries=(
                datetime(2026, 11, 17, 8, 0, tzinfo=UTC),
                datetime(2026, 11, 18, 8, 0, tzinfo=UTC),
            )
        ),
        source_id="deribit",
        check_id="deribit:expired:payload",
        expired=True,
    )
    assert result.status is CheckStatus.FAIL
    assert result.reason is not None and "several batches" in result.reason


def test_deribit_expired_empty_fails() -> None:
    result = check_deribit_instruments(
        b'{"result": []}',
        source_id="deribit",
        check_id="deribit:expired:payload",
        expired=True,
    )
    assert result.status is CheckStatus.FAIL


def test_deribit_listed_pass() -> None:
    result = check_deribit_instruments(
        _deribit_instruments_payload(
            expiries=(datetime(2026, 11, 27, 8, 0, tzinfo=UTC),)
        ),
        source_id="deribit",
        check_id="deribit:listed:payload",
        expired=False,
    )
    assert result.status is CheckStatus.PASS


def test_deribit_dvol_pass_and_fail() -> None:
    ok = check_deribit_dvol(
        _dvol_payload(),
        source_id="deribit",
        check_id="deribit:DVOL-BTC:payload",
        index_name="btc_vol",
        currency="BTC",
    )
    assert ok.status is CheckStatus.PASS
    assert ok.latest_date == date(2026, 11, 17)
    bad = check_deribit_dvol(
        b'{"error": {"code": 1234}}',
        source_id="deribit",
        check_id="deribit:DVOL-BTC:payload",
        index_name="btc_vol",
        currency="BTC",
    )
    assert bad.status is CheckStatus.FAIL


def test_deribit_dvol_excludes_provisional_point() -> None:
    # The endpoint also serves the current day's row, whose close
    # is still forming; with as_of it must not count as the latest
    # final point (the 6b probe caught this: the 2026-11-18 row
    # existed at 21:34 UTC with a running close).
    payload = json.dumps(
        {
            "result": {
                "data": [
                    [_ms(datetime(2026, 11, 17, tzinfo=UTC)), 56.0, 58.0, 55.0, 57.0],
                    [_ms(datetime(2026, 11, 18, tzinfo=UTC)), 57.0, 59.0, 45.0, 45.53],
                ]
            }
        }
    ).encode()
    result = check_deribit_dvol(
        payload,
        source_id="deribit",
        check_id="deribit:DVOL-BTC:payload",
        index_name="btc_vol",
        currency="BTC",
        as_of=date(2026, 11, 18),
    )
    assert result.status is CheckStatus.PASS
    assert result.latest_date == date(2026, 11, 17)
    assert "1 current-day point(s) excluded as provisional" in result.evidence
    # Without as_of the current day's row is the latest point.
    unfiltered = check_deribit_dvol(
        payload,
        source_id="deribit",
        check_id="deribit:DVOL-BTC:payload",
        index_name="btc_vol",
        currency="BTC",
    )
    assert unfiltered.latest_date == date(2026, 11, 18)
    # A payload of only provisional points has no final point.
    only_provisional = check_deribit_dvol(
        json.dumps(
            {
                "result": {
                    "data": [
                        [
                            _ms(datetime(2026, 11, 18, tzinfo=UTC)),
                            57.0,
                            59.0,
                            45.0,
                            45.53,
                        ]
                    ]
                }
            }
        ).encode(),
        source_id="deribit",
        check_id="deribit:DVOL-BTC:payload",
        index_name="btc_vol",
        currency="BTC",
        as_of=date(2026, 11, 18),
    )
    assert only_provisional.status is CheckStatus.FAIL
    assert "no final DVOL point" in (only_provisional.reason or "")


def test_deribit_dvol_non_midnight_point_fails() -> None:
    # DVOL points are timestamped 00:00 UTC by the recorded
    # convention; a midday point means the convention no longer
    # holds.
    payload = json.dumps(
        {
            "result": {
                "data": [
                    [_ms(datetime(2026, 11, 16, tzinfo=UTC)), 55.0, 57.0, 54.0, 56.0],
                    [_ms(datetime(2026, 11, 17, 12, 0, tzinfo=UTC)), 56.0, 58.0, 55.0, 57.0],
                ]
            }
        }
    ).encode()
    result = check_deribit_dvol(
        payload,
        source_id="deribit",
        check_id="deribit:DVOL-BTC:payload",
        index_name="btc_vol",
        currency="BTC",
    )
    assert result.status is CheckStatus.FAIL
    assert result.reason is not None and "00:00 UTC" in result.reason


def test_fred_csv_pass_with_empty_missing() -> None:
    result = check_fred_csv(
        _fred_payload(),
        source_id="fred",
        check_id="fred:VIXCLS:payload",
        series_id="VIXCLS",
    )
    assert result.status is CheckStatus.PASS
    assert result.latest_date == date(2026, 11, 18)
    assert "1 missing" in result.evidence
    assert "2 observations" in result.evidence
    assert "1 empty field" in result.evidence


def test_fred_csv_dot_form_missing_fails() -> None:
    # Missing values are empty fields by the recorded claim; a
    # "."-form missing value fails the check (the adapter would
    # still handle it, but the registry statement would be stale).
    text = (
        "observation_date,VIXCLS\n"
        "2026-11-16,18.50\n"
        "2026-11-17,.\n"
        "2026-11-18,19.20\n"
    )
    result = check_fred_csv(
        text.encode(),
        source_id="fred",
        check_id="fred:VIXCLS:payload",
        series_id="VIXCLS",
    )
    assert result.status is CheckStatus.FAIL
    assert result.reason is not None and "empty" in result.reason


def test_fred_csv_bad_header_fails() -> None:
    result = check_fred_csv(
        b"<html>not a csv</html>",
        source_id="fred",
        check_id="fred:VIXCLS:payload",
        series_id="VIXCLS",
    )
    assert result.status is CheckStatus.FAIL


def test_fred_csv_wrong_series_fails() -> None:
    result = check_fred_csv(
        _fred_payload(series_id="DGS10"),
        source_id="fred",
        check_id="fred:VIXCLS:payload",
        series_id="VIXCLS",
    )
    assert result.status is CheckStatus.FAIL


def test_discontinued_series_end() -> None:
    ok = check_discontinued_series_end(
        source_id="fred",
        check_id="fred:VXTYN:series-end",
        series_id="VXTYN",
        latest_date=date(2020, 5, 15),
        expected_end=date(2020, 5, 15),
    )
    assert ok.status is CheckStatus.PASS
    resumed = check_discontinued_series_end(
        source_id="fred",
        check_id="fred:VXTYN:series-end",
        series_id="VXTYN",
        latest_date=date(2026, 11, 17),
        expected_end=date(2020, 5, 15),
    )
    assert resumed.status is CheckStatus.FAIL
    truncated = check_discontinued_series_end(
        source_id="fred",
        check_id="fred:VXTYN:series-end",
        series_id="VXTYN",
        latest_date=date(2020, 5, 14),
        expected_end=date(2020, 5, 15),
    )
    assert truncated.status is CheckStatus.FAIL


def test_yahoo_chart_pass_and_mismatch() -> None:
    ok = check_yahoo_chart(
        _yahoo_payload(),
        source_id="yahoo-finance",
        check_id="yahoo:^GSPC:payload",
        symbol="^GSPC",
    )
    assert ok.status is CheckStatus.PASS
    assert ok.latest_date == date(2026, 11, 18)
    assert "1 missing" in ok.evidence
    assert "S&P 500" in ok.evidence
    mismatch = check_yahoo_chart(
        _yahoo_payload(meta_symbol="^MOVE"),
        source_id="yahoo-finance",
        check_id="yahoo:^GSPC:payload",
        symbol="^GSPC",
    )
    assert mismatch.status is CheckStatus.FAIL
    assert mismatch.reason is not None and "^MOVE" in mismatch.reason


def test_yahoo_chart_error_payload_fails() -> None:
    payload = json.dumps(
        {"chart": {"error": {"code": "Not Found"}, "result": None}}
    ).encode()
    result = check_yahoo_chart(
        payload,
        source_id="yahoo-finance",
        check_id="yahoo:^GSPC:payload",
        symbol="^GSPC",
    )
    assert result.status is CheckStatus.FAIL


def test_fed_page_pass_and_fail() -> None:
    ok = check_fed_page(
        _fed_payload(), source_id="federalreserve", check_id="fed:calendar:payload"
    )
    assert ok.status is CheckStatus.PASS
    bad = check_fed_page(
        _fed_payload(markers=False),
        source_id="federalreserve",
        check_id="fed:calendar:payload",
    )
    assert bad.status is CheckStatus.FAIL
    assert bad.reason is not None and "missing markers" in bad.reason
    binary = check_fed_page(
        b"\xff\xfe not utf-8",
        source_id="federalreserve",
        check_id="fed:calendar:payload",
    )
    assert binary.status is CheckStatus.FAIL


def test_fiscal_api_pass_and_fail() -> None:
    ok = check_fiscal_api(
        _fiscal_payload(), source_id="fiscaldata", check_id="fiscal:recent:payload"
    )
    assert ok.status is CheckStatus.PASS
    assert ok.latest_date == date(2026, 10, 22)
    assert "total-count 2" in ok.evidence
    empty = check_fiscal_api(
        b'{"data": [], "meta": {"total-count": 0}}',
        source_id="fiscaldata",
        check_id="fiscal:recent:payload",
    )
    assert empty.status is CheckStatus.FAIL
    bad_date = check_fiscal_api(
        b'{"data": [{"auction_date": "not-a-date"}]}',
        source_id="fiscaldata",
        check_id="fiscal:recent:payload",
    )
    assert bad_date.status is CheckStatus.FAIL
    not_json = check_fiscal_api(
        b"nope", source_id="fiscaldata", check_id="fiscal:recent:payload"
    )
    assert not_json.status is CheckStatus.FAIL


def test_fiscal_api_lag_days_in_evidence() -> None:
    # With the probe date given, the evidence reports how far the
    # latest auction lags it (fixture latest 2026-10-22, probe
    # date 2026-11-18: 27 days).
    result = check_fiscal_api(
        _fiscal_payload(),
        source_id="fiscaldata",
        check_id="fiscal:recent:payload",
        as_of=date(2026, 11, 18),
    )
    assert result.status is CheckStatus.PASS
    assert "27 days behind the probe date" in result.evidence
    without_date = check_fiscal_api(
        _fiscal_payload(),
        source_id="fiscaldata",
        check_id="fiscal:recent:payload",
    )
    assert "behind the probe date" not in without_date.evidence


def test_hyperliquid_mids_pass_and_fail() -> None:
    ok = check_hyperliquid_mids(
        _hyperliquid_payload(),
        source_id="hyperliquid",
        check_id="hyperliquid:mids:payload",
        expect_symbols=("BTC", "ETH"),
    )
    assert ok.status is CheckStatus.PASS
    assert "3 mids" in ok.evidence
    assert "BTC 62460.5" in ok.evidence
    empty = check_hyperliquid_mids(
        b"{}",
        source_id="hyperliquid",
        check_id="hyperliquid:mids:payload",
    )
    assert empty.status is CheckStatus.FAIL
    not_an_object = check_hyperliquid_mids(
        b'[{"BTC": "1.0"}]',
        source_id="hyperliquid",
        check_id="hyperliquid:mids:payload",
    )
    assert not_an_object.status is CheckStatus.FAIL
    missing_symbol = check_hyperliquid_mids(
        _hyperliquid_payload(),
        source_id="hyperliquid",
        check_id="hyperliquid:mids:payload",
        expect_symbols=("BTC", "DOGE"),
    )
    assert missing_symbol.status is CheckStatus.FAIL
    assert "DOGE" in (missing_symbol.reason or "")
    non_numeric = check_hyperliquid_mids(
        b'{"BTC": "62460.5", "ETH": "n/a"}',
        source_id="hyperliquid",
        check_id="hyperliquid:mids:payload",
    )
    assert non_numeric.status is CheckStatus.FAIL
    assert "ETH" in (non_numeric.reason or "")


def test_check_probe_dispatch_and_unknowns() -> None:
    registry = EvidenceRegistry.model_validate(_registry_dict())
    results = check_probe(registry, "fred", "fred:VIXCLS", _fred_payload())
    assert len(results) == 1
    assert results[0].status is CheckStatus.PASS
    assert results[0].latest_date == date(2026, 11, 18)
    with pytest.raises(ValueError, match="unknown source id"):
        check_probe(registry, "nope", "fred:VIXCLS", _fred_payload())
    with pytest.raises(ValueError, match="unknown probe"):
        check_probe(registry, "fred", "fred:NOPE", _fred_payload())


def test_check_probe_series_end_appended() -> None:
    data = _registry_dict()
    probe = data["sources"][0]["probes"][0]
    probe["key"] = "fred:VXTYN"
    probe["check_params"] = {
        "series_id": "VXTYN",
        "expected_series_end": "2020-05-15",
    }
    registry = EvidenceRegistry.model_validate(data)
    payload = (
        b"observation_date,VXTYN\n2020-05-14,12.5\n2020-05-15,12.7\n"
    )
    results = check_probe(registry, "fred", "fred:VXTYN", payload)
    assert len(results) == 2
    assert results[0].status is CheckStatus.PASS
    assert results[1].check_id == "fred:VXTYN:series-end"
    assert results[1].status is CheckStatus.PASS


# ---------------------------------------------------------------------------
# Expected-latest helpers.
# ---------------------------------------------------------------------------


def test_previous_trading_day() -> None:
    assert previous_trading_day(date(2026, 11, 18)) == date(2026, 11, 18)  # Wed
    assert previous_trading_day(date(2026, 11, 21)) == date(2026, 11, 20)  # Sat -> Fri
    assert previous_trading_day(date(2026, 11, 22)) == date(2026, 11, 20)  # Sun -> Fri


def test_expected_latest_fred() -> None:
    # Wednesday 21:30 UTC: Tuesday's value is the latest posted.
    assert expected_latest_fred(datetime(2026, 11, 18, 21, 30, tzinfo=UTC)) == date(
        2026, 11, 17
    )
    # Monday morning: Friday's value.
    assert expected_latest_fred(datetime(2026, 11, 23, 9, 0, tzinfo=UTC)) == date(
        2026, 11, 20
    )


def test_expected_latest_okx_daily() -> None:
    # After 16:00 UTC: the bar that opened yesterday completed today.
    assert expected_latest_okx_daily(
        datetime(2026, 11, 18, 21, 30, tzinfo=UTC)
    ) == date(2026, 11, 17)
    # Before 16:00 UTC: the latest completed bar opened the day before.
    assert expected_latest_okx_daily(
        datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    ) == date(2026, 11, 16)
    # Exactly at the boundary: the bar completing now counts.
    assert expected_latest_okx_daily(
        datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
    ) == date(2026, 11, 17)


def test_expected_latest_dvol() -> None:
    assert expected_latest_dvol(datetime(2026, 11, 18, 21, 30, tzinfo=UTC)) == date(
        2026, 11, 17
    )


def test_expected_latest_yahoo() -> None:
    # After the 21:00 UTC close on a weekday: today.
    assert expected_latest_yahoo(datetime(2026, 11, 18, 21, 30, tzinfo=UTC)) == date(
        2026, 11, 18
    )
    # Before the close: the previous trading day.
    assert expected_latest_yahoo(datetime(2026, 11, 18, 15, 0, tzinfo=UTC)) == date(
        2026, 11, 17
    )
    # Saturday after 21:00 UTC: Friday.
    assert expected_latest_yahoo(datetime(2026, 11, 21, 22, 0, tzinfo=UTC)) == date(
        2026, 11, 20
    )


def test_expected_latest_cpi_month() -> None:
    releases = (
        (date(2026, 10, 24), date(2026, 9, 1)),  # delayed Sep 2025-style entry
        (date(2026, 11, 10), date(2026, 10, 1)),
        (date(2026, 12, 10), date(2026, 11, 1)),
    )
    assert expected_latest_cpi_month(
        releases, datetime(2026, 11, 19, 5, 0, tzinfo=UTC)
    ) == date(2026, 10, 1)
    assert expected_latest_cpi_month((), datetime(2026, 11, 19, tzinfo=UTC)) is None


# ---------------------------------------------------------------------------
# Panel freshness boundaries.
# ---------------------------------------------------------------------------


def _freshness(**kwargs) -> FreshnessResult:
    defaults = {
        "instrument_id": "index:vix",
        "source_id": "fred",
        "panel_last": date(2026, 11, 16),
        "latest_observed": date(2026, 11, 17),
        "expected_latest": date(2026, 11, 17),
    }
    defaults.update(kwargs)
    return check_panel_freshness(**defaults)


def test_freshness_exactly_current() -> None:
    result = check_panel_freshness(
        instrument_id="index:vix",
        source_id="fred",
        panel_last=date(2026, 11, 17),
        latest_observed=date(2026, 11, 17),
        expected_latest=date(2026, 11, 17),
    )
    assert result.status is FreshnessStatus.FRESH
    assert result.days_behind == 0


def test_freshness_one_day_stale() -> None:
    result = _freshness()
    assert result.status is FreshnessStatus.STALE
    assert result.days_behind == 1


def test_freshness_no_observation_unknown() -> None:
    result = check_panel_freshness(
        instrument_id="index:vix",
        source_id="fred",
        panel_last=date(2026, 11, 16),
        latest_observed=None,
        expected_latest=date(2026, 11, 17),
    )
    assert result.status is FreshnessStatus.UNKNOWN
    assert result.days_behind is None


def test_freshness_source_serves_less_unknown() -> None:
    result = check_panel_freshness(
        instrument_id="index:vix",
        source_id="fred",
        panel_last=date(2026, 11, 17),
        latest_observed=date(2026, 11, 16),
        expected_latest=date(2026, 11, 17),
    )
    assert result.status is FreshnessStatus.UNKNOWN
    assert result.days_behind is None
    assert any("truncation" in note for note in result.notes)


def test_freshness_source_behind_expectation_noted() -> None:
    result = check_panel_freshness(
        instrument_id="index:vix",
        source_id="fred",
        panel_last=date(2026, 11, 16),
        latest_observed=date(2026, 11, 16),
        expected_latest=date(2026, 11, 17),
    )
    # Panel holds everything the source serves: fresh, with a note
    # that the source itself is behind.
    assert result.status is FreshnessStatus.FRESH
    assert any("behind its expected latest" in note for note in result.notes)


def test_freshness_observed_past_expectation_noted() -> None:
    # The source serves a point past the expected latest (e.g. a
    # current-day provisional point): the verdict stands, but the
    # note flags that the newest point may not be final.
    result = check_panel_freshness(
        instrument_id="index:btc-dvol",
        source_id="deribit",
        panel_last=date(2026, 11, 17),
        latest_observed=date(2026, 11, 18),
        expected_latest=date(2026, 11, 17),
    )
    assert result.status is FreshnessStatus.STALE
    assert result.days_behind == 1
    assert any("past the expected latest" in note for note in result.notes)


def test_freshness_discontinued_expected_state() -> None:
    result = check_panel_freshness(
        instrument_id="index:tyvix",
        source_id="fred",
        panel_last=date(2020, 5, 15),
        latest_observed=date(2020, 5, 15),
        expected_latest=date(2020, 5, 15),
        discontinued=True,
        series_end=date(2020, 5, 15),
    )
    assert result.status is FreshnessStatus.FRESH
    assert result.days_behind == 0
    assert any("discontinued" in note for note in result.notes)


def test_freshness_discontinued_resumed_is_stale() -> None:
    result = check_panel_freshness(
        instrument_id="index:tyvix",
        source_id="fred",
        panel_last=date(2020, 5, 15),
        latest_observed=date(2026, 11, 17),
        expected_latest=date(2020, 5, 15),
        discontinued=True,
        series_end=date(2020, 5, 15),
    )
    assert result.status is FreshnessStatus.STALE
    assert result.days_behind is not None and result.days_behind > 0


def test_freshness_discontinued_without_series_end_rejected() -> None:
    with pytest.raises(ValueError, match="series_end"):
        check_panel_freshness(
            instrument_id="index:tyvix",
            source_id="fred",
            panel_last=date(2020, 5, 15),
            latest_observed=date(2020, 5, 15),
            expected_latest=date(2020, 5, 15),
            discontinued=True,
            series_end=None,
        )


# ---------------------------------------------------------------------------
# Report determinism and fetch isolation.
# ---------------------------------------------------------------------------


def _sample_report() -> EvidenceReport:
    return EvidenceReport(
        probed_at=datetime(2026, 11, 18, 21, 30, tzinfo=UTC),
        sources=(
            SourceProbeResult(
                source_id="fred",
                probe_kind=ProbeKind.AUTOMATIC,
                requests_made=1,
                checks=(
                    CheckResult(
                        check_id="fred:VIXCLS:reachability",
                        source_id="fred",
                        status=CheckStatus.PASS,
                        evidence="HTTP 200",
                    ),
                    CheckResult(
                        check_id="fred:VIXCLS:payload",
                        source_id="fred",
                        status=CheckStatus.PASS,
                        evidence="2 observations, 1 missing, latest 2026-11-18",
                        latest_date=date(2026, 11, 18),
                    ),
                ),
            ),
            SourceProbeResult(
                source_id="bls",
                probe_kind=ProbeKind.MANUAL_ONLY,
                requests_made=0,
                checks=(
                    CheckResult(
                        check_id="bls:manual",
                        source_id="bls",
                        status=CheckStatus.SKIP,
                        evidence="Manual-only: re-check by hand",
                    ),
                ),
                manual_check="Open the BLS schedule page in a browser.",
            ),
        ),
        panels=(
            FreshnessResult(
                instrument_id="index:vix",
                source_id="fred",
                status=FreshnessStatus.STALE,
                panel_last=date(2026, 11, 16),
                latest_observed=date(2026, 11, 17),
                expected_latest=date(2026, 11, 17),
                days_behind=1,
                notes=(),
            ),
        ),
        recorded_only=(
            RecordedOnlyItem(
                source_id="okx-public",
                statement="history-trades retention is ~90 days.",
                verified_by="Stage 4a (microstructure-4a)",
                verified_date=date(2026, 11, 18),
                recheck="Bisect trade IDs from the live head.",
            ),
        ),
    )


def test_report_render_deterministic() -> None:
    report = _sample_report()
    first = render_markdown(report)
    second = render_markdown(report)
    assert first == second
    assert "2026-11-18T21:30:00+00:00" in first
    assert "Recorded, not re-verified" in first
    assert "history-trades retention" in first


def test_report_render_timestamp_is_input() -> None:
    report = _sample_report()
    moved = report.model_copy(
        update={"probed_at": datetime(2026, 11, 19, 5, 0, tzinfo=UTC)}
    )
    first = render_markdown(report).splitlines()
    second = render_markdown(moved).splitlines()
    differing = [
        (a, b) for a, b in zip(first, second, strict=True) if a != b
    ]
    assert len(differing) == 1
    assert "Probed at" in differing[0][0]


def test_evidence_pure_modules_do_not_import_fetch() -> None:
    """The checks/registry/report modules must not import fetch.py.

    Parsed from source so the test holds regardless of import order
    in the test session.
    """
    package = REPO_ROOT / "src" / "myquant" / "evidence"
    for module in ("checks.py", "registry.py", "report.py"):
        tree = ast.parse((package / module).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in (
                    "myquant.evidence.fetch",
                    "fetch",
                ), f"{module} imports the fetch layer"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in (
                        "myquant.evidence.fetch",
                        "fetch",
                    ), f"{module} imports the fetch layer"


def test_check_kind_enum_covers_registry() -> None:
    # Every check kind the dispatcher handles is a real enum member;
    # a registry naming an unknown kind fails validation at load.
    assert {kind.value for kind in CheckKind} == {
        "okx_candles",
        "deribit_instruments",
        "deribit_dvol",
        "fred_csv",
        "yahoo_chart",
        "fed_page",
        "fiscal_api",
        "hyperliquid_mids",
    }
    assert {kind.value for kind in LagKind} == {
        "fred_business_day",
        "okx_daily_bar",
        "dvol_daily",
        "yahoo_close",
        "cpi_monthly",
        "discontinued",
    }
