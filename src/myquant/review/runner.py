"""Review orchestration (Stage 6d): run the checks over one study or the lab.

The runner is the only piece that touches the filesystem, and only to
read: study directories, registries, ledgers, reports, the audit
summary and the PIT cache. It writes nothing; rendering produces
strings/bytes the caller decides what to do with.

Fail-closed loading: when a study's ledger cannot be verified, the
checks that need its records are reported UNVERIFIED ("ledger
unreadable") rather than run on untrusted records. Checks that do not
need the ledger (registry events, PIT) still run.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from myquant.canonical import canonical_json
from myquant.hypotheses import HypothesisRegistry, HypothesisSpec
from myquant.registry import read_and_verify
from myquant.review import checks
from myquant.review.models import (
    CheckResult,
    LabReview,
    ReviewVerdict,
    StudyReview,
    count_verdicts,
)
from myquant.review.tables import REPORT_RULES

# The twelve empirical studies, in lab order, with their main reports.
STUDY_REPORTS: dict[str, str] = {
    "btc-eth-001": "docs/studies/btc-eth-transmission-001.md",
    "lowvol-002": "docs/studies/lowvol-transmission-002.md",
    "move-vix-003": "docs/studies/move-vix-transmission-003.md",
    "options-expiry-004": "docs/studies/options-expiry-004.md",
    "fomc-event-study-005": "docs/studies/fomc-event-study-005.md",
    "macro-windows-006": "docs/studies/macro-windows-006.md",
    "publication-lag-007": "docs/studies/publication-lag-007.md",
    "credit-spread-spx-008": "docs/studies/credit-spread-spx-008.md",
    "credit-spread-tyvix-009": "docs/studies/credit-spread-tyvix-009.md",
    "credit-spread-vix-010": "docs/studies/credit-spread-vix-010.md",
    "credit-spread-vxn-011": "docs/studies/credit-spread-vxn-011.md",
    "credit-spread-dgs10-012": "docs/studies/credit-spread-dgs10-012.md",
}

AUDIT_SUMMARY_PATH = "research/statistical-audit-2b/summary.json"
CACHE_DIRNAME = "data/cache"


def load_audit_mde_entries(
    summary_path: Path,
) -> dict[str, tuple[dict[str, Any], ...]]:
    """Index the 2B audit's power-section MDE entries by trial ID."""
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    power = summary.get("power") or {}
    by_trial: dict[str, list[dict[str, Any]]] = {}
    sections: list[Any] = [
        power.get("lead_lag_partial_r_squared") or [],
        power.get("event_study_car") or [],
        power.get("mean_comparison") or [],
    ]
    cross_section = power.get("cross_section_r_squared")
    if isinstance(cross_section, dict):
        sections.append([cross_section])
    for section in sections:
        for entry in section:
            if isinstance(entry, dict) and isinstance(entry.get("trial_id"), str):
                by_trial.setdefault(str(entry["trial_id"]), []).append(entry)
    return {
        trial_id: tuple(entries) for trial_id, entries in sorted(by_trial.items())
    }


def _load_records(ledger_path: Path) -> list[dict[str, Any]] | None:
    """Load a study's verified ledger records, or None if unverifiable."""
    if not ledger_path.exists():
        return None
    try:
        return read_and_verify(ledger_path)
    except (ValueError, KeyError, TypeError):
        return None


def _load_registry(registry_root: Path) -> HypothesisRegistry | None:
    return HypothesisRegistry(registry_root) if registry_root.exists() else None


def _spec_for(
    registry: HypothesisRegistry | None,
    record: dict[str, Any],
) -> HypothesisSpec | None:
    """Fetch the preregistered spec a trial record binds to, if verifiable."""
    if registry is None:
        return None
    spec_dict = (record.get("result") or {}).get("spec") or {}
    hypothesis_id = str(spec_dict.get("hypothesis_id", ""))
    version = spec_dict.get("hypothesis_version")
    if not hypothesis_id or not isinstance(version, int):
        return None
    try:
        return registry.get(hypothesis_id, version=version).spec
    except (ValueError, FileNotFoundError):
        return None


