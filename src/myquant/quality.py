"""Auditable quality diagnostics for normalized market observations."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from math import ceil, isfinite

from pydantic import Field

from myquant.contracts import Observation, StrictContract


class QualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class QualityIssue(StrictContract):
    code: str = Field(min_length=3)
    severity: QualitySeverity
    message: str = Field(min_length=1)
    count: int = Field(default=1, ge=1)


class ObservationQualityReport(StrictContract):
    row_count: int = Field(ge=0)
    unique_series_count: int = Field(ge=0)
    unique_instrument_count: int = Field(ge=0)
    source_versions: tuple[str, ...]
    event_time_min: datetime | None = None
    event_time_max: datetime | None = None
    median_ingestion_lag_seconds: float | None = None
    p95_ingestion_lag_seconds: float | None = None
    available_before_event_count: int = Field(ge=0)
    available_after_event_count: int = Field(ge=0)
    missing_expected_series: tuple[str, ...] = ()
    issues: tuple[QualityIssue, ...] = ()


SeriesKey = tuple[str, str, str, str, int]

# Issues that can occur once per row are aggregated by code with a count
# instead of emitting one issue per row, so a large batch cannot produce a
# report as large as its input.
_REPEATABLE_ISSUES: dict[str, tuple[QualitySeverity, str]] = {
    "DUPLICATE_ROW": (
        QualitySeverity.WARNING,
        "An identical observation row appears more than once.",
    ),
    "REVISION_COLLISION": (
        QualitySeverity.ERROR,
        "Different observation payloads share the same instrument, "
        "event time, source version and revision.",
    ),
    "HIGH_INGESTION_LAG": (
        QualitySeverity.WARNING,
        "Observation reached MyQuant later than the configured "
        "ingestion-lag threshold.",
    ),
}


def inspect_observations(
    observations: Sequence[Observation],
    *,
    expected_series: set[SeriesKey] | None = None,
    max_ingestion_lag_seconds: float | None = None,
) -> ObservationQualityReport:
    """Summarize quality without inventing an expected sampling frequency.

    A series key is (instrument_id, venue, field, source_id, source_version).
    Missing coverage is reported only when the caller supplies an explicit
    expected_series set. Missing rows cannot be interpreted as missing bars
    until the market calendar and expected cadence are known.

    The p95 ingestion lag uses the nearest-rank definition (index
    min(n-1, ceil(0.95*n)-1)), not linear interpolation. Repeated issues
    are aggregated by code with a count.
    """
    if (
        max_ingestion_lag_seconds is not None
        and (
            not isfinite(max_ingestion_lag_seconds)
            or max_ingestion_lag_seconds < 0
        )
    ):
        raise ValueError("max_ingestion_lag_seconds must be finite and non-negative")

    issues: list[QualityIssue] = []
    if not observations:
        issues.append(
            QualityIssue(
                code="EMPTY_BATCH",
                severity=QualitySeverity.ERROR,
                message="No observations were supplied for quality inspection.",
            )
        )
        missing = tuple(sorted(_format_series(key) for key in (expected_series or set())))
        if missing:
            issues.append(
                QualityIssue(
                    code="MISSING_EXPECTED_SERIES",
                    severity=QualitySeverity.ERROR,
                    message="No observations were found for expected series.",
                    count=len(missing),
                )
            )
        return ObservationQualityReport(
            row_count=0,
            unique_series_count=0,
            unique_instrument_count=0,
            source_versions=(),
            available_before_event_count=0,
            available_after_event_count=0,
            missing_expected_series=missing,
            issues=tuple(issues),
        )

    seen: dict[tuple[str, str, str, datetime, str, int, int], Observation] = {}
    series: set[SeriesKey] = set()
    instruments: set[str] = set()
    ingestion_lags: list[float] = []
    repeatable_counts: dict[str, int] = {}
    before_event = 0
    after_event = 0

    for observation in observations:
        series.add(_series_key(observation))
        instruments.add(observation.instrument_id)
        identity = (
            observation.instrument_id,
            observation.venue,
            observation.field,
            observation.event_time,
            observation.source_id,
            observation.source_version,
            observation.revision,
        )
        previous = seen.get(identity)
        if previous is None:
            seen[identity] = observation
        elif previous != observation:
            repeatable_counts["REVISION_COLLISION"] = (
                repeatable_counts.get("REVISION_COLLISION", 0) + 1
            )
        else:
            repeatable_counts["DUPLICATE_ROW"] = (
                repeatable_counts.get("DUPLICATE_ROW", 0) + 1
            )

        ingestion_lag = (
            observation.ingested_at - observation.available_at
        ).total_seconds()
        ingestion_lags.append(ingestion_lag)
        if (
            max_ingestion_lag_seconds is not None
            and ingestion_lag > max_ingestion_lag_seconds
        ):
            repeatable_counts["HIGH_INGESTION_LAG"] = (
                repeatable_counts.get("HIGH_INGESTION_LAG", 0) + 1
            )

        if observation.available_at < observation.event_time:
            before_event += 1
        elif observation.available_at > observation.event_time:
            after_event += 1

    for code, count in repeatable_counts.items():
        severity, message = _REPEATABLE_ISSUES[code]
        issues.append(
            QualityIssue(
                code=code,
                severity=severity,
                message=message,
                count=count,
            )
        )

    missing_expected = tuple(
        sorted(
            _format_series(key)
            for key in (expected_series or set()).difference(series)
        )
    )
    if missing_expected:
        issues.append(
            QualityIssue(
                code="MISSING_EXPECTED_SERIES",
                severity=QualitySeverity.ERROR,
                message="Expected instrument/field/source combinations are absent.",
                count=len(missing_expected),
            )
        )

    if before_event:
        issues.append(
            QualityIssue(
                code="AVAILABLE_BEFORE_EVENT",
                severity=QualitySeverity.INFO,
                message=(
                    "Some observations were available before their event_time; "
                    "this can be valid for forecasts and scheduled events."
                ),
                count=before_event,
            )
        )

    lags = sorted(ingestion_lags)
    p95_index = min(len(lags) - 1, ceil(0.95 * len(lags)) - 1)
    event_times = [item.event_time for item in observations]
    versions = tuple(
        sorted(
            {
                f"{item.source_id}@v{item.source_version}"
                for item in observations
            }
        )
    )

    return ObservationQualityReport(
        row_count=len(observations),
        unique_series_count=len(series),
        unique_instrument_count=len(instruments),
        source_versions=versions,
        event_time_min=min(event_times),
        event_time_max=max(event_times),
        median_ingestion_lag_seconds=_median(lags),
        p95_ingestion_lag_seconds=lags[p95_index],
        available_before_event_count=before_event,
        available_after_event_count=after_event,
        missing_expected_series=missing_expected,
        issues=tuple(issues),
    )


def _series_key(observation: Observation) -> SeriesKey:
    return (
        observation.instrument_id,
        observation.venue,
        observation.field,
        observation.source_id,
        observation.source_version,
    )


def _format_series(key: SeriesKey) -> str:
    instrument, venue, field, source, version = key
    return f"{instrument}|{venue}|{field}|{source}@v{version}"


def _median(values: list[float]) -> float:
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2
