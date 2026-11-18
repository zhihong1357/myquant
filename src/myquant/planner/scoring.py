"""Hypothesis planner core (Stage 6a): rank untested candidate pairs.

The planner answers one question: given the lab's graph (39 edges,
123 untested pairs), its decision records and its power audit, which
candidate pair should the next study test first? It answers with an
explicit, auditable heuristic — not with evidence. "Adjacent to a
supported edge" is a graph fact; "therefore likely to be supported"
is a forbidden inference, and the planner never makes it. The
ranking is a sorting device; the validation report shows how it
moves when the weights change.

Scoring (each component 0–1, weights in
:class:`myquant.planner.config.PlannerConfig`):

- **Adjacency**: 1.0 when the candidate shares a node with a
  SUPPORTED edge, 0.5 when it shares a node one hop away from a
  supported edge (connected to a supported-edge node by any tested
  edge), 0 otherwise. Only SUPPORTED edges count; DESCRIPTIVE and
  PENDING edges do not.
- **Data availability**: 1.0 when both endpoints have verified
  panels, 0.5 when one endpoint's panel is verified unavailable,
  0 when both are. A node with *no* availability record is
  *unknown*, not unavailable: its candidates are unrankable, never
  scored on assumed data.
- **Power feasibility**: 1 when the design's MDE at the available
  sample size is below the lab threshold for the suggested test
  type, 0 otherwise, None when no MDE is defined for the test type
  (the component drops out and the remaining weights renormalize).

The **anti-retest guard** is a hard rule, not a score: a candidate
whose (pair, test type, condition) exactly matches a tested edge is
excluded; a candidate on a pair already REJECTED under a different
test type or condition is admitted at half score and flagged, because
the lab's recurring pattern is same-day transmission with no
next-day carryover, so re-testing the same pair under another setting
needs a new reason. (On the current registry the guard never fires:
candidates are by construction pairs with no tested edge. It is a
safety net for future registries and manually supplied lists, and
it is tested on synthetic inputs.)

The suggested test type comes from an explicit mapping (see
:func:`suggest_test`): first tests are unconditional — conditional
designs are follow-ups, not first tests — and the only
cross-instrument designs in the lab are lead-lag transmission and
the FOMC cross-event regression. Sample sizes are *estimated* from
the verified per-node panels (see :func:`estimate_joint_n`); the
estimate is labelled as such everywhere it appears, and the
preregistration draft marks the confirmed sample size TODO.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from myquant.contracts import StrictContract
from myquant.graph import EdgeStatus, EdgeTestType
from myquant.planner.config import (
    AvailabilityConfig,
    PanelAvailability,
    PanelCalendar,
    PanelStatus,
    PlannerConfig,
    PlannerWeights,
    TestTypeThreshold,
)
from myquant.stats.power import mde_partial_r_squared, mde_standardized_mean

#: The lab's policy-surprise proxy: a DGS10 source suggests the
#: FOMC cross-event regression (the H0008 design), not a lead-lag.
POLICY_SURPRISE_PROXY = "rates:us-10y-yield"

#: The only monthly node: a CPI target suggests a monthly lead-lag;
#: a CPI source suggests the daily step-predictor lead-lag (H0012).
MONTHLY_NODE = "macro:cpi-mom"


class MechanismLabel(StrEnum):
    """Controlled mechanism vocabulary for candidate pairs.

    A label classifies the suggested design; it never enters the
    score. VOL_LEVEL, EVENT_RESPONSE and REGIME_CONDITIONAL are
    defined for completeness but do not occur among registry
    candidates: level and event-response tests are self-loops (never
    candidates), and regime-conditional designs are follow-ups, not
    first tests.
    """

    TRANSMISSION = "transmission"
    VOL_LEVEL = "vol-level"
    EVENT_RESPONSE = "event-response"
    CROSS_SECTION = "cross-section"
    REGIME_CONDITIONAL = "regime-conditional"


class TestedEdge(StrictContract):
    """A tested (or pending/descriptive) edge, as the planner sees it.

    Only the fields the guard and the adjacency tiers need. The
    loader converts registry edges to this shape; tests build it
    directly, which is what makes the guard testable on synthetic
    inputs (a strict registry would reject a candidate duplicating
    a tested pair).
    """

    __test__ = False

    edge_id: Annotated[str, Field(min_length=1)]
    source_instrument: Annotated[str, Field(min_length=1)]
    target_instrument: Annotated[str, Field(min_length=1)]
    test_type: EdgeTestType
    condition: str | None
    status: EdgeStatus


class CandidatePair(StrictContract):
    """One untested directed pair, as the planner sees it."""

    source_instrument: Annotated[str, Field(min_length=1)]
    target_instrument: Annotated[str, Field(min_length=1)]


class SuggestedTest(StrictContract):
    """The planner's suggested first test for a candidate pair."""

    test_type: EdgeTestType
    frequency: Annotated[str, Field(pattern=r"^(daily|monthly)$")]
    mechanism: MechanismLabel
    reason: Annotated[str, Field(min_length=1)]


