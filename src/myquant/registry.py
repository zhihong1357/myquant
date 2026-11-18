"""Append-only, hash-chained experiment ledger.

The hash chain detects tampering with records that are still present: any
change to a record's contents or its ``previous_hash`` breaks verification.
It does NOT detect truncation: deleting trailing records leaves a shorter
chain that still verifies. Use :func:`write_anchor` to publish the latest
record hash (and record count) to an independent anchor file — ideally one
committed to version control or stored on another machine — and pass that
file to :func:`read_and_verify` so truncation is detected as a mismatch
against the anchor.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from myquant.canonical import canonical_json
from myquant.files import atomic_replace

GENESIS_HASH = "0" * 64


def _default_anchor_path(ledger: Path) -> Path:
    return Path(str(ledger) + ".anchor")


def append_trial(
    path: str | Path,
    *,
    trial_id: str,
    hypothesis_id: str,
    status: str,
    result: dict[str, Any],
) -> str:
    """Append one immutable trial record and return its record hash.

    Each append re-reads and re-verifies the whole ledger to find the
    previous hash, so n appends cost O(n^2) time in total. That is
    acceptable for research-scale ledgers; this is not a high-throughput
    store.
    """
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
    record_hash = hashlib.sha256(canonical_json(payload)).hexdigest()
    record = {**payload, "record_hash": record_hash}
    with ledger.open("ab") as stream:
        stream.write(canonical_json(record) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return record_hash


def write_anchor(
    ledger_path: str | Path,
    anchor_path: str | Path | None = None,
) -> dict[str, Any]:
    """Publish the ledger's latest record hash to an independent anchor file.

    The anchor records the ledger's record count and latest record hash.
    Store it somewhere the ledger writer cannot silently rewrite — for
    example, committed to version control or on another machine — and pass
    it to :func:`read_and_verify` to detect truncation of trailing records.
    The ledger is fully verified before the anchor is written; a corrupt
    ledger produces no anchor. Returns the anchor payload.
    """
    ledger = Path(ledger_path)
    anchor = Path(anchor_path) if anchor_path is not None else _default_anchor_path(ledger)
    records = read_and_verify(ledger)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "ledger_file": ledger.name,
        "record_count": len(records),
        "latest_record_hash": (
            records[-1]["record_hash"] if records else GENESIS_HASH
        ),
        "anchored_at": datetime.now(UTC).isoformat(),
    }
    atomic_replace(anchor, canonical_json(payload) + b"\n")
    return payload


def read_and_verify(
    path: str | Path,
    *,
    anchor_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Read the ledger and verify its hash chain; fail closed on corruption.

    Without an anchor this verifies tampering only: a truncated ledger
    still verifies. With ``anchor_path``, the record count and latest
    record hash are additionally compared against the anchor, so deleting
    trailing records is detected. A missing or malformed anchor file fails
    closed.
    """
    ledger = Path(path)
    if not ledger.exists():
        records: list[dict[str, Any]] = []
    else:
        records = []
        expected_previous = GENESIS_HASH
        for line_number, raw_line in enumerate(ledger.read_bytes().splitlines(), start=1):
            if not raw_line:
                continue
            record = json.loads(raw_line)
            supplied_hash = record.pop("record_hash", None)
            if record.get("previous_hash") != expected_previous:
                raise ValueError(f"broken hash chain at line {line_number}")
            actual_hash = hashlib.sha256(canonical_json(record)).hexdigest()
            if supplied_hash != actual_hash:
                raise ValueError(f"record hash mismatch at line {line_number}")
            records.append({**record, "record_hash": supplied_hash})
            expected_previous = supplied_hash

    if anchor_path is not None:
        anchor = _read_anchor(Path(anchor_path))
        latest_hash = records[-1]["record_hash"] if records else GENESIS_HASH
        if (
            anchor["record_count"] != len(records)
            or anchor["latest_record_hash"] != latest_hash
        ):
            raise ValueError(
                "ledger does not match its anchor: anchor records "
                f"{anchor['record_count']} record(s) ending at "
                f"{anchor['latest_record_hash']}, ledger has {len(records)} "
                f"record(s) ending at {latest_hash}; "
                "the ledger may have been truncated"
            )
    return records


def _read_anchor(anchor: Path) -> dict[str, Any]:
    if not anchor.exists():
        raise FileNotFoundError(f"anchor file not found: {anchor}")
    try:
        payload = json.loads(anchor.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"anchor file is not valid JSON: {anchor}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"anchor file has an unsupported format: {anchor}")
    record_count = payload.get("record_count")
    latest_hash = payload.get("latest_record_hash")
    if (
        not isinstance(record_count, int)
        or isinstance(record_count, bool)
        or record_count < 0
        or not isinstance(latest_hash, str)
        or len(latest_hash) != 64
        or any(char not in "0123456789abcdef" for char in latest_hash)
    ):
        raise ValueError(f"anchor file contains invalid record data: {anchor}")
    return payload
