from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from myquant.contracts import Observation, is_available_at


def make_observation(**overrides):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = {
        "instrument_id": "rates:ust:10y",
        "venue": "treasury",
        "event_time": now,
        "available_at": now + timedelta(seconds=2),
        "ingested_at": now + timedelta(seconds=5),
        "field": "yield",
        "value": 4.2,
        "unit": "percent",
        "source_id": "test",
    }
    values.update(overrides)
    return Observation(**values)


def test_observation_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        make_observation(event_time=datetime(2026, 1, 1))


def test_observation_rejects_ingestion_before_availability():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        make_observation(
            available_at=now + timedelta(seconds=2),
            ingested_at=now + timedelta(seconds=1),
        )


def test_pit_uses_available_at_not_event_time():
    observation = make_observation()
    decision = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=1)
    assert not is_available_at(observation, decision)
    assert is_available_at(observation, decision + timedelta(seconds=1))


def test_forecast_can_be_available_before_future_event():
    event_time = datetime(2026, 2, 1, tzinfo=UTC)
    available_at = datetime(2026, 1, 15, tzinfo=UTC)
    observation = make_observation(
        event_time=event_time,
        available_at=available_at,
        ingested_at=available_at + timedelta(seconds=1),
    )
    assert observation.available_at < observation.event_time
