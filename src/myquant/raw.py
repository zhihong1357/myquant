"""Content-addressed immutable raw-payload storage."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from myquant.contracts import StrictContract, require_utc
from myquant.sources import _write_new_file


class RawPayloadRecord(StrictContract):
    schema_version: int = Field(default=1, ge=1)
    record_id: str = Field(min_length=64, max_length=64)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=2)
    source_version: int = Field(default=1, ge=1)
    event_time: datetime | None = None
    available_at: datetime
    ingested_at: datetime
    content_type: str = Field(min_length=3)
    byte_length: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_times(self) -> RawPayloadRecord:
        available = require_utc(self.available_at)
        ingested = require_utc(self.ingested_at)
        if ingested < available:
            raise ValueError("ingested_at cannot precede available_at")
        if self.event_time is not None:
            object.__setattr__(self, "event_time", require_utc(self.event_time))
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "ingested_at", ingested)
        return self


class RawStore:
    """Store exact payload bytes once, with immutable provenance manifests."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.blob_root = self.root / "blobs"
        self.manifest_root = self.root / "manifests"

    def put(
        self,
        payload: bytes,
        *,
        source_id: str,
        available_at: datetime,
        content_type: str,
        source_version: int = 1,
        event_time: datetime | None = None,
        ingested_at: datetime | None = None,
    ) -> RawPayloadRecord:
        if not source_id or len(source_id) < 2:
            raise ValueError("source_id must contain at least two characters")
        available = require_utc(available_at)
        ingested = require_utc(ingested_at or datetime.now(UTC))
        event = require_utc(event_time) if event_time is not None else None
        if ingested < available:
            raise ValueError("ingested_at cannot precede available_at")
        if source_version < 1:
            raise ValueError("source_version must be >= 1")

        payload_hash = hashlib.sha256(payload).hexdigest()
        metadata: dict[str, Any] = {
            "payload_sha256": payload_hash,
            "source_id": source_id,
            "source_version": source_version,
            "event_time": event.isoformat() if event else None,
            "available_at": available.isoformat(),
            "ingested_at": ingested.isoformat(),
            "content_type": content_type,
            "byte_length": len(payload),
        }
        record_id = hashlib.sha256(_canonical(metadata)).hexdigest()
        record = RawPayloadRecord(record_id=record_id, **metadata)

        blob_path = self.blob_root / payload_hash[:2] / f"{payload_hash}.bin"
        manifest_path = self.manifest_root / record_id[:2] / f"{record_id}.json"
        _write_new_file(blob_path, payload)
        manifest = json.dumps(
            record.model_dump(mode="json"),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        ) + "\n"
        _write_new_file(manifest_path, manifest.encode("utf-8"))
        return record

    def get_record(self, record_id: str) -> RawPayloadRecord:
        if len(record_id) != 64 or any(char not in "0123456789abcdef" for char in record_id):
            raise ValueError("record_id must be a lowercase SHA-256 digest")
        path = self.manifest_root / record_id[:2] / f"{record_id}.json"
        record = RawPayloadRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if record.record_id != record_id:
            raise ValueError("manifest record_id mismatch")
        expected_id = hashlib.sha256(
            _canonical({
                "payload_sha256": record.payload_sha256,
                "source_id": record.source_id,
                "source_version": record.source_version,
                "event_time": record.event_time.isoformat() if record.event_time else None,
                "available_at": record.available_at.isoformat(),
                "ingested_at": record.ingested_at.isoformat(),
                "content_type": record.content_type,
                "byte_length": record.byte_length,
            })
        ).hexdigest()
        if expected_id != record_id:
            raise ValueError("raw manifest integrity check failed")
        return record

    def read_payload(self, record_id: str) -> bytes:
        record = self.get_record(record_id)
        path = self.blob_root / record.payload_sha256[:2] / f"{record.payload_sha256}.bin"
        payload = path.read_bytes()
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != record.payload_sha256:
            raise ValueError("raw payload checksum mismatch")
        if len(payload) != record.byte_length:
            raise ValueError("raw payload length mismatch")
        return payload


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
