"""Run identity: source revision, environment lock, and the immutable run
header.

``RunHeader.execution_authorized`` is typed ``Literal[False]`` -- not
``bool`` -- so no value other than the literal ``False`` type-checks or
validates. There is no configuration, environment variable, or CLI flag
anywhere in this package that can produce a ``RunHeader`` with
``execution_authorized=True``.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.holdout import HoldoutState
from trading_engine_conformance.schema.types import Sha256Hex, UtcNanos
from trading_engine_conformance.schema.version import SchemaVersionError, check_schema_version

_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40}$")


class SourceRevision(StrictBaseModel):
    commit_hash: str
    is_dirty: bool
    repository_url: str | None = None

    @field_validator("commit_hash")
    @classmethod
    def _check_commit_hash(cls, value: str) -> str:
        if not _COMMIT_HASH_RE.match(value):
            raise ValueError("commit_hash must be a 40-character lowercase hex SHA-1")
        return value


class EnvironmentLock(StrictBaseModel):
    lock_hash: Sha256Hex
    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    tool_versions: dict[str, str] = Field(min_length=1)


class RunHeader(StrictBaseModel):
    run_id: str = Field(min_length=1)
    schema_version: str
    created_ts: UtcNanos
    source_revision: SourceRevision
    environment_lock: EnvironmentLock
    seed: int = Field(ge=0)
    tool_versions: dict[str, str] = Field(min_length=1)
    holdout_state: HoldoutState
    execution_authorized: Literal[False] = False

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        try:
            check_schema_version(value)
        except SchemaVersionError as exc:
            raise ValueError(str(exc)) from exc
        return value
