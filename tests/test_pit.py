from datetime import UTC, datetime, timedelta

import pytest

from myquant.contracts import Observation
from myquant.pit import ParquetPITStore
from myquant.sources import LicenseStatus, SourceDefinition, SourceRegistry


def make_store(tmp_path):
    registry = SourceRegistry(tmp_path / "source-registry")
    for source_id in ("sample", "other"):
        registry.register(
            SourceDefinition(
                source_id=source_id,
                provider="Synthetic test fixture",
                description="Artificial data generated exclusively for unit tests",
                license_status=LicenseStatus.APPROVED,
                permission_basis="Synthetic test fixture; no third-party market data is used.",
                timestamp_basis="synthetic event timestamp",
            )
        )
    return ParquetPITStore(tmp_path / "observations", registry)


def make_observation(
    *,
    revision: int = 1,
    available_offset_seconds: int = 0,
    value: float = 1.0,
    event_time: datetime | None = None,
    source_id: str = "sample",
) -> Observation:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return Observation(
        instrument_id="volatility:vix",
        venue="CBOE",
        event_time=event_time or base,
        available_at=base + timedelta(seconds=available_offset_seconds),
        ingested_at=base + timedelta(seconds=available_offset_seconds + 1),
        field="close",
        value=value,
        unit="index_points",
        source_id=source_id,
        revision=revision,
    )


def test_query_as_of_hides_later_available_revision(tmp_path):
    store = make_store(tmp_path)
    store.write_batch([
        make_observation(revision=1, available_offset_seconds=2, value=20.0),
        make_observation(revision=2, available_offset_seconds=10, value=21.0),
    ])
    decision = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=5)
    result = store.query_as_of(decision)
    assert len(result) == 1
    assert result[0].revision == 1
    assert result[0].value == 20.0


def test_query_as_of_selects_latest_known_revision(tmp_path):
    store = make_store(tmp_path)
    store.write_batch([
        make_observation(revision=1, available_offset_seconds=2, value=20.0),
        make_observation(revision=2, available_offset_seconds=10, value=21.0),
    ])
    decision = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=20)
    result = store.query_as_of(decision)
    assert len(result) == 1
    assert result[0].revision == 2
    assert result[0].value == 21.0


def test_query_as_of_allows_forecast_available_before_future_event(tmp_path):
    store = make_store(tmp_path)
    event_time = datetime(2026, 2, 1, tzinfo=UTC)
    store.write_batch([make_observation(event_time=event_time, value=3.5)])
    decision = datetime(2026, 1, 15, tzinfo=UTC)
    result = store.query_as_of(decision)
    assert len(result) == 1
    assert result[0].event_time == event_time


def test_query_as_of_keeps_separate_sources(tmp_path):
    store = make_store(tmp_path)
    base = make_observation()
    second = base.model_copy(update={"source_id": "other", "value": 99.0})
    store.write_batch([base, second])
    result = store.query_as_of(datetime(2026, 1, 2, tzinfo=UTC))
    assert len(result) == 2
    assert {item.source_id for item in result} == {"sample", "other"}


def test_write_batch_is_deduplicated(tmp_path):
    store = make_store(tmp_path)
    batch = [make_observation()]
    first = store.write_batch(batch)
    second = store.write_batch(batch)
    assert first == second


def test_write_batch_rejects_unapproved_source(tmp_path):
    store = make_store(tmp_path)
    observation = make_observation(source_id="unknown")
    with pytest.raises(PermissionError, match="not registered"):
        store.write_batch([observation])
