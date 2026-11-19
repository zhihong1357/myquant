"""Catalog and report contracts for the research librarian (Stage 6e).

The librarian is read-only: it scans the lab's committed records
(registrations, trial ledgers, the graph registry, decision records,
planner output, the evidence registry, the 6d review report and the 2B
audit summary) and builds a unified catalog plus a lab status report.
Every number in the catalog is derived by reading a record — nothing
is transcribed by hand.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from myquant.contracts import StrictContract

SCHEMA_VERSION = 1


class StudyEntry(StrictContract):
    """One empirical study (a research directory with a trial ledger)."""

    slug: str = Field(min_length=1)
    report_path: str | None = None
    report_exists: bool = False
    hypotheses: tuple[str, ...] = ()
    trials: tuple[str, ...] = ()
    anchor_present: bool = False
    manifest_present: bool = False
    panel_summary_present: bool = False
    # "open" when any hypothesis is still registered/testing (a forward
    # test pending); "closed" when every hypothesis is terminal.
    status: str = "closed"


class HypothesisVersionEntry(StrictContract):
    """One registered version of a hypothesis."""

    version: int
    spec_fingerprint: str = Field(min_length=1)
    registration_hash: str = Field(min_length=1)
    registered_at: str = Field(min_length=1)
    state: str = Field(min_length=1)


class HypothesisEntry(StrictContract):
    """One hypothesis across its registered versions."""

    hypothesis_id: str = Field(min_length=1)
    study: str = Field(min_length=1)
    versions: tuple[HypothesisVersionEntry, ...] = ()
    latest_state: str = Field(min_length=1)
    trials: tuple[str, ...] = ()
    decision_records: tuple[str, ...] = ()
    edges: tuple[str, ...] = ()


class TrialEntry(StrictContract):
    """One trial ledger record, with its primary-test summary derived.

    The primary test is the first entry of the trial's recorded Holm
    family (the same convention the 6d reviewer uses, true for all 11
    completed trials). Failed trials carry no metrics: the effect and
    p-value fields are None and `failure_reason` holds the recorded
    error.
    """

    trial_id: str = Field(min_length=1)
    study: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    supported: bool | None = None
    primary_test: str | None = None
    primary_test_type: str | None = None
    primary_effect_label: str | None = None
    primary_effect_value: float | None = None
    secondary_effect_label: str | None = None
    secondary_effect_value: float | None = None
    primary_adjusted_p_value: float | None = None
    primary_raw_p_value: float | None = None
    observations: int | None = None
    record_hash: str = Field(min_length=1)
    recorded_at: str = Field(min_length=1)
    failure_reason: str | None = None
    # Keys of the trial's recorded tests (empty for failed trials).
    test_keys: tuple[str, ...] = ()


class NodeEntry(StrictContract):
    """One graph node (instrument), with its display label."""

    instrument_id: str = Field(min_length=1)
    short_label: str = Field(min_length=1)
    name: str = Field(min_length=1)
    asset_class: str = Field(min_length=1)


class ForwardSampleEntry(StrictContract):
    """Forward-sample progress for a pending edge (H0003's gate)."""

    checked_at: str = ""
    forward_rows: int = 0
    minimum_lowvol_rows: int = 0
    observed_lowvol_rows: int = 0
    ready: bool = False
    window_start: str = ""
    window_end: str = ""


class EdgeEntry(StrictContract):
    """One graph edge, with its decision-record and audit links."""

    edge_id: str = Field(min_length=1)
    source_instrument: str = Field(min_length=1)
    target_instrument: str = Field(min_length=1)
    status: str = Field(min_length=1)
    hypothesis_id: str | None = None
    trial_id: str | None = None
    ledger_test_key: str | None = None
    test_type: str | None = None
    report_path: str | None = None
    ledger_path: str | None = None
    decision_record_id: str | None = None
    # Lab-wide audit survival (2B audit summary, cited not recomputed);
    # only meaningful for supported edges, else None.
    holm_significant: bool | None = None
    bh_significant: bool | None = None
    audit_caveat: str | None = None
    # Forward-sample progress, for pending edges only.
    forward_sample: ForwardSampleEntry | None = None


class DecisionRecordEntry(StrictContract):
    """One decision record (edge-linked or hypothesis-linked)."""

    record_id: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    study: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    edge_id: str | None = None
    conclusion: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    ledger_path: str = Field(min_length=1)


class CandidateEntry(StrictContract):
    """One untested candidate pair from the planner ranking."""

    source_instrument: str = Field(min_length=1)
    target_instrument: str = Field(min_length=1)
    ranked: bool
    rank: int | None = None
    total_score: float | None = None
    mechanism: str | None = None
    test_type: str | None = None
    unrankable_reason: str | None = None
    has_template: bool = False


class SourceEntry(StrictContract):
    """One evidence-registry source with its probe outcome."""

    source_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    quirks: int = 0
    recorded_only: int = 0
    probe_kind: str = Field(min_length=1)
    probe_pass: int = 0
    probe_skip: int = 0
    probe_fail: int = 0
    last_verified: str | None = None
    used_by: tuple[str, ...] = ()


class PanelEntry(StrictContract):
    """One panel's freshness at the evidence probe time."""

    instrument_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    panel_last: str | None = None
    expected_latest: str | None = None
    days_behind: int | None = None
    lag_kind: str | None = None
    latest_from: str | None = None


class BrokenLink(StrictContract):
    """One cross-reference that does not resolve."""

    referrer: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    referenced: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class MissingOptional(StrictContract):
    """One optional file that is absent — recorded, not a failure."""

    path: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ReviewSummary(StrictContract):
    """The 6d full-lab review, quoted (not re-run)."""

    reviewed_at: str = Field(min_length=1)
    counts: dict[str, int] = Field(default_factory=dict)
    per_study_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    unverified_items: tuple[str, ...] = ()


class AuditSummary(StrictContract):
    """The 2B lab-wide multiple-testing audit, quoted (not recomputed)."""

    family_size: int
    supported_total: int
    holm_survivors: int
    bh_survivors: int
    registry_content_hash: str = Field(min_length=1)


class PostProbeUpdate(StrictContract):
    """A data update recorded after the evidence probe time."""

    instrument_id: str = Field(min_length=1)
    note: str = Field(min_length=1)
    source_file: str = Field(min_length=1)


class Catalog(StrictContract):
    """The unified lab catalog: every record, cross-linked."""

    schema_version: int = SCHEMA_VERSION
    generated_at: datetime
    source_files: tuple[str, ...] = ()
    studies: tuple[StudyEntry, ...] = ()
    hypotheses: tuple[HypothesisEntry, ...] = ()
    trials: tuple[TrialEntry, ...] = ()
    reserved_trial_ids: tuple[str, ...] = ()
    nodes: tuple[NodeEntry, ...] = ()
    edges: tuple[EdgeEntry, ...] = ()
    decision_records: tuple[DecisionRecordEntry, ...] = ()
    candidates: tuple[CandidateEntry, ...] = ()
    sources: tuple[SourceEntry, ...] = ()
    panels: tuple[PanelEntry, ...] = ()
    review: ReviewSummary | None = None
    audit: AuditSummary | None = None
    # When the 6b evidence probe ran (the freshness snapshot's time).
    evidence_probed_at: str = ""
    post_probe_updates: tuple[PostProbeUpdate, ...] = ()
    broken_links: tuple[BrokenLink, ...] = ()
    missing_optional: tuple[MissingOptional, ...] = ()
    counts: dict[str, int] = Field(default_factory=dict)
