"""Signal: an observation with an earliest order-eligibility timestamp.

A signal is an analytical fact, not an executable record, so its instrument
may be a continuous analytical reference. Any order intent derived from a
signal must still name an exact outright contract (see ``orders.py``).
"""

from __future__ import annotations

from pydantic import Field, model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.enums import OrderSide
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.types import SequenceNo, UtcNanos


class Signal(StrictBaseModel):
    signal_id: str = Field(min_length=1)
    instrument: InstrumentIdentity
    observed_ts: UtcNanos
    eligible_ts: UtcNanos
    direction: OrderSide
    sequence: SequenceNo

    @model_validator(mode="after")
    def _check_eligible_not_before_observed(self) -> Signal:
        if self.eligible_ts < self.observed_ts:
            raise ValueError("eligible_ts must not be earlier than observed_ts")
        return self
