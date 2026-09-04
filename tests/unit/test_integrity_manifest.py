"""Unit tests for manifest build/verify and tamper detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.hashing import sha256_bytes
from trading_engine_conformance.integrity.manifest import (
    Manifest,
    ManifestEntry,
    build_manifest,
    load_manifest,
    verify_manifest,
    write_manifest,
)
from trading_engine_conformance.integrity.paths import PathContainmentError


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "a.json").write_text('{"a":1}', encoding="utf-8")
    (run_dir / "sub").mkdir()
    (run_dir / "sub" / "b.json").write_text('{"b":2}', encoding="utf-8")
    return run_dir


class TestBuildManifest:
    def test_builds_entry_per_file(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        paths = {e.relative_path for e in manifest.entries}
        assert paths == {"a.json", "sub/b.json"}

    def test_entries_sorted_deterministically(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        paths = [e.relative_path for e in manifest.entries]
        assert paths == sorted(paths)

    def test_root_hash_stable_across_rebuilds(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        m1 = build_manifest(run_dir, created_ts=1)
        m2 = build_manifest(run_dir, created_ts=1)
        assert m1.root_hash == m2.root_hash

    def test_root_hash_changes_when_content_changes(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        m1 = build_manifest(run_dir, created_ts=1)
        (run_dir / "a.json").write_text('{"a":2}', encoding="utf-8")
        m2 = build_manifest(run_dir, created_ts=1)
        assert m1.root_hash != m2.root_hash

    def test_excludes_manifest_file_itself(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json")), encoding="utf-8"
        )
        rebuilt = build_manifest(run_dir, created_ts=1)
        assert "manifest.json" not in {e.relative_path for e in rebuilt.entries}

    def test_rejects_symlinked_file(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        target = tmp_path / "outside.json"
        target.write_text("{}", encoding="utf-8")
        link = run_dir / "link.json"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlink creation not permitted in this environment")
        with pytest.raises(PathContainmentError):
            build_manifest(run_dir, created_ts=1)


class TestVerifyManifest:
    def test_ok_when_untouched(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        receipt = verify_manifest(run_dir, manifest, verified_ts=2)
        assert receipt.ok is True
        assert receipt.missing == []
        assert receipt.extra == []
        assert receipt.changed == []

    def test_detects_missing_file(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        (run_dir / "a.json").unlink()
        receipt = verify_manifest(run_dir, manifest, verified_ts=2)
        assert receipt.ok is False
        assert receipt.missing == ["a.json"]

    def test_detects_extra_file(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        (run_dir / "extra.json").write_text("{}", encoding="utf-8")
        receipt = verify_manifest(run_dir, manifest, verified_ts=2)
        assert receipt.ok is False
        assert receipt.extra == ["extra.json"]

    def test_detects_changed_content(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        (run_dir / "a.json").write_text('{"a":"tampered"}', encoding="utf-8")
        receipt = verify_manifest(run_dir, manifest, verified_ts=2)
        assert receipt.ok is False
        assert receipt.changed == ["a.json"]

    def test_detects_duplicate_declared_paths(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        real = build_manifest(run_dir, created_ts=1)
        entries = [*list(real.entries), real.entries[0]]
        tampered = Manifest(
            schema_version=real.schema_version,
            created_ts=real.created_ts,
            entries=entries,
            root_hash=real.root_hash,
        )
        receipt = verify_manifest(run_dir, tampered, verified_ts=2)
        assert receipt.ok is False
        assert receipt.duplicate_paths == [real.entries[0].relative_path]

    def test_detects_case_collision(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        real = build_manifest(run_dir, created_ts=1)
        colliding_entry = ManifestEntry(relative_path="A.json", byte_size=7, sha256="a" * 64)
        entries = [*list(real.entries), colliding_entry]
        tampered = Manifest(
            schema_version=real.schema_version,
            created_ts=real.created_ts,
            entries=entries,
            root_hash=real.root_hash,
        )
        receipt = verify_manifest(run_dir, tampered, verified_ts=2)
        assert receipt.ok is False
        assert receipt.case_collisions == ["A.json", "a.json"]

    def test_detects_root_hash_mismatch(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        real = build_manifest(run_dir, created_ts=1)
        tampered = Manifest(
            schema_version=real.schema_version,
            created_ts=real.created_ts,
            entries=real.entries,
            root_hash="f" * 64,
        )
        receipt = verify_manifest(run_dir, tampered, verified_ts=2)
        assert receipt.ok is False
        assert receipt.root_hash_mismatch is True

    def test_round_trip_through_disk(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        manifest_path = run_dir / "manifest.json"
        write_manifest(manifest_path, manifest)
        loaded = load_manifest(manifest_path)
        receipt = verify_manifest(run_dir, loaded, verified_ts=2)
        assert receipt.ok is True

    def test_receipt_hash_is_tamper_evident(self, tmp_path: Path) -> None:
        run_dir = _make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        receipt = verify_manifest(run_dir, manifest, verified_ts=2)
        payload = receipt.model_dump(mode="json")
        payload["ok"] = False
        payload.pop("receipt_hash")
        recomputed = sha256_bytes(canonical_json_bytes(payload))
        assert recomputed != receipt.receipt_hash
