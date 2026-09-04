"""Tamper-evident manifest verification receipts.

A ``VerificationReceipt`` records exactly what ``verify_manifest`` found:
missing/extra/changed/duplicate declared paths, case-insensitive path
collisions, and whether the manifest's own declared root hash matches the
hash recomputed from its entries. The receipt carries its own
``receipt_hash`` -- the SHA-256 of the canonical JSON of every other field
-- so the verification *result itself* cannot be silently edited without
detection.
"""

from __future__ import annotations

from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.hashing import sha256_bytes
from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.types import PortableRelPath, Sha256Hex, UtcNanos


class VerificationReceipt(StrictBaseModel):
    manifest_root_hash: Sha256Hex
    verified_ts: UtcNanos
    ok: bool
    missing: list[PortableRelPath]
    extra: list[PortableRelPath]
    changed: list[PortableRelPath]
    duplicate_paths: list[PortableRelPath]
    case_collisions: list[PortableRelPath]
    root_hash_mismatch: bool
    receipt_hash: Sha256Hex


def build_receipt(
    *,
    manifest_root_hash: str,
    verified_ts: int,
    missing: list[str],
    extra: list[str],
    changed: list[str],
    duplicate_paths: list[str],
    case_collisions: list[str],
    root_hash_mismatch: bool,
) -> VerificationReceipt:
    """Build a ``VerificationReceipt`` from verification findings.

    ``ok`` is derived: true iff every finding list is empty and the
    manifest's declared root hash matches its recomputed value.
    """
    missing_sorted = sorted(missing)
    extra_sorted = sorted(extra)
    changed_sorted = sorted(changed)
    duplicate_sorted = sorted(duplicate_paths)
    case_collisions_sorted = sorted(case_collisions)
    ok = not (
        missing_sorted
        or extra_sorted
        or changed_sorted
        or duplicate_sorted
        or case_collisions_sorted
        or root_hash_mismatch
    )
    payload: dict[str, object] = {
        "manifest_root_hash": manifest_root_hash,
        "verified_ts": verified_ts,
        "ok": ok,
        "missing": missing_sorted,
        "extra": extra_sorted,
        "changed": changed_sorted,
        "duplicate_paths": duplicate_sorted,
        "case_collisions": case_collisions_sorted,
        "root_hash_mismatch": root_hash_mismatch,
    }
    receipt_hash = sha256_bytes(canonical_json_bytes(payload))
    return VerificationReceipt(
        manifest_root_hash=manifest_root_hash,
        verified_ts=verified_ts,
        ok=ok,
        missing=missing_sorted,
        extra=extra_sorted,
        changed=changed_sorted,
        duplicate_paths=duplicate_sorted,
        case_collisions=case_collisions_sorted,
        root_hash_mismatch=root_hash_mismatch,
        receipt_hash=receipt_hash,
    )
