"""Data-source registry with explicit research-use permissions."""

from __future__ import annotations

import json
import re
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
        description="Document whether timestamps mean event, publication, exchange, or retrieval time.",
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
        if target.exists():
            if target.read_text(encoding="utf-8") != payload:
                raise FileExistsError(f"source version already exists: {target}")
            return target
        _write_new_file(target, payload.encode("utf-8"))
        return target

    def get(self, source_id: str, *, version: int = 1) -> SourceDefinition:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]+", source_id):
            raise ValueError("invalid source_id")
        path = self.root / source_id / f"v{version}.json"
        return SourceDefinition.model_validate_json(path.read_text(encoding="utf-8"))


def _write_new_file(target: Path, content: bytes) -> None:
    """Create a file without replacing an existing path."""
    import os
    import tempfile

    target.parent.mkdir(parents=True, exist_ok=True)
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
            raise
    finally:
        temporary.unlink(missing_ok=True)
