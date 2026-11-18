"""Study specification for the experiment assistant (Stage 6c).

A :class:`StudySpec` is everything the scaffold needs to generate one
standard study directory: the study number and slug, the hypothesis id,
the instrument pair and test type, the data sources, the universe and
calendars, and the acceptance criteria with their effect-size threshold.
Everything else — the mechanism, the windows, the benchmark, the cost
model, the fixed parameters — is a researcher decision and stays a TODO
in the generated ``design.json``.

The scaffold never invents design: thresholds and criteria come from
this spec (or from a planner draft mapped onto it); the generator writes
them verbatim. Unknown values are refused, never defaulted: a spec with
a bad slug, a mismatched pair for its test type, or a source id the
generator cannot verify is rejected before anything is written.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from myquant.contracts import StrictContract
from myquant.graph import EdgeTestType
from myquant.hypotheses import MultiplicityCorrection

TODO = "TODO"

#: Horizon in seconds per observation frequency. Monthly uses the
#: planner's 30-day convention (2,592,000 s), matching template.py.
HORIZON_SECONDS: dict[str, int] = {
    "daily": 86_400,
    "1h": 3_600,
    "monthly": 2_592_000,
}

#: Bar length in seconds for panel gap invalidation. Monthly bars are
#: not uniform (28–31 days), so no gap invalidation applies.
BAR_SECONDS: dict[str, int | None] = {
    "daily": 86_400,
    "1h": 3_600,
    "monthly": None,
}

#: PIT store suffix per frequency (one store per frequency, as in 001:
#: daily and hourly observations share event times but carry different
#: values and must never sit in the same store).
PIT_STORE_SUFFIX: dict[str, str] = {
    "daily": "1d",
    "1h": "1h",
    "monthly": "1mo",
}

#: Test types that are within-instrument level tests (self-loops):
#: source and target must be the same instrument.
SELF_LOOP_TEST_TYPES = frozenset(
    {EdgeTestType.MEAN_COMPARISON, EdgeTestType.EVENT_STUDY}
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SOURCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]+$")
_CALENDAR_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
#: Instrument ids must already satisfy the catalog contract's pattern
#: (myquant.market.Instrument), so a bad id is refused at spec time
#: instead of failing later at preregistration.
_INSTRUMENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:_./-]+$")


class ScaffoldFrequency(StrEnum):
    """Observation frequencies the scaffold knows how to wire."""

    DAILY = "daily"
    HOURLY = "1h"
    MONTHLY = "monthly"


class ScaffoldError(ValueError):
    """The scaffold refuses: a guard tripped, nothing was written."""


class StudySpec(StrictContract):
    """The complete input to one scaffold generation.

    Required fields are the researcher's decisions about *what* the
    study is. Optional text fields come from a planner draft when one
    is mapped onto the spec (``None`` means the draft left it TODO);
    the generator writes ``None`` fields as ``"TODO"`` in
    ``design.json``. Planner provenance fields are carried through to
    the draft for audit, never into the preregistration.
    """

    schema_version: Annotated[int, Field(ge=1)] = 1
    study_number: Annotated[int, Field(ge=1, le=999)]
    slug: Annotated[str, Field(min_length=1)]
    hypothesis_id: Annotated[str, Field(pattern=r"^H[0-9]{4,}$")]
    trial_id: Annotated[str, Field(pattern=r"^T[0-9]{4,}$")] | None = None
    source_instrument: Annotated[str, Field(min_length=1)]
    target_instrument: Annotated[str, Field(min_length=1)]
    test_type: EdgeTestType
    frequency: ScaffoldFrequency
    source_ids: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1
    )
    universe: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1
    )
    calendar_ids: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1
    )
    minimum_effect_size: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    acceptance_criteria: tuple[Annotated[str, Field(min_length=1)], ...] = (
        Field(min_length=1)
    )

    # Planner-derived text (None -> TODO in design.json).
    research_question: str | None = None
    null_hypothesis: str | None = None
    alternative_hypothesis: str | None = None
    target_definition: str | None = None
    primary_metric: str | None = None
    model_definition: tuple[str, ...] = ()
    rejection_criteria: tuple[str, ...] = ()
    missing_data_policy: str | None = None
    multiple_testing_method: str | None = None
    target_error_rate: Annotated[float, Field(gt=0, lt=1)] | None = None

    # Planner provenance (audit only; never registered).
    planner_rank: Annotated[int, Field(ge=1)] | None = None
    planner_total_score: Annotated[float, Field(ge=0, le=1)] | None = None
    suggested_test_reason: str | None = None
    adjacent_supported_edges: tuple[str, ...] = ()
    decision_records: tuple[str, ...] = ()
    estimated_joint_rows: Annotated[int, Field(ge=0)] | None = None
    estimated_joint_rows_basis: str | None = None
    planner_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_study_identity(self) -> StudySpec:
        expected_suffix = f"-{self.study_number:03d}"
        if not _SLUG_PATTERN.fullmatch(self.slug):
            raise ValueError(
                "slug must be lowercase kebab-case "
                f"(letters, digits, hyphens): {self.slug!r}"
            )
        if not self.slug.endswith(expected_suffix):
            raise ValueError(
                f"slug must end with the study number {expected_suffix!r}: "
                f"{self.slug!r}"
            )
        if self.test_type in SELF_LOOP_TEST_TYPES:
            if self.source_instrument != self.target_instrument:
                raise ValueError(
                    f"{self.test_type.value} is a within-instrument test: "
                    "source and target must be the same instrument"
                )
        elif self.source_instrument == self.target_instrument:
            raise ValueError(
                f"{self.test_type.value} is a cross-instrument test: "
                "source and target must differ"
            )
        if self.source_instrument not in self.universe:
            raise ValueError("universe must include the source instrument")
        if self.target_instrument not in self.universe:
            raise ValueError("universe must include the target instrument")
        if len(set(self.universe)) != len(self.universe):
            raise ValueError("universe entries must be unique")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids entries must be unique")
        if len(set(self.calendar_ids)) != len(self.calendar_ids):
            raise ValueError("calendar_ids entries must be unique")
        if len(set(self.acceptance_criteria)) != len(self.acceptance_criteria):
            raise ValueError("acceptance_criteria entries must be unique")
        for source_id in self.source_ids:
            if not _SOURCE_ID_PATTERN.fullmatch(source_id):
                raise ValueError(f"invalid source id: {source_id!r}")
        for calendar_id in self.calendar_ids:
            if not _CALENDAR_ID_PATTERN.fullmatch(calendar_id):
                raise ValueError(f"invalid calendar id: {calendar_id!r}")
        for instrument_id in self.universe:
            if not _INSTRUMENT_ID_PATTERN.fullmatch(instrument_id):
                raise ValueError(
                    "instrument id must match the catalog pattern "
                    f"^[a-z0-9][a-z0-9:_./-]+$: {instrument_id!r}"
                )
        if self.multiple_testing_method is not None:
            valid_methods = {
                item.value for item in MultiplicityCorrection
            }
            if self.multiple_testing_method not in valid_methods:
                raise ValueError(
                    "multiple_testing_method must be one of "
                    f"{sorted(valid_methods)}: "
                    f"{self.multiple_testing_method!r}"
                )
        return self

    @property
    def horizon_seconds(self) -> int:
        """Prediction horizon in seconds for the spec frequency."""
        return HORIZON_SECONDS[self.frequency.value]

    @property
    def bar_seconds(self) -> int | None:
        """Bar length for panel gap invalidation (None for monthly)."""
        return BAR_SECONDS[self.frequency.value]

    @property
    def pit_store_suffix(self) -> str:
        """PIT store directory suffix for the spec frequency."""
        return PIT_STORE_SUFFIX[self.frequency.value]
