"""Shared strict base model for the neutral schema.

Every schema model forbids unknown fields (fail closed on unrecognized
data) and is frozen/immutable after construction, so a validated artifact
can never be mutated in place after the fact -- only replaced by a new,
independently validated artifact.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    """Base model: forbid unknown fields, frozen instances, strict validation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )
