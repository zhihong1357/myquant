"""Pure source checks for the evidence analyst (Stage 6b).

Every function here is pure: it judges an already-fetched payload
and returns a verdict, and never touches the network. The probe
script fetches; this module judges. Tests run entirely against
recorded fixtures.

Each check returns PASS, FAIL or SKIP with evidence (timestamps,
counts, a payload hash or an excerpt). A FAIL always carries a
reason. A PASS means only "this probe, at this moment, matched the
recorded expectation" — never "this source is reliable".

The checks reuse the adapters' pure parsers (``parse_*``), wrapped
into verdicts: a parser raising becomes a FAIL with the parser's
message as the reason. This module must never import the fetch
layer (``myquant.evidence.fetch``); a test asserts that.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, timedelta
from datetime import time as dtime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from myquant.adapters.deribit import (
    DeribitAPIError,
    parse_instruments_response,
    parse_volatility_response,
)
from myquant.adapters.fred import FredError, parse_series_csv
from myquant.adapters.okx import OKXAPIError, parse_candles_response
from myquant.adapters.yahoo import YahooError, parse_chart_response
from myquant.contracts import StrictContract
from myquant.evidence.registry import CheckKind, EvidenceRegistry

#: OKX daily bars open at 16:00 UTC and complete 24 hours later.
OKX_DAILY_BAR_OPEN_UTC = dtime(16, 0, 0)

#: Deribit DVOL daily points are timestamped 00:00 UTC.
DVOL_POINT_TIME_UTC = dtime(0, 0, 0)

#: US equity close recorded as a fixed 21:00 UTC timestamp (the
#: lab's convention, shared with the FRED and Yahoo adapters; DST
#: is not modelled, so this is approximate in summer).
US_EQUITY_CLOSE_UTC = dtime(21, 0, 0)

#: Markers a Federal Reserve FOMC calendar page must contain for
#: the smoke check to pass. This is a presence check, not a parse:
#: it confirms the page is the expected document, not that its
#: meeting list is complete.
FED_PAGE_MARKERS = ("Federal Open Market Committee", "FOMC")

_YEAR_PATTERN = re.compile(r"\b(19|20)\d\d\b")


class CheckStatus(StrEnum):
    """Verdict of one check: pass, fail, or skipped."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class FreshnessStatus(StrEnum):
    """Verdict of one panel-freshness comparison."""

    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class CheckResult(StrictContract):
    """One check verdict with its evidence.

    ``latest_date`` is the observed latest point the check yields
    (a bar date, an observation date, a trading date), when the
    check yields one; the panel-freshness comparison reads it.
    ``evidence`` is a short human-readable summary, never the full
    payload.
    """

    check_id: Annotated[str, Field(min_length=1)]
    source_id: Annotated[str, Field(min_length=1)]
    status: CheckStatus
    evidence: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)] | None = None
    latest_date: date | None = None

    @model_validator(mode="after")
    def validate_fail_reason(self) -> CheckResult:
        if self.status is CheckStatus.FAIL and self.reason is None:
            raise ValueError("a FAIL check result needs a reason")
        return self


class FreshnessResult(StrictContract):
    """One panel-freshness verdict.

    ``days_behind`` counts calendar days from the panel's last date
    to the latest date the source serves (0 when the panel is
    current); it is None when freshness cannot be judged. The
    verdict is judged against what the source serves
    (``latest_observed``), not against the expectation: when the
    source itself is behind its expected latest, that is recorded
    in ``notes`` instead of blaming the panel.
    """

    instrument_id: Annotated[str, Field(min_length=1)]
    source_id: Annotated[str, Field(min_length=1)]
    status: FreshnessStatus
    panel_last: date
    latest_observed: date | None
    expected_latest: date
    days_behind: Annotated[int, Field(ge=0)] | None
    notes: tuple[str, ...] = ()


def _payload_fingerprint(payload: bytes) -> str:
    """Short SHA-256 fingerprint of a payload (12 hex chars)."""
    return hashlib.sha256(payload).hexdigest()[:12]


def check_skipped(
    source_id: str,
    check_id: str,
    *,
    evidence: str,
) -> CheckResult:
    """A SKIP verdict: the check was deliberately not run.

    Used for manual-only sources, where no automated probe exists.
    The evidence must name the manual method, so a SKIP is never
    mistaken for a pass.
    """
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.SKIP,
        evidence=evidence,
    )


