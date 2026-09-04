"""Mandatory explicit economics and execution profile."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.types import EconomicDecimal


class NautilusResearchProfile(StrictBaseModel):
    """All fields are required; there are intentionally no model defaults."""

    nautilus_asset_class: Literal[
        "FX", "EQUITY", "COMMODITY", "DEBT", "INDEX", "CRYPTOCURRENCY", "ALTERNATIVE"
    ]
    underlying: str = Field(min_length=1)
    lot_size: EconomicDecimal
    maker_fee_rate: EconomicDecimal
    taker_fee_rate: EconomicDecimal
    initial_margin_rate: EconomicDecimal
    maintenance_margin_rate: EconomicDecimal
    latency_ns: int = Field(ge=0)
    fill_model: Literal["L1_FINITE_TRADE", "L3_MBO_FINITE"]
    queue_model: Literal["NO_QUEUE_L1_DIAGNOSTIC", "FIFO_L3"]
    liquidity_consumption: Literal["FINITE_EVENT_SIZE"]
    limit_fill_probability: EconomicDecimal
    slippage_probability: EconomicDecimal
    trade_execution: bool
    reject_stop_orders: bool
    session_timezone: str = Field(min_length=1)
    settlement_price: EconomicDecimal
    random_seed: int = Field(ge=0)

    @model_validator(mode="after")
    def _positive_economics(self) -> NautilusResearchProfile:
        positive = {
            "lot_size": self.lot_size,
            "maker_fee_rate": self.maker_fee_rate,
            "taker_fee_rate": self.taker_fee_rate,
            "initial_margin_rate": self.initial_margin_rate,
            "maintenance_margin_rate": self.maintenance_margin_rate,
            "settlement_price": self.settlement_price,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be strictly positive; zero/default is forbidden")
        for name, value in {
            "limit_fill_probability": self.limit_fill_probability,
            "slippage_probability": self.slippage_probability,
        }.items():
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be within [0, 1]")
        if self.fill_model == "L3_MBO_FINITE" and self.queue_model != "FIFO_L3":
            raise ValueError("L3 MBO requires the explicit FIFO_L3 queue model")
        if self.fill_model == "L1_FINITE_TRADE" and self.queue_model != "NO_QUEUE_L1_DIAGNOSTIC":
            raise ValueError("L1 diagnostic runs require NO_QUEUE_L1_DIAGNOSTIC")
        return self
