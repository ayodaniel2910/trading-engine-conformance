"""Input dataset identity: relative path, byte size and content hash."""

from __future__ import annotations

from pydantic import Field

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.types import PortableRelPath, Sha256Hex


class DatasetIdentity(StrictBaseModel):
    dataset_id: str = Field(min_length=1)
    relative_path: PortableRelPath
    byte_size: int = Field(ge=0)
    sha256: Sha256Hex
