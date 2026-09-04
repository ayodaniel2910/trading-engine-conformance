"""Unit tests for RunHeader, SourceRevision, EnvironmentLock and the
execution_authorized invariant."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.enums import HoldoutAccessState
from trading_engine_conformance.schema.holdout import HoldoutState
from trading_engine_conformance.schema.run import EnvironmentLock, RunHeader, SourceRevision


def _source_revision(**overrides: object) -> SourceRevision:
    fields: dict[str, object] = {
        "commit_hash": "a" * 40,
        "is_dirty": False,
        "repository_url": "https://example.invalid/org/repo",
    }
    fields.update(overrides)
    return SourceRevision(**fields)  # type: ignore[arg-type]


def _env_lock(**overrides: object) -> EnvironmentLock:
    fields: dict[str, object] = {
        "lock_hash": "b" * 64,
        "python_version": "3.11.8",
        "platform": "win32",
        "tool_versions": {"pytest": "8.2.0"},
    }
    fields.update(overrides)
    return EnvironmentLock(**fields)  # type: ignore[arg-type]


def _holdout() -> HoldoutState:
    return HoldoutState(state=HoldoutAccessState.SEALED, sealed_ts=1, opened_ts=None)


def _header(**overrides: object) -> RunHeader:
    fields: dict[str, object] = {
        "run_id": "run-0001",
        "schema_version": "1.0.0",
        "created_ts": 1_767_225_600_000_000_000,
        "source_revision": _source_revision(),
        "environment_lock": _env_lock(),
        "seed": 42,
        "tool_versions": {"tec": "0.1.0"},
        "holdout_state": _holdout(),
    }
    fields.update(overrides)
    return RunHeader(**fields)  # type: ignore[arg-type]


class TestSourceRevision:
    def test_valid(self) -> None:
        rev = _source_revision()
        assert rev.is_dirty is False

    def test_rejects_short_hash(self) -> None:
        with pytest.raises(ValidationError):
            _source_revision(commit_hash="abc123")

    def test_rejects_non_hex_hash(self) -> None:
        with pytest.raises(ValidationError):
            _source_revision(commit_hash="z" * 40)

    def test_repository_url_optional(self) -> None:
        rev = _source_revision(repository_url=None)
        assert rev.repository_url is None


class TestEnvironmentLock:
    def test_valid(self) -> None:
        lock = _env_lock()
        assert lock.python_version == "3.11.8"

    def test_rejects_bad_hash(self) -> None:
        with pytest.raises(ValidationError):
            _env_lock(lock_hash="not-a-hash")

    def test_rejects_empty_tool_versions(self) -> None:
        with pytest.raises(ValidationError):
            _env_lock(tool_versions={})


class TestRunHeader:
    def test_valid(self) -> None:
        header = _header()
        assert header.execution_authorized is False

    def test_execution_authorized_defaults_false(self) -> None:
        header = _header()
        assert header.model_dump()["execution_authorized"] is False

    def test_execution_authorized_rejects_true(self) -> None:
        with pytest.raises(ValidationError):
            RunHeader(
                run_id="run-0001",
                schema_version="1.0.0",
                created_ts=1,
                source_revision=_source_revision(),
                environment_lock=_env_lock(),
                seed=42,
                tool_versions={"tec": "0.1.0"},
                holdout_state=_holdout(),
                execution_authorized=True,
            )

    def test_rejects_unsupported_major_schema_version(self) -> None:
        with pytest.raises(ValidationError):
            _header(schema_version="99.0.0")

    def test_rejects_negative_seed(self) -> None:
        with pytest.raises(ValidationError):
            _header(seed=-1)

    def test_rejects_empty_run_id(self) -> None:
        with pytest.raises(ValidationError):
            _header(run_id="")

    def test_rejects_empty_tool_versions(self) -> None:
        with pytest.raises(ValidationError):
            _header(tool_versions={})

    def test_serialized_json_always_has_execution_authorized_false(self) -> None:
        header = _header()
        dumped = header.model_dump(mode="json")
        assert dumped["execution_authorized"] is False
