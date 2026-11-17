import json
from datetime import UTC, datetime, timedelta

import pytest

from myquant.raw import RawStore


def test_raw_store_is_content_addressed_and_verifies_checksum(tmp_path):
    store = RawStore(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    record = store.put(
        b'{"bid": 1, "ask": 2}',
        source_id="test-feed",
        available_at=now,
        ingested_at=now + timedelta(seconds=1),
        content_type="application/json",
    )
    assert store.read_payload(record.record_id) == b'{"bid": 1, "ask": 2}'
    assert store.get_record(record.record_id).payload_sha256 == record.payload_sha256


def test_raw_store_is_idempotent_for_identical_ingestion(tmp_path):
    store = RawStore(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    kwargs = {
        "source_id": "test-feed",
        "available_at": now,
        "ingested_at": now + timedelta(seconds=1),
        "content_type": "text/plain",
    }
    first = store.put(b"payload", **kwargs)
    second = store.put(b"payload", **kwargs)
    assert first.record_id == second.record_id


def test_raw_store_keeps_distinct_provenance_manifests_for_same_bytes(tmp_path):
    store = RawStore(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first = store.put(
        b"same",
        source_id="source-a",
        available_at=now,
        ingested_at=now + timedelta(seconds=1),
        content_type="text/plain",
    )
    second = store.put(
        b"same",
        source_id="source-b",
        available_at=now,
        ingested_at=now + timedelta(seconds=1),
        content_type="text/plain",
    )
    assert first.payload_sha256 == second.payload_sha256
    assert first.record_id != second.record_id


def test_raw_store_rejects_ingestion_before_availability(tmp_path):
    store = RawStore(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="cannot precede"):
        store.put(
            b"x",
            source_id="test-feed",
            available_at=now + timedelta(seconds=2),
            ingested_at=now,
            content_type="text/plain",
        )


def test_raw_store_detects_blob_tampering(tmp_path):
    store = RawStore(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    record = store.put(
        b"original",
        source_id="test-feed",
        available_at=now,
        ingested_at=now,
        content_type="text/plain",
    )
    blob = store.blob_root / record.payload_sha256[:2] / f"{record.payload_sha256}.bin"
    blob.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        store.read_payload(record.record_id)


def test_raw_store_detects_manifest_tampering(tmp_path):
    store = RawStore(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    record = store.put(
        b"original",
        source_id="test-feed",
        available_at=now,
        ingested_at=now,
        content_type="text/plain",
    )
    manifest = store.manifest_root / record.record_id[:2] / f"{record.record_id}.json"
    data = json.loads(manifest.read_text())
    data["source_id"] = "forged-source"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="manifest integrity"):
        store.get_record(record.record_id)
