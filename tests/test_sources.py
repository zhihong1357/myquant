import pytest
from pydantic import ValidationError

from myquant.sources import LicenseStatus, SourceDefinition, SourceRegistry


def make_source(**overrides):
    values = {
        "source_id": "sample-api",
        "provider": "Example Data",
        "description": "Synthetic source for tests only",
        "license_status": LicenseStatus.APPROVED,
        "timestamp_basis": "publication timestamp",
    }
    values.update(overrides)
    return SourceDefinition(**values)


def test_source_registry_registers_and_reads_version(tmp_path):
    registry = SourceRegistry(tmp_path)
    definition = make_source()
    path = registry.register(definition, version=1)
    assert path.exists()
    assert registry.get("sample-api") == definition


def test_source_registry_never_overwrites_a_version(tmp_path):
    registry = SourceRegistry(tmp_path)
    registry.register(make_source())
    with pytest.raises(FileExistsError):
        registry.register(make_source(provider="Different Provider"))


def test_unknown_source_license_is_not_approved_for_research():
    source = make_source(license_status=LicenseStatus.UNKNOWN)
    with pytest.raises(PermissionError):
        source.require_research_permission()


def test_source_rejects_invalid_timestamp_basis():
    with pytest.raises(ValidationError):
        make_source(timestamp_basis="UTC")
