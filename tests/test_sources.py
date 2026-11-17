import pytest
from pydantic import ValidationError

from myquant.sources import LicenseStatus, SourceDefinition, SourceRegistry


def make_source(**overrides):
    values = {
        "source_id": "sample-api",
        "provider": "Example Data",
        "description": "Synthetic source for tests only",
        "license_status": LicenseStatus.APPROVED,
        "permission_basis": "Synthetic test fixture; no third-party market data is used.",
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


def test_approved_source_requires_permission_basis():
    with pytest.raises(ValidationError):
        make_source(permission_basis=None)


def test_source_registry_permission_gate_rejects_unregistered_sources(tmp_path):
    registry = SourceRegistry(tmp_path)
    with pytest.raises(PermissionError, match="not registered"):
        registry.require_research_permission("unregistered-feed")


def test_source_registry_rejects_path_traversal(tmp_path):
    registry = SourceRegistry(tmp_path)
    with pytest.raises(ValueError, match="invalid"):
        registry.get("../secret")
