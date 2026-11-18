"""Stage 6b evidence probe: check the lab's sources live, once each.

Run from the repo root:

    .venv/bin/python research/evidence-6b/probe_sources.py

Makes one small request per registered probe (13 in total),
sequentially with a short delay between requests: OKX candles (1),
Deribit expired instruments + DVOL (2), FRED per-series bounded
CSVs (6), Yahoo ^GSPC (1), Fiscal Data API (1), Fed calendar page
(1), Hyperliquid mids (1). BLS is manual-only: no request is made
for it. Writes:

- ``research/evidence-6b/evidence_report.json`` — structured
  evidence: per-source checks, per-panel freshness, recorded-only
  items, probe timestamp.
- ``research/evidence-6b/report.md`` — the same report, readable.

The report is a snapshot of probe time: re-running changes the
probe timestamp, the observed latest dates and the freshness
verdicts, by design. The registry citations and the recorded-only
items do not change. A failing check may be a transient outage —
re-probe before concluding a source is dead.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from myquant.evidence import (  # noqa: E402
    EvidenceReport,
    LagKind,
    ProbeKind,
    RecordedOnlyItem,
    SourceProbeResult,
    check_panel_freshness,
    check_probe,
    check_reachable,
    check_skipped,
    expected_latest_cpi_month,
    expected_latest_dvol,
    expected_latest_fred,
    expected_latest_okx_daily,
    expected_latest_yahoo,
    fetch_once,
    load_panel_freshness,
    load_registry,
    render_markdown,
)
from myquant.planner.loader import load_availability  # noqa: E402

#: Days of history each bounded probe window covers (10 for daily
#: series; 60 for the monthly CPI series and the lagging Fiscal
#: Data API, whose latest data can be weeks old).
WINDOW_DAYS = 10
WINDOW_DAYS_LONG = 60

#: Delay between probe requests, in seconds (politeness, not a
#: rate-limit requirement: 13 requests total).
REQUEST_DELAY_SECONDS = 0.5


def _placeholders(probed_at: datetime) -> dict[str, str]:
    """Fill the URL-template placeholders for one probe run."""
    probe_date = probed_at.date()
    window_start = probe_date - timedelta(days=WINDOW_DAYS)
    window_start_60 = probe_date - timedelta(days=WINDOW_DAYS_LONG)
    period1 = datetime.combine(window_start, datetime.min.time(), tzinfo=UTC)
    period2 = datetime.combine(
        probe_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC
    )
    return {
        "window_start": window_start.isoformat(),
        "window_start_60": window_start_60.isoformat(),
        "probe_date": probe_date.isoformat(),
        "period1": str(int(period1.timestamp())),
        "period2": str(int(period2.timestamp())),
        "period1_ms": str(int(period1.timestamp() * 1000)),
        "period2_ms": str(int(period2.timestamp() * 1000)),
    }


def _load_cpi_releases() -> tuple[tuple[date, date], ...]:
    """(release_date, reference_month) pairs from the study-006 calendar."""
    calendar = json.loads(
        (
            REPO_ROOT
            / "research"
            / "macro-windows-006"
            / "cpi_calendar.json"
        ).read_text()
    )
    releases = []
    for entry in calendar["releases"]:
        year, month = entry["reference_month"].split("-")
        releases.append(
            (
                date.fromisoformat(entry["release_date"]),
                date(int(year), int(month), 1),
            )
        )
    return tuple(releases)


def _expected_latest(
    lag_kind: LagKind,
    probed_at: datetime,
    releases: tuple[tuple[date, date], ...],
    series_end: date | None,
) -> date:
    """The expected latest point for a panel's lag rule at probe time."""
    if lag_kind is LagKind.FRED_BUSINESS_DAY:
        return expected_latest_fred(probed_at)
    if lag_kind is LagKind.OKX_DAILY_BAR:
        return expected_latest_okx_daily(probed_at)
    if lag_kind is LagKind.DVOL_DAILY:
        return expected_latest_dvol(probed_at)
    if lag_kind is LagKind.YAHOO_CLOSE:
        return expected_latest_yahoo(probed_at)
    if lag_kind is LagKind.CPI_MONTHLY:
        latest = expected_latest_cpi_month(releases, probed_at)
        if latest is None:
            raise ValueError("CPI calendar has no release before the probe date")
        return latest
    if lag_kind is LagKind.DISCONTINUED:
        if series_end is None:
            raise ValueError("discontinued panel needs a series_end")
        return series_end
    raise ValueError(f"unsupported lag kind: {lag_kind}")


