"""Versioned, timestamp-aware contracts shared by research modules."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    offset = value.utcoffset()
    if offset is None:
        raise ValueError("timestamps must be timezone-aware")
    if offset.total_seconds() != 0:
        return value.astimezone(UTC)
    return value


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HypothesisStatus(StrEnum):
    DRAFT = "draft"
    REGISTERED = "registered"
    TESTING = "testing"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    RETIRED = "retired"


class Observation(StrictContract):
    """One value with separate event, availability, and ingestion clocks.

    available_at may precede event_time for forecasts and scheduled future
    events. It must not be inferred from event_time.
    """

    schema_version: Annotated[int, Field(ge=1)] = 1
    instrument_id: Annotated[str, Field(min_length=1)]
    venue: Annotated[str, Field(min_length=1)]
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    field: Annotated[str, Field(min_length=1)]
    value: Annotated[float, Field(allow_inf_nan=False)]
    unit: Annotated[str, Field(min_length=1)]
    source_id: Annotated[str, Field(min_length=1)]
    source_version: Annotated[int, Field(ge=1)] = 1
    revision: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode="after")
    def validate_times(self) -> Observation:
        event = require_utc(self.event_time)
        available = require_utc(self.available_at)
        ingested = require_utc(self.ingested_at)
        if ingested < available:
            raise ValueError("ingested_at cannot precede available_at")
        object.__setattr__(self, "event_time", event)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "ingested_at", ingested)
        return self


class Hypothesis(StrictContract):
    hypothesis_id: Annotated[str, Field(pattern=r"^H[0-9]{4,}$")]
    title: Annotated[str, Field(min_length=8)]
    statement: Annotated[str, Field(min_length=20)]
    null_hypothesis: Annotated[str, Field(min_length=10)]
    universe: tuple[str, ...]
    horizon_seconds: Annotated[int, Field(gt=0)]
    benchmark: Annotated[str, Field(min_length=1)]
    cost_model: Annotated[str, Field(min_length=1)]
    rejection_criteria: tuple[str, ...]
    status: HypothesisStatus = HypothesisStatus.DRAFT
    created_at: datetime

    @model_validator(mode="after")
    def validate_created_at(self) -> Hypothesis:
        object.__setattr__(self, "created_at", require_utc(self.created_at))
        if not self.universe:
            raise ValueError("universe must contain at least one instrument or market")
        if not self.rejection_criteria:
            raise ValueError("at least one rejection criterion is required")
        return self


class FeatureRecord(StrictContract):
    feature_id: Annotated[str, Field(min_length=1)]
    feature_version: Annotated[str, Field(min_length=1)]
    instrument_id: Annotated[str, Field(min_length=1)]
    observation_time: datetime
    available_at: datetime
    value: Annotated[float, Field(allow_inf_nan=False)]
    input_fingerprints: tuple[str, ...]
    config_fingerprint: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def validate_feature_time(self) -> FeatureRecord:
        observation = require_utc(self.observation_time)
        available = require_utc(self.available_at)
        if available < observation:
            raise ValueError("feature cannot be available before its observation time")
        if not self.input_fingerprints:
            raise ValueError("feature must identify its input data")
        object.__setattr__(self, "observation_time", observation)
        object.__setattr__(self, "available_at", available)
        return self


def is_available_at(observation: Observation, decision_time: datetime) -> bool:
    """Return whether an observation was knowable at a decision timestamp."""
    decision = require_utc(decision_time)
    return observation.available_at <= decision
