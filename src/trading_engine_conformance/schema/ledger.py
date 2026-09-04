"""Cash, position, margin and PnL ledger snapshots.

Every fill in the golden oracle (and any conforming engine adapter) must
produce an updated ``LedgerSnapshot`` -- this module only defines the shape;
causal update rules live in ``trading_engine_conformance.golden``.
"""

from __future__ import annotations

from pydantic import model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.types import EconomicDecimal, SequenceNo, UtcNanos


class CashSnapshot(StrictBaseModel):
    cash: EconomicDecimal
    ts: UtcNanos
    sequence: SequenceNo


class PositionSnapshot(StrictBaseModel):
    instrument: InstrumentIdentity
    quantity: EconomicDecimal
    average_price: EconomicDecimal
    ts: UtcNanos
    sequence: SequenceNo

    @model_validator(mode="after")
    def _check_exact_outright_contract(self) -> PositionSnapshot:
        if self.instrument.is_continuous:
            raise ValueError(
                "position snapshots must reference an exact outright contract, "
                "not a continuous analytical reference"
            )
        return self

    @model_validator(mode="after")
    def _check_average_price_bounds(self) -> PositionSnapshot:
        if self.average_price < 0:
            raise ValueError("average_price must not be negative")
        return self


class MarginSnapshot(StrictBaseModel):
    used_margin: EconomicDecimal
    available_margin: EconomicDecimal
    ts: UtcNanos
    sequence: SequenceNo

    @model_validator(mode="after")
    def _check_non_negative_margins(self) -> MarginSnapshot:
        if self.used_margin < 0:
            raise ValueError("used_margin must not be negative")
        if self.available_margin < 0:
            raise ValueError("available_margin must not be negative")
        return self


class PnLSnapshot(StrictBaseModel):
    realized_pnl: EconomicDecimal
    unrealized_pnl: EconomicDecimal
    ts: UtcNanos
    sequence: SequenceNo


class LedgerSnapshot(StrictBaseModel):
    cash: CashSnapshot
    positions: list[PositionSnapshot]
    margin: MarginSnapshot
    pnl: PnLSnapshot
    ts: UtcNanos
    sequence: SequenceNo