class RankedCandidate(StrictContract):
    """One ranked candidate with its full scoring breakdown."""

    rank: Annotated[int, Field(ge=1)]
    source_instrument: Annotated[str, Field(min_length=1)]
    target_instrument: Annotated[str, Field(min_length=1)]
    test_type: EdgeTestType
    frequency: Annotated[str, Field(pattern=r"^(daily|monthly)$")]
    mechanism: MechanismLabel
    suggestion_reason: Annotated[str, Field(min_length=1)]
    adjacency: Annotated[float, Field(ge=0.0, le=1.0)]
    data: Annotated[float, Field(ge=0.0, le=1.0)]
    power: Annotated[float, Field(ge=0.0, le=1.0)] | None
    total: Annotated[float, Field(ge=0.0, le=1.0)]
    downgraded: bool = False
    downgrade_reason: str | None = None
    joint_n: Annotated[int, Field(ge=0)] | None
    joint_n_basis: Annotated[str, Field(min_length=1)]
    mde: Annotated[float, Field(ge=0.0, allow_inf_nan=False)] | None
    mde_measure: str | None = None
    mde_threshold: Annotated[float, Field(gt=0.0, allow_inf_nan=False)] | None = None
    adjacent_supported_edges: tuple[str, ...] = ()
    decision_records: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


class ExcludedCandidate(StrictContract):
    """A candidate removed by the anti-retest guard, with its reason."""

    source_instrument: Annotated[str, Field(min_length=1)]
    target_instrument: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]
    edge_id: Annotated[str, Field(min_length=1)]


class UnrankableCandidate(StrictContract):
    """A candidate that cannot be ranked, with its reason."""

    source_instrument: Annotated[str, Field(min_length=1)]
    target_instrument: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1)]


class RankingResult(StrictContract):
    """The complete result of one planner run."""

    ranked: tuple[RankedCandidate, ...]
    excluded: tuple[ExcludedCandidate, ...]
    unrankable: tuple[UnrankableCandidate, ...]
    weights: PlannerWeights
    total_candidates: Annotated[int, Field(ge=0)]


@dataclass(frozen=True)
class GuardOutcome:
    """The anti-retest guard's verdict for one candidate."""

    excluded: bool
    downgraded: bool
    reason: str | None
    edge_id: str | None


def suggest_test(source: str, target: str) -> SuggestedTest:
    """Suggest the first test for a candidate pair (explicit mapping).

    Rules, in precedence order:

    1. CPI as target -> monthly lead-lag (a monthly series cannot be
       the target of a daily-grid test).
    2. DGS10 as source -> FOMC cross-event regression (the DGS10 CAR
       is the lab's policy-surprise proxy; the H0008 design).
    3. Otherwise -> daily lead-lag transmission (the lab's standard
       first test for an untested cross-instrument pair).

    First tests are unconditional by design: conditional designs
    (regime, window) are follow-ups to an unconditional result, not
    first tests. The suggestion is labelled as such in the
    preregistration draft ("suggested value, researcher to confirm").
    """
    if target == MONTHLY_NODE:
        return SuggestedTest(
            test_type=EdgeTestType.LEAD_LAG,
            frequency="monthly",
            mechanism=MechanismLabel.TRANSMISSION,
            reason=(
                "CPI is a monthly series; the target cannot sit on the "
                "daily grid, so the first test is a monthly lead-lag."
            ),
        )
    if source == POLICY_SURPRISE_PROXY:
        return SuggestedTest(
            test_type=EdgeTestType.CROSS_SECTION,
            frequency="daily",
            mechanism=MechanismLabel.CROSS_SECTION,
            reason=(
                "DGS10 is the lab's policy-surprise proxy: the first "
                "test is the FOMC cross-event regression of the "
                "target's event-window CAR on the DGS10 CAR (H0008)."
            ),
        )
    return SuggestedTest(
        test_type=EdgeTestType.LEAD_LAG,
        frequency="daily",
        mechanism=MechanismLabel.TRANSMISSION,
        reason=(
            "Default first test for an untested cross-instrument "
            "pair: unconditional daily lead-lag transmission."
        ),
    )


