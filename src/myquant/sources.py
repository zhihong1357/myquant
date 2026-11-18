"""Data-source registry with explicit research-use permissions."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from myquant.contracts import StrictContract
from myquant.files import write_new_file


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
    permission_basis: str | None = None
    terms_url: str | None = None
    attribution: str | None = None
    nominal_delay_seconds: int = Field(default=0, ge=0)
    timestamp_basis: str = Field(
        min_length=5,
        description=(
            "Document whether timestamps mean event, publication, exchange, or retrieval time."
        ),
    )

    @model_validator(mode="after")
    def validate_permission_basis(self) -> SourceDefinition:
        if self.license_status == LicenseStatus.APPROVED and not self.permission_basis:
            raise ValueError("approved sources require a documented permission_basis")
        return self

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
        write_new_file(target, payload.encode("utf-8"))
        return target

    def get(self, source_id: str, *, version: int = 1) -> SourceDefinition:
        if version < 1:
            raise ValueError("version must be >= 1")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]+", source_id):
            raise ValueError("invalid source_id")
        path = self.root / source_id / f"v{version}.json"
        return SourceDefinition.model_validate_json(path.read_text(encoding="utf-8"))

    def require_research_permission(
        self,
        source_id: str,
        *,
        version: int = 1,
    ) -> SourceDefinition:
        try:
            definition = self.get(source_id, version=version)
        except FileNotFoundError as exc:
            raise PermissionError(
                f"source {source_id!r} version {version} is not registered"
            ) from exc
        definition.require_research_permission()
        return definition