def check_reachable(
    source_id: str,
    check_id: str,
    *,
    status: int | None,
    error: str | None,
) -> CheckResult:
    """Reachability verdict from a fetch outcome's primitives.

    Takes the HTTP status and the error string, not a fetch object,
    so this module never imports the fetch layer. HTTP 200 passes;
    any other recorded status fails with the code; no status at all
    (a network failure) fails with the error type.
    """
    if status == 200:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.PASS,
            evidence="HTTP 200",
        )
    if status is not None:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"HTTP {status}",
            reason=f"expected HTTP 200, got HTTP {status}",
        )
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.FAIL,
        evidence="no HTTP response",
        reason=f"request failed before a response: {error or 'unknown error'}",
    )


def check_okx_candles(
    payload: bytes,
    *,
    source_id: str,
    check_id: str,
    instrument: str,
    bar: str = "1D",
) -> CheckResult:
    """OKX candles payload: code "0", rows parse, latest confirmed bar.

    The latest row of a live candles response is usually the still
    forming bar (confirm "0"); the check reports the latest
    *confirmed* bar, since only confirmed bars enter a panel.
    For 1D bars the check also asserts the recorded timing
    convention: every bar opens at 16:00 UTC.
    """
    try:
        candles = parse_candles_response(payload, inst_id=instrument, bar=bar)
    except OKXAPIError as exc:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=str(exc),
        )
    if bar == "1D":
        mistimed = [
            candle
            for candle in candles
            if candle.open_time.time() != OKX_DAILY_BAR_OPEN_UTC
        ]
        if mistimed:
            return CheckResult(
                check_id=check_id,
                source_id=source_id,
                status=CheckStatus.FAIL,
                evidence=(
                    f"{len(candles)} candle rows; bar opens "
                    f"{mistimed[0].open_time.isoformat()}, not 16:00 UTC "
                    f"(sha {_payload_fingerprint(payload)})"
                ),
                reason="recorded convention is 1D bars opening at "
                "16:00 UTC; the endpoint now serves bars at another "
                "time",
            )
    confirmed = [candle for candle in candles if candle.confirmed]
    forming = len(candles) - len(confirmed)
    if not confirmed:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=(
                f"{len(candles)} candle rows, 0 confirmed "
                f"(sha {_payload_fingerprint(payload)})"
            ),
            reason="no confirmed bar in the payload; cannot establish "
            "the latest panel point",
        )
    latest = max(confirmed, key=lambda candle: candle.open_time)
    timing = (
        "; all bars open 16:00 UTC" if bar == "1D" else ""
    )
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.PASS,
        evidence=(
            f"{len(candles)} candle rows, {len(confirmed)} confirmed, "
            f"{forming} forming; latest confirmed bar opens "
            f"{latest.open_time.isoformat()}{timing} "
            f"(sha {_payload_fingerprint(payload)})"
        ),
        latest_date=latest.open_time.date(),
    )


def check_deribit_instruments(
    payload: bytes,
    *,
    source_id: str,
    check_id: str,
    expired: bool,
) -> CheckResult:
    """Deribit get_instruments payload.

    For an expired listing the recorded characteristic is that the
    endpoint returns only the most recent expired batch: the check
    passes when every returned contract shares one expiry date and
    fails when the listing spans several batches (the recorded
    behaviour no longer holds) or is empty. For a listed listing
    the check passes when the listing is non-empty.
    """
    try:
        instruments = parse_instruments_response(payload)
    except DeribitAPIError as exc:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=str(exc),
        )
    if not instruments:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence="empty instrument listing",
            reason="expected a non-empty listing (listed contracts, or "
            "the most recent expired batch)",
        )
    expiries = sorted(
        {item.expiration_timestamp.date() for item in instruments}
    )
    if expired:
        if len(expiries) != 1:
            return CheckResult(
                check_id=check_id,
                source_id=source_id,
                status=CheckStatus.FAIL,
                evidence=(
                    f"{len(instruments)} expired contracts across "
                    f"{len(expiries)} expiry dates "
                    f"(sha {_payload_fingerprint(payload)})"
                ),
                reason="recorded behaviour is one expired batch "
                "(all contracts sharing one expiry date); the "
                "endpoint now returns several batches",
            )
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.PASS,
            evidence=(
                f"{len(instruments)} expired contracts, single batch "
                f"expiring {expiries[0].isoformat()} "
                f"(sha {_payload_fingerprint(payload)})"
            ),
        )
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.PASS,
        evidence=(
            f"{len(instruments)} listed contracts across "
            f"{len(expiries)} expiry dates "
            f"(sha {_payload_fingerprint(payload)})"
        ),
    )


