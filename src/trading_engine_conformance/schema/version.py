"""Schema-version dispatch.

Every ``RunHeader`` records the schema version it was produced under. Only
the current major version is understood by this package; any other major
version -- higher or lower -- fails closed rather than being silently
misinterpreted under the wrong field semantics.
"""

from __future__ import annotations

import re

SCHEMA_MAJOR_VERSION = 1
CURRENT_SCHEMA_VERSION = f"{SCHEMA_MAJOR_VERSION}.0.0"

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class SchemaVersionError(ValueError):
    """Raised when a schema version string is malformed or unsupported."""


def check_schema_version(version: str) -> None:
    """Raise ``SchemaVersionError`` unless ``version`` is well-formed
    ``major.minor.patch`` with ``major == SCHEMA_MAJOR_VERSION``."""
    match = _VERSION_RE.match(version)
    if match is None:
        raise SchemaVersionError(f"malformed schema version string: {version!r}")
    major = int(match.group(1))
    if major != SCHEMA_MAJOR_VERSION:
        raise SchemaVersionError(
            f"unsupported schema major version {major}; this package only "
            f"understands major version {SCHEMA_MAJOR_VERSION}"
        )