def _rows_in_window(panel: PanelAvailability, start: date, end: date) -> int:
    """Estimated panel rows inside [start, end] (pro-rata by days).

    The panel's verified row count is spread uniformly over its
    verified date range. This is an estimate — the true joint row
    count must be confirmed when the study is designed — and it is
    labelled as such everywhere it is used.
    """
    if panel.first is None or panel.last is None or end < start:
        return 0
    window_days = (end - start).days + 1
    range_days = (panel.last - panel.first).days + 1
    if range_days <= 0:
        return 0
    return int(panel.rows * window_days / range_days)


def _months_in_window(first: date, last: date) -> int:
    """Whole calendar months between two dates, inclusive."""
    if last < first:
        return 0
    return (last.year - first.year) * 12 + (last.month - first.month) + 1


def estimate_joint_n(
    source: PanelAvailability,
    target: PanelAvailability,
    suggested: SuggestedTest,
    fomc_statement_dates: tuple[date, ...],
    *,
    event_warmup_days: int,
) -> tuple[int, str]:
    """Estimate the available sample size for a suggested test.

    Returns (n, basis). n is 0 when the panels do not overlap on
    the test's grid — such a pair cannot be tested with the
    verified panels and is unrankable. The basis string names the
    estimation method so the number is never mistaken for a
    verified count.
    """
    if suggested.test_type is EdgeTestType.CROSS_SECTION:
        if (
            source.first is None
            or source.last is None
            or target.first is None
            or target.last is None
        ):
            return 0, "cross-section needs dated panels"
        earliest = max(source.first, target.first) + timedelta(
            days=event_warmup_days
        )
        latest = min(source.last, target.last) - timedelta(days=1)
        usable = [
            day
            for day in fomc_statement_dates
            if earliest <= day <= latest
        ]
        return (
            len(usable),
            "FOMC statements in the overlap window after the "
            f"{event_warmup_days}-day estimation warm-up",
        )
    if suggested.frequency == "monthly":
        # CPI is the monthly node; the other panel bounds the months.
        monthly = target if target.calendar is PanelCalendar.MONTHLY else source
        other = source if monthly is target else target
        if (
            monthly.first is None
            or monthly.last is None
            or other.first is None
            or other.last is None
        ):
            return 0, "monthly design needs dated panels"
        first = max(monthly.first, other.first)
        last = min(monthly.last, other.last)
        return (
            _months_in_window(first, last),
            "calendar months in the overlap of the monthly panel "
            "with the other panel",
        )
    # Daily lead-lag.
    if source.calendar is PanelCalendar.MONTHLY:
        # CPI as source: the daily step predictor is usable from its
        # first release date, not from its first reference month.
        step_start = source.step_start or source.first
        if step_start is None or target.first is None or target.last is None:
            return 0, "step-predictor design needs dated panels"
        start = max(step_start, target.first)
        end = target.last
        return (
            _rows_in_window(target, start, end),
            "estimated daily rows of the target panel inside the "
            "step-predictor window (first release to panel end)",
        )
    if (
        source.first is None
        or source.last is None
        or target.first is None
        or target.last is None
    ):
        return 0, "daily design needs dated panels"
    start = max(source.first, target.first)
    end = min(source.last, target.last)
    if end < start:
        return 0, "no overlapping panel window"
    return (
        min(
            _rows_in_window(source, start, end),
            _rows_in_window(target, start, end),
        ),
        "estimated daily rows in the overlap window "
        "(pro-rata by days, sparser panel binds)",
    )


