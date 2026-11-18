from datetime import UTC, datetime, timedelta

from myquant.contracts import Observation
from myquant.quality import QualitySeverity, inspect_observations


def make_observation(
    *,
    instrument_id: str = "volatility:vix",
    source_id: str = "sample",
    available_offset: int = 0,
    ingestion_delay: int = 2,
    event_time: datetime | None = None,
    value: float = 20.0,
    revision: int = 1,
) -> Observation:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    available = base + timedelta(seconds=available_offset)
    return Observation(
        instrument_id=instrument_id,
        venue="CBOE",
        event_time=event_time or base,
        available_at=available,
        ingested_at=available + timedelta(seconds=ingestion_delay),
        field="close",
        value=value,
        unit="index_points",
        source_id=source_id,
        revision=revision,
    )


def test_quality_report_summarizes_series_and_ingestion_lag():
    observations = [
        make_observation(ingestion_delay=2),
        make_observation(
            instrument_id="volatility:move",
            ingestion_delay=8,
        ),
    ]
    report = inspect_observations(observations)

    assert report.row_count == 2
    assert report.unique_series_count == 2
    assert report.unique_instrument_count == 2
    assert report.median_ingestion_lag_seconds == 5
    assert report.p95_ingestion_lag_seconds == 8


def test_quality_report_only_reports_missingness_against_expected_series():
    expected = {
        ("volatility:vix", "CBOE", "close", "sample", 1),
        ("volatility:move", "ICE", "close", "sample", 1),
    }
    report = inspect_observations(
        [make_observation()],
        expected_series=expected,
    )

    assert len(report.missing_expected_series) == 1
    missing_issue = next(
        issue for issue in report.issues if issue.code == "MISSING_EXPECTED_SERIES"
    )
    assert missing_issue.severity == QualitySeverity.ERROR


def test_quality_report_detects_duplicate_identical_rows():
    observation = make_observation()
    report = inspect_observations([observation, observation])
    assert any(issue.code == "DUPLICATE_ROW" for issue in report.issues)


def test_quality_report_detects_same_revision_collision():
    first = make_observation(value=20)
    second = first.model_copy(update={"value": 21})
    report = inspect_observations([first, second])
    assert any(issue.code == "REVISION_COLLISION" for issue in report.issues)


def test_quality_report_flags_high_ingestion_latency():
    observation = make_observation(ingestion_delay=30)
    report = inspect_observations(
        [observation],
        max_ingestion_lag_seconds=10,
    )
    assert any(issue.code == "HIGH_INGESTION_LAG" for issue in report.issues)


def test_quality_report_explains_pre_event_information():
    future_event = datetime(2026, 2, 1, tzinfo=UTC)
    observation = make_observation(event_time=future_event)
    report = inspect_observations([observation])
    assert report.available_before_event_count == 1
    assert any(issue.code == "AVAILABLE_BEFORE_EVENT" for issue in report.issues)


def test_quality_report_aggregates_repeated_issues_with_counts():
    observation = make_observation()
    report = inspect_observations([observation] * 5)
    duplicates = [issue for issue in report.issues if issue.code == "DUPLICATE_ROW"]
    assert len(duplicates) == 1
    assert duplicates[0].count == 4

    laggy = inspect_observations(
        [make_observation(ingestion_delay=30) for _ in range(3)],
        max_ingestion_lag_seconds=10,
    )
    lag_issues = [
        issue for issue in laggy.issues if issue.code == "HIGH_INGESTION_LAG"
    ]
    assert len(lag_issues) == 1
    assert lag_issues[0].count == 3


def test_quality_report_empty_batch_is_explicit_error():
    expected = {("volatility:vix", "CBOE", "close", "sample", 1)}
    report = inspect_observations([], expected_series=expected)
    assert report.row_count == 0
    assert any(issue.code == "EMPTY_BATCH" for issue in report.issues)
    assert len(report.missing_expected_series) == 1
