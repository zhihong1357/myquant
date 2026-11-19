"""Research librarian (Stage 6e): unified catalog and lab status report.

Read-only: scans the lab's committed records and builds a catalog
plus a status report. Nothing here modifies a source record.
"""

from __future__ import annotations

from myquant.librarian.build import build_catalog
from myquant.librarian.integrity import (
    AvailabilityRef,
    TemplateRef,
    check_audit_links,
    check_availability_links,
    check_candidate_links,
    check_decision_record_links,
    check_edge_links,
    check_hypothesis_trials,
    check_review_links,
    check_source_used_by,
    check_study_reports,
    check_template_links,
    check_trial_sequence,
)
from myquant.librarian.models import (
    AuditSummary,
    BrokenLink,
    CandidateEntry,
    Catalog,
    DecisionRecordEntry,
    EdgeEntry,
    ForwardSampleEntry,
    HypothesisEntry,
    HypothesisVersionEntry,
    MissingOptional,
    NodeEntry,
    PanelEntry,
    PostProbeUpdate,
    ReviewSummary,
    SourceEntry,
    StudyEntry,
    TrialEntry,
)
from myquant.librarian.report import (
    fmt_num,
    render_catalog_json,
    render_lab_report_json,
    render_lab_report_markdown,
    report_data,
)

__all__ = [
    "AuditSummary",
    "AvailabilityRef",
    "BrokenLink",
    "CandidateEntry",
    "Catalog",
    "DecisionRecordEntry",
    "EdgeEntry",
    "ForwardSampleEntry",
    "HypothesisEntry",
    "HypothesisVersionEntry",
    "MissingOptional",
    "NodeEntry",
    "PanelEntry",
    "PostProbeUpdate",
    "ReviewSummary",
    "SourceEntry",
    "StudyEntry",
    "TemplateRef",
    "TrialEntry",
    "build_catalog",
    "check_audit_links",
    "check_availability_links",
    "check_candidate_links",
    "check_decision_record_links",
    "check_edge_links",
    "check_hypothesis_trials",
    "check_review_links",
    "check_source_used_by",
    "check_study_reports",
    "check_template_links",
    "check_trial_sequence",
    "fmt_num",
    "render_catalog_json",
    "render_lab_report_json",
    "render_lab_report_markdown",
    "report_data",
]
