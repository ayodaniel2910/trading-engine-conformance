"""Unit tests for InstrumentIdentity: exact outright contracts vs.
continuous analytical references."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.enums import AssetClass
from trading_engine_conformance.schema.instrument import InstrumentIdentity


def _make(**overrides: object) -> InstrumentIdentity:
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


class TestInstrumentIdentity:
    def test_valid_outright_future(self) -> None:
        instrument = _make()
        assert instrument.symbol == "GCZ26"
        assert instrument.tick_size == Decimal("0.1")

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            _make(extra_field="nope")

    def test_rejects_non_positive_tick_size(self) -> None:
        with pytest.raises(ValidationError):
            _make(tick_size="0")

    def test_rejects_negative_tick_value(self) -> None:
        with pytest.raises(ValidationError):
            _make(tick_value="-1")

    def test_rejects_non_positive_multiplier(self) -> None:
        with pytest.raises(ValidationError):
            _make(multiplier="0")

    def test_rejects_lowercase_currency(self) -> None:
        with pytest.raises(ValidationError):
            _make(currency="usd")

    def test_rejects_wrong_length_currency(self) -> None:
        with pytest.raises(ValidationError):
            _make(currency="US")

    def test_rejects_empty_symbol(self) -> None:
        with pytest.raises(ValidationError):
            _make(symbol="")

    def test_continuous_reference_allows_null_expiry(self) -> None:
        instrument = _make(symbol="GC=CONTINUOUS", is_continuous=True, expiry_ts=None)
        assert instrument.is_continuous is True
        assert instrument.expiry_ts is None

    def test_outright_requires_expiry_for_expiring_asset_classes(self) -> None:
        with pytest.raises(ValidationError):
            _make(is_continuous=False, expiry_ts=None)

    def test_non_expiring_asset_class_allows_null_expiry(self) -> None:
        instrument = _make(
            symbol="EURUSD",
            asset_class=AssetClass.FOREX,
            expiry_ts=None,
            is_continuous=False,
        )
        assert instrument.expiry_ts is None
