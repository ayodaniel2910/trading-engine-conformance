"""Manifest binding a run directory's declared artifacts to their SHA-256
hashes and sizes, plus build/verify against the real filesystem.

Verification never descends into symlinked directories and never trusts a
file that is itself a symlink: such paths are reported as ``changed`` (if
declared) or ``extra`` (if not), never silently hashed through.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.hashing import sha256_bytes, sha256_file
from trading_engine_conformance.integrity.atomic import atomic_write_text
from trading_engine_conformance.integrity.paths import PathContainmentError, resolve_contained
from trading_engine_conformance.integrity.receipt import VerificationReceipt, build_receipt
from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.types import PortableRelPath, Sha256Hex, UtcNanos
from trading_engine_conformance.schema.version import CURRENT_SCHEMA_VERSION

MANIFEST_FILENAME = "manifest.json"


class ManifestEntry(StrictBaseModel):
    relative_path: PortableRelPath
    byte_size: int
    sha256: Sha256Hex


class Manifest(StrictBaseModel):
    schema_version: str
    created_ts: UtcNanos
    entries: list[ManifestEntry]
    root_hash: Sha256Hex


def _walk_actual(root: Path, *, exclude: set[str]) -> tuple[list[Path], list[str]]:
    """Return ``(safe_file_paths, symlink_relative_paths)`` under ``root``.

    Never descends into a symlinked directory (``os.walk(followlinks=False)``),
    so a real subtree replaced by a symlink is discovered as missing rather
    than silently read from an unexpected location.
    """
    safe_files: list[Path] = []
    symlinks: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(dirnames)
        current_dir = Path(dirpath)
        for filename in sorted(filenames):
            file_path = current_dir / filename
            rel = file_path.relative_to(root).as_posix()
            if rel in exclude:
                continue
            if file_path.is_symlink():
                symlinks.append(rel)
            else:
                safe_files.append(file_path)
    return safe_files, symlinks


def _compute_root_hash(entries: list[ManifestEntry]) -> str:
    payload = [
        {"relative_path": e.relative_path, "byte_size": e.byte_size, "sha256": e.sha256}
        for e in entries
    ]
    return sha256_bytes(canonical_json_bytes(payload))


def _find_duplicate_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for path in paths:
        if path in seen:
            duplicates.add(path)
        seen.add(path)
    return sorted(duplicates)


def _find_case_collisions(paths: list[str]) -> list[str]:
    groups: dict[str, set[str]] = {}
    for path in paths:
        groups.setdefault(path.lower(), set()).add(path)
    collisions: set[str] = set()
    for group in groups.values():
        if len(group) > 1:
            collisions.update(group)
    return sorted(collisions)


def build_manifest(
    run_dir: Path, *, created_ts: int, schema_version: str = CURRENT_SCHEMA_VERSION
) -> Manifest:
    """Build a ``Manifest`` for every file under ``run_dir`` (excluding
    ``manifest.json`` itself). Raises ``PathContainmentError`` if any file
    under ``run_dir`` is itself a symlink."""
    root = run_dir.resolve(strict=True)
    safe_files, symlinks = _walk_actual(root, exclude={MANIFEST_FILENAME})
    if symlinks:
        raise PathContainmentError(
            f"refusing to include symlinked file(s) in manifest: {sorted(symlinks)!r}"
        )
    entries: list[ManifestEntry] = []
    for file_path in sorted(safe_files, key=lambda p: p.relative_to(root).as_posix()):
        rel = file_path.relative_to(root).as_posix()
        digest, size = sha256_file(file_path)
        entries.append(ManifestEntry(relative_path=rel, byte_size=size, sha256=digest))
    root_hash = _compute_root_hash(entries)
    return Manifest(
        schema_version=schema_version, created_ts=created_ts, entries=entries, root_hash=root_hash
    )


def verify_manifest(run_dir: Path, manifest: Manifest, *, verified_ts: int) -> VerificationReceipt:
    """Verify ``manifest`` against the real contents of ``run_dir``.

    Returns a ``VerificationReceipt`` describing every discrepancy found;
    never raises for a tampered/corrupted state -- that state is exactly
    what the receipt reports.
    """
    root = run_dir.resolve(strict=True)

    declared: dict[str, ManifestEntry] = {}
    for entry in manifest.entries:
        declared.setdefault(entry.relative_path, entry)

    duplicate_paths = _find_duplicate_paths([e.relative_path for e in manifest.entries])
    case_collisions = _find_case_collisions([e.relative_path for e in manifest.entries])

    safe_files, symlinks = _walk_actual(root, exclude={MANIFEST_FILENAME})
    safe_rel_paths = {f.relative_to(root).as_posix() for f in safe_files}
    symlink_rel_paths = set(symlinks)
    actual_rel_paths = safe_rel_paths | symlink_rel_paths

    declared_paths = set(declared)
    missing = sorted(declared_paths - actual_rel_paths)
    extra = sorted((actual_rel_paths - declared_paths) | (symlink_rel_paths - declared_paths))

    changed: list[str] = sorted(symlink_rel_paths & declared_paths)
    for rel in sorted(declared_paths & safe_rel_paths):
        entry = declared[rel]
        try:
            file_path = resolve_contained(root, rel)
            digest, size = sha256_file(file_path)
        except (PathContainmentError, OSError):
            changed.append(rel)
            continue
        if digest != entry.sha256 or size != entry.byte_size:
            changed.append(rel)
    changed = sorted(set(changed))

    recomputed_root_hash = _compute_root_hash(list(manifest.entries))
    root_hash_mismatch = recomputed_root_hash != manifest.root_hash

    return build_receipt(
        manifest_root_hash=recomputed_root_hash,
        verified_ts=verified_ts,
        missing=missing,
        extra=extra,
        changed=changed,
        duplicate_paths=duplicate_paths,
        case_collisions=case_collisions,
        root_hash_mismatch=root_hash_mismatch,
    )


def write_manifest(path: Path, manifest: Manifest) -> None:
    """Atomically write ``manifest`` as canonical JSON to ``path``."""
    atomic_write_text(path, canonical_json_bytes(manifest.model_dump(mode="json")).decode("utf-8"))


def load_manifest(path: Path) -> Manifest:
    """Load and validate a ``Manifest`` from a JSON file at ``path``."""
    return Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
