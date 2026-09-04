"""Order intents and order-state transitions.

An ``OrderIntent`` always names an exact outright contract -- continuous
analytical references are rejected. The allowed state-machine transitions
in ``validate_transition`` are the single source of truth for "impossible
order transitions" used both here and by the golden oracle ledger.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.types import EconomicDecimal, SequenceNo, UtcNanos

_LIMIT_PRICE_TYPES = frozenset({OrderType.LIMIT, OrderType.STOP_LIMIT})
_STOP_PRICE_TYPES = frozenset({OrderType.STOP, OrderType.STOP_LIMIT})


class OrderIntent(StrictBaseModel):
    order_id: str = Field(min_length=1)
    instrument: InstrumentIdentity
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce
    quantity: EconomicDecimal
    limit_price: EconomicDecimal | None = None
    stop_price: EconomicDecimal | None = None
    expiry_ts: UtcNanos | None = None
    created_ts: UtcNanos
    sequence: SequenceNo
    linked_order_id: str | None = None
    oco_group_id: str | None = None

    @model_validator(mode="after")
    def _check_quantity(self) -> OrderIntent:
        if self.quantity <= 0:
            raise ValueError("quantity must be strictly positive")
        return self

    @model_validator(mode="after")
    def _check_price_presence_matches_order_type(self) -> OrderIntent:
        needs_limit = self.order_type in _LIMIT_PRICE_TYPES
        has_limit = self.limit_price is not None
        if needs_limit != has_limit:
            raise ValueError(
                f"{self.order_type} requires limit_price to be present iff order type needs it"
            )
        needs_stop = self.order_type in _STOP_PRICE_TYPES
        has_stop = self.stop_price is not None
        if needs_stop != has_stop:
            raise ValueError(
                f"{self.order_type} requires stop_price to be present iff order type needs it"
            )
        return self

    @model_validator(mode="after")
    def _check_expiry_presence_matches_tif(self) -> OrderIntent:
        needs_expiry = self.time_in_force == TimeInForce.GTD
        has_expiry = self.expiry_ts is not None
        if needs_expiry != has_expiry:
            raise ValueError("expiry_ts must be present iff time_in_force is GTD")
        return self

    @model_validator(mode="after")
    def _check_exact_outright_contract(self) -> OrderIntent:
        if self.instrument.is_continuous:
            raise ValueError(
                "order intents must reference an exact outright contract, "
                "not a continuous analytical reference"
            )
        return self


class OrderStateTransition(StrictBaseModel):
    order_id: str = Field(min_length=1)
    from_status: OrderStatus | None
    to_status: OrderStatus
    ts: UtcNanos
    sequence: SequenceNo
    reason: str | None = None


class OrderTransitionError(ValueError):
    """Raised when an order-state transition is not causally possible."""


_TERMINAL_STATUSES = frozenset(
    {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED}
)

_ALLOWED_TRANSITIONS: dict[OrderStatus | None, frozenset[OrderStatus]] = {
    None: frozenset({OrderStatus.NEW}),
    OrderStatus.NEW: frozenset({OrderStatus.ACCEPTED, OrderStatus.REJECTED, OrderStatus.CANCELED}),
    OrderStatus.ACCEPTED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
        }
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


def validate_transition(from_status: OrderStatus | None, to_status: OrderStatus) -> None:
    """Raise ``OrderTransitionError`` unless ``from_status -> to_status`` is
    a causally possible order-lifecycle transition."""
    allowed = _ALLOWED_TRANSITIONS.get(from_status, frozenset())
    if to_status not in allowed:
        raise OrderTransitionError(f"impossible order transition: {from_status} -> {to_status}")