def check_deribit_dvol(
    payload: bytes,
    *,
    source_id: str,
    check_id: str,
    index_name: str,
    currency: str,
    as_of: date | None = None,
) -> CheckResult:
    """Deribit DVOL payload: rows parse, latest *final* point reported.

    The endpoint also serves the current day's row, whose close is
    still forming (the lab's adapter treats a point as usable only
    from the next day, 00:00 UTC). When ``as_of`` is given, points
    dated on or after it are excluded as provisional and counted
    in the evidence, so the reported latest is the newest final
    point — the one a panel could hold. Without ``as_of`` every
    parsed point counts. The check also asserts the recorded
    timestamping convention: every point is timestamped 00:00 UTC.
    """
    try:
        points = parse_volatility_response(
            payload, index_name=index_name, currency=currency
        )
    except DeribitAPIError as exc:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=str(exc),
        )
    mistimed = [
        point
        for point in points
        if point.timestamp.time() != DVOL_POINT_TIME_UTC
    ]
    if mistimed:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=(
                f"{len(points)} DVOL points; point timestamped "
                f"{mistimed[0].timestamp.isoformat()}, not 00:00 UTC "
                f"(sha {_payload_fingerprint(payload)})"
            ),
            reason="recorded convention is DVOL points timestamped "
            "00:00 UTC; the endpoint now serves points at another "
            "time",
        )
    excluded = 0
    if as_of is not None:
        final_points = tuple(
            point for point in points if point.timestamp.date() < as_of
        )
        excluded = len(points) - len(final_points)
        points = final_points
    if not points:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=(
                "no final DVOL point before "
                f"{as_of.isoformat() if as_of else 'today'}"
            ),
        )
    latest = max(points, key=lambda point: point.timestamp)
    exclusion = (
        f", {excluded} current-day point(s) excluded as provisional"
        if excluded
        else ""
    )
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.PASS,
        evidence=(
            f"{len(points)} DVOL points; latest final point "
            f"{latest.timestamp.isoformat()} close {latest.close}"
            f"{exclusion} (sha {_payload_fingerprint(payload)})"
        ),
        latest_date=latest.timestamp.date(),
    )


def check_fred_csv(
    payload: bytes,
    *,
    source_id: str,
    check_id: str,
    series_id: str,
) -> CheckResult:
    """FRED fredgraph CSV payload: header, rows, missing count, latest date.

    The parser counts missing values (empty fields or "." per the
    API docs) without distinguishing the form. The check inspects
    the raw rows and asserts the recorded claim: missing values
    are empty fields, not ".". A "."-form missing value fails the
    check — the adapter would still handle it, but the registry
    statement would be stale.
    """
    try:
        observations, missing_count = parse_series_csv(
            payload, series_id=series_id
        )
    except FredError as exc:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=str(exc),
        )
    empty_missing, dot_missing = _fred_missing_forms(payload)
    if dot_missing:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=(
                f"{len(observations)} observations, {missing_count} "
                f"missing ({dot_missing} as '.', {empty_missing} empty) "
                f"(sha {_payload_fingerprint(payload)})"
            ),
            reason="recorded claim is missing values as empty "
            "fields, not '.'; the source now serves '.'-form "
            "missing values",
        )
    form = (
        f" ({empty_missing} empty field"
        f"{'s' if empty_missing != 1 else ''})"
        if missing_count
        else ""
    )
    latest = observations[-1][0]
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.PASS,
        evidence=(
            f"{len(observations)} observations, {missing_count} missing"
            f"{form}, latest {latest.isoformat()} "
            f"(sha {_payload_fingerprint(payload)})"
        ),
        latest_date=latest,
    )


