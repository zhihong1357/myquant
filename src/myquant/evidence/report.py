"""Evidence report contracts and rendering (Stage 6b).

The probe script assembles an :class:`EvidenceReport` from fetch
outcomes and check verdicts; this module renders it to Markdown.
Rendering is pure and deterministic: the probe timestamp is an
input field of the report, never read from the clock, so the same
report renders byte-identically every time.

The report keeps two columns apart by construction: what this
probe observed live (per-source checks, per-panel freshness) and
what the lab only has on record (quirks the probe cannot
re-verify). A re-run changes the probe timestamp and the observed
latest dates — those fields are snapshots of probe time, and the
report says so.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import Field

from myquant.contracts import StrictContract
from myquant.evidence.checks import (
    CheckResult,
    CheckStatus,
    FreshnessResult,
    FreshnessStatus,
)
from myquant.evidence.registry import ProbeKind


class SourceProbeResult(StrictContract):
    """What the probe found for one source.

    ``requests_made`` counts the HTTP requests actually issued
    (0 for manual-only sources). ``manual_check`` carries the
    manual verification method for manual-only sources.
    """

    source_id: Annotated[str, Field(min_length=1)]
    probe_kind: ProbeKind
    requests_made: Annotated[int, Field(ge=0)]
    checks: tuple[CheckResult, ...]
    manual_check: Annotated[str, Field(min_length=1)] | None = None


class RecordedOnlyItem(StrictContract):
    """One recorded fact the probe did not re-verify, with its citation."""

    source_id: Annotated[str, Field(min_length=1)]
    statement: Annotated[str, Field(min_length=1)]
    verified_by: Annotated[str, Field(min_length=1)]
    verified_date: date
    recheck: Annotated[str, Field(min_length=1)] | None = None


class EvidenceReport(StrictContract):
    """One complete evidence run: live observations plus recorded facts."""

    probed_at: datetime
    sources: tuple[SourceProbeResult, ...]
    panels: tuple[FreshnessResult, ...]
    recorded_only: tuple[RecordedOnlyItem, ...]

    def to_json(self) -> str:
        """Structured evidence (the probe script writes this to disk)."""
        return self.model_dump_json(indent=2)


def _status_mark(status: CheckStatus) -> str:
    return {
        CheckStatus.PASS: "PASS",
        CheckStatus.FAIL: "FAIL",
        CheckStatus.SKIP: "SKIP",
    }[status]


def _freshness_mark(status: FreshnessStatus) -> str:
    return {
        FreshnessStatus.FRESH: "fresh",
        FreshnessStatus.STALE: "stale",
        FreshnessStatus.UNKNOWN: "unknown",
    }[status]


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value is not None else "n/a"


def render_markdown(report: EvidenceReport) -> str:
    """Render an evidence report to Markdown (deterministic)."""
    lines: list[str] = [
        "# Stage 6b evidence and source report",
        "",
        f"- Probed at: {report.probed_at.isoformat()}",
        "- This report is a snapshot of probe time: the probe "
        "timestamp, the observed latest dates and the freshness "
        "verdicts change on every re-run, by design. The registry "
        "citations and the recorded-only items do not.",
        "- A PASS means only that this probe, at this moment, "
        "matched the recorded expectation. It is not a claim that "
        "the source is reliable or will stay available.",
        "",
        "## Source status",
        "",
        "| Source | Requests | PASS | FAIL | SKIP |",
        "| --- | --- | --- | --- | --- |",
    ]
    for source in report.sources:
        counts = {status: 0 for status in CheckStatus}
        for check in source.checks:
            counts[check.status] += 1
        lines.append(
            f"| {source.source_id} | {source.requests_made} | "
            f"{counts[CheckStatus.PASS]} | {counts[CheckStatus.FAIL]} | "
            f"{counts[CheckStatus.SKIP]} |"
        )
    lines += ["", "## Checks (live observations)", ""]
    for source in report.sources:
        lines.append(f"### {source.source_id}")
        lines.append("")
        if source.probe_kind is ProbeKind.MANUAL_ONLY:
            lines.append(
                "- Manual-only source: no automated probe was made. "
                f"Manual check: {source.manual_check}"
            )
        for check in source.checks:
            lines.append(
                f"- [{_status_mark(check.status)}] `{check.check_id}`: "
                f"{check.evidence}"
            )
            if check.reason is not None:
                lines.append(f"  - Reason: {check.reason}")
        lines.append("")
    lines += [
        "## Panel freshness",
        "",
        "Freshness compares each registered panel's last date "
        "against the latest point the source serves now, allowing "
        "for the source's known publication lag (see the expected-"
        "latest column). A panel is fresh when it already holds "
        "everything the source serves; stale when the source has "
        "newer points; unknown when no latest point was observed.",
        "",
        "| Panel | Source | Panel last | Observed | Expected | Status | Behind |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for panel in report.panels:
        lines.append(
            f"| {panel.instrument_id} | {panel.source_id} | "
            f"{_fmt_date(panel.panel_last)} | "
            f"{_fmt_date(panel.latest_observed)} | "
            f"{_fmt_date(panel.expected_latest)} | "
            f"{_freshness_mark(panel.status)} | "
            f"{panel.days_behind if panel.days_behind is not None else 'n/a'} |"
        )
    lines.append("")
    for panel in report.panels:
        for note in panel.notes:
            lines.append(f"- {panel.instrument_id}: {note}")
    if any(panel.notes for panel in report.panels):
        lines.append("")
    lines += [
        "## Recorded, not re-verified",
        "",
        "These facts come from the studies' records and were not "
        "re-checked by this probe (too expensive to re-verify, or "
        "only observable at a specific time of day). They are "
        "recorded facts with citations, not fresh verifications.",
        "",
    ]
    if not report.recorded_only:
        lines.append("None.")
    for item in report.recorded_only:
        lines.append(
            f"- [{item.source_id}] {item.statement} "
            f"(verified by {item.verified_by}, {item.verified_date.isoformat()})"
        )
        if item.recheck is not None:
            lines.append(f"  - Re-check: {item.recheck}")
    lines += [
        "",
        "## Limitations",
        "",
        "- One probe is one moment: a passing check says nothing "
        "about the source tomorrow, and a failing check may be a "
        "transient outage rather than a dead source — re-probe "
        "before concluding anything.",
        "- The expected-latest rules use a weekday calendar and "
        "ignore market holidays, so a holiday-week expectation can "
        "be one day early; the freshness verdict is judged against "
        "what the source serves, not the expectation, for exactly "
        "this reason.",
        "- The Fed page check is a smoke check (markers present), "
        "not a parse of the meeting list; the Fiscal Data API lag "
        "is observed from the latest auction date, not measured "
        "against the live schedule.",
        "- BLS has no automated probe: its calendar stays a "
        "manual transcription until someone re-checks it by hand.",
        "",
    ]
    return "\n".join(lines)
