"""Crash-safe atomic writes.

Data is written to a uniquely named temporary file in the same directory as
the final target, flushed and ``fsync``'d, then moved onto the final path
with ``os.replace`` -- an atomic rename on both POSIX and Windows. If the
process is interrupted at any point before the replace, the final path is
left untouched; no partially written file is ever visible under its final
name.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically write ``data`` to ``path``, creating parent directories
    as needed. Either the previous contents or the full new contents are
    visible under ``path`` at all times -- never a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    try:
        with tmp_path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path``. See ``atomic_write_bytes``."""
    atomic_write_bytes(path, text.encode(encoding))
