"""Exact instrument identity.

Executable records (order intents, fills) must reference an exact outright
contract (``is_continuous=False``). Continuous symbols may only appear as
``is_continuous=True`` analytical references and are rejected by executable
record validators elsewhere in the schema.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.enums import AssetClass
from trading_engine_conformance.schema.types import EconomicDecimal, UtcNanos

_EXPIRING_ASSET_CLASSES = frozenset({AssetClass.FUTURE, AssetClass.OPTION})


class InstrumentIdentity(StrictBaseModel):
    venue: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    asset_class: AssetClass
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    price_precision: int = Field(ge=0)
    size_precision: int = Field(ge=0)
    tick_size: EconomicDecimal
    tick_value: EconomicDecimal
    multiplier: EconomicDecimal
    expiry_ts: UtcNanos | None = None
    metadata_effective_ts: UtcNanos
    is_continuous: bool = False

    @model_validator(mode="after")
    def _check_economic_bounds(self) -> InstrumentIdentity:
        if self.tick_size <= 0:
            raise ValueError("tick_size must be strictly positive")
        if self.tick_value < 0:
            raise ValueError("tick_value must not be negative")
        if self.multiplier <= 0:
            raise ValueError("multiplier must be strictly positive")
        return self

    @model_validator(mode="after")
    def _check_expiry_required_for_exact_expiring_contracts(self) -> InstrumentIdentity:
        if (
            not self.is_continuous
            and self.asset_class in _EXPIRING_ASSET_CLASSES
            and self.expiry_ts is None
        ):
            raise ValueError(
                "exact outright contracts in an expiring asset class must declare expiry_ts"
            )
        return self
