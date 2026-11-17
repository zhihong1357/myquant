"""Append-only, hash-chained experiment ledger."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


def _canonical(payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return encoded.encode("utf-8")


def append_trial(
    path: str | Path,
    *,
    trial_id: str,
    hypothesis_id: str,
    status: str,
    result: dict[str, Any],
) -> str:
    """Append one immutable trial record and return its record hash."""
    ledger = Path(path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = GENESIS_HASH
    if ledger.exists():
        records = read_and_verify(ledger)
        if records:
            previous_hash = records[-1]["record_hash"]

    payload = {
        "trial_id": trial_id,
        "hypothesis_id": hypothesis_id,
        "status": status,
        "result": result,
        "recorded_at": datetime.now(UTC).isoformat(),
        "previous_hash": previous_hash,
    }
    record_hash = hashlib.sha256(_canonical(payload)).hexdigest()
    record = {**payload, "record_hash": record_hash}
    with ledger.open("ab") as stream:
        stream.write(_canonical(record) + b"\n")
        stream.flush()
    return record_hash


def read_and_verify(path: str | Path) -> list[dict[str, Any]]:
    """Read the ledger and verify its hash chain; fail closed on corruption."""
    ledger = Path(path)
    if not ledger.exists():
        return []
    records: list[dict[str, Any]] = []
    expected_previous = GENESIS_HASH
    for line_number, raw_line in enumerate(ledger.read_bytes().splitlines(), start=1):
        if not raw_line:
            continue
        record = json.loads(raw_line)
        supplied_hash = record.pop("record_hash", None)
        if record.get("previous_hash") != expected_previous:
            raise ValueError(f"broken hash chain at line {line_number}")
        actual_hash = hashlib.sha256(_canonical(record)).hexdigest()
        if supplied_hash != actual_hash:
            raise ValueError(f"record hash mismatch at line {line_number}")
        records.append({**record, "record_hash": supplied_hash})
        expected_previous = supplied_hash
    return records
