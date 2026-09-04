"""Unit tests for the top-level RunArtifact envelope: binds all schema
objects and enforces monotonic ordering across every event stream."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.assumptions import ExecutionAssumptions
from trading_engine_conformance.schema.dataset import DatasetIdentity
from trading_engine_conformance.schema.enums import (
    AssetClass,
    HoldoutAccessState,
    LiquidityFlag,
    OrderSide,
)
from trading_engine_conformance.schema.envelope import RunArtifact
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.holdout import HoldoutState
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.ledger import (
    CashSnapshot,
    LedgerSnapshot,
    MarginSnapshot,
    PnLSnapshot,
    PositionSnapshot,
)
from trading_engine_conformance.schema.market_events import Trade
from trading_engine_conformance.schema.run import EnvironmentLock, RunHeader, SourceRevision


def _instrument() -> InstrumentIdentity:
    return InstrumentIdentity(
        venue="CME",
        symbol="GCZ26",
        asset_class=AssetClass.FUTURE,
        currency="USD",
        price_precision=1,
        size_precision=0,
        tick_size="0.1",
        tick_value="10.00",
        multiplier="100",
        expiry_ts=1_798_761_600_000_000_000,
        metadata_effective_ts=1_767_225_600_000_000_000,
        is_continuous=False,
    )


def _header() -> RunHeader:
    return RunHeader(
        run_id="run-0001",
        schema_version="1.0.0",
        created_ts=1,
        source_revision=SourceRevision(commit_hash="a" * 40, is_dirty=False, repository_url=None),
        environment_lock=EnvironmentLock(
            lock_hash="b" * 64,
            python_version="3.11.8",
            platform="win32",
            tool_versions={"tec": "0.1.0"},
        ),
        seed=1,
        tool_versions={"tec": "0.1.0"},
        holdout_state=HoldoutState(state=HoldoutAccessState.SEALED, sealed_ts=1, opened_ts=None),
    )


def _assumptions() -> ExecutionAssumptions:
    return ExecutionAssumptions(
        fee_model="fixed",
        fee_rate="1",
        spread_model="fixed",
        slippage_model="none",
        latency_ns=0,
        queue_model="fifo",
        partial_fill_policy="preserve-residual",
        margin_model="reg-t",
        session_policy="cme",
        settlement_policy="daily",
        roll_policy="manual",
    )


def _trade(sequence: int, ts: int) -> Trade:
    return Trade(
        instrument=_instrument(),
        exchange_ts=ts,
        receive_ts=ts,
        sequence=sequence,
        price="2000.0",
        size="1",
        aggressor_side=OrderSide.BUY,
    )


def _ledger_snapshot(sequence: int, ts: int) -> LedgerSnapshot:
    return LedgerSnapshot(
        cash=CashSnapshot(cash="10000.00", ts=ts, sequence=sequence),
        positions=[
            PositionSnapshot(
                instrument=_instrument(), quantity="0", average_price="0", ts=ts, sequence=sequence
            )
        ],
        margin=MarginSnapshot(
            used_margin="0", available_margin="10000.00", ts=ts, sequence=sequence
        ),
        pnl=PnLSnapshot(realized_pnl="0", unrealized_pnl="0", ts=ts, sequence=sequence),
        ts=ts,
        sequence=sequence,
    )


def _fill(sequence: int, ts: int) -> Fill:
    return Fill(
        fill_id=f"fill-{sequence}",
        order_id="ord-1",
        instrument=_instrument(),
        side=OrderSide.BUY,
        price="2000.0",
        quantity="1",
        fee="0",
        ts=ts,
        sequence=sequence,
        liquidity=LiquidityFlag.TAKER,
        slippage=None,
        queue_position=None,
        provenance="golden-oracle:test",
    )


def _dataset() -> DatasetIdentity:
    return DatasetIdentity(
        dataset_id="ds-1", relative_path="data/x.csv", byte_size=10, sha256="c" * 64
    )


class TestRunArtifact:
    def test_valid_minimal_artifact(self) -> None:
        artifact = RunArtifact(
            header=_header(),
            datasets=[_dataset()],
            instruments=[_instrument()],
            market_events=[_trade(0, 100), _trade(1, 200)],
            signals=[],
            order_intents=[],
            order_transitions=[],
            fills=[_fill(0, 100)],
            ledger_snapshots=[_ledger_snapshot(0, 100), _ledger_snapshot(1, 200)],
            execution_assumptions=_assumptions(),
        )
        assert artifact.header.execution_authorized is False

    def test_rejects_non_monotonic_market_event_sequence(self) -> None:
        with pytest.raises(ValidationError):
            RunArtifact(
                header=_header(),
                datasets=[],
                instruments=[_instrument()],
                market_events=[_trade(1, 200), _trade(0, 100)],
                signals=[],
                order_intents=[],
                order_transitions=[],
                fills=[],
                ledger_snapshots=[],
                execution_assumptions=_assumptions(),
            )

    def test_rejects_duplicate_fill_sequence(self) -> None:
        with pytest.raises(ValidationError):
            RunArtifact(
                header=_header(),
                datasets=[],
                instruments=[_instrument()],
                market_events=[],
                signals=[],
                order_intents=[],
                order_transitions=[],
                fills=[_fill(0, 100), _fill(0, 200)],
                ledger_snapshots=[],
                execution_assumptions=_assumptions(),
            )

    def test_rejects_non_monotonic_ledger_snapshot_timestamp(self) -> None:
        with pytest.raises(ValidationError):
            RunArtifact(
                header=_header(),
                datasets=[],
                instruments=[_instrument()],
                market_events=[],
                signals=[],
                order_intents=[],
                order_transitions=[],
                fills=[],
                ledger_snapshots=[_ledger_snapshot(0, 200), _ledger_snapshot(1, 100)],
                execution_assumptions=_assumptions(),
            )

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            RunArtifact(
                header=_header(),
                datasets=[],
                instruments=[],
                market_events=[],
                signals=[],
                order_intents=[],
                order_transitions=[],
                fills=[],
                ledger_snapshots=[],
                execution_assumptions=_assumptions(),
                bogus_field="nope",
            )