def adjacency_tiers(
    tested_edges: tuple[TestedEdge, ...],
    *,
    direct: float = 1.0,
    one_hop: float = 0.5,
) -> tuple[dict[str, float], dict[str, tuple[str, ...]]]:
    """Graph-distance tiers around the SUPPORTED edges.

    Tier ``direct``: nodes that share an edge endpoint with a
    SUPPORTED edge. Tier ``one_hop``: nodes adjacent (via any
    tested edge, supported or rejected) to a tier-``direct`` node.
    Tier 0: all other nodes. Descriptive and pending edges never
    contribute: only tested edges define adjacency, and only
    supported edges define the direct tier. Returns (tier per
    node, supported edge ids per direct-tier node). The tier
    values are parameters (see
    :class:`myquant.planner.config.PlannerConfig`); the defaults
    match the documented 1.0 / 0.5.
    """
    tested = [
        edge
        for edge in tested_edges
        if edge.status in {EdgeStatus.SUPPORTED, EdgeStatus.REJECTED}
    ]
    supported_nodes: dict[str, list[str]] = {}
    for edge in tested:
        if edge.status is EdgeStatus.SUPPORTED:
            for node in (edge.source_instrument, edge.target_instrument):
                supported_nodes.setdefault(node, []).append(edge.edge_id)
    neighbours: dict[str, set[str]] = {}
    for edge in tested:
        neighbours.setdefault(edge.source_instrument, set()).add(
            edge.target_instrument
        )
        neighbours.setdefault(edge.target_instrument, set()).add(
            edge.source_instrument
        )
    tiers: dict[str, float] = {}
    for node in supported_nodes:
        tiers[node] = direct
    for node in supported_nodes:
        for neighbour in neighbours.get(node, set()):
            if neighbour not in tiers:
                tiers[neighbour] = one_hop
    supported_ids = {
        node: tuple(sorted(ids)) for node, ids in supported_nodes.items()
    }
    return tiers, supported_ids


def data_component(
    source: PanelAvailability | None,
    target: PanelAvailability | None,
) -> float:
    """Data-availability component (0–1).

    Both panels verified available: 1.0. One verified unavailable:
    0.5 (half the pair is ready; the missing side needs a fetch, not
    a redesign). Both verified unavailable: 0.0. Unknown panels
    (None) never reach this function: their candidates are
    unrankable, not scored.
    """
    available = sum(
        1
        for panel in (source, target)
        if panel is not None and panel.status is PanelStatus.AVAILABLE
    )
    return available / 2.0


def power_component(
    test_type: EdgeTestType,
    sample_size: int,
    threshold: TestTypeThreshold | None,
) -> tuple[float | None, float | None, str | None]:
    """Power-feasibility component (1, 0, or None).

    Returns (score, mde, note). Score 1 when the design's MDE at
    the available sample size is below the lab threshold for the
    test type, 0 otherwise. None when no MDE is defined for the
    test type at the available information: mean comparison needs
    two group sizes the planner does not know until the window is
    defined, and an unmapped test type has no threshold at all.
    A None component drops out of the weighted total (the remaining
    weights renormalize) instead of scoring 0.
    """
    if threshold is None:
        return None, None, f"no lab threshold mapped for {test_type.value}"
    if test_type is EdgeTestType.LEAD_LAG:
        mde = mde_partial_r_squared(sample_size).minimum_detectable_effect
        return (1.0 if mde < threshold.threshold else 0.0), mde, None
    if test_type is EdgeTestType.CROSS_SECTION:
        # A cross-section R-squared is a single-coefficient F-test
        # R-squared, so its MDE uses the same formula as the
        # lead-lag partial R-squared (validated against the audit's
        # 0.0549 at n = 135).
        mde = mde_partial_r_squared(sample_size).minimum_detectable_effect
        return (1.0 if mde < threshold.threshold else 0.0), mde, None
    if test_type is EdgeTestType.EVENT_STUDY:
        mde = mde_standardized_mean(
            sample_size, one_sided=True
        ).minimum_detectable_effect
        return (1.0 if mde < threshold.threshold else 0.0), mde, None
    return (
        None,
        None,
        "mean comparison needs window/non-window group sizes, "
        "unknown until the window is defined",
    )


