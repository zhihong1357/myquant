"""Cross-reference integrity checks for the research librarian (Stage 6e).

Every check takes already-loaded catalog entries (plus the repo root
for file-existence checks) and returns the broken links it finds. A
check that cannot run because its input is absent records a broken
link rather than passing silently. These functions are pure: they
read no files except existence checks against `repo_root`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from myquant.librarian.models import (
    BrokenLink,
    CandidateEntry,
    DecisionRecordEntry,
    EdgeEntry,
    HypothesisEntry,
    StudyEntry,
    TrialEntry,
)


@dataclass(frozen=True)
class TemplateRef:
    """One planner preregistration template, identified by its pair."""

    source_instrument: str
    target_instrument: str
    rank: int | None
    filename: str


@dataclass(frozen=True)
class AvailabilityRef:
    """One planner data-availability panel with its cited sources."""

    instrument_id: str
    verified_by_paths: tuple[str, ...]


def _link(referrer: str, kind: str, referenced: str, reason: str) -> BrokenLink:
    return BrokenLink(
        referrer=referrer, kind=kind, referenced=referenced, reason=reason
    )


def _file_exists(repo_root: Path, rel_path: str | None) -> bool:
    return rel_path is not None and (repo_root / rel_path).is_file()


def check_edge_links(
    edges: tuple[EdgeEntry, ...],
    trials: tuple[TrialEntry, ...],
    hypotheses: tuple[HypothesisEntry, ...],
    nodes: tuple[str, ...],
    repo_root: Path,
) -> list[BrokenLink]:
    """Edges must resolve to their trial, hypothesis, files and nodes.

    Pending edges have no trial and no test key by design (the test has
    not run); descriptive edges have a trial but no test key (they
    describe a ledger, they do not test it). Neither is a broken link.
    """
    broken: list[BrokenLink] = []
    trial_by_id = {t.trial_id: t for t in trials}
    hypothesis_ids = {h.hypothesis_id for h in hypotheses}
    node_set = set(nodes)
    for edge in edges:
        ref = f"edge {edge.edge_id}"
        if edge.source_instrument not in node_set:
            broken.append(
                _link(
                    ref,
                    "edge_source",
                    edge.source_instrument,
                    "source instrument is not a graph node",
                )
            )
        if edge.target_instrument not in node_set:
            broken.append(
                _link(
                    ref,
                    "edge_target",
                    edge.target_instrument,
                    "target instrument is not a graph node",
                )
            )
        if edge.hypothesis_id is not None and edge.hypothesis_id not in hypothesis_ids:
            broken.append(
                _link(
                    ref,
                    "edge_hypothesis",
                    edge.hypothesis_id,
                    "hypothesis has no registration",
                )
            )
        if edge.status in ("supported", "rejected"):
            if edge.trial_id is None:
                broken.append(
                    _link(ref, "edge_trial", "-", "tested edge has no trial id")
                )
            elif edge.trial_id not in trial_by_id:
                broken.append(
                    _link(
                        ref,
                        "edge_trial",
                        edge.trial_id,
                        "trial id is not in any ledger",
                    )
                )
            elif edge.ledger_test_key is not None:
                trial = trial_by_id[edge.trial_id]
                if edge.ledger_test_key not in trial.test_keys:
                    broken.append(
                        _link(
                            ref,
                            "edge_test_key",
                            edge.ledger_test_key,
                            f"test key is not in trial {edge.trial_id}",
                        )
                    )
        elif edge.status == "descriptive" and edge.trial_id is not None:
            if edge.trial_id not in trial_by_id:
                broken.append(
                    _link(
                        ref,
                        "edge_trial",
                        edge.trial_id,
                        "trial id is not in any ledger",
                    )
                )
        if not _file_exists(repo_root, edge.ledger_path):
            broken.append(
                _link(
                    ref,
                    "edge_ledger",
                    edge.ledger_path or "-",
                    "ledger file does not exist",
                )
            )
        if not _file_exists(repo_root, edge.report_path):
            broken.append(
                _link(
                    ref,
                    "edge_report",
                    edge.report_path or "-",
                    "report file does not exist",
                )
            )
    return broken


def check_candidate_links(
    candidates: tuple[CandidateEntry, ...],
    registry_candidates: tuple[tuple[str, str], ...],
    nodes: tuple[str, ...],
) -> list[BrokenLink]:
    """Planner candidates must be registry candidates with known nodes."""
    broken: list[BrokenLink] = []
    registry_set = set(registry_candidates)
    node_set = set(nodes)
    for cand in candidates:
        ref = f"candidate {cand.source_instrument} -> {cand.target_instrument}"
        pair = (cand.source_instrument, cand.target_instrument)
        if pair not in registry_set:
            broken.append(
                _link(
                    ref,
                    "candidate_registry",
                    f"{cand.source_instrument} -> {cand.target_instrument}",
                    "pair is not a candidate in the graph registry",
                )
            )
        if cand.source_instrument not in node_set:
            broken.append(
                _link(
                    ref,
                    "candidate_source",
                    cand.source_instrument,
                    "source instrument is not a graph node",
                )
            )
        if cand.target_instrument not in node_set:
            broken.append(
                _link(
                    ref,
                    "candidate_target",
                    cand.target_instrument,
                    "target instrument is not a graph node",
                )
            )
    return broken


def check_decision_record_links(
    records: tuple[DecisionRecordEntry, ...],
    edges: tuple[EdgeEntry, ...],
    hypotheses: tuple[HypothesisEntry, ...],
    trials: tuple[TrialEntry, ...],
    studies: tuple[StudyEntry, ...],
    repo_root: Path,
) -> list[BrokenLink]:
    """Decision records must resolve to their edge, hypothesis, trial,
    study and files."""
    broken: list[BrokenLink] = []
    edge_ids = {e.edge_id for e in edges}
    hypothesis_ids = {h.hypothesis_id for h in hypotheses}
    trial_ids = {t.trial_id for t in trials}
    study_slugs = {s.slug for s in studies}
    for record in records:
        ref = f"decision record {record.record_id}"
        if record.edge_id is not None and record.edge_id not in edge_ids:
            broken.append(
                _link(
                    ref,
                    "record_edge",
                    record.edge_id,
                    "edge id is not in the graph registry",
                )
            )
        if record.hypothesis_id not in hypothesis_ids:
            broken.append(
                _link(
                    ref,
                    "record_hypothesis",
                    record.hypothesis_id,
                    "hypothesis has no registration",
                )
            )
        if record.trial_id not in trial_ids:
            broken.append(
                _link(
                    ref,
                    "record_trial",
                    record.trial_id,
                    "trial id is not in any ledger",
                )
            )
        if record.study not in study_slugs:
            broken.append(
                _link(
                    ref,
                    "record_study",
                    record.study,
                    "study has no trial ledger",
                )
            )
        if not _file_exists(repo_root, record.report_path):
            broken.append(
                _link(
                    ref,
                    "record_report",
                    record.report_path,
                    "report file does not exist",
                )
            )
        if not _file_exists(repo_root, record.ledger_path):
            broken.append(
                _link(
                    ref,
                    "record_ledger",
                    record.ledger_path,
                    "ledger file does not exist",
                )
            )
    return broken


def check_template_links(
    templates: tuple[TemplateRef, ...],
    candidates: tuple[CandidateEntry, ...],
) -> list[BrokenLink]:
    """Planner templates must match a ranked candidate pair and rank."""
    broken: list[BrokenLink] = []
    ranked = {
        (c.source_instrument, c.target_instrument): c
        for c in candidates
        if c.ranked and c.rank is not None
    }
    for template in templates:
        ref = f"template {template.filename}"
        pair = (template.source_instrument, template.target_instrument)
        candidate = ranked.get(pair)
        if candidate is None:
            broken.append(
                _link(
                    ref,
                    "template_candidate",
                    f"{template.source_instrument} -> {template.target_instrument}",
                    "pair is not a ranked planner candidate",
                )
            )
        elif template.rank is not None and candidate.rank != template.rank:
            broken.append(
                _link(
                    ref,
                    "template_rank",
                    str(template.rank),
                    f"template rank disagrees with the ranking "
                    f"(ranked {candidate.rank})",
                )
            )
    return broken


def check_review_links(
    review_studies: tuple[str, ...],
    studies: tuple[StudyEntry, ...],
) -> list[BrokenLink]:
    """The 6d review must cover exactly the lab's studies."""
    broken: list[BrokenLink] = []
    study_slugs = {s.slug for s in studies}
    for slug in review_studies:
        if slug not in study_slugs:
            broken.append(
                _link(
                    "6d review report",
                    "review_study",
                    slug,
                    "reviewed study has no trial ledger",
                )
            )
    for slug in sorted(study_slugs - set(review_studies)):
        broken.append(
            _link(
                "6d review report",
                "review_coverage",
                slug,
                "study is not covered by the 6d review",
            )
        )
    return broken