def _fred_missing_forms(payload: bytes) -> tuple[int, int]:
    """Count empty-field vs "."-form missing values in a raw FRED CSV.

    Runs after ``parse_series_csv`` has validated the payload, so
    the structure is trusted here; rows that do not have exactly
    two columns are ignored rather than re-validated.
    """
    text = payload.decode("utf-8")
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    empty_count = 0
    dot_count = 0
    for row in rows[1:]:
        if len(row) != 2:
            continue
        value = row[1].strip()
        if value == "":
            empty_count += 1
        elif value == ".":
            dot_count += 1
    return empty_count, dot_count


def check_discontinued_series_end(
    *,
    source_id: str,
    check_id: str,
    series_id: str,
    latest_date: date,
    expected_end: date,
) -> CheckResult:
    """A discontinued series still ends where the lab recorded it ends.

    PASS when the observed latest date equals the recorded series
    end; FAIL when the series has data past it (the "discontinued"
    fact is stale) or ends earlier (the source truncated it).
    """
    if latest_date == expected_end:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.PASS,
            evidence=(
                f"{series_id} still ends {expected_end.isoformat()} "
                "(discontinued series)"
            ),
            latest_date=latest_date,
        )
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.FAIL,
        evidence=(
            f"{series_id} latest date is {latest_date.isoformat()}, "
            f"recorded series end is {expected_end.isoformat()}"
        ),
        reason="the recorded series end no longer matches the source",
        latest_date=latest_date,
    )


def check_yahoo_chart(
    payload: bytes,
    *,
    source_id: str,
    check_id: str,
    symbol: str,
) -> CheckResult:
    """Yahoo chart payload: meta symbol matches, bars parse, latest date."""
    try:
        parsed = parse_chart_response(payload, symbol=symbol)
    except YahooError as exc:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=str(exc),
        )
    latest = parsed.bars[-1].trading_date
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.PASS,
        evidence=(
            f"{len(parsed.bars)} bars, {parsed.missing_count} missing, "
            f"latest {latest.isoformat()}, longName "
            f"{parsed.long_name!r} "
            f"(sha {_payload_fingerprint(payload)})"
        ),
        latest_date=latest,
    )


def check_fed_page(
    payload: bytes,
    *,
    source_id: str,
    check_id: str,
) -> CheckResult:
    """Federal Reserve FOMC calendar page: smoke check, not a parse.

    Passes when the page decodes as UTF-8 and contains the expected
    document markers plus a four-digit year. It confirms the page
    is the expected document; it does not verify the meeting list.
    """
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=f"page is not UTF-8: {exc}",
        )
    missing = [marker for marker in FED_PAGE_MARKERS if marker not in text]
    year_found = _YEAR_PATTERN.search(text) is not None
    if missing or not year_found:
        reasons = []
        if missing:
            reasons.append(f"missing markers: {', '.join(missing)}")
        if not year_found:
            reasons.append("no four-digit year found")
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=(
                f"{len(payload)} bytes "
                f"(sha {_payload_fingerprint(payload)})"
            ),
            reason="; ".join(reasons),
        )
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.PASS,
        evidence=(
            f"{len(payload)} bytes, FOMC markers and a year present "
            f"(sha {_payload_fingerprint(payload)})"
        ),
    )


