"""Exact Decimal/string translators for NautilusTrader v1.231.0.

Nautilus imports stay inside functions so this optional adapter never becomes
a core dependency. Unsupported object/event types always raise explicitly.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from trading_engine_conformance.adapters.nautilus.errors import (
    NautilusEnvironmentError,
    NautilusSemanticError,
)
from trading_engine_conformance.adapters.nautilus.profile import NautilusResearchProfile
from trading_engine_conformance.schema.enums import (
    AssetClass,
    LiquidityFlag,
    OrderSide,
    OrderType,
    TimeInForce,
)
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.ledger import (
    CashSnapshot,
    LedgerSnapshot,
    MarginSnapshot,
    PnLSnapshot,
    PositionSnapshot,
)
from trading_engine_conformance.schema.market_events import BookDelta, BookDeltaAction, Quote, Trade
from trading_engine_conformance.schema.orders import OrderIntent


def _module(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise NautilusEnvironmentError(
            "NautilusTrader v1.231.0 is required for this translator operation"
        ) from exc


def decimal_to_fixed(value: Decimal, precision: int, *, field: str) -> str:
    quantum = Decimal(1).scaleb(-precision)
    if value != value.quantize(quantum):
        raise NautilusSemanticError(
            f"{field}={value} exceeds declared precision {precision}; rounding is forbidden"
        )
    return format(value, f".{precision}f")


def _enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    if not isinstance(name, str):
        raise NautilusSemanticError(f"Nautilus enum value has no stable name: {value!r}")
    return name


def validate_instrument_profile(
    instrument: InstrumentIdentity, profile: NautilusResearchProfile
) -> None:
    if instrument.is_continuous:
        raise NautilusSemanticError("continuous instruments are analytical only and unsupported")
    if instrument.asset_class != AssetClass.FUTURE:
        raise NautilusSemanticError("the pinned pilot supports exact futures contracts only")
    if instrument.expiry_ts is None:
        raise NautilusSemanticError("exact futures metadata requires expiry_ts")
    expected_tick_value = instrument.tick_size * instrument.multiplier
    if instrument.tick_value != expected_tick_value:
        raise NautilusSemanticError(
            "tick_value metadata is inconsistent with tick_size * multiplier: "
            f"{instrument.tick_value} != {expected_tick_value}"
        )
    decimal_to_fixed(instrument.tick_size, instrument.price_precision, field="tick_size")
    decimal_to_fixed(profile.lot_size, instrument.size_precision, field="lot_size")


def _instrument_id(instrument: InstrumentIdentity) -> Any:
    identifiers = _module("nautilus_trader.model.identifiers")
    return identifiers.InstrumentId(
        identifiers.Symbol(instrument.symbol), identifiers.Venue(instrument.venue)
    )


def to_nautilus_instrument(instrument: InstrumentIdentity, profile: NautilusResearchProfile) -> Any:
    validate_instrument_profile(instrument, profile)
    enums = _module("nautilus_trader.model.enums")
    instruments = _module("nautilus_trader.model.instruments")
    objects = _module("nautilus_trader.model.objects")
    identifiers = _module("nautilus_trader.model.identifiers")
    if instrument.expiry_ts is None:
        raise NautilusSemanticError("exact futures metadata requires expiry_ts")
    return instruments.FuturesContract(
        instrument_id=_instrument_id(instrument),
        raw_symbol=identifiers.Symbol(instrument.symbol),
        asset_class=getattr(enums.AssetClass, profile.nautilus_asset_class),
        currency=objects.Currency.from_str(instrument.currency),
        price_precision=instrument.price_precision,
        price_increment=objects.Price.from_str(
            decimal_to_fixed(instrument.tick_size, instrument.price_precision, field="tick_size")
        ),
        multiplier=objects.Quantity.from_str(str(instrument.multiplier)),
        lot_size=objects.Quantity.from_str(
            decimal_to_fixed(profile.lot_size, instrument.size_precision, field="lot_size")
        ),
        underlying=profile.underlying,
        activation_ns=instrument.metadata_effective_ts,
        expiration_ns=instrument.expiry_ts,
        ts_event=instrument.metadata_effective_ts,
        ts_init=instrument.metadata_effective_ts,
        margin_init=profile.initial_margin_rate,
        margin_maint=profile.maintenance_margin_rate,
        maker_fee=profile.maker_fee_rate,
        taker_fee=profile.taker_fee_rate,
        info={
            "neutral_tick_value": str(instrument.tick_value),
            "session_timezone": profile.session_timezone,
            "settlement_price": str(profile.settlement_price),
            "latency_ns": profile.latency_ns,
            "fill_model": profile.fill_model,
            "queue_model": profile.queue_model,
            "liquidity_consumption": profile.liquidity_consumption,
            "limit_fill_probability": str(profile.limit_fill_probability),
            "slippage_probability": str(profile.slippage_probability),
            "trade_execution": profile.trade_execution,
            "reject_stop_orders": profile.reject_stop_orders,
        },
    )


def from_nautilus_instrument(value: Any) -> InstrumentIdentity:
    if type(value).__name__ != "FuturesContract":
        raise NautilusSemanticError(f"unsupported Nautilus instrument type: {type(value).__name__}")
    info = value.info or {}
    required = {"neutral_tick_value", "session_timezone", "settlement_price"}
    missing = sorted(required - set(info))
    if missing:
        raise NautilusSemanticError(f"missing adapter instrument metadata: {missing}")
    return InstrumentIdentity(
        venue=str(value.id.venue),
        symbol=str(value.raw_symbol),
        asset_class=AssetClass.FUTURE,
        currency=str(value.quote_currency),
        price_precision=value.price_precision,
        size_precision=value.size_precision,
        tick_size=Decimal(str(value.price_increment)),
        tick_value=Decimal(str(info["neutral_tick_value"])),
        multiplier=Decimal(str(value.multiplier)),
        expiry_ts=value.expiration_ns,
        metadata_effective_ts=value.activation_ns,
        is_continuous=False,
    )


def to_nautilus_trade(value: Trade) -> Any:
    data = _module("nautilus_trader.model.data")
    enums = _module("nautilus_trader.model.enums")
    identifiers = _module("nautilus_trader.model.identifiers")
    objects = _module("nautilus_trader.model.objects")
    side = {
        OrderSide.BUY: enums.AggressorSide.BUYER,
        OrderSide.SELL: enums.AggressorSide.SELLER,
        None: enums.AggressorSide.NO_AGGRESSOR,
    }[value.aggressor_side]
    return data.TradeTick(
        instrument_id=_instrument_id(value.instrument),
        price=objects.Price.from_str(
            decimal_to_fixed(value.price, value.instrument.price_precision, field="trade.price")
        ),
        size=objects.Quantity.from_str(
            decimal_to_fixed(value.size, value.instrument.size_precision, field="trade.size")
        ),
        aggressor_side=side,
        trade_id=identifiers.TradeId(str(value.sequence)),
        ts_event=value.exchange_ts,
        ts_init=value.receive_ts,
    )


def from_nautilus_trade(value: Any, instrument: InstrumentIdentity) -> Trade:
    if type(value).__name__ != "TradeTick":
        raise NautilusSemanticError(f"unsupported Nautilus event type: {type(value).__name__}")
    side_name = _enum_name(value.aggressor_side)
    side = {"BUYER": OrderSide.BUY, "SELLER": OrderSide.SELL}.get(side_name)
    try:
        sequence = int(str(value.trade_id))
    except ValueError as exc:
        raise NautilusSemanticError("trade_id does not contain the preserved sequence") from exc
    return Trade(
        instrument=instrument,
        exchange_ts=value.ts_event,
        receive_ts=value.ts_init,
        sequence=sequence,
        price=Decimal(str(value.price)),
        size=Decimal(str(value.size)),
        aggressor_side=side,
    )


def to_nautilus_quote(value: Quote) -> Any:
    if (
        value.bid_price is None
        or value.bid_size is None
        or value.ask_price is None
        or value.ask_size is None
    ):
        raise NautilusSemanticError("one-sided quotes are unsupported by Nautilus QuoteTick")
    data = _module("nautilus_trader.model.data")
    objects = _module("nautilus_trader.model.objects")
    return data.QuoteTick(
        instrument_id=_instrument_id(value.instrument),
        bid_price=objects.Price.from_str(
            decimal_to_fixed(
                value.bid_price, value.instrument.price_precision, field="quote.bid_price"
            )
        ),
        ask_price=objects.Price.from_str(
            decimal_to_fixed(
                value.ask_price, value.instrument.price_precision, field="quote.ask_price"
            )
        ),
        bid_size=objects.Quantity.from_str(
            decimal_to_fixed(
                value.bid_size, value.instrument.size_precision, field="quote.bid_size"
            )
        ),
        ask_size=objects.Quantity.from_str(
            decimal_to_fixed(
                value.ask_size, value.instrument.size_precision, field="quote.ask_size"
            )
        ),
        ts_event=value.exchange_ts,
        ts_init=value.receive_ts,
    )


def from_nautilus_quote(value: Any, instrument: InstrumentIdentity, *, sequence: int) -> Quote:
    if type(value).__name__ != "QuoteTick":
        raise NautilusSemanticError(f"unsupported Nautilus event type: {type(value).__name__}")
    return Quote(
        instrument=instrument,
        exchange_ts=value.ts_event,
        receive_ts=value.ts_init,
        sequence=sequence,
        bid_price=Decimal(str(value.bid_price)),
        bid_size=Decimal(str(value.bid_size)),
        ask_price=Decimal(str(value.ask_price)),
        ask_size=Decimal(str(value.ask_size)),
    )


def to_nautilus_book_delta(value: BookDelta) -> Any:
    data = _module("nautilus_trader.model.data")
    enums = _module("nautilus_trader.model.enums")
    objects = _module("nautilus_trader.model.objects")
    action = getattr(enums.BookAction, value.action)
    side = getattr(enums.OrderSide, value.side.value)
    order = data.BookOrder(
        side=side,
        price=objects.Price.from_str(
            decimal_to_fixed(value.price, value.instrument.price_precision, field="delta.price")
        ),
        size=objects.Quantity.from_str(
            decimal_to_fixed(value.size, value.instrument.size_precision, field="delta.size")
        ),
        order_id=value.level,
    )
    return data.OrderBookDelta(
        instrument_id=_instrument_id(value.instrument),
        action=cast(BookDeltaAction, action),
        order=order,
        flags=0,
        sequence=value.sequence,
        ts_event=value.exchange_ts,
        ts_init=value.receive_ts,
    )


def from_nautilus_book_delta(value: Any, instrument: InstrumentIdentity) -> BookDelta:
    if type(value).__name__ != "OrderBookDelta":
        raise NautilusSemanticError(f"unsupported Nautilus event type: {type(value).__name__}")
    action = _enum_name(value.action)
    if action not in {"ADD", "UPDATE", "DELETE"}:
        raise NautilusSemanticError(f"unsupported book action: {action}")
    book_action = cast(BookDeltaAction, action)
    return BookDelta(
        instrument=instrument,
        exchange_ts=value.ts_event,
        receive_ts=value.ts_init,
        sequence=value.sequence,
        side=OrderSide(_enum_name(value.order.side)),
        price=Decimal(str(value.order.price)),
        size=Decimal(str(value.order.size)),
        level=value.order.order_id,
        action=book_action,
    )


def to_nautilus_order(value: OrderIntent) -> Any:
    if value.linked_order_id is not None:
        raise NautilusSemanticError("linked-order semantics are unsupported by the pilot mapping")
    if value.oco_group_id is not None:
        raise NautilusSemanticError("OCO semantics are unsupported by the pilot mapping")
    orders = _module("nautilus_trader.model.orders")
    enums = _module("nautilus_trader.model.enums")
    identifiers = _module("nautilus_trader.model.identifiers")
    objects = _module("nautilus_trader.model.objects")
    uuid = _module("nautilus_trader.core.uuid")
    common: dict[str, Any] = {
        "trader_id": identifiers.TraderId("TEC-001"),
        "strategy_id": identifiers.StrategyId("VERIFY-001"),
        "instrument_id": _instrument_id(value.instrument),
        "client_order_id": identifiers.ClientOrderId(value.order_id),
        "order_side": getattr(enums.OrderSide, value.side.value),
        "quantity": objects.Quantity.from_str(
            decimal_to_fixed(
                value.quantity, value.instrument.size_precision, field="order.quantity"
            )
        ),
        "init_id": uuid.UUID4(),
        "ts_init": value.created_ts,
        "time_in_force": getattr(enums.TimeInForce, value.time_in_force.value),
    }
    if value.time_in_force.value == "GTD":
        common["expire_time_ns"] = value.expiry_ts
    if value.order_type == OrderType.MARKET:
        if value.time_in_force.value == "GTD":
            raise NautilusSemanticError("Nautilus market orders do not support GTD")
        return orders.MarketOrder(**common)
    if value.limit_price is not None:
        common["price"] = objects.Price.from_str(
            decimal_to_fixed(
                value.limit_price, value.instrument.price_precision, field="order.limit_price"
            )
        )
    if value.stop_price is not None:
        common["trigger_price"] = objects.Price.from_str(
            decimal_to_fixed(
                value.stop_price, value.instrument.price_precision, field="order.stop_price"
            )
        )
        common["trigger_type"] = enums.TriggerType.LAST_PRICE
    constructors = {
        OrderType.LIMIT: orders.LimitOrder,
        OrderType.STOP: orders.StopMarketOrder,
        OrderType.STOP_LIMIT: orders.StopLimitOrder,
    }
    try:
        constructor = constructors[value.order_type]
    except KeyError as exc:
        raise NautilusSemanticError(f"unsupported order type: {value.order_type}") from exc
    return constructor(**common)


def from_nautilus_order(
    value: Any, instrument: InstrumentIdentity, *, sequence: int
) -> OrderIntent:
    mapping = {
        "MarketOrder": OrderType.MARKET,
        "LimitOrder": OrderType.LIMIT,
        "StopMarketOrder": OrderType.STOP,
        "StopLimitOrder": OrderType.STOP_LIMIT,
    }
    try:
        order_type = mapping[type(value).__name__]
    except KeyError as exc:
        raise NautilusSemanticError(
            f"unsupported Nautilus order type: {type(value).__name__}"
        ) from exc
    expiry = value.expire_time_ns if _enum_name(value.time_in_force) == "GTD" else None
    return OrderIntent(
        order_id=str(value.client_order_id),
        instrument=instrument,
        side=OrderSide(_enum_name(value.side)),
        order_type=order_type,
        time_in_force=TimeInForce(_enum_name(value.time_in_force)),
        quantity=Decimal(str(value.quantity)),
        limit_price=Decimal(str(value.price)) if value.has_price else None,
        stop_price=Decimal(str(value.trigger_price)) if value.has_trigger_price else None,
        expiry_ts=expiry,
        created_ts=value.ts_init,
        sequence=sequence,
    )


def from_nautilus_fill(value: Any, instrument: InstrumentIdentity, *, sequence: int) -> Fill:
    if type(value).__name__ != "OrderFilled":
        raise NautilusSemanticError(f"unsupported Nautilus order event: {type(value).__name__}")
    liquidity = {
        "MAKER": LiquidityFlag.MAKER,
        "TAKER": LiquidityFlag.TAKER,
        "NO_LIQUIDITY_SIDE": LiquidityFlag.UNKNOWN,
    }[_enum_name(value.liquidity_side)]
    return Fill(
        fill_id=str(value.trade_id),
        order_id=str(value.client_order_id),
        instrument=instrument,
        side=OrderSide(_enum_name(value.order_side)),
        price=Decimal(str(value.last_px)),
        quantity=Decimal(str(value.last_qty)),
        fee=Decimal(str(value.commission.as_decimal())),
        ts=value.ts_event,
        sequence=sequence,
        liquidity=liquidity,
        slippage=None,
        queue_position=None,
        provenance="nautilus_trader_v1.231.0",
    )


def to_nautilus_fill(value: Fill, *, order_type: OrderType) -> Any:
    """Build an exact v1 ``OrderFilled`` event from a neutral fill.

    ``order_type`` is mandatory because the neutral fill intentionally does
    not duplicate it; guessing would be a semantic default.
    """
    events = _module("nautilus_trader.model.events")
    enums = _module("nautilus_trader.model.enums")
    identifiers = _module("nautilus_trader.model.identifiers")
    objects = _module("nautilus_trader.model.objects")
    uuid = _module("nautilus_trader.core.uuid")
    liquidity = {
        LiquidityFlag.MAKER: enums.LiquiditySide.MAKER,
        LiquidityFlag.TAKER: enums.LiquiditySide.TAKER,
        LiquidityFlag.UNKNOWN: enums.LiquiditySide.NO_LIQUIDITY_SIDE,
    }[value.liquidity]
    currency = objects.Currency.from_str(value.instrument.currency)
    decimal_to_fixed(value.fee, currency.precision, field="fill.fee")
    return events.OrderFilled(
        trader_id=identifiers.TraderId("TEC-001"),
        strategy_id=identifiers.StrategyId("VERIFY-001"),
        instrument_id=_instrument_id(value.instrument),
        client_order_id=identifiers.ClientOrderId(value.order_id),
        venue_order_id=identifiers.VenueOrderId(f"VERIFY-{value.order_id}"),
        account_id=identifiers.AccountId("SIM-001"),
        trade_id=identifiers.TradeId(value.fill_id),
        position_id=None,
        order_side=getattr(enums.OrderSide, value.side.value),
        order_type=getattr(enums.OrderType, order_type.value),
        last_qty=objects.Quantity.from_str(
            decimal_to_fixed(value.quantity, value.instrument.size_precision, field="fill.quantity")
        ),
        last_px=objects.Price.from_str(
            decimal_to_fixed(value.price, value.instrument.price_precision, field="fill.price")
        ),
        currency=currency,
        commission=objects.Money(value.fee, currency),
        liquidity_side=liquidity,
        event_id=uuid.UUID4(),
        ts_event=value.ts,
        ts_init=value.ts,
    )


def ledger_to_nautilus_boundaries(value: LedgerSnapshot) -> dict[str, str | int]:
    """Translate ledger economics to explicit string boundaries.

    A neutral snapshot spans account, position, margin and PnL objects; there
    is no single lossless Nautilus domain object. Returning a typed boundary
    record avoids inventing account IDs or timestamps.
    """
    if len(value.positions) != 1:
        raise NautilusSemanticError("the pilot ledger translator supports exactly one position")
    position = value.positions[0]
    return {
        "cash": str(value.cash.cash),
        "position_quantity": str(position.quantity),
        "average_price": str(position.average_price),
        "used_margin": str(value.margin.used_margin),
        "available_margin": str(value.margin.available_margin),
        "realized_pnl": str(value.pnl.realized_pnl),
        "unrealized_pnl": str(value.pnl.unrealized_pnl),
        "ts": value.ts,
        "sequence": value.sequence,
    }


@dataclass(frozen=True)
class NautilusLedgerBundle:
    account_balance: Any
    margin_balance: Any
    neutral_boundary: dict[str, str | int]


def to_nautilus_ledger(
    value: LedgerSnapshot, *, maintenance_margin: Decimal
) -> NautilusLedgerBundle:
    """Translate a one-position ledger without guessing maintenance margin."""
    if maintenance_margin < 0:
        raise NautilusSemanticError("maintenance_margin must not be negative")
    boundaries = ledger_to_nautilus_boundaries(value)
    objects = _module("nautilus_trader.model.objects")
    currency = objects.Currency.from_str(value.positions[0].instrument.currency)
    for name, amount in (
        ("ledger.cash", value.cash.cash),
        ("ledger.used_margin", value.margin.used_margin),
        ("ledger.available_margin", value.margin.available_margin),
        ("ledger.maintenance_margin", maintenance_margin),
    ):
        decimal_to_fixed(amount, currency.precision, field=name)
    account = objects.AccountBalance(
        total=objects.Money(value.cash.cash, currency),
        locked=objects.Money(value.margin.used_margin, currency),
        free=objects.Money(value.margin.available_margin, currency),
    )
    margin = objects.MarginBalance(
        initial=objects.Money(value.margin.used_margin, currency),
        maintenance=objects.Money(maintenance_margin, currency),
        instrument_id=_instrument_id(value.positions[0].instrument),
    )
    return NautilusLedgerBundle(account, margin, boundaries)


def from_nautilus_ledger(
    value: NautilusLedgerBundle, instrument: InstrumentIdentity
) -> LedgerSnapshot:
    """Restore the neutral snapshot and validate the native account boundaries."""
    boundary = value.neutral_boundary
    cash = Decimal(str(boundary["cash"]))
    used = Decimal(str(boundary["used_margin"]))
    available = Decimal(str(boundary["available_margin"]))
    if value.account_balance.total.as_decimal() != cash:
        raise NautilusSemanticError("Nautilus account total changed the neutral cash value")
    if value.account_balance.locked.as_decimal() != used:
        raise NautilusSemanticError("Nautilus account locked value changed neutral used margin")
    if value.account_balance.free.as_decimal() != available:
        raise NautilusSemanticError("Nautilus account free value changed neutral available margin")
    ts = int(boundary["ts"])
    sequence = int(boundary["sequence"])
    return LedgerSnapshot(
        cash=CashSnapshot(cash=cash, ts=ts, sequence=sequence),
        positions=[
            PositionSnapshot(
                instrument=instrument,
                quantity=Decimal(str(boundary["position_quantity"])),
                average_price=Decimal(str(boundary["average_price"])),
                ts=ts,
                sequence=sequence,
            )
        ],
        margin=MarginSnapshot(
            used_margin=used, available_margin=available, ts=ts, sequence=sequence
        ),
        pnl=PnLSnapshot(
            realized_pnl=Decimal(str(boundary["realized_pnl"])),
            unrealized_pnl=Decimal(str(boundary["unrealized_pnl"])),
            ts=ts,
            sequence=sequence,
        ),
        ts=ts,
        sequence=sequence,
    )
