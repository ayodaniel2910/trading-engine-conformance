"""Unit tests for crash-safe atomic writes."""

from __future__ import annotations

import contextlib
from pathlib import Path

import trading_engine_conformance.integrity.atomic as atomic_mod
from trading_engine_conformance.integrity.atomic import atomic_write_bytes, atomic_write_text


class _SimulatedCrashError(Exception):
    pass


class TestAtomicWriteBytes:
    def test_writes_file_with_exact_contents(self, tmp_path: Path) -> None:
        target = tmp_path / "out.bin"
        atomic_write_bytes(target, b"hello world")
        assert target.read_bytes() == b"hello world"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "dir" / "out.bin"
        atomic_write_bytes(target, b"data")
        assert target.read_bytes() == b"data"

    def test_replaces_existing_file_atomically(self, tmp_path: Path) -> None:
        target = tmp_path / "out.bin"
        atomic_write_bytes(target, b"first")
        atomic_write_bytes(target, b"second")
        assert target.read_bytes() == b"second"

    def test_leaves_no_temp_file_behind(self, tmp_path: Path) -> None:
        target = tmp_path / "out.bin"
        atomic_write_bytes(target, b"data")
        leftovers = [p for p in tmp_path.iterdir() if p != target]
        assert leftovers == []

    def test_no_partial_file_visible_under_final_name_on_write_failure(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "out.bin"
        atomic_write_bytes(target, b"good data")

        original_open = Path.open

        def _boom_open(self: Path, *args: object, **kwargs: object) -> object:
            if self.name.endswith(".tmp") and "wb" in args:
                raise _SimulatedCrashError("simulated crash mid-write")
            return original_open(self, *args, **kwargs)

        try:
            Path.open = _boom_open  # type: ignore[method-assign]
            with contextlib.suppress(_SimulatedCrashError):
                atomic_mod.atomic_write_bytes(target, b"corrupted data")
        finally:
            Path.open = original_open  # type: ignore[method-assign]

        assert target.read_bytes() == b"good data"
        leftovers = [p for p in tmp_path.iterdir() if p != target]
        assert leftovers == []


class TestAtomicWriteText:
    def test_writes_utf8_text(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        atomic_write_text(target, "héllo")
        assert target.read_text(encoding="utf-8") == "héllo"
