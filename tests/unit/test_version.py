"""Unit tests for schema-version dispatch: unknown major versions fail closed."""

import pytest

from trading_engine_conformance.schema.version import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_MAJOR_VERSION,
    SchemaVersionError,
    check_schema_version,
)


class TestSchemaVersionConstants:
    def test_current_version_matches_major(self) -> None:
        assert CURRENT_SCHEMA_VERSION.startswith(f"{SCHEMA_MAJOR_VERSION}.")


class TestCheckSchemaVersion:
    def test_accepts_current_version(self) -> None:
        check_schema_version(CURRENT_SCHEMA_VERSION)  # should not raise

    def test_accepts_same_major_different_minor_patch(self) -> None:
        check_schema_version(f"{SCHEMA_MAJOR_VERSION}.99.99")

    def test_rejects_unknown_major_version_higher(self) -> None:
        with pytest.raises(SchemaVersionError):
            check_schema_version(f"{SCHEMA_MAJOR_VERSION + 1}.0.0")

    def test_rejects_unknown_major_version_lower(self) -> None:
        with pytest.raises(SchemaVersionError):
            check_schema_version("0.9.0")

    def test_rejects_malformed_version_string(self) -> None:
        with pytest.raises(SchemaVersionError):
            check_schema_version("not-a-version")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(SchemaVersionError):
            check_schema_version("")