def main() -> None:
    probed_at = datetime.now(UTC)
    registry = load_registry(ROOT / "sources.json")
    freshness_config = load_panel_freshness(ROOT / "panel_freshness.json")
    availability = load_availability(
        REPO_ROOT / "research/planner-6a/data_availability.json"
    )
    cpi_releases = _load_cpi_releases()
    placeholders = _placeholders(probed_at)

    # Fail fast on config inconsistencies, before any request:
    # every freshness rule must name a planner panel and a probe.
    for rule in freshness_config.panels:
        if availability.panel(rule.instrument_id) is None:
            raise ValueError(
                f"freshness rule names unknown planner panel: "
                f"{rule.instrument_id!r}"
            )
        registry.probe(rule.source_id, rule.latest_from)

    latest_by_probe: dict[str, date] = {}
    source_results: list[SourceProbeResult] = []
    for record in registry.sources:
        if record.probe_kind is ProbeKind.MANUAL_ONLY:
            source_results.append(
                SourceProbeResult(
                    source_id=record.source_id,
                    probe_kind=record.probe_kind,
                    requests_made=0,
                    checks=(
                        check_skipped(
                            record.source_id,
                            f"{record.source_id}:manual",
                            evidence=(
                                "Manual-only source: no automated probe "
                                "exists (see the manual check above)."
                            ),
                        ),
                    ),
                    manual_check=record.manual_check,
                )
            )
            continue
        checks = []
        requests_made = 0
        for probe in record.probes:
            url = probe.url_template.format(**placeholders)
            body = (
                probe.body_template.encode()
                if probe.body_template is not None
                else None
            )
            outcome = fetch_once(
                url,
                method=probe.method,
                body=body,
                user_agent=probe.user_agent,
                timeout_seconds=probe.timeout_seconds,
            )
            requests_made += 1
            checks.append(
                check_reachable(
                    record.source_id,
                    f"{probe.key}:reachability",
                    status=outcome.status,
                    error=outcome.error,
                )
            )
            if outcome.status == 200 and outcome.payload:
                probe_results = check_probe(
                    registry,
                    record.source_id,
                    probe.key,
                    outcome.payload,
                    as_of=probed_at.date(),
                )
                checks.extend(probe_results)
                for result in probe_results:
                    if result.latest_date is not None:
                        latest_by_probe[probe.key] = result.latest_date
                        break
            else:
                checks.append(
                    check_skipped(
                        record.source_id,
                        f"{probe.key}:payload",
                        evidence=(
                            "not run: no payload received "
                            f"(status {outcome.status})"
                        ),
                    )
                )
            time.sleep(REQUEST_DELAY_SECONDS)
        source_results.append(
            SourceProbeResult(
                source_id=record.source_id,
                probe_kind=record.probe_kind,
                requests_made=requests_made,
                checks=tuple(checks),
            )
        )

    panel_results = []
    for rule in freshness_config.panels:
        panel = availability.panel(rule.instrument_id)
        assert panel is not None  # validated above
        expected = _expected_latest(
            rule.lag_kind, probed_at, cpi_releases, rule.series_end
        )
        panel_results.append(
            check_panel_freshness(
                instrument_id=rule.instrument_id,
                source_id=rule.source_id,
                panel_last=panel.last,
                latest_observed=latest_by_probe.get(rule.latest_from),
                expected_latest=expected,
                discontinued=rule.lag_kind is LagKind.DISCONTINUED,
                series_end=rule.series_end,
            )
        )

    recorded_only = tuple(
        RecordedOnlyItem(
            source_id=record.source_id,
            statement=quirk.statement,
            verified_by=quirk.verified_by,
            verified_date=quirk.verified_date,
            recheck=quirk.recheck,
        )
        for record in registry.sources
        for quirk in record.quirks
        if quirk.recorded_only
    )

    report = EvidenceReport(
        probed_at=probed_at,
        sources=tuple(source_results),
        panels=tuple(panel_results),
        recorded_only=recorded_only,
    )
    (ROOT / "evidence_report.json").write_text(
        report.to_json() + "\n", encoding="utf-8"
    )
    (ROOT / "report.md").write_text(render_markdown(report), encoding="utf-8")

    total_requests = sum(s.requests_made for s in source_results)
    total_pass = sum(
        1
        for s in source_results
        for c in s.checks
        if c.status.value == "pass"
    )
    total_fail = sum(
        1
        for s in source_results
        for c in s.checks
        if c.status.value == "fail"
    )
    total_skip = sum(
        1
        for s in source_results
        for c in s.checks
        if c.status.value == "skip"
    )
    print(f"probed at {probed_at.isoformat()}")
    print(
        f"requests: {total_requests}; checks: {total_pass} pass, "
        f"{total_fail} fail, {total_skip} skip"
    )
    for panel in panel_results:
        behind = (
            f", {panel.days_behind}d behind"
            if panel.days_behind
            else ""
        )
        print(f"  {panel.instrument_id}: {panel.status.value}{behind}")
    print("report written: evidence_report.json, report.md")


if __name__ == "__main__":
    main()
