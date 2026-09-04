"""Unit tests for streaming SHA-256 hashing and byte counting."""

import hashlib
from pathlib import Path

from trading_engine_conformance.hashing import sha256_bytes, sha256_file


class TestSha256Bytes:
    def test_matches_hashlib(self) -> None:
        data = b"hello world"
        assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()

    def test_empty_bytes(self) -> None:
        assert sha256_bytes(b"") == hashlib.sha256(b"").hexdigest()


class TestSha256File:
    def test_matches_hashlib_and_reports_size(self, tmp_path: Path) -> None:
        content = b"x" * (1024 * 1024 + 17)  # cross a chunk boundary
        target = tmp_path / "data.bin"
        target.write_bytes(content)

        digest, size = sha256_file(target)

        assert digest == hashlib.sha256(content).hexdigest()
        assert size == len(content)

    def test_empty_file(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.bin"
        target.write_bytes(b"")

        digest, size = sha256_file(target)

        assert digest == hashlib.sha256(b"").hexdigest()
        assert size == 0

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.bin"
        try:
            sha256_file(missing)
        except OSError:
            pass
        else:
            raise AssertionError("expected OSError for missing file")
