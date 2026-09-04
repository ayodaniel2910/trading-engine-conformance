"""Fill: an execution against an order, with fee/slippage/liquidity/queue
provenance. Always references an exact outright contract."""

from __future__ import annotations

from pydantic import Field, model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.enums import LiquidityFlag, OrderSide
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.types import EconomicDecimal, SequenceNo, UtcNanos


class Fill(StrictBaseModel):
    fill_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    instrument: InstrumentIdentity
    side: OrderSide
    price: EconomicDecimal
    quantity: EconomicDecimal
    fee: EconomicDecimal
    ts: UtcNanos
    sequence: SequenceNo
    liquidity: LiquidityFlag
    slippage: EconomicDecimal | None = None
    queue_position: int | None = Field(default=None, ge=0)
    provenance: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_economic_bounds(self) -> Fill:
        if self.price <= 0:
            raise ValueError("fill price must be strictly positive")
        if self.quantity <= 0:
            raise ValueError("fill quantity must be strictly positive")
        if self.fee < 0:
            raise ValueError("fee must not be negative")
        return self

    @model_validator(mode="after")
    def _check_exact_outright_contract(self) -> Fill:
        if self.instrument.is_continuous:
            raise ValueError(
                "fills must reference an exact outright contract, "
                "not a continuous analytical reference"
            )
        return self