def apply_guard(
    source: str,
    target: str,
    suggested_test_type: EdgeTestType,
    tested_edges: tuple[TestedEdge, ...],
) -> GuardOutcome:
    """The anti-retest guard for one candidate pair.

    Excluded: a tested edge (supported or rejected) matches the
    pair, the suggested test type, and the (unconditional)
    condition exactly — re-running it would duplicate the test.
    Downgraded: a REJECTED edge matches the pair but differs in
    test type or condition — admitted at half score, flagged.
    A SUPPORTED edge on the same pair under a different setting
    neither excludes nor downgrades: the follow-up question is
    different from re-testing a null.
    """
    downgrade: GuardOutcome | None = None
    for edge in tested_edges:
        if edge.status not in {EdgeStatus.SUPPORTED, EdgeStatus.REJECTED}:
            continue
        if (
            edge.source_instrument != source
            or edge.target_instrument != target
        ):
            continue
        if edge.test_type is suggested_test_type and edge.condition is None:
            return GuardOutcome(
                excluded=True,
                downgraded=False,
                reason=(
                    f"exact re-test of {edge.edge_id} "
                    f"({suggested_test_type.value}, unconditional)"
                ),
                edge_id=edge.edge_id,
            )
        if edge.status is EdgeStatus.REJECTED and downgrade is None:
            downgrade = GuardOutcome(
                excluded=False,
                downgraded=True,
                reason=(
                    f"same pair rejected under a different setting "
                    f"({edge.edge_id}: {edge.test_type.value}, "
                    f"condition "
                    f"{edge.condition if edge.condition else 'unconditional'})"
                ),
                edge_id=edge.edge_id,
            )
    if downgrade is not None:
        return downgrade
    return GuardOutcome(
        excluded=False, downgraded=False, reason=None, edge_id=None
    )


def _weighted_total(
    adjacency: float,
    data: float,
    power: float | None,
    weights: PlannerWeights,
) -> float:
    """Weighted total; a None power component renormalizes the rest."""
    if power is None:
        remaining = weights.adjacency + weights.data
        if remaining == 0.0:
            return 0.0
        return (
            weights.adjacency * adjacency + weights.data * data
        ) / remaining
    return (
        weights.adjacency * adjacency
        + weights.data * data
        + weights.power * power
    )


