"""Immutable Parquet observation batches and point-in-time queries."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from myquant.contracts import Observation, require_utc
from myquant.sources import SourceRegistry, _write_new_file


class ParquetPITStore:
    """Append-only observation batches with availability-time filtering.

    Corrections are new rows with higher revision numbers. Old rows are never
    overwritten, so a historical as-of query can recover what was knowable then.
    Only observations from explicitly research-approved source versions are
    admitted to the canonical research table.
    """

    def __init__(self, root: str | Path, source_registry: SourceRegistry) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.source_registry = source_registry

    def write_batch(self, observations: Sequence[Observation]) -> Path:
        if not observations:
            raise ValueError("cannot write an empty observation batch")
        for source_id, source_version in {
            (item.source_id, item.source_version) for item in observations
        }:
            self.source_registry.require_research_permission(
                source_id,
                version=source_version,
            )
        rows = [item.model_dump(mode="python") for item in observations]
        table = pa.Table.from_pylist(rows)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd", version="2.6")
        content = sink.getvalue().to_pybytes()
        digest = hashlib.sha256(content).hexdigest()
        target = self.root / f"{digest}.parquet"
        _write_new_file(target, content)
        return target

    def query_as_of(
        self,
        decision_time: datetime,
        *,
        instrument_ids: set[str] | None = None,
        fields: set[str] | None = None,
    ) -> list[Observation]:
        """Return the latest source revision knowable at decision_time.

        Revision resolution is performed independently per instrument, venue,
        field, event_time and exact source version. Multiple data sources remain
        separate; callers must not silently average conflicting providers.
        """
        decision = require_utc(decision_time)
        eligible: list[Observation] = []
        for path in sorted(self.root.glob("*.parquet")):
            table = pq.read_table(path)
            for row in table.to_pylist():
                observation = Observation.model_validate(row)
                self.source_registry.require_research_permission(
                    observation.source_id,
                    version=observation.source_version,
                )
                if observation.available_at > decision:
                    continue
                if instrument_ids is not None and observation.instrument_id not in instrument_ids:
                    continue
                if fields is not None and observation.field not in fields:
                    continue
                eligible.append(observation)

        latest: dict[tuple[str, str, str, datetime, str, int], Observation] = {}
        for observation in eligible:
            key = (
                observation.instrument_id,
                observation.venue,
                observation.field,
                observation.event_time,
                observation.source_id,
                observation.source_version,
            )
            previous = latest.get(key)
            if previous is None:
                latest[key] = observation
                continue
            current_order = _revision_order(observation)
            previous_order = _revision_order(previous)
            if current_order > previous_order:
                latest[key] = observation
            elif current_order == previous_order and observation.value != previous.value:
                raise ValueError(
                    "conflicting observations share the same source revision and timestamps"
                )

        return sorted(
            latest.values(),
            key=lambda item: (
                item.event_time,
                item.instrument_id,
                item.field,
                item.source_id,
                item.source_version,
            ),
        )


def _revision_order(observation: Observation) -> tuple[int, datetime, datetime]:
    return (
        observation.revision,
        observation.available_at,
        observation.ingested_at,
    )