def check_fiscal_api(
    payload: bytes,
    *,
    source_id: str,
    check_id: str,
    as_of: date | None = None,
) -> CheckResult:
    """Fiscal Data API auctions_query payload: records, latest auction date.

    When ``as_of`` (the probe date) is given, the evidence reports
    how many days the latest auction lags the probe date, so the
    recorded "about four weeks" lag is re-observed on every run
    rather than merely asserted once.
    """
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=f"payload is not JSON: {exc}",
        )
    if not isinstance(document, dict):
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason="top level is not a JSON object",
        )
    records = document.get("data")
    if not isinstance(records, list) or not records:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason="no 'data' records in the response",
        )
    auction_dates: list[date] = []
    for record in records:
        if not isinstance(record, dict):
            return CheckResult(
                check_id=check_id,
                source_id=source_id,
                status=CheckStatus.FAIL,
                evidence=f"payload sha {_payload_fingerprint(payload)}",
                reason=f"auction record is not an object: {record!r}",
            )
        raw = record.get("auction_date")
        if not isinstance(raw, str):
            return CheckResult(
                check_id=check_id,
                source_id=source_id,
                status=CheckStatus.FAIL,
                evidence=f"payload sha {_payload_fingerprint(payload)}",
                reason=f"auction record has no auction_date: {record!r}",
            )
        try:
            auction_dates.append(date.fromisoformat(raw))
        except ValueError:
            return CheckResult(
                check_id=check_id,
                source_id=source_id,
                status=CheckStatus.FAIL,
                evidence=f"payload sha {_payload_fingerprint(payload)}",
                reason=f"bad auction_date: {raw!r}",
            )
    latest = max(auction_dates)
    meta = document.get("meta")
    total = None
    if isinstance(meta, dict):
        total = meta.get("total-count")
    evidence = (
        f"{len(records)} auction records, latest auction "
        f"{latest.isoformat()}"
    )
    if total is not None:
        evidence += f", total-count {total}"
    if as_of is not None:
        evidence += (
            f", {(as_of - latest).days} days behind the probe date"
        )
    evidence += f" (sha {_payload_fingerprint(payload)})"
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.PASS,
        evidence=evidence,
        latest_date=latest,
    )


def check_hyperliquid_mids(
    payload: bytes,
    *,
    source_id: str,
    check_id: str,
    expect_symbols: tuple[str, ...] = (),
) -> CheckResult:
    """Hyperliquid allMids payload: a flat symbol-to-price mapping.

    The live shape (observed 2026-11-19, correcting the first
    draft of this check, which assumed a ``{"mids": [...]}``
    wrapper): a JSON object mapping each asset symbol to its mid
    price as a numeric string, e.g. ``{"BTC": "62460.5", ...}``.
    Passes when the object is non-empty, every value parses as a
    float, and every expected symbol is present.
    """
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=f"payload is not JSON: {exc}",
        )
    if not isinstance(document, dict) or not document:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason="top level is not a non-empty JSON object",
        )
    non_numeric = [
        key
        for key, value in document.items()
        if not isinstance(value, str) or not _is_float(value)
    ]
    if non_numeric:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=(
                "non-numeric mid values for: "
                f"{', '.join(sorted(non_numeric)[:5])}"
            ),
        )
    missing = [symbol for symbol in expect_symbols if symbol not in document]
    if missing:
        return CheckResult(
            check_id=check_id,
            source_id=source_id,
            status=CheckStatus.FAIL,
            evidence=f"payload sha {_payload_fingerprint(payload)}",
            reason=f"expected symbols missing: {', '.join(missing)}",
        )
    samples = ", ".join(
        f"{symbol} {document[symbol]}" for symbol in expect_symbols
    )
    return CheckResult(
        check_id=check_id,
        source_id=source_id,
        status=CheckStatus.PASS,
        evidence=(
            f"{len(document)} mids"
            + (f", {samples}" if samples else "")
            + f" (sha {_payload_fingerprint(payload)})"
        ),
    )


