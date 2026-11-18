"""Preregistration draft generation (Stage 6a).

For a ranked candidate, the planner writes a preregistration *draft*
mirroring the registry's spec fields. The draft is a file under
``research/planner-6a/templates/``; it is never written to the
registry, never registers a hypothesis, and never runs a trial.
Every field the planner knows is filled; every field it does not
know is marked ``TODO`` for the researcher. The draft header says so
in plain text.

Known fields come from the ranking itself: the pair, the suggested
test type and frequency, the lab threshold for that test type, the
estimated joint sample (labelled as an estimate), the data sources
from the availability config, and the standard lab acceptance
criteria for the test type. Unknown fields — the mechanism, the
research question's motivation, the benchmark, the cost model, the
train/validation/holdout windows, the confounders — are the
researcher's decisions, not the planner's, and stay TODO.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from myquant.graph import EdgeTestType
from myquant.planner.config import AvailabilityConfig
from myquant.planner.scoring import RankedCandidate

TODO = "TODO"


def _label(
    instrument_id: str, short_labels: Mapping[str, str] | None
) -> str:
    """Display label for an instrument (short label when known)."""
    if short_labels is not None and instrument_id in short_labels:
        return short_labels[instrument_id]
    return instrument_id


def _lead_lag_statements(
    candidate: RankedCandidate, short_labels: Mapping[str, str] | None
) -> dict[str, str]:
    source = _label(candidate.source_instrument, short_labels)
    target = _label(candidate.target_instrument, short_labels)
    if candidate.frequency == "monthly":
        horizon = "next month"
        grid = "monthly"
    else:
        horizon = "next day"
        grid = "daily"
    return {
        "research_question": (
            f"Does the lagged {source} return contain incremental "
            f"information about the {horizon} {target} return, beyond "
            f"the target's own history and a common-factor control?"
        ),
        "null_hypothesis": (
            f"Lagged {source} returns have no incremental predictive "
            f"value for {horizon} {target} returns over the target's "
            f"own history and the common-factor control."
        ),
        "alternative_hypothesis": (
            f"Lagged {source} returns explain a positive, "
            f"out-of-sample component of {horizon} {target} returns "
            f"beyond the target's own history and the common-factor "
            f"control."
        ),
        "target_definition": (
            f"{grid} log return of {target} at t+1; predictor is the "
            f"{grid} log return of {source} at t"
        ),
        "primary_metric": (
            f"Partial R-squared of lag-1 {source} return in the "
            f"{grid} {source}->{target} partial lead-lag regression"
        ),
    }


def _cross_section_statements(
    candidate: RankedCandidate, short_labels: Mapping[str, str] | None
) -> dict[str, str]:
    source = _label(candidate.source_instrument, short_labels)
    target = _label(candidate.target_instrument, short_labels)
    return {
        "research_question": (
            f"Across scheduled FOMC statement days, does the {target} "
            f"event-window CAR co-move with the {source} CAR (the "
            f"lab's policy-surprise proxy)?"
        ),
        "null_hypothesis": (
            f"The {target} CAR[0,+1] has no linear relationship with "
            f"the {source} CAR[0,+1] across FOMC events."
        ),
        "alternative_hypothesis": (
            f"The {target} CAR[0,+1] moves systematically with the "
            f"{source} CAR[0,+1] across FOMC events."
        ),
        "target_definition": (
            f"{target} cumulative abnormal return over the [0,+1] "
            f"event window around scheduled FOMC statement days; "
            f"predictor is the {source} CAR over the same window"
        ),
        "primary_metric": (
            f"R-squared of the cross-event OLS of {target} CAR[0,+1] "
            f"on {source} CAR[0,+1]"
        ),
    }


def _acceptance_criteria(candidate: RankedCandidate) -> list[str]:
    if candidate.test_type is EdgeTestType.CROSS_SECTION:
        return [
            "Holm-adjusted primary p-value below 0.05",
            "Cross-section R-squared at least 0.05",
            "Split-half replication (chronological halves, same sign)",
            "TODO: cost gate — the target CAR is not directly tradable; "
            "state whether a cost gate applies",
        ]
    if candidate.frequency == "monthly":
        return [
            "Holm-adjusted primary p-value below 0.05",
            "Primary partial R-squared at least 0.005",
            "Holdout out-of-sample incremental R-squared above 0",
            "TODO: cost gate — state the tradable instrument and "
            "round-trip cost, or mark informational with a reason",
        ]
    return [
        "Holm-adjusted primary p-value below 0.05",
        "Primary partial R-squared at least 0.005",
        "Holdout out-of-sample incremental R-squared above 0",
        "Net daily edge after the round-trip taker cost is positive "
        "(TODO: confirm the tradable instrument and fee schedule)",
    ]


def generate_prereg_draft(
    candidate: RankedCandidate,
    availability: AvailabilityConfig,
    short_labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a preregistration draft for one ranked candidate.

    Pure function: it reads the ranking and the availability config
    and returns a JSON-serializable dict. It writes nothing and
    never touches the registry. ``short_labels`` maps instrument ids
    to display labels for the templated sentences; ids are used when
    no label is given.
    """
    if candidate.test_type is EdgeTestType.CROSS_SECTION:
        statements = _cross_section_statements(candidate, short_labels)
    else:
        statements = _lead_lag_statements(candidate, short_labels)
    source_panel = availability.panel(candidate.source_instrument)
    target_panel = availability.panel(candidate.target_instrument)
    source_versions = [
        panel.source
        for panel in (source_panel, target_panel)
        if panel is not None
    ]
    horizon_seconds = 2_592_000 if candidate.frequency == "monthly" else 86_400
    return {
        "schema_version": 1,
        "draft": True,
        "draft_note": (
            "DRAFT generated by the Stage 6a hypothesis planner. "
            "Not registered, not a hypothesis, not a trial. Fields "
            "marked TODO are researcher decisions. The suggested test "
            "type, frequency and effect-size threshold are planner "
            "suggestions, to be confirmed before registration."
        ),
        "planner_rank": candidate.rank,
        "planner_total_score": candidate.total,
        "planner_scores": {
            "adjacency": candidate.adjacency,
            "data": candidate.data,
            "power": candidate.power,
        },
        "title": TODO,
        "research_question": statements["research_question"],
        "mechanism": TODO,
        "null_hypothesis": statements["null_hypothesis"],
        "alternative_hypothesis": statements["alternative_hypothesis"],
        "hypothesis_id": TODO,
        "universe": [
            candidate.source_instrument,
            candidate.target_instrument,
        ],
        "target_definition": statements["target_definition"],
        "observation_frequency": candidate.frequency,
        "horizon_seconds": horizon_seconds,
        "suggested_test_type": candidate.test_type.value,
        "suggested_test_reason": candidate.suggestion_reason,
        "model_definition": [
            (
                "Cross-event OLS of target CAR on source CAR, "
                "HC0 standard errors"
                if candidate.test_type is EdgeTestType.CROSS_SECTION
                else "Partial lead-lag OLS with Newey-West HAC "
                "standard errors"
            ),
            "TODO: robustness checks (frequency, subsample, venue)",
        ],
        "feature_set": [TODO],
        "fixed_parameters": [TODO],
        "source_versions": source_versions,
        "sample_period": {
            "estimated_joint_rows": candidate.joint_n,
            "estimated_joint_rows_basis": candidate.joint_n_basis,
            "note": (
                "Estimated from the verified per-node panels; confirm "
                "the exact joint row count when the panel is built."
            ),
        },
        "train_window": TODO,
        "validation_window": TODO,
        "holdout_window": TODO,
        "purge_gap_seconds": horizon_seconds,
        "minimum_train_observations": TODO,
        "minimum_validation_observations": TODO,
        "minimum_holdout_observations": TODO,
        "minimum_effect_size": candidate.mde_threshold,
        "primary_metric": statements["primary_metric"],
        "expected_direction": TODO,
        "benchmark": TODO,
        "cost_model": TODO,
        "cost_assumptions": [TODO],
        "multiple_testing_method": "holm",
        "multiple_testing_family": TODO,
        "planned_test_count": TODO,
        "target_error_rate": 0.05,
        "missing_data_policy": (
            "No forward filling; drop incomplete synchronized rows "
            "and report the dropped count"
        ),
        "known_confounders": [TODO],
        "exclusions": [TODO],
        "random_seed": TODO,
        "acceptance_criteria": _acceptance_criteria(candidate),
        "rejection_criteria": [
            "Primary test fails any acceptance criterion",
            "TODO: state the verdict rule for secondary tests",
        ],
        "adjacent_supported_edges": list(candidate.adjacent_supported_edges),
        "decision_records": list(candidate.decision_records),
        "planner_notes": list(candidate.notes),
    }
