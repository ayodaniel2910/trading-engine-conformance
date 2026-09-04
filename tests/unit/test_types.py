"""Unit tests for the canonical scalar types: Decimal-as-string economic
fields and bounded UTC-nanosecond timestamps."""

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from trading_engine_conformance.schema.types import (
    EconomicDecimal,
    PortableRelPath,
    Sha256Hex,
    UtcNanos,
)


class _DecimalHolder(BaseModel):
    value: EconomicDecimal


class _NanosHolder(BaseModel):
    ts: UtcNanos


class _PathHolder(BaseModel):
    path: PortableRelPath


class _HashHolder(BaseModel):
    digest: Sha256Hex


class TestEconomicDecimal:
    def test_accepts_string_decimal(self) -> None:
        holder = _DecimalHolder(value="1.2345")
        assert holder.value == Decimal("1.2345")

    def test_accepts_decimal_instance(self) -> None:
        holder = _DecimalHolder(value=Decimal("10"))
        assert holder.value == Decimal("10")

    def test_rejects_float(self) -> None:
        with pytest.raises(ValidationError):
            _DecimalHolder(value=1.5)

    def test_rejects_bool(self) -> None:
        with pytest.raises(ValidationError):
            _DecimalHolder(value=True)

    def test_rejects_nan_string(self) -> None:
        with pytest.raises(ValidationError):
            _DecimalHolder(value="NaN")

    def test_rejects_infinity_string(self) -> None:
        with pytest.raises(ValidationError):
            _DecimalHolder(value="Infinity")

    def test_rejects_negative_infinity_string(self) -> None:
        with pytest.raises(ValidationError):
            _DecimalHolder(value="-Infinity")

    def test_rejects_malformed_string(self) -> None:
        with pytest.raises(ValidationError):
            _DecimalHolder(value="not-a-number")

    def test_serializes_as_canonical_string(self) -> None:
        holder = _DecimalHolder(value=Decimal("1.20"))
        dumped = holder.model_dump(mode="json")
        assert dumped["value"] == "1.20"
        assert isinstance(dumped["value"], str)

    def test_accepts_integer_string(self) -> None:
        holder = _DecimalHolder(value="42")
        assert holder.value == Decimal("42")


class TestUtcNanos:
    def test_accepts_zero(self) -> None:
        holder = _NanosHolder(ts=0)
        assert holder.ts == 0

    def test_accepts_reasonable_timestamp(self) -> None:
        # 2026-01-01T00:00:00Z in ns, approximately.
        holder = _NanosHolder(ts=1_767_225_600_000_000_000)
        assert holder.ts == 1_767_225_600_000_000_000

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            _NanosHolder(ts=-1)

    def test_rejects_above_int64_max(self) -> None:
        with pytest.raises(ValidationError):
            _NanosHolder(ts=2**63)

    def test_rejects_float(self) -> None:
        with pytest.raises(ValidationError):
            _NanosHolder(ts=1.0)

    def test_rejects_bool(self) -> None:
        with pytest.raises(ValidationError):
            _NanosHolder(ts=True)

    def test_rejects_string(self) -> None:
        with pytest.raises(ValidationError):
            _NanosHolder(ts="123")


class TestPortableRelPath:
    def test_accepts_simple_relative_path(self) -> None:
        holder = _PathHolder(path="data/prices.csv")
        assert holder.path == "data/prices.csv"

    def test_rejects_absolute_posix_path(self) -> None:
        with pytest.raises(ValidationError):
            _PathHolder(path="/etc/passwd")

    def test_rejects_windows_drive_path(self) -> None:
        with pytest.raises(ValidationError):
            _PathHolder(path="C:/IPDA_GOLD/secret.json")

    def test_rejects_backslashes(self) -> None:
        with pytest.raises(ValidationError):
            _PathHolder(path="data\\prices.csv")

    def test_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValidationError):
            _PathHolder(path="../secret.json")

    def test_rejects_embedded_parent_traversal(self) -> None:
        with pytest.raises(ValidationError):
            _PathHolder(path="data/../../secret.json")

    def test_rejects_empty_path(self) -> None:
        with pytest.raises(ValidationError):
            _PathHolder(path="")

    def test_rejects_current_dir_segment(self) -> None:
        with pytest.raises(ValidationError):
            _PathHolder(path="./data/prices.csv")


class TestSha256Hex:
    def test_accepts_valid_lowercase_hex(self) -> None:
        digest = "a" * 64
        holder = _HashHolder(digest=digest)
        assert holder.digest == digest

    def test_rejects_uppercase_hex(self) -> None:
        with pytest.raises(ValidationError):
            _HashHolder(digest="A" * 64)

    def test_rejects_wrong_length(self) -> None:
        with pytest.raises(ValidationError):
            _HashHolder(digest="a" * 63)

    def test_rejects_non_hex_characters(self) -> None:
        with pytest.raises(ValidationError):
            _HashHolder(digest="g" * 64)