def check_audit_links(
    audit_edge_ids: tuple[str, ...],
    edges: tuple[EdgeEntry, ...],
) -> list[BrokenLink]:
    """The 2B audit's supported edges must exist in the registry."""
    broken: list[BrokenLink] = []
    edge_ids = {e.edge_id for e in edges}
    for edge_id in audit_edge_ids:
        if edge_id not in edge_ids:
            broken.append(
                _link(
                    "2B audit summary",
                    "audit_edge",
                    edge_id,
                    "supported edge is not in the graph registry",
                )
            )
    return broken


def check_availability_links(
    availability: tuple[AvailabilityRef, ...],
    nodes: tuple[str, ...],
    repo_root: Path,
) -> list[BrokenLink]:
    """Planner availability panels must cite existing nodes and files."""
    broken: list[BrokenLink] = []
    node_set = set(nodes)
    for panel in availability:
        ref = f"availability {panel.instrument_id}"
        if panel.instrument_id not in node_set:
            broken.append(
                _link(
                    ref,
                    "availability_node",
                    panel.instrument_id,
                    "panel instrument is not a graph node",
                )
            )
        for path in panel.verified_by_paths:
            if not (repo_root / path).is_file():
                broken.append(
                    _link(
                        ref,
                        "availability_source",
                        path,
                        "cited verification file does not exist",
                    )
                )
    return broken


