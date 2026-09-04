"""Unit tests for OrderIntent, OrderStateTransition, and the order
lifecycle state machine (impossible transitions rejected)."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.enums import (
    AssetClass,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.orders import (
    OrderIntent,
    OrderStateTransition,
    OrderTransitionError,
    validate_transition,
)


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


def _order(**overrides: object) -> OrderIntent:
    fields: dict[str, object] = {
        "order_id": "ord-1",
        "instrument": _instrument(),
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
        "quantity": "1",
        "limit_price": None,
        "stop_price": None,
        "expiry_ts": None,
        "created_ts": 1_767_225_600_000_000_000,
        "sequence": 0,
        "linked_order_id": None,
        "oco_group_id": None,
    }
    fields.update(overrides)
    return OrderIntent(**fields)  # type: ignore[arg-type]


class TestOrderIntent:
    def test_market_order_valid(self) -> None:
        order = _order()
        assert order.order_type == OrderType.MARKET

    def test_limit_requires_limit_price(self) -> None:
        with pytest.raises(ValidationError):
            _order(order_type=OrderType.LIMIT, limit_price=None)

    def test_limit_rejects_stop_price(self) -> None:
        with pytest.raises(ValidationError):
            _order(order_type=OrderType.LIMIT, limit_price="10", stop_price="9")

    def test_limit_valid(self) -> None:
        order = _order(order_type=OrderType.LIMIT, limit_price="10")
        assert order.limit_price == 10

    def test_stop_requires_stop_price(self) -> None:
        with pytest.raises(ValidationError):
            _order(order_type=OrderType.STOP, stop_price=None)

    def test_stop_limit_requires_both_prices(self) -> None:
        with pytest.raises(ValidationError):
            _order(order_type=OrderType.STOP_LIMIT, limit_price="10", stop_price=None)

    def test_stop_limit_valid(self) -> None:
        order = _order(order_type=OrderType.STOP_LIMIT, limit_price="10", stop_price="9.5")
        assert order.stop_price is not None

    def test_market_rejects_limit_price(self) -> None:
        with pytest.raises(ValidationError):
            _order(order_type=OrderType.MARKET, limit_price="10")

    def test_gtd_requires_expiry(self) -> None:
        with pytest.raises(ValidationError):
            _order(time_in_force=TimeInForce.GTD, expiry_ts=None)

    def test_non_gtd_rejects_expiry(self) -> None:
        with pytest.raises(ValidationError):
            _order(time_in_force=TimeInForce.DAY, expiry_ts=1_767_225_600_000_000_500)

    def test_gtd_valid(self) -> None:
        order = _order(time_in_force=TimeInForce.GTD, expiry_ts=1_767_225_600_000_000_500)
        assert order.expiry_ts is not None

    def test_rejects_non_positive_quantity(self) -> None:
        with pytest.raises(ValidationError):
            _order(quantity="0")

    def test_rejects_continuous_instrument(self) -> None:
        continuous = _instrument(is_continuous=True, symbol="GC=CONTINUOUS", expiry_ts=None)
        with pytest.raises(ValidationError):
            _order(instrument=continuous)


class TestOrderStateTransition:
    def test_initial_transition_from_none(self) -> None:
        transition = OrderStateTransition(
            order_id="ord-1",
            from_status=None,
            to_status=OrderStatus.NEW,
            ts=1_767_225_600_000_000_000,
            sequence=0,
            reason=None,
        )
        assert transition.from_status is None

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            OrderStateTransition(
                order_id="ord-1",
                from_status=None,
                to_status=OrderStatus.NEW,
                ts=0,
                sequence=0,
                reason=None,
                bogus="nope",
            )


class TestValidateTransition:
    def test_new_to_accepted_allowed(self) -> None:
        validate_transition(OrderStatus.NEW, OrderStatus.ACCEPTED)  # no raise

    def test_none_to_new_allowed(self) -> None:
        validate_transition(None, OrderStatus.NEW)  # no raise

    def test_accepted_to_partially_filled_allowed(self) -> None:
        validate_transition(OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED)

    def test_partially_filled_to_filled_allowed(self) -> None:
        validate_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)

    def test_filled_to_anything_rejected(self) -> None:
        with pytest.raises(OrderTransitionError):
            validate_transition(OrderStatus.FILLED, OrderStatus.CANCELED)

    def test_canceled_to_anything_rejected(self) -> None:
        with pytest.raises(OrderTransitionError):
            validate_transition(OrderStatus.CANCELED, OrderStatus.NEW)

    def test_none_to_filled_rejected(self) -> None:
        with pytest.raises(OrderTransitionError):
            validate_transition(None, OrderStatus.FILLED)

    def test_new_to_new_rejected(self) -> None:
        with pytest.raises(OrderTransitionError):
            validate_transition(OrderStatus.NEW, OrderStatus.NEW)

    def test_rejected_is_terminal(self) -> None:
        with pytest.raises(OrderTransitionError):
            validate_transition(OrderStatus.REJECTED, OrderStatus.NEW)

    def test_expired_is_terminal(self) -> None:
        with pytest.raises(OrderTransitionError):
            validate_transition(OrderStatus.EXPIRED, OrderStatus.NEW)
