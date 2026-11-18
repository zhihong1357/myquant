"""Validate the Stage 5a funding-rate history and write the report.

Run from the repo root (after ``fetch_data.py``):

    .venv/bin/python research/funding-history/validate_funding.py

Offline: re-reads the cached raw pages through the RawStore
(verifying checksums), re-parses them, rebuilds the funding series,
and checks grid alignment, completeness, the settled-rate
cross-check against the stored live current-rate payload, and the
Stage 4b live-rate cross-reference. Writes
``research/funding-history/funding_report.md``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from myquant.adapters.okx_funding import (
    parse_funding_history_response,
    parse_funding_rate_response,
)
from myquant.execution.funding import FundingRateSeries
from myquant.raw import RawStore

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "funding-history"

#: Stage 4b's recorded live funding rate: read from OKX
#: /api/v5/public/funding-rate on 2026-11-18 (~08:10 UTC), recorded in
#: research/microstructure-4b/replay.py as FUNDING_RATE_OBSERVED. It
#: is a mid-interval *estimate* for the interval ending 16:00 UTC, not
#: the settled rate — the two are different quantities and are not
#: expected to match. The settled rate for that interval is the
#: history row at 2026-11-18T16:00:00Z.
STAGE4B_LIVE_RATE = 0.0000214958653344
STAGE4B_LIVE_RATE_READ_AT = datetime(2026, 11, 18, 8, 10, tzinfo=UTC)
STAGE4B_INTERVAL_END = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)


def _fmt_rate(rate: float) -> str:
    return f"{rate:.8f}"


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    raw_store = RawStore(CACHE_ROOT / "raw")

    lines: list[str] = []
    lines.append("# Funding-rate history (Stage 5a)")
    lines.append("")
    lines.append(
        "Settled funding rates from OKX `/public/funding-rate-history` "
        "(public, no key), pulled by `research/funding-history/fetch_data.py`. "
        "This closes the Stage 4b data gap: funding is no longer only an "
        "input parameter — see `src/myquant/execution/funding.py` for the "
        "series and its use in the cost model."
    )
    lines.append("")

    per_instrument: dict = {}
    for inst_id, entry in sorted(manifest["instruments"].items()):
        # Re-read every cached page through the RawStore (checksum
        # verified on read) and re-parse.
        all_rows = []
        for page in entry["pages"]:
            payload = raw_store.read_payload(page["record_id"])
            rows = parse_funding_history_response(payload, inst_id=inst_id)
            all_rows.extend(rows)
        all_rows.sort(key=lambda row: row.settlement_time)
        series = FundingRateSeries.from_okx_rows(inst_id, all_rows)
        coverage = series.coverage()
        rates = [row.funding_rate for row in series.rows]
        positive = sum(1 for rate in rates if rate > 0)
        negative = sum(1 for rate in rates if rate < 0)
        per_instrument[inst_id] = {
            "series": series,
            "coverage": coverage,
            "mean": sum(rates) / len(rates),
            "min": min(rates),
            "max": max(rates),
            "positive": positive,
            "negative": negative,
            "zero": len(rates) - positive - negative,
        }
        cross = entry["current_rate"]
        current_payload = raw_store.read_payload(cross["current_record_id"])
        current = parse_funding_rate_response(current_payload, inst_id=inst_id)
        lines.append(f"## {inst_id}")
        lines.append("")
        lines.append(
            f"- Rows: **{len(series.rows)}** settled rates, "
            f"{entry['page_count']} pages "
            f"({len(entry['pages'])} cached, all checksums verified)."
        )
        span_days = (
            coverage.last_settlement - coverage.first_settlement
        ).total_seconds() / 86400
        lines.append(
            f"- Range: **{coverage.first_settlement.isoformat()}** to "
            f"**{coverage.last_settlement.isoformat()}** "
            f"({span_days:.1f} days of history)."
        )
        lines.append(
            f"- Grid completeness: {coverage.row_count} rows vs "
            f"{coverage.expected_settlements} expected grid slots; "
            f"missing: "
            + (
                ", ".join(
                    slot.isoformat() for slot in coverage.missing_settlements
                )
                if coverage.missing_settlements
                else "**none** — every 8-hour settlement in range is present"
            )
            + "."
        )
        lines.append(
            f"- Methods: {', '.join(entry['methods'])}; formula types: "
            f"{', '.join(entry['formula_types'])}; rows where "
            f"fundingRate != realizedRate: "
            f"{entry['rate_not_equal_realized_count']}."
        )
        lines.append(
            f"- Rate distribution (per 8-hour interval): mean "
            f"{_fmt_rate(per_instrument[inst_id]['mean'])}, min "
            f"{_fmt_rate(per_instrument[inst_id]['min'])}, max "
            f"{_fmt_rate(per_instrument[inst_id]['max'])}; "
            f"{positive} positive / {negative} negative / "
            f"{per_instrument[inst_id]['zero']} zero rows."
        )
        lines.append(
            f"- Live cross-check (fetch started "
            f"{manifest['fetch_started_at']}): "
            f"the live endpoint's settled rate "
            f"{_fmt_rate(cross['settled_funding_rate'])} at "
            f"{cross['prev_funding_time']} "
            + (
                "**matches the history row exactly**."
                if cross["settled_rate_matches_history"]
                else "**DOES NOT MATCH the history row** "
                f"(history: {cross['history_row_at_prev_settlement']})."
            )
        )
        lines.append(
            f"- Live cap/floor at fetch time: "
            f"[{_fmt_rate(cross['min_funding_rate'])}, "
            f"{_fmt_rate(cross['max_funding_rate'])}] per interval; "
            f"interest-rate component {_fmt_rate(current.interest_rate)}, "
            f"premium {_fmt_rate(current.premium)}."
        )
        if per_instrument[inst_id]["max"] == current.interest_rate:
            lines.append(
                "- Note: the maximum observed rate over the window equals "
                "the interest-rate component exactly (0.0001 per interval). "
                "No mechanism is claimed for this; the premium index was "
                "negative at fetch time, and the funding formula is not "
                "re-derived here."
            )
        lines.append("")

    lines.append("## Depth and limits")
    lines.append("")
    lines.append(
        "The endpoint retains about **93 days** of funding history as of "
        "2026-11-19 (oldest row 2026-08-17T16:00:00Z, 280 rows per "
        "instrument, complete grid). The exact retention rule is "
        "unknown, but the floor moves: a probe minutes before this "
        "fetch showed a 281st row (2026-08-17T08:00:00Z) for BTC and "
        "SOL that was gone by fetch time, consistent with a rolling "
        "retention window. Treat the floor as approximate and "
        "re-establish it on every pull. Anything needing funding rates "
        "before 2026-08-17 has no data here: the series must not be "
        "extended by interpolation or extrapolation, and "
        "`compute_funding_from_series` skips settlements with no rate "
        "rather than inventing one."
    )
    lines.append("")
    lines.append(
        "Pagination note: on this endpoint `after=<ms>` pages backwards "
        "(rows strictly older than the cursor, newest first); `before` "
        "acts as a lower bound and is never used — see "
        "`src/myquant/adapters/okx_funding.py`. The first probe of this "
        "endpoint paged with `before` and looped over a shrinking "
        "subset of the recent window; the corrected probe with `after` "
        "reaches the floor in 4–5 pages per instrument."
    )
    lines.append("")
    lines.append("## Stage 4b cross-reference")
    lines.append("")
    btc = per_instrument["BTC-USDT-SWAP"]["series"]
    settled_4b = btc.rate_at(STAGE4B_INTERVAL_END)
    lines.append(
        f"Stage 4b recorded a live funding rate of "
        f"{_fmt_rate(STAGE4B_LIVE_RATE)} per interval, read "
        f"{STAGE4B_LIVE_RATE_READ_AT.isoformat()} (mid-interval, for the "
        f"interval ending {STAGE4B_INTERVAL_END.isoformat()}). The "
        f"settled rate for that interval (history row at "
        f"{STAGE4B_INTERVAL_END.isoformat()}) is "
        f"**{_fmt_rate(settled_4b)}**."
        if settled_4b is not None
        else "The history row for that interval is missing."
    )
    lines.append("")
    lines.append(
        "The two numbers differ, as they should: the live rate is a "
        "mid-interval estimate that moves with the premium index, while "
        "the settled rate is the final rate fixed at settlement. They "
        "are different quantities; the 4b figure was never a settled "
        "rate and must not be compared to history rows as if it were. "
        "No settlement was crossed in either 4b replay window, so the "
        "4b funding total (zero) is unaffected."
    )
    lines.append("")
    lines.append("## Sign convention")
    lines.append("")
    lines.append(
        "A positive rate means longs pay shorts at settlement. Funding "
        "for a signed position held across a settlement is "
        "`position x price x contract_value x rate` (positive = paid). "
        "See `src/myquant/execution/funding.py` and `docs/portfolio.md`."
    )
    lines.append("")

    report_path = ROOT / "funding_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written: {report_path}")
    for inst_id, data in sorted(per_instrument.items()):
        coverage = data["coverage"]
        print(
            f"{inst_id}: {coverage.row_count} rows, "
            f"{coverage.first_settlement.isoformat()} -> "
            f"{coverage.last_settlement.isoformat()}, "
            f"missing={len(coverage.missing_settlements)}"
        )


if __name__ == "__main__":
    main()