def review_study(
    repo_root: Path,
    study_slug: str,
    *,
    mde_entries: dict[str, tuple[dict[str, Any], ...]] | None = None,
) -> StudyReview:
    """Run every applicable check for one study."""
    study_dir = repo_root / "research" / study_slug
    report_rel = STUDY_REPORTS[study_slug]
    ledger_path = study_dir / "trials.jsonl"
    registry_root = study_dir / "hypotheses"
    ledger_label = f"research/{study_slug}/trials.jsonl"
    registry_label = f"research/{study_slug}/hypotheses"

    results: list[CheckResult] = []
    results.append(checks.check_ledger_chain(ledger_path, ledger_label))
    results.append(checks.check_ledger_anchor(ledger_path, ledger_label))
    results.append(checks.check_registry_events(registry_root, registry_label))

    records = _load_records(ledger_path)
    registry = _load_registry(registry_root)
    if records is None:
        results.append(
            CheckResult(
                check_id="trial_checks",
                subject=study_slug,
                verdict=ReviewVerdict.UNVERIFIED,
                summary="ledger unreadable; per-trial checks not run",
                evidence=(f"{ledger_label}: records could not be verified",),
            )
        )
    else:
        for record in records:
            trial_id = str(record.get("trial_id", "?"))
            spec = _spec_for(registry, record)
            results.append(
                checks.check_prereg_binding(record, registry, trial_id)
            )
            if record.get("status") != "completed":
                continue
            results.append(
                checks.check_multiple_testing(record, spec, trial_id)
            )
            results.append(
                checks.check_verdict_consistency(record, spec, trial_id)
            )
            if mde_entries is not None:
                results.append(
                    checks.power_note(
                        trial_id, mde_entries.get(trial_id, ()), study_slug
                    )
                )
        # Lifecycle state per tested hypothesis version (latest completed
        # trial's verdict decides).
        latest_verdict: dict[tuple[str, int], bool] = {}
        for record in records:
            if record.get("status") != "completed":
                continue
            spec_dict = (record.get("result") or {}).get("spec") or {}
            hypothesis_id = str(spec_dict.get("hypothesis_id", ""))
            version = spec_dict.get("hypothesis_version")
            metrics = (record.get("result") or {}).get("metrics") or {}
            verdict = metrics.get("verdict") or {}
            if (
                hypothesis_id
                and isinstance(version, int)
                and isinstance(verdict.get("supported"), bool)
            ):
                latest_verdict[(hypothesis_id, version)] = bool(
                    verdict["supported"]
                )
        for (hypothesis_id, version), supported in sorted(latest_verdict.items()):
            results.append(
                checks.check_hypothesis_state(
                    registry,
                    hypothesis_id,
                    version,
                    supported,
                    f"{study_slug} {hypothesis_id} v{version}",
                )
            )

    report_path = repo_root / report_rel
    report_text = (
        report_path.read_text(encoding="utf-8") if report_path.exists() else None
    )
    results.append(
        checks.check_report_ledger(
            report_text,
            records or [],
            REPORT_RULES.get(study_slug, ()),
            study_slug,
        )
    )
    results.append(
        checks.check_pit(repo_root / CACHE_DIRNAME, study_slug, study_slug)
    )

    ordered = tuple(results)
    return StudyReview(
        study=study_slug,
        report_path=report_rel,
        checks=ordered,
        counts=count_verdicts(ordered),
    )


def review_lab(repo_root: Path, reviewed_at: datetime) -> LabReview:
    """Run the full-lab review: every study plus the lab-wide checks."""
    summary_path = repo_root / AUDIT_SUMMARY_PATH
    mde_entries = (
        load_audit_mde_entries(summary_path) if summary_path.exists() else {}
    )
    studies = tuple(
        review_study(repo_root, slug, mde_entries=mde_entries)
        for slug in STUDY_REPORTS
    )
    records_by_study: dict[str, list[dict[str, Any]]] = {}
    for slug in STUDY_REPORTS:
        records = _load_records(repo_root / "research" / slug / "trials.jsonl")
        if records is not None:
            records_by_study[slug] = records
    lab_checks = (checks.check_trial_sequence(records_by_study),)
    all_checks = tuple(
        check for study in studies for check in study.checks
    ) + lab_checks
    return LabReview(
        reviewed_at=reviewed_at,
        studies=studies,
        lab_checks=lab_checks,
        counts=count_verdicts(all_checks),
    )


def render_json(review: LabReview) -> bytes:
    """Render the review as canonical JSON (deterministic for one timestamp)."""
    return canonical_json(review.model_dump(mode="json")) + b"\n"


def _verdict_mark(verdict: ReviewVerdict) -> str:
    return {
        ReviewVerdict.PASS: "PASS",
        ReviewVerdict.FAIL: "FAIL",
        ReviewVerdict.UNVERIFIED: "UNVERIFIED",
        ReviewVerdict.NOTE: "NOTE",
    }[verdict]


def render_markdown(review: LabReview) -> str:
    """Render the review as a markdown report (deterministic for one timestamp)."""
    counts = review.counts
    lines = [
        "# Adversarial review report (Stage 6d)",
        "",
        f"Reviewed at: {review.reviewed_at.isoformat()}",
        "",
        f"Read-only review of the lab's {len(review.studies)} empirical "
        "studies: ledger "
        "integrity, preregistration binding, multiple-testing "
        "recomputation, verdict consistency, lifecycle state, report-"
        "ledger agreement, trial-ID sequence and point-in-time "
        "discipline. UNVERIFIED means the check could not be performed — "
        "it is not a pass. NOTE entries are informational MDE annotations "
        "from the 2B audit and never fail.",
        "",
        "## Summary",
        "",
        f"- PASS: {counts.get('pass', 0)}",
        f"- FAIL: {counts.get('fail', 0)}",
        f"- UNVERIFIED: {counts.get('unverified', 0)}",
        f"- NOTE: {counts.get('note', 0)}",
        "",
    ]
    for study in review.studies:
        lines.append(f"## {study.study}")
        lines.append("")
        lines.append(f"- Report: `{study.report_path}`")
        study_counts = study.counts
        lines.append(
            "- Checks: "
            f"{study_counts.get('pass', 0)} pass, "
            f"{study_counts.get('fail', 0)} fail, "
            f"{study_counts.get('unverified', 0)} unverified, "
            f"{study_counts.get('note', 0)} note"
        )
        lines.append("")
        for check in study.checks:
            lines.append(
                f"- **[{_verdict_mark(check.verdict)}]** `{check.check_id}` "
                f"({check.subject}): {check.summary}"
            )
            for item in check.evidence:
                lines.append(f"  - {item}")
        lines.append("")
    lines.append("## Lab-wide checks")
    lines.append("")
    for check in review.lab_checks:
        lines.append(
            f"- **[{_verdict_mark(check.verdict)}]** `{check.check_id}` "
            f"({check.subject}): {check.summary}"
        )
        for item in check.evidence:
            lines.append(f"  - {item}")
    lines.append("")
    return "\n".join(lines)
