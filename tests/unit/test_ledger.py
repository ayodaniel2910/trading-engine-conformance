"""Unit tests for cash/position/margin/PnL ledger snapshot models."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.enums import AssetClass
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.ledger import (
    CashSnapshot,
    LedgerSnapshot,
    MarginSnapshot,
    PnLSnapshot,
    PositionSnapshot,
)


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


class TestCashSnapshot:
    def test_valid(self) -> None:
        snap = CashSnapshot(cash="10000.00", ts=1, sequence=0)
        assert snap.cash == 10000

    def test_negative_cash_allowed_for_margin_debit(self) -> None:
        snap = CashSnapshot(cash="-500.00", ts=1, sequence=0)
        assert snap.cash < 0


class TestPositionSnapshot:
    def test_valid_long(self) -> None:
        pos = PositionSnapshot(
            instrument=_instrument(), quantity="2", average_price="2000.0", ts=1, sequence=0
        )
        assert pos.quantity == 2

    def test_valid_short(self) -> None:
        pos = PositionSnapshot(
            instrument=_instrument(), quantity="-2", average_price="2000.0", ts=1, sequence=0
        )
        assert pos.quantity == -2

    def test_flat_position_requires_zero_average_price(self) -> None:
        pos = PositionSnapshot(
            instrument=_instrument(), quantity="0", average_price="0", ts=1, sequence=0
        )
        assert pos.average_price == 0

    def test_rejects_continuous_instrument(self) -> None:
        continuous = _instrument().model_copy(
            update={"is_continuous": True, "symbol": "GC=CONTINUOUS", "expiry_ts": None}
        )
        with pytest.raises(ValidationError):
            PositionSnapshot(
                instrument=continuous, quantity="1", average_price="2000.0", ts=1, sequence=0
            )


class TestMarginSnapshot:
    def test_valid(self) -> None:
        margin = MarginSnapshot(used_margin="100.00", available_margin="900.00", ts=1, sequence=0)
        assert margin.used_margin == 100

    def test_rejects_negative_used_margin(self) -> None:
        with pytest.raises(ValidationError):
            MarginSnapshot(used_margin="-1", available_margin="900.00", ts=1, sequence=0)


class TestPnLSnapshot:
    def test_valid(self) -> None:
        pnl = PnLSnapshot(realized_pnl="10.00", unrealized_pnl="-5.00", ts=1, sequence=0)
        assert pnl.realized_pnl == 10


class TestLedgerSnapshot:
    def test_valid(self) -> None:
        snapshot = LedgerSnapshot(
            cash=CashSnapshot(cash="10000.00", ts=1, sequence=0),
            positions=[
                PositionSnapshot(
                    instrument=_instrument(),
                    quantity="1",
                    average_price="2000.0",
                    ts=1,
                    sequence=0,
                )
            ],
            margin=MarginSnapshot(
                used_margin="100.00", available_margin="900.00", ts=1, sequence=0
            ),
            pnl=PnLSnapshot(realized_pnl="0", unrealized_pnl="0", ts=1, sequence=0),
            ts=1,
            sequence=0,
        )
        assert len(snapshot.positions) == 1

    def test_empty_positions_allowed(self) -> None:
        snapshot = LedgerSnapshot(
            cash=CashSnapshot(cash="10000.00", ts=1, sequence=0),
            positions=[],
            margin=MarginSnapshot(used_margin="0", available_margin="10000.00", ts=1, sequence=0),
            pnl=PnLSnapshot(realized_pnl="0", unrealized_pnl="0", ts=1, sequence=0),
            ts=1,
            sequence=0,
        )
        assert snapshot.positions == []
