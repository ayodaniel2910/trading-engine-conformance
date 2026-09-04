"""Canonical JSON serialization.

Deterministic key ordering, no incidental whitespace, ``Decimal`` rendered
as a string (never a JSON number), non-ASCII preserved as UTF-8 rather than
``\\uXXXX``-escaped, and binary ``float`` rejected outright so economic
values can never silently round-trip through IEEE-754.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def _default(obj: Any) -> str:
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"object of type {type(obj).__name__} is not canonical-JSON serializable")


def _reject_floats(obj: Any) -> None:
    if isinstance(obj, float):
        raise TypeError("float values are not permitted in canonical JSON; use Decimal")
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, float):
                raise TypeError("float keys are not permitted in canonical JSON")
            _reject_floats(value)
    elif isinstance(obj, list | tuple):
        for item in obj:
            _reject_floats(item)


def canonical_json_dumps(obj: Any) -> str:
    """Serialize ``obj`` to a canonical JSON string.

    Keys are sorted, separators are minimal, non-ASCII characters are kept
    as-is (UTF-8), and ``Decimal`` values render as strings. Raises
    ``TypeError`` if any ``float`` value or key is present anywhere in the
    structure.
    """
    _reject_floats(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
        allow_nan=False,
    )


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize ``obj`` to canonical JSON UTF-8 bytes. See ``canonical_json_dumps``."""
    return canonical_json_dumps(obj).encode("utf-8")
