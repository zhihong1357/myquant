"""Review verdicts and report contracts for the adversarial reviewer (6d).

The reviewer is read-only: it inspects study directories, registries,
ledgers and reports, and writes only its own review report. Every check
returns a verdict plus located evidence; a check that cannot be performed
returns UNVERIFIED, never PASS.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from myquant.contracts import StrictContract


class ReviewVerdict(StrEnum):
    """One check's outcome.

    PASS: the check ran and the record satisfies it. FAIL: the check ran
    and the record violates it, with located evidence. UNVERIFIED: the
    check could not be performed (data not retained, value not locatable,
    prerequisite unreadable) — this is not a pass. NOTE: informational
    only; the check never fails (power/sample-size annotations).
    """

    PASS = "pass"
    FAIL = "fail"
    UNVERIFIED = "unverified"
    NOTE = "note"


class CheckResult(StrictContract):
    """One check's verdict with located evidence."""

    check_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    verdict: ReviewVerdict
    summary: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class StudyReview(StrictContract):
    """All checks run for one study."""

    study: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    checks: tuple[CheckResult, ...] = ()
    counts: dict[str, int] = Field(default_factory=dict)


class LabReview(StrictContract):
    """The full-lab review: per-study reviews plus lab-wide checks."""

    reviewed_at: datetime
    studies: tuple[StudyReview, ...] = ()
    lab_checks: tuple[CheckResult, ...] = ()
    counts: dict[str, int] = Field(default_factory=dict)


def count_verdicts(checks: tuple[CheckResult, ...]) -> dict[str, int]:
    """Tally verdicts over a set of check results (all four keys present)."""
    counts = {verdict.value: 0 for verdict in ReviewVerdict}
    for check in checks:
        counts[check.verdict.value] += 1
    return counts
