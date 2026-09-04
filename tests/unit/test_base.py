"""Unit tests for the strict base model: unknown-field rejection and
frozen (immutable) instances."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.base import StrictBaseModel


class _Sample(StrictBaseModel):
    a: int
    b: str


class TestStrictBaseModel:
    def test_accepts_known_fields(self) -> None:
        obj = _Sample(a=1, b="x")
        assert obj.a == 1
        assert obj.b == "x"

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            _Sample(a=1, b="x", c="unexpected")

    def test_is_frozen_immutable(self) -> None:
        obj = _Sample(a=1, b="x")
        with pytest.raises(ValidationError):
            obj.a = 2

    def test_rejects_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            _Sample(a=1)
