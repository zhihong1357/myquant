"""Adversarial reviewer (Stage 6d): a read-only study auditor.

The reviewer runs a set of checks over one study or the whole lab and
returns a verdict (PASS / FAIL / UNVERIFIED / NOTE) plus located
evidence for each. It never modifies study records, registries,
ledgers or reports — it writes only its own review report.
"""

from myquant.review.checks import (
    KNOWN_FAILED_TRIAL_IDS,
    RESERVED_TRIAL_IDS,
    check_hypothesis_state,
    check_ledger_anchor,
    check_ledger_chain,
    check_multiple_testing,
    check_pit,
    check_prereg_binding,
    check_registry_events,
    check_report_ledger,
    check_trial_sequence,
    check_verdict_consistency,
    power_note,
)
from myquant.review.models import (
    CheckResult,
    LabReview,
    ReviewVerdict,
    StudyReview,
    count_verdicts,
)
from myquant.review.runner import (
    STUDY_REPORTS,
    load_audit_mde_entries,
    render_json,
    render_markdown,
    review_lab,
    review_study,
)
from myquant.review.tables import REPORT_RULES

__all__ = [
    "KNOWN_FAILED_TRIAL_IDS",
    "RESERVED_TRIAL_IDS",
    "REPORT_RULES",
    "STUDY_REPORTS",
    "CheckResult",
    "LabReview",
    "ReviewVerdict",
    "StudyReview",
    "check_hypothesis_state",
    "check_ledger_anchor",
    "check_ledger_chain",
    "check_multiple_testing",
    "check_pit",
    "check_prereg_binding",
    "check_registry_events",
    "check_report_ledger",
    "check_trial_sequence",
    "check_verdict_consistency",
    "count_verdicts",
    "load_audit_mde_entries",
    "power_note",
    "render_json",
    "render_markdown",
    "review_lab",
    "review_study",
]
