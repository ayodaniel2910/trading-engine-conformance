"""The top-level, immutable run artifact envelope.

Binds the run header, input datasets, instruments, and every event stream
(market events, signals, order intents/transitions, fills, ledger
snapshots) together with the run's execution assumptions. Each event
stream's sequence/timestamp ordering is validated independently using
``trading_engine_conformance.ordering``.
"""

from __future__ import annotations

from pydantic import model_validator

from trading_engine_conformance.ordering import SequenceError, assert_monotonic
from trading_engine_conformance.schema.assumptions import ExecutionAssumptions
from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.dataset import DatasetIdentity
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.ledger import LedgerSnapshot
from trading_engine_conformance.schema.market_events import MarketEvent
from trading_engine_conformance.schema.orders import OrderIntent, OrderStateTransition
from trading_engine_conformance.schema.run import RunHeader
from trading_engine_conformance.schema.signals import Signal


class RunArtifact(StrictBaseModel):
    header: RunHeader
    datasets: list[DatasetIdentity]
    instruments: list[InstrumentIdentity]
    market_events: list[MarketEvent]
    signals: list[Signal]
    order_intents: list[OrderIntent]
    order_transitions: list[OrderStateTransition]
    fills: list[Fill]
    ledger_snapshots: list[LedgerSnapshot]
    execution_assumptions: ExecutionAssumptions

    @model_validator(mode="after")
    def _check_stream_ordering(self) -> RunArtifact:
        try:
            assert_monotonic(self.market_events, ts_attr="exchange_ts")
            assert_monotonic(self.signals, ts_attr="observed_ts")
            assert_monotonic(self.order_intents, ts_attr="created_ts")
            assert_monotonic(self.order_transitions, ts_attr="ts")
            assert_monotonic(self.fills, ts_attr="ts")
            assert_monotonic(self.ledger_snapshots, ts_attr="ts")
        except SequenceError as exc:
            raise ValueError(str(exc)) from exc
        return self
