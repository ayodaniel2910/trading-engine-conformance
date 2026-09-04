"""Explicit execution assumptions.

Every cost/behavior policy that could silently change a comparison's
outcome must be named explicitly. There are no defaults: an artifact that
omits one of these fields, or names an empty policy, fails validation
rather than falling back to an implicit assumption.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.types import EconomicDecimal, UtcNanos


class ExecutionAssumptions(StrictBaseModel):
    fee_model: str = Field(min_length=1)
    fee_rate: EconomicDecimal
    spread_model: str = Field(min_length=1)
    slippage_model: str = Field(min_length=1)
    latency_ns: UtcNanos
    queue_model: str = Field(min_length=1)
    partial_fill_policy: str = Field(min_length=1)
    margin_model: str = Field(min_length=1)
    session_policy: str = Field(min_length=1)
    settlement_policy: str = Field(min_length=1)
    roll_policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_non_negative_fee_rate(self) -> ExecutionAssumptions:
        if self.fee_rate < 0:
            raise ValueError("fee_rate must not be negative")
        return self
