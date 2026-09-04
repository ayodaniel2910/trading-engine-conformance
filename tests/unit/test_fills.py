"""Unit tests for Fill: fee/slippage/liquidity/queue provenance and exact
outright contract requirement."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.enums import AssetClass, LiquidityFlag, OrderSide
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.instrument import InstrumentIdentity


def _instrument(**overrides: object) -> InstrumentIdentity:
    fields: dict[str, object] = {
        "venue": "CME",
        "symbol": "GCZ26",
        "asset_class": AssetClass.FUTURE,
        "currency": "USD",
        "price_precision": 1,
        "size_precision": 0,
        "tick_size": "0.1",
        "tick_value": "10.00",
        "multiplier": "100",
        "expiry_ts": 1_798_761_600_000_000_000,
        "metadata_effective_ts": 1_767_225_600_000_000_000,
        "is_continuous": False,
    }
    fields.update(overrides)
    return InstrumentIdentity(**fields)  # type: ignore[arg-type]


def _fill(**overrides: object) -> Fill:
    fields: dict[str, object] = {
        "fill_id": "fill-1",
        "order_id": "ord-1",
        "instrument": _instrument(),
        "side": OrderSide.BUY,
        "price": "2000.5",
        "quantity": "1",
        "fee": "0.5",
        "ts": 1_767_225_600_000_000_000,
        "sequence": 0,
        "liquidity": LiquidityFlag.TAKER,
        "slippage": "0.1",
        "queue_position": None,
        "provenance": "golden-oracle:market-order",
    }
    fields.update(overrides)
    return Fill(**fields)  # type: ignore[arg-type]


class TestFill:
    def test_valid(self) -> None:
        fill = _fill()
        assert fill.provenance.startswith("golden-oracle")

    def test_rejects_non_positive_price(self) -> None:
        with pytest.raises(ValidationError):
            _fill(price="0")

    def test_rejects_non_positive_quantity(self) -> None:
        with pytest.raises(ValidationError):
            _fill(quantity="0")

    def test_rejects_negative_fee(self) -> None:
        with pytest.raises(ValidationError):
            _fill(fee="-0.01")

    def test_zero_fee_allowed(self) -> None:
        fill = _fill(fee="0")
        assert fill.fee == 0

    def test_rejects_empty_provenance(self) -> None:
        with pytest.raises(ValidationError):
            _fill(provenance="")

    def test_rejects_continuous_instrument(self) -> None:
        continuous = _instrument(is_continuous=True, symbol="GC=CONTINUOUS", expiry_ts=None)
        with pytest.raises(ValidationError):
            _fill(instrument=continuous)

    def test_queue_position_optional(self) -> None:
        fill = _fill(queue_position=3)
        assert fill.queue_position == 3

    def test_rejects_negative_queue_position(self) -> None:
        with pytest.raises(ValidationError):
            _fill(queue_position=-1)