def rank_candidates(
    candidates: tuple[CandidatePair, ...],
    tested_edges: tuple[TestedEdge, ...],
    availability: AvailabilityConfig,
    fomc_statement_dates: tuple[date, ...],
    decision_records: Mapping[str, str],
    config: PlannerConfig | None = None,
) -> RankingResult:
    """Rank untested candidate pairs under the planner's rules.

    Deterministic: candidates are processed in (source, target)
    order and ties break lexicographically, so identical inputs
    always produce identical output. Candidates leave the ranking
    through exactly two lists, each entry carrying its reason:
    excluded (anti-retest guard) and unrankable (unknown data, or
    no overlapping panel window).
    """
    settings = config or PlannerConfig()
    tiers, supported_ids = adjacency_tiers(
        tested_edges,
        direct=settings.adjacency_tier_direct,
        one_hop=settings.adjacency_tier_one_hop,
    )
    ranked: list[RankedCandidate] = []
    excluded: list[ExcludedCandidate] = []
    unrankable: list[UnrankableCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda c: (c.source_instrument, c.target_instrument),
    ):
        source_id = candidate.source_instrument
        target_id = candidate.target_instrument
        suggested = suggest_test(source_id, target_id)
        guard = apply_guard(
            source_id, target_id, suggested.test_type, tested_edges
        )
        if guard.excluded:
            excluded.append(
                ExcludedCandidate(
                    source_instrument=source_id,
                    target_instrument=target_id,
                    reason=guard.reason or "exact re-test",
                    edge_id=guard.edge_id or "",
                )
            )
            continue
        source_panel = availability.panel(source_id)
        target_panel = availability.panel(target_id)
        unknown = [
            node
            for node, panel in (
                (source_id, source_panel),
                (target_id, target_panel),
            )
            if panel is None
        ]
        if unknown:
            unrankable.append(
                UnrankableCandidate(
                    source_instrument=source_id,
                    target_instrument=target_id,
                    reason=(
                        "data availability unknown for "
                        + ", ".join(sorted(unknown))
                        + " (no verified panel record; never assumed)"
                    ),
                )
            )
            continue
        assert source_panel is not None and target_panel is not None
        data = data_component(source_panel, target_panel)
        both_available = (
            source_panel.status is PanelStatus.AVAILABLE
            and target_panel.status is PanelStatus.AVAILABLE
        )
        notes: list[str] = []
        if not both_available:
            joint_n: int | None = None
            joint_basis = (
                "no joint sample: at least one panel is verified "
                "unavailable"
            )
            power: float | None = None
            mde: float | None = None
            mde_measure: str | None = None
            mde_threshold: float | None = None
            notes.append(
                "power unknown: no joint sample without both panels"
            )
        else:
            joint_n, joint_basis = estimate_joint_n(
                source_panel,
                target_panel,
                suggested,
                fomc_statement_dates,
                event_warmup_days=settings.event_warmup_days,
            )
            if joint_n == 0:
                unrankable.append(
                    UnrankableCandidate(
                        source_instrument=source_id,
                        target_instrument=target_id,
                        reason=(
                            "no overlapping panel window for the "
                            f"suggested {suggested.test_type.value} test "
                            f"({joint_basis})"
                        ),
                    )
                )
                continue
            threshold = settings.threshold_for(suggested.test_type)
            power, mde, power_note = power_component(
                suggested.test_type, joint_n, threshold
            )
            mde_measure = (
                threshold.effect_measure if threshold is not None else None
            )
            mde_threshold = (
                threshold.threshold if threshold is not None else None
            )
            if power_note is not None:
                notes.append(f"power unknown: {power_note}")
        if source_panel.calendar is PanelCalendar.MONTHLY:
            notes.append(
                "CPI step predictor: daily rows are not the effective "
                "sample size (69 distinct step values in-sample); "
                "the MDE uses daily rows, matching the H0012 audit "
                "treatment — confirm at design time"
            )
        adjacency = max(
            tiers.get(source_id, 0.0), tiers.get(target_id, 0.0)
        )
        adjacent_edges = sorted(
            {
                edge_id
                for node in (source_id, target_id)
                for edge_id in supported_ids.get(node, ())
            }
        )
        records = tuple(
            sorted(
                {
                    decision_records[edge_id]
                    for edge_id in adjacent_edges
                    if edge_id in decision_records
                }
            )
        )
        total = _weighted_total(adjacency, data, power, settings.weights)
        if guard.downgraded:
            total *= settings.downgrade_factor
        ranked.append(
            RankedCandidate(
                rank=len(ranked) + 1,  # provisional; reassigned after sorting
                source_instrument=source_id,
                target_instrument=target_id,
                test_type=suggested.test_type,
                frequency=suggested.frequency,
                mechanism=suggested.mechanism,
                suggestion_reason=suggested.reason,
                adjacency=adjacency,
                data=data,
                power=power,
                total=round(total, 10),
                downgraded=guard.downgraded,
                downgrade_reason=guard.reason,
                joint_n=joint_n,
                joint_n_basis=joint_basis,
                mde=mde,
                mde_measure=mde_measure,
                mde_threshold=mde_threshold,
                adjacent_supported_edges=tuple(adjacent_edges),
                decision_records=records,
                notes=tuple(notes),
            )
        )
    ranked.sort(key=lambda c: (-c.total, c.source_instrument, c.target_instrument))
    ranked = [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(ranked)
    ]
    excluded.sort(key=lambda c: (c.source_instrument, c.target_instrument))
    unrankable.sort(key=lambda c: (c.source_instrument, c.target_instrument))
    return RankingResult(
        ranked=tuple(ranked),
        excluded=tuple(excluded),
        unrankable=tuple(unrankable),
        weights=settings.weights,
        total_candidates=len(candidates),
    )
