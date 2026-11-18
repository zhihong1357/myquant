"""Load the planner's inputs from the repository (Stage 6a).

All inputs are committed local files; nothing here touches the
network. The loader converts them into the planner core's plain
input types so the scoring logic stays independent of the file
formats (and testable on synthetic inputs).

Inputs:

- ``research/graph/registry.json`` — nodes, tested edges and
  untested candidates, loaded through the strict
  :class:`myquant.graph.MarketGraph` validation (content hash and
  all).
- ``research/decision-records/records/DR-E*.json`` — supported-edge
  decision records, mapped edge id -> record id so the shortlist
  can cite the evidence behind each adjacent supported edge.
- ``research/statistical-audit-2b/summary.json`` — the Stage 2B
  audit's MDE table, used to cross-check the planner's MDE
  formulas (see :func:`mde_cross_check`): the planner recomputes
  every audit MDE entry from its sample size and compares.
- ``research/fomc-event-study-005/fomc_calendar.json`` — scheduled
  FOMC statement dates, for cross-section event counts.
- ``research/planner-6a/data_availability.json`` — the verified
  per-node panels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from myquant.graph import MarketGraph
from myquant.planner.config import AvailabilityConfig, PlannerConfig
from myquant.planner.scoring import CandidatePair, TestedEdge
from myquant.stats.power import (
    mde_cohens_d,
    mde_partial_r_squared,
    mde_standardized_mean,
)


@dataclass(frozen=True)
class PlannerInputs:
    """Everything one planner run needs, loaded from the repo."""

    candidates: tuple[CandidatePair, ...]
    tested_edges: tuple[TestedEdge, ...]
    availability: AvailabilityConfig
    fomc_statement_dates: tuple[date, ...]
    decision_records: dict[str, str]
    registry_content_hash: str
    node_count: int
    edge_count: int
    short_labels: dict[str, str]


@dataclass(frozen=True)
class MDECheck:
    """One audit-MDE cross-check: the audit's value vs recomputed."""

    label: str
    audit_value: float
    recomputed_value: float
    passed: bool


def load_availability(path: str | Path) -> AvailabilityConfig:
    """Load and validate the data-availability config."""
    return AvailabilityConfig.model_validate_json(Path(path).read_text())


def load_fomc_statement_dates(path: str | Path) -> tuple[date, ...]:
    """Scheduled FOMC statement dates, sorted, from the calendar file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    dates = sorted(
        date.fromisoformat(meeting["statement_date"])
        for meeting in data["scheduled_meetings"]
    )
    return tuple(dates)


def load_decision_records(records_dir: str | Path) -> dict[str, str]:
    """Map supported edge id -> decision-record id (DR-E*.json)."""
    mapping: dict[str, str] = {}
    for record_path in sorted(Path(records_dir).glob("DR-E*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("record_type") != "supported_edge":
            continue
        mapping[record["edge_id"]] = record["record_id"]
    return mapping


def load_planner_inputs(
    repo_root: str | Path,
    availability_path: str | Path | None = None,
) -> PlannerInputs:
    """Load every planner input from the repository tree."""
    root = Path(repo_root)
    graph = MarketGraph.from_file(root / "research/graph/registry.json")
    registry = graph.registry
    candidates = tuple(
        CandidatePair(
            source_instrument=c.source_instrument,
            target_instrument=c.target_instrument,
        )
        for c in registry.candidates
    )
    tested_edges = tuple(
        TestedEdge(
            edge_id=edge.edge_id,
            source_instrument=edge.source_instrument,
            target_instrument=edge.target_instrument,
            test_type=edge.test_type,
            condition=edge.condition,
            status=edge.status,
        )
        for edge in registry.edges
    )
    availability = load_availability(
        availability_path or root / "research/planner-6a/data_availability.json"
    )
    fomc_dates = load_fomc_statement_dates(
        root / "research/fomc-event-study-005/fomc_calendar.json"
    )
    decision_records = load_decision_records(
        root / "research/decision-records/records"
    )
    return PlannerInputs(
        candidates=candidates,
        tested_edges=tested_edges,
        availability=availability,
        fomc_statement_dates=fomc_dates,
        decision_records=decision_records,
        registry_content_hash=registry.content_hash,
        node_count=len(registry.nodes),
        edge_count=len(registry.edges),
        short_labels={
            node.instrument_id: node.short_label for node in registry.nodes
        },
    )


def mde_cross_check(
    audit_summary: dict[str, Any],
    *,
    tolerance: float = 1e-9,
) -> tuple[MDECheck, ...]:
    """Recompute every audit MDE entry from its sample size.

    The planner's power component uses the same analytic MDE
    formulas as the Stage 2B audit; this check proves the two agree
    on the audit's own table before any candidate is scored. The
    mean-ratio MDEs are not recomputed (they need the design's
    noise scale, not just n); the Cohen's d MDEs are, from the
    recorded group sizes.
    """
    power = audit_summary["power"]
    checks: list[MDECheck] = []

    def _check(label: str, audit_value: float, recomputed: float) -> None:
        checks.append(
            MDECheck(
                label=label,
                audit_value=audit_value,
                recomputed_value=recomputed,
                passed=abs(audit_value - recomputed) <= tolerance,
            )
        )

    for entry in power["lead_lag_partial_r_squared"]:
        _check(
            f"lead-lag partial R² MDE ({entry['edge_id']}, "
            f"n={entry['observations']})",
            entry["mde_partial_r_squared"],
            mde_partial_r_squared(entry["observations"]).minimum_detectable_effect,
        )
    cross = power["cross_section_r_squared"]
    _check(
        f"cross-section R² MDE ({cross['edge_id']}, "
        f"n={cross['observations']})",
        cross["mde_r_squared"],
        mde_partial_r_squared(cross["observations"]).minimum_detectable_effect,
    )
    for entry in power["event_study_car"]:
        _check(
            f"standardized CAR MDE ({entry['edge_id']}, "
            f"n={entry['observations']})",
            entry["mde_standardized_mean_car"],
            mde_standardized_mean(
                entry["observations"], one_sided=True
            ).minimum_detectable_effect,
        )
    for entry in power["mean_comparison"]:
        _check(
            f"Cohen's d MDE ({entry['edge_id']}, "
            f"n={entry['window_observations']}/"
            f"{entry['nonwindow_observations']})",
            entry["mde_cohens_d"],
            mde_cohens_d(
                entry["window_observations"], entry["nonwindow_observations"]
            ).minimum_detectable_effect,
        )
    return tuple(checks)


def default_config() -> PlannerConfig:
    """The planner's default configuration (weights, thresholds)."""
    return PlannerConfig()