def _is_float(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def check_probe(
    registry: EvidenceRegistry,
    source_id: str,
    probe_key: str,
    payload: bytes,
    *,
    as_of: date | None = None,
) -> tuple[CheckResult, ...]:
    """Run a registered probe's payload check(s).

    Unknown source ids and unknown probe keys are refused with
    ValueError, never guessed. Returns the payload check, plus a
    series-end check when the probe declares
    ``expected_series_end`` in its check parameters (discontinued
    series only). ``as_of`` is the probe date: the DVOL check uses
    it to exclude the current day's provisional point and the
    fiscal check uses it to report the lag in days; other checks
    ignore it.
    """
    probe = registry.probe(source_id, probe_key)
    check_id = f"{probe_key}:payload"
    params = probe.check_params
    if probe.check_kind is CheckKind.OKX_CANDLES:
        result = check_okx_candles(
            payload,
            source_id=source_id,
            check_id=check_id,
            instrument=params["instrument"],
            bar=params.get("bar", "1D"),
        )
    elif probe.check_kind is CheckKind.DERIBIT_INSTRUMENTS:
        result = check_deribit_instruments(
            payload,
            source_id=source_id,
            check_id=check_id,
            expired=params.get("expired", "false") == "true",
        )
    elif probe.check_kind is CheckKind.DERIBIT_DVOL:
        result = check_deribit_dvol(
            payload,
            source_id=source_id,
            check_id=check_id,
            index_name=params["index_name"],
            currency=params["currency"],
            as_of=as_of,
        )
    elif probe.check_kind is CheckKind.FRED_CSV:
        result = check_fred_csv(
            payload,
            source_id=source_id,
            check_id=check_id,
            series_id=params["series_id"],
        )
    elif probe.check_kind is CheckKind.YAHOO_CHART:
        result = check_yahoo_chart(
            payload,
            source_id=source_id,
            check_id=check_id,
            symbol=params["symbol"],
        )
    elif probe.check_kind is CheckKind.FED_PAGE:
        result = check_fed_page(
            payload, source_id=source_id, check_id=check_id
        )
    elif probe.check_kind is CheckKind.FISCAL_API:
        result = check_fiscal_api(
            payload,
            source_id=source_id,
            check_id=check_id,
            as_of=as_of,
        )
    elif probe.check_kind is CheckKind.HYPERLIQUID_MIDS:
        result = check_hyperliquid_mids(
            payload,
            source_id=source_id,
            check_id=check_id,
            expect_symbols=tuple(
                symbol
                for symbol in params.get("expect_symbols", "").split(",")
                if symbol
            ),
        )
    else:  # pragma: no cover - the enum is exhaustive
        raise ValueError(f"unsupported check kind: {probe.check_kind}")
    results = [result]
    expected_end = params.get("expected_series_end")
    if expected_end is not None and result.latest_date is not None:
        results.append(
            check_discontinued_series_end(
                source_id=source_id,
                check_id=f"{probe_key}:series-end",
                series_id=params.get("series_id", probe_key),
                latest_date=result.latest_date,
                expected_end=date.fromisoformat(expected_end),
            )
        )
    return tuple(results)


# ---------------------------------------------------------------------------
# Expected-latest helpers: what "current" means for each lag rule.
# ---------------------------------------------------------------------------


def previous_trading_day(day: date) -> date:
    """The most recent weekday on or before ``day``.

    The study-007 convention: weekdays only, market holidays are not
    modelled, so a holiday-week expectation can be one day early.
    """
    current = day
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def expected_latest_fred(as_of: datetime) -> date:
    """Latest FRED value expected at ``as_of``: the previous trading day.

    FRED posts day-t values on the next business day (study 007,
    N=1), so at any probe time the latest available value is dated
    the trading day before today.
    """
    return previous_trading_day(as_of.date() - timedelta(days=1))


def expected_latest_okx_daily(as_of: datetime) -> date:
    """Latest completed OKX 1D bar open date at ``as_of``.

    Bars open at 16:00 UTC and complete 24 hours later, so the
    latest completed bar opened yesterday (when the probe runs
    after 16:00 UTC) or the day before (when it runs before).
    """
    if as_of.time() >= OKX_DAILY_BAR_OPEN_UTC:
        return as_of.date() - timedelta(days=1)
    return as_of.date() - timedelta(days=2)


def expected_latest_dvol(as_of: datetime) -> date:
    """Latest complete DVOL point date at ``as_of``: yesterday.

    DVOL points are timestamped 00:00 UTC and complete the next
    day, so today's point is still forming at any probe time.
    """
    return as_of.date() - timedelta(days=1)


def expected_latest_yahoo(as_of: datetime) -> date:
    """Latest Yahoo close expected at ``as_of``.

    The US equity close (16:00 ET, 21:00 UTC by the lab's fixed
    convention) is knowable at the close: a probe after 21:00 UTC
    on a weekday expects today's close, otherwise the previous
    trading day's.
    """
    today = as_of.date()
    if as_of.time() >= US_EQUITY_CLOSE_UTC and today.weekday() < 5:
        return today
    return previous_trading_day(today - timedelta(days=1))


def expected_latest_cpi_month(
    releases: tuple[tuple[date, date], ...],
    as_of: datetime,
) -> date | None:
    """Latest CPI reference month released by ``as_of``.

    ``releases`` are (release_date, reference_month) pairs from the
    BLS calendar; the expected latest reference month is the
    greatest one whose release date has passed. None when no
    release has happened yet (an empty calendar).
    """
    released = [
        reference for release_date, reference in releases
        if release_date <= as_of.date()
    ]
    return max(released) if released else None


# ---------------------------------------------------------------------------
# Panel freshness: compare a registered panel against a live observation.
# ---------------------------------------------------------------------------


def check_panel_freshness(
    *,
    instrument_id: str,
    source_id: str,
    panel_last: date,
    latest_observed: date | None,
    expected_latest: date,
    discontinued: bool = False,
    series_end: date | None = None,
) -> FreshnessResult:
    """Judge one panel's freshness against a live latest point.

    FRESH when the panel already holds everything the source
    serves (``panel_last >= latest_observed``); STALE otherwise,
    with ``days_behind`` counting calendar days from the panel's
    last date to the observed latest. UNKNOWN when no latest point
    was observed, or when the source serves *less* than the panel
    (possible truncation or revision — freshness cannot be judged
    then). A discontinued series is FRESH when the panel ends at
    the series end; new data past the recorded end makes it STALE
    with a note, because the "discontinued" fact itself is stale.
    """
    if latest_observed is None:
        return FreshnessResult(
            instrument_id=instrument_id,
            source_id=source_id,
            status=FreshnessStatus.UNKNOWN,
            panel_last=panel_last,
            latest_observed=None,
            expected_latest=expected_latest,
            days_behind=None,
            notes=(
                "no latest point observed (the probe failed or "
                "returned no data)",
            ),
        )
    if discontinued:
        if series_end is None:
            raise ValueError(
                "discontinued freshness needs a series_end"
            )
        if latest_observed > series_end:
            return FreshnessResult(
                instrument_id=instrument_id,
                source_id=source_id,
                status=FreshnessStatus.STALE,
                panel_last=panel_last,
                latest_observed=latest_observed,
                expected_latest=expected_latest,
                days_behind=(latest_observed - panel_last).days,
                notes=(
                    f"recorded series end was {series_end.isoformat()}; "
                    "the source now serves data past it",
                ),
            )
        if panel_last >= series_end:
            return FreshnessResult(
                instrument_id=instrument_id,
                source_id=source_id,
                status=FreshnessStatus.FRESH,
                panel_last=panel_last,
                latest_observed=latest_observed,
                expected_latest=expected_latest,
                days_behind=0,
                notes=(
                    "discontinued series; the panel end is the "
                    "series end, as expected",
                ),
            )
        return FreshnessResult(
            instrument_id=instrument_id,
            source_id=source_id,
            status=FreshnessStatus.STALE,
            panel_last=panel_last,
            latest_observed=latest_observed,
            expected_latest=expected_latest,
            days_behind=(series_end - panel_last).days,
            notes=(
                "discontinued series; the panel does not cover "
                f"the full series to {series_end.isoformat()}",
            ),
        )
    if latest_observed < panel_last:
        return FreshnessResult(
            instrument_id=instrument_id,
            source_id=source_id,
            status=FreshnessStatus.UNKNOWN,
            panel_last=panel_last,
            latest_observed=latest_observed,
            expected_latest=expected_latest,
            days_behind=None,
            notes=(
                "the source serves less than the panel (possible "
                "truncation or revision); freshness cannot be judged",
            ),
        )
    days_behind = (latest_observed - panel_last).days
    notes: list[str] = []
    if latest_observed < expected_latest:
        notes.append(
            "the source itself is "
            f"{(expected_latest - latest_observed).days} day(s) behind "
            f"its expected latest ({expected_latest.isoformat()}); "
            "the verdict is judged against what the source serves"
        )
    elif latest_observed > expected_latest:
        notes.append(
            "the source serves a point dated "
            f"{latest_observed.isoformat()}, past the expected latest "
            f"({expected_latest.isoformat()}); the newest point may be "
            "provisional (still forming)"
        )
    return FreshnessResult(
        instrument_id=instrument_id,
        source_id=source_id,
        status=(
            FreshnessStatus.FRESH
            if days_behind <= 0
            else FreshnessStatus.STALE
        ),
        panel_last=panel_last,
        latest_observed=latest_observed,
        expected_latest=expected_latest,
        days_behind=days_behind,
        notes=tuple(notes),
    )
