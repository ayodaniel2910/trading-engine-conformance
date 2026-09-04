"""Unit tests for DatasetIdentity: relative path, byte size, SHA-256."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.dataset import DatasetIdentity


def _make(**overrides: object) -> DatasetIdentity:
    fields: dict[str, object] = {
        "dataset_id": "gc-1min-2026",
        "relative_path": "data/gc_1min_2026.csv",
        "byte_size": 1234,
        "sha256": "a" * 64,
    }
    fields.update(overrides)
    return DatasetIdentity(**fields)  # type: ignore[arg-type]


class TestDatasetIdentity:
    def test_valid(self) -> None:
        dataset = _make()
        assert dataset.byte_size == 1234

    def test_rejects_negative_byte_size(self) -> None:
        with pytest.raises(ValidationError):
            _make(byte_size=-1)

    def test_zero_byte_size_allowed(self) -> None:
        dataset = _make(byte_size=0)
        assert dataset.byte_size == 0

    def test_rejects_absolute_path(self) -> None:
        with pytest.raises(ValidationError):
            _make(relative_path="/etc/passwd")

    def test_rejects_bad_hash(self) -> None:
        with pytest.raises(ValidationError):
            _make(sha256="not-a-hash")

    def test_rejects_empty_dataset_id(self) -> None:
        with pytest.raises(ValidationError):
            _make(dataset_id="")
