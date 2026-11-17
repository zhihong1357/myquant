"""Data-source registry with explicit research-use permissions."""

from __future__ import annotations

import json
import os
import tempfile
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from myquant.contracts import StrictContract


class LicenseStatus(StrEnum):
    APPROVED = "approved"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"


class SourceDefinition(StrictContract):
    source_id: str = Field(min_length=2, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]+$")
    provider: str = Field(min_length=1)
    description: str = Field(min_length=8)
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    terms_url: str | None = None
    attribution: str | None = None
    nominal_delay_seconds: int = Field(default=0, ge=0)
    timestamp_basis: str = Field(
        min_length=5,
        description=(
            "Document whether timestamps mean event, publication, exchange, or retrieval time."
        ),
    )

    def require_research_permission(self) -> None:
        if self.license_status != LicenseStatus.APPROVED:
            raise PermissionError(
                f"source {self.source_id!r} is not approved for research use "
                f"(status={self.license_status.value})"
            )


class SourceRegistry:
    """Versioned local registry; each definition is stored as a separate file."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def register(self, definition: SourceDefinition, *, version: int = 1) -> Path:
        if version < 1:
            raise ValueError("version must be >= 1")
        directory = self.root / definition.source_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"v{version}.json"
        payload = json.dumps(
            definition.model_dump(mode="json"),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        ) + "\n"
        _write_new_file(target, payload.encode("utf-8"))
        return target

    def get(self, source_id: str, *, version: int = 1) -> SourceDefinition:
        if version < 1:
            raise ValueError("version must be >= 1")
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        if not source_id or any(char not in allowed for char in source_id):
            raise ValueError("invalid source_id")
        path = self.root / source_id / f"v{version}.json"
        return SourceDefinition.model_validate_json(path.read_text(encoding="utf-8"))


def _write_new_file(target: Path, content: bytes) -> None:
    """Atomically create a file; identical existing bytes are treated as idempotent."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() == content:
            return
        raise FileExistsError(f"immutable path already contains different bytes: {target}")

    descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != content:
                raise
    finally:
        temporary.unlink(missing_ok=True)
