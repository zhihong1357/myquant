"""Canonical JSON encoding shared by hash-chained research records."""

from __future__ import annotations

import json
from typing import Any


def canonical_json(value: Any) -> bytes:
    """Encode a value as canonical JSON bytes for hashing and storage.

    Keys are sorted, separators are compact, non-ASCII text is preserved,
    and NaN/Infinity are rejected. Every hash input in the codebase uses
    this exact encoding so fingerprints are comparable across modules.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
