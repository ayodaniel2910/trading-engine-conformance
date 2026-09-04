"""Canonical scalar types shared across the neutral schema.

``EconomicDecimal`` is the only type permitted for economic fields (price,
size, fees, PnL, ...). It accepts ``Decimal`` or ``str`` input only -- never
``float`` or ``bool`` -- and rejects non-finite values (``NaN``,
``Infinity``, ``-Infinity``) and malformed strings. It always serializes as
a canonical decimal string, never a JSON number, so downstream consumers
never round-trip through binary floating point.

``UtcNanos`` is a bounded integer representing a UTC timestamp in
nanoseconds since the Unix epoch. It accepts ``int`` only -- never
``float``, ``bool`` or ``str`` -- and is bounded to ``[0, 2**63 - 1]`` (a
signed 64-bit integer range), which comfortably covers 1970-01-01 through
the year 2262.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, PydanticCustomError, core_schema

_INT64_MAX = 2**63 - 1
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class _EconomicDecimalAnnotation:
    """Pydantic-aware Decimal type: str/Decimal input, finite only, str output."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                str, return_schema=core_schema.str_schema(), when_used="always"
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, _handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {
            "type": "string",
            "description": "Canonical finite decimal value serialized as a string.",
        }

    @staticmethod
    def _validate(value: Any) -> Decimal:
        if isinstance(value, bool):
            raise PydanticCustomError(
                "economic_decimal_type",
                "bool is not a valid economic decimal value",
            )
        if isinstance(value, Decimal):
            candidate = value
        elif isinstance(value, str):
            try:
                candidate = Decimal(value)
            except InvalidOperation as exc:
                raise PydanticCustomError(
                    "economic_decimal_parse",
                    "could not parse {value!r} as a decimal",
                    {"value": value},
                ) from exc
        else:
            raise PydanticCustomError(
                "economic_decimal_type",
                "economic decimal fields accept only str or Decimal, got {type_name}",
                {"type_name": type(value).__name__},
            )
        if not candidate.is_finite():
            raise PydanticCustomError(
                "economic_decimal_finite",
                "economic decimal fields must be finite, got {value!r}",
                {"value": str(candidate)},
            )
        return candidate


EconomicDecimal = Annotated[Decimal, _EconomicDecimalAnnotation]


class _UtcNanosAnnotation:
    """Pydantic-aware bounded-int64 UTC nanosecond timestamp: int input only."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(cls._validate)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, _handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "integer", "minimum": 0, "maximum": _INT64_MAX}

    @staticmethod
    def _validate(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise PydanticCustomError(
                "utc_nanos_type",
                "UTC nanosecond timestamps accept only int, got {type_name}",
                {"type_name": type(value).__name__},
            )
        if value < 0 or value > _INT64_MAX:
            raise PydanticCustomError(
                "utc_nanos_range",
                "UTC nanosecond timestamps must be within [0, {max_value}], got {value}",
                {"max_value": _INT64_MAX, "value": value},
            )
        return value


UtcNanos = Annotated[int, _UtcNanosAnnotation]


class _SequenceNoAnnotation:
    """Bounded non-negative int64 stream-position identifier.

    Distinct from ``UtcNanos`` in intent (ordering position, not wall-clock
    time) even though the numeric bounds happen to coincide.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(cls._validate)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, _handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "integer", "minimum": 0, "maximum": _INT64_MAX}

    @staticmethod
    def _validate(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise PydanticCustomError(
                "sequence_no_type",
                "sequence numbers accept only int, got {type_name}",
                {"type_name": type(value).__name__},
            )
        if value < 0 or value > _INT64_MAX:
            raise PydanticCustomError(
                "sequence_no_range",
                "sequence numbers must be within [0, {max_value}], got {value}",
                {"max_value": _INT64_MAX, "value": value},
            )
        return value


SequenceNo = Annotated[int, _SequenceNoAnnotation]


class _PortableRelPathAnnotation:
    """A relative, forward-slash, traversal-free portable path.

    Rejects absolute POSIX paths, Windows drive-letter paths, backslashes,
    empty strings, and any ``.``/``..`` path segment -- so a validated path
    can always be safely joined under a known root directory without risk
    of escaping it.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(cls._validate)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, _handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {
            "type": "string",
            "minLength": 1,
            "description": "Relative, forward-slash, traversal-free portable path.",
        }

    @staticmethod
    def _validate(value: Any) -> str:
        if not isinstance(value, str):
            raise PydanticCustomError(
                "portable_rel_path_type",
                "path must be a string, got {type_name}",
                {"type_name": type(value).__name__},
            )
        if value == "":
            raise PydanticCustomError("portable_rel_path_empty", "path must not be empty")
        if "\\" in value:
            raise PydanticCustomError(
                "portable_rel_path_backslash",
                "path must use forward slashes only: {value!r}",
                {"value": value},
            )
        if value.startswith("/"):
            raise PydanticCustomError(
                "portable_rel_path_absolute",
                "path must not be absolute: {value!r}",
                {"value": value},
            )
        if _WINDOWS_DRIVE_RE.match(value):
            raise PydanticCustomError(
                "portable_rel_path_drive",
                "path must not contain a drive letter: {value!r}",
                {"value": value},
            )
        segments = value.split("/")
        if any(segment in ("", ".", "..") for segment in segments):
            raise PydanticCustomError(
                "portable_rel_path_segment",
                "path must not contain empty, '.' or '..' segments: {value!r}",
                {"value": value},
            )
        return value


PortableRelPath = Annotated[str, _PortableRelPathAnnotation]


class _Sha256HexAnnotation:
    """A lowercase, 64-character hexadecimal SHA-256 digest string."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(cls._validate)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, _handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "string", "pattern": "^[0-9a-f]{64}$"}

    @staticmethod
    def _validate(value: Any) -> str:
        if not isinstance(value, str) or not _SHA256_HEX_RE.match(value):
            raise PydanticCustomError(
                "sha256_hex_invalid",
                "must be a 64-character lowercase hex SHA-256 digest, got {value!r}",
                {"value": value},
            )
        return value


Sha256Hex = Annotated[str, _Sha256HexAnnotation]
