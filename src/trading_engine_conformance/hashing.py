"""Streaming SHA-256 hashing and byte counting.

Files are hashed in fixed-size chunks so arbitrarily large artifacts never
need to be loaded fully into memory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    """Return the hex-encoded SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    """Return ``(hex_digest, byte_count)`` for the file at ``path``.

    Reads the file in fixed-size chunks; raises ``OSError`` (e.g.
    ``FileNotFoundError``) if the file cannot be opened.
    """
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total
