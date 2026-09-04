"""Unit tests for Signal: earliest eligibility timestamp causality."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.enums import AssetClass, OrderSide
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.signals import Signal


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


def _make(**overrides: object) -> Signal:
    fields: dict[str, object] = {
        "signal_id": "sig-1",
        "instrument": _instrument(),
        "observed_ts": 1_767_225_600_000_000_000,
        "eligible_ts": 1_767_225_600_000_000_500,
        "direction": OrderSide.BUY,
        "sequence": 0,
    }
    fields.update(overrides)
    return Signal(**fields)  # type: ignore[arg-type]


class TestSignal:
    def test_valid(self) -> None:
        signal = _make()
        assert signal.eligible_ts > signal.observed_ts

    def test_eligible_may_equal_observed(self) -> None:
        signal = _make(eligible_ts=1_767_225_600_000_000_000)
        assert signal.eligible_ts == signal.observed_ts

    def test_rejects_eligible_before_observed(self) -> None:
        with pytest.raises(ValidationError):
            _make(observed_ts=200, eligible_ts=100)

    def test_rejects_empty_signal_id(self) -> None:
        with pytest.raises(ValidationError):
            _make(signal_id="")

    def test_allows_continuous_instrument_as_analytical_reference(self) -> None:
        continuous = _instrument().model_copy(
            update={"is_continuous": True, "symbol": "GC=CONTINUOUS", "expiry_ts": None}
        )
        signal = _make(instrument=continuous)
        assert signal.instrument.is_continuous is True
