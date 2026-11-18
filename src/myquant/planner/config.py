"""Configuration contracts for the hypothesis planner (Stage 6a).

The planner ranks untested candidate pairs from the market graph by
explicit, auditable criteria. Every number that shapes the ranking
lives here as a declared parameter — never as a hidden constant in
the scoring code — so anyone can re-run the ranking under a different
weighting and see how the shortlist changes. The weights are
parameters, not findings: no weighting is "optimal" or "validated".

Two configurations matter:

- **Data availability** (``AvailabilityConfig``): one verified panel
  record per graph node, hand-written from the studies' manifests
  (``research/planner-6a/data_availability.json``). A node with no
  record is *unknown* (never assumed available); a record may also
  state that a panel is *unavailable* (verified: no usable panel).
  Unknown and unavailable are different states and the planner treats
  them differently (see :mod:`myquant.planner.scoring`).
- **Planner configuration** (``PlannerConfig``): scoring weights,
  the anti-retest downgrade factor, the lab effect-size thresholds
  each test type is judged against, and the event-study warm-up.

The thresholds are lab conventions recorded in the preregistrations
and study reports, cited per threshold below; they are inputs to the
planner, not conclusions it draws.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from myquant.contracts import StrictContract
from myquant.graph import EdgeTestType

#: Default scoring weights: adjacency 0.4, data 0.3, power 0.3.
#: Adjacency carries the largest weight because it is the only
#: component that uses the lab's own evidence (supported edges);
#: data and power are feasibility gates of equal standing. The
#: choice is documented, not derived: the validation report shows
#: how the shortlist moves under other weightings.
DEFAULT_WEIGHT_ADJACENCY = 0.4
DEFAULT_WEIGHT_DATA = 0.3
DEFAULT_WEIGHT_POWER = 0.3

#: Anti-retest downgrade: a candidate on a pair already rejected
#: under a *different* test type or condition keeps half its score.
#: The lab's recurring pattern is same-day transmission with no
#: next-day carryover, so re-testing the same pair under another
#: setting needs a new reason; the downgrade prices that in.
DEFAULT_DOWNGRADE_FACTOR = 0.5

#: Warm-up (calendar days) before the first usable FOMC event in a
#: cross-section design: the CAR estimation window needs 60 trading
#: days of panel history, approximated as 84 calendar days.
DEFAULT_EVENT_WARMUP_DAYS = 84


class PanelCalendar(StrEnum):
    """Calendar a verified panel runs on."""

    CALENDAR_DAY = "calendar_day"
    TRADING_DAY = "trading_day"
    MONTHLY = "monthly"


class PanelStatus(StrEnum):
    """Whether a node has a verified usable panel.

    AVAILABLE means a panel was verified from a study manifest.
    UNAVAILABLE means the lab verified that no usable panel exists
    (e.g. no free source). A node with no record at all is UNKNOWN
    and is never treated as available.
    """

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class PanelAvailability(StrictContract):
    """One node's verified data panel, hand-written from manifests.

    ``first``/``last`` are the panel's date range (inclusive) and
    ``rows`` the verified row count on that range. ``step_start`` is
    set only for step-function predictors (CPI): the first date the
    predictor is usable on the daily grid (the first release date),
    which is later than the first reference month.
    """

    instrument_id: Annotated[str, Field(min_length=1)]
    status: PanelStatus = PanelStatus.AVAILABLE
    source: Annotated[str, Field(min_length=1)]
    first: date | None = None
    last: date | None = None
    rows: Annotated[int, Field(ge=0)] = 0
    calendar: PanelCalendar = PanelCalendar.TRADING_DAY
    step_start: date | None = None
    verified_by: Annotated[str, Field(min_length=1)]
    notes: str = ""

    @model_validator(mode="after")
    def validate_panel(self) -> PanelAvailability:
        if self.status is PanelStatus.AVAILABLE:
            if self.first is None or self.last is None:
                raise ValueError("an available panel needs first and last dates")
            if self.last < self.first:
                raise ValueError("panel last date precedes its first date")
            if self.rows < 1:
                raise ValueError("an available panel needs at least one row")
        return self


class AvailabilityConfig(StrictContract):
    """The verified panels behind the planner, keyed by instrument id."""

    schema_version: Annotated[int, Field(ge=1)] = 1
    panels: tuple[PanelAvailability, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> AvailabilityConfig:
        ids = [panel.instrument_id for panel in self.panels]
        if len(set(ids)) != len(ids):
            raise ValueError("panel instrument ids must be unique")
        return self

    def panel(self, instrument_id: str) -> PanelAvailability | None:
        """The panel record for a node, or None when unknown."""
        for record in self.panels:
            if record.instrument_id == instrument_id:
                return record
        return None


class PlannerWeights(StrictContract):
    """Scoring weights. They must sum to one; they are parameters."""

    adjacency: Annotated[float, Field(ge=0.0, le=1.0)]
    data: Annotated[float, Field(ge=0.0, le=1.0)]
    power: Annotated[float, Field(ge=0.0, le=1.0)]

    @model_validator(mode="after")
    def validate_sum(self) -> PlannerWeights:
        total = self.adjacency + self.data + self.power
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"planner weights must sum to 1.0, got {total}")
        return self


class TestTypeThreshold(StrictContract):
    """Lab effect-size threshold for one test type.

    The power component scores 1 when the design's MDE at the
    available sample size is *below* this threshold — i.e. the
    design can detect a threshold-sized effect at 80% power — and
    0 otherwise. Thresholds are lab conventions, cited in the
    planner documentation.
    """

    test_type: EdgeTestType
    effect_measure: Annotated[str, Field(min_length=1)]
    threshold: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    alpha: Annotated[float, Field(gt=0.0, lt=1.0)] = 0.05
    power: Annotated[float, Field(gt=0.0, lt=1.0)] = 0.80


class PlannerConfig(StrictContract):
    """All parameters that shape a ranking, in one place."""

    weights: PlannerWeights = PlannerWeights(
        adjacency=DEFAULT_WEIGHT_ADJACENCY,
        data=DEFAULT_WEIGHT_DATA,
        power=DEFAULT_WEIGHT_POWER,
    )
    downgrade_factor: Annotated[float, Field(gt=0.0, le=1.0)] = (
        DEFAULT_DOWNGRADE_FACTOR
    )
    adjacency_tier_direct: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    adjacency_tier_one_hop: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    event_warmup_days: Annotated[int, Field(ge=0)] = DEFAULT_EVENT_WARMUP_DAYS
    thresholds: tuple[TestTypeThreshold, ...] = (
        # Lead-lag partial R-squared 0.005: the minimum effect size
        # preregistered in every lead-lag study (e.g. H0001).
        TestTypeThreshold(
            test_type=EdgeTestType.LEAD_LAG,
            effect_measure="partial_r_squared",
            threshold=0.005,
        ),
        # Cross-section R-squared 0.05: H0008's acceptance criterion.
        TestTypeThreshold(
            test_type=EdgeTestType.CROSS_SECTION,
            effect_measure="r_squared",
            threshold=0.05,
        ),
        # Standardized mean CAR 0.3: H0007/H0011's acceptance
        # criterion (standardized mean CAR at least 0.3 in magnitude).
        TestTypeThreshold(
            test_type=EdgeTestType.EVENT_STUDY,
            effect_measure="standardized_mean_car",
            threshold=0.3,
        ),
        # Mean ratio 1.15: H0006/H0010's acceptance criterion
        # (window/non-window mean |log return| ratio at least 1.15).
        TestTypeThreshold(
            test_type=EdgeTestType.MEAN_COMPARISON,
            effect_measure="mean_ratio",
            threshold=1.15,
        ),
    )

    def threshold_for(self, test_type: EdgeTestType) -> TestTypeThreshold | None:
        """The lab threshold for a test type, or None when unmapped."""
        for entry in self.thresholds:
            if entry.test_type is test_type:
                return entry
        return None


DEFAULT_CONFIG = PlannerConfig()
