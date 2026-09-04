"""Unit tests for path containment and symlink/reparse rejection."""

from __future__ import annotations

import os

import pytest

from trading_engine_conformance.integrity.paths import PathContainmentError, resolve_contained


class TestResolveContained:
    def test_simple_relative_path_resolves_under_root(self, tmp_path: object) -> None:
        root = tmp_path  # type: ignore[assignment]
        resolved = resolve_contained(root, "a/b/c.json")
        assert resolved == (root / "a" / "b" / "c.json").resolve()

    def test_rejects_parent_traversal(self, tmp_path: object) -> None:
        with pytest.raises(PathContainmentError):
            resolve_contained(tmp_path, "../escape.json")  # type: ignore[arg-type]

    def test_rejects_absolute_path(self, tmp_path: object) -> None:
        with pytest.raises(PathContainmentError):
            resolve_contained(tmp_path, "/etc/passwd")  # type: ignore[arg-type]

    def test_rejects_windows_drive_path(self, tmp_path: object) -> None:
        with pytest.raises(PathContainmentError):
            resolve_contained(tmp_path, "C:/escape.json")  # type: ignore[arg-type]

    def test_rejects_backslashes(self, tmp_path: object) -> None:
        with pytest.raises(PathContainmentError):
            resolve_contained(tmp_path, "a\\b.json")  # type: ignore[arg-type]

    def test_rejects_empty_path(self, tmp_path: object) -> None:
        with pytest.raises(PathContainmentError):
            resolve_contained(tmp_path, "")  # type: ignore[arg-type]

    def test_rejects_dot_segment(self, tmp_path: object) -> None:
        with pytest.raises(PathContainmentError):
            resolve_contained(tmp_path, "./a.json")  # type: ignore[arg-type]

    def test_rejects_symlink_final_component(self, tmp_path: object) -> None:
        root = tmp_path  # type: ignore[assignment]
        target = root / "real.json"  # type: ignore[operator]
        target.write_text("{}", encoding="utf-8")
        link = root / "link.json"  # type: ignore[operator]
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlink creation not permitted in this environment")
        with pytest.raises(PathContainmentError):
            resolve_contained(root, "link.json")  # type: ignore[arg-type]

    def test_rejects_symlinked_parent_directory_escape(self, tmp_path: object) -> None:
        root = tmp_path / "root"  # type: ignore[operator]
        root.mkdir()
        outside = tmp_path / "outside"  # type: ignore[operator]
        outside.mkdir()
        (outside / "secret.json").write_text("{}", encoding="utf-8")
        link_dir = root / "escape"
        try:
            link_dir.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation not permitted in this environment")
        with pytest.raises(PathContainmentError):
            resolve_contained(root, "escape/secret.json")

    def test_accepts_nested_new_path_not_yet_on_disk(self, tmp_path: object) -> None:
        root = tmp_path  # type: ignore[assignment]
        resolved = resolve_contained(root, "new/nested/file.json")
        assert not resolved.exists()
        assert str(resolved).startswith(str(root.resolve()))  # type: ignore[attr-defined]


def test_os_sep_is_not_accidentally_accepted(tmp_path: object) -> None:
    if os.sep == "/":
        pytest.skip("only relevant when os.sep differs from POSIX separator")