def check_source_used_by(
    used_by: tuple[tuple[str, str], ...],
    repo_root: Path,
) -> list[BrokenLink]:
    """Evidence sources' used_by entries must name research directories.

    Entries may carry an annotation after the slug ("slug (note)");
    only the slug is checked.
    """
    broken: list[BrokenLink] = []
    for source_id, entry in used_by:
        slug = entry.split(" (", 1)[0].strip()
        if not (repo_root / "research" / slug).is_dir():
            broken.append(
                _link(
                    f"source {source_id}",
                    "source_used_by",
                    entry,
                    "used_by entry is not a research directory",
                )
            )
    return broken


def check_trial_sequence(
    trials: tuple[TrialEntry, ...],
    reserved_trial_ids: tuple[str, ...],
) -> list[BrokenLink]:
    """Trial IDs must form a contiguous sequence with gaps only where a
    reservation is recorded (the librarian records gaps as reserved;
    this check flags a gap it was not told about)."""
    broken: list[BrokenLink] = []
    numbers = sorted(
        int(t.trial_id[1:]) for t in trials if t.trial_id[1:].isdigit()
    )
    if not numbers:
        return broken
    present = set(numbers)
    for n in range(1, max(numbers) + 1):
        trial_id = f"T{n:04d}"
        if n not in present and trial_id not in reserved_trial_ids:
            broken.append(
                _link(
                    "trial sequence",
                    "trial_gap",
                    trial_id,
                    "trial id is missing from the ledgers with no "
                    "recorded reservation",
                )
            )
    return broken


def check_hypothesis_trials(
    hypotheses: tuple[HypothesisEntry, ...],
    edges: tuple[EdgeEntry, ...],
) -> list[BrokenLink]:
    """A hypothesis with no trial must have a pending edge (a forward
    test not yet run) or a non-terminal state; otherwise the loop is
    unclosed with no record of why."""
    broken: list[BrokenLink] = []
    pending_hypotheses = {
        e.hypothesis_id for e in edges if e.status == "pending" and e.hypothesis_id
    }
    for hypothesis in hypotheses:
        if hypothesis.trials:
            continue
        if hypothesis.hypothesis_id in pending_hypotheses:
            continue
        if hypothesis.latest_state in ("registered", "testing"):
            continue
        broken.append(
            _link(
                f"hypothesis {hypothesis.hypothesis_id}",
                "hypothesis_no_trial",
                hypothesis.hypothesis_id,
                f"no trial, no pending edge, state is "
                f"{hypothesis.latest_state}",
            )
        )
    return broken


def check_study_reports(
    studies: tuple[StudyEntry, ...],
) -> list[BrokenLink]:
    """Every study must resolve to an existing report file."""
    broken: list[BrokenLink] = []
    for study in studies:
        if study.report_path is None:
            broken.append(
                _link(
                    f"study {study.slug}",
                    "study_report",
                    "-",
                    "no report path derivable from the graph edges",
                )
            )
        elif not study.report_exists:
            broken.append(
                _link(
                    f"study {study.slug}",
                    "study_report",
                    study.report_path,
                    "report file does not exist",
                )
            )
    return broken
