"""Unit tests for tamper-evident verification receipts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from trading_engine_conformance.integrity.receipt import build_receipt


class TestBuildReceipt:
    def test_ok_when_no_discrepancies(self) -> None:
        receipt = build_receipt(
            manifest_root_hash="a" * 64,
            verified_ts=1,
            missing=[],
            extra=[],
            changed=[],
            duplicate_paths=[],
            case_collisions=[],
            root_hash_mismatch=False,
        )
        assert receipt.ok is True
        assert len(receipt.receipt_hash) == 64

    def test_not_ok_when_missing_present(self) -> None:
        receipt = build_receipt(
            manifest_root_hash="a" * 64,
            verified_ts=1,
            missing=["a.json"],
            extra=[],
            changed=[],
            duplicate_paths=[],
            case_collisions=[],
            root_hash_mismatch=False,
        )
        assert receipt.ok is False
        assert receipt.missing == ["a.json"]

    def test_not_ok_when_root_hash_mismatch(self) -> None:
        receipt = build_receipt(
            manifest_root_hash="a" * 64,
            verified_ts=1,
            missing=[],
            extra=[],
            changed=[],
            duplicate_paths=[],
            case_collisions=[],
            root_hash_mismatch=True,
        )
        assert receipt.ok is False

    def test_receipt_hash_deterministic_for_same_input(self) -> None:
        kwargs = {
            "manifest_root_hash": "b" * 64,
            "verified_ts": 42,
            "missing": ["x.json"],
            "extra": [],
            "changed": [],
            "duplicate_paths": [],
            "case_collisions": [],
            "root_hash_mismatch": False,
        }
        r1 = build_receipt(**kwargs)  # type: ignore[arg-type]
        r2 = build_receipt(**kwargs)  # type: ignore[arg-type]
        assert r1.receipt_hash == r2.receipt_hash

    def test_receipt_hash_changes_when_content_differs(self) -> None:
        base = build_receipt(
            manifest_root_hash="c" * 64,
            verified_ts=1,
            missing=[],
            extra=[],
            changed=[],
            duplicate_paths=[],
            case_collisions=[],
            root_hash_mismatch=False,
        )
        other = build_receipt(
            manifest_root_hash="c" * 64,
            verified_ts=2,
            missing=[],
            extra=[],
            changed=[],
            duplicate_paths=[],
            case_collisions=[],
            root_hash_mismatch=False,
        )
        assert base.receipt_hash != other.receipt_hash

    def test_lists_sorted_for_determinism(self) -> None:
        receipt = build_receipt(
            manifest_root_hash="d" * 64,
            verified_ts=1,
            missing=["b.json", "a.json"],
            extra=[],
            changed=[],
            duplicate_paths=[],
            case_collisions=[],
            root_hash_mismatch=False,
        )
        assert receipt.missing == ["a.json", "b.json"]

    def test_receipt_is_frozen(self) -> None:
        receipt = build_receipt(
            manifest_root_hash="e" * 64,
            verified_ts=1,
            missing=[],
            extra=[],
            changed=[],
            duplicate_paths=[],
            case_collisions=[],
            root_hash_mismatch=False,
        )
        with pytest.raises(ValidationError):
            receipt.ok = False  # type: ignore[misc]
