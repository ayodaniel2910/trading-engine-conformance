"""A small, pure-Python, hand-calculable Decimal reference ledger.

This is a conformance oracle, not a production simulator. It encodes a
deliberately small set of unambiguous causal execution rules so a human
reviewer can check the arithmetic by hand:

- **Causality.** An order may only be matched against a ``Trade`` whose
  ``exchange_ts`` is strictly after the order's ``created_ts``, or a
  ``Bar`` whose ``bar_open_ts`` is at or after the order's ``created_ts``
  (i.e. the order existed before the bar began). A bar's ``close`` is
  never used to fill an order that was itself created during that same
  bar -- there is no same-bar close fill path.
- **Same-timestamp priority.** When multiple orders are eligible for the
  same event, they compete for that event's liquidity strictly in
  ascending ``sequence`` order -- independent of the input list order.
- **Gaps.** On a ``Trade`` tape, a gap is simply the next eligible trade
  price; a triggered stop always fills at that price, whether or not it
  matches the stop level exactly. On a ``Bar`` tape, a gap through a stop
  level at the bar's ``open`` fills at ``open`` (the first available
  price); a level only touched within ``[low, high]`` fills at the level
  itself.
- **Liquidity.** Each event carries finite liquidity (``Trade.size`` or
  ``Bar.volume``); a fill can never exceed it, and any unfilled residual
  remains open for a future event.
- **Time in force.** ``IOC``/``FOK`` orders only ever act on their first
  causally eligible event; ``FOK`` fills fully or not at all; ``GTD``
  orders expire the first time an event's timestamp passes their
  ``expiry_ts`` without being fully filled.
- **Final liquidation.** If configured, any open position is force-closed
  at the last known trade price when the run ends, as an explicit, costed
  fill.

Every fill updates cash, position (weighted-average price), realized and
unrealized PnL, and a simplified used/available margin snapshot -- exact
``Decimal`` throughout, no floats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from trading_engine_conformance.ordering import SequenceError, canonical_order
from trading_engine_conformance.schema.enums import (
    LiquidityFlag,
    OrderSide,
    OrderStatus,
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
from trading_engine_conformance.schema.market_events import Bar, Trade
from trading_engine_conformance.schema.orders import (
    OrderIntent,
    OrderStateTransition,
    OrderTransitionError,
    validate_transition,
)

_ACTIVE_STATUSES = frozenset({OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED})
_SINGLE_SHOT_TIF = frozenset({TimeInForce.IOC, TimeInForce.FOK})

MarketTick = Trade | Bar


class GoldenOracleError(ValueError):
    """Raised when a golden case cannot be evaluated: non-causal input,
    a wrong instrument reference, or an internally impossible order
    transition."""


@dataclass(frozen=True)
class OracleConfig:
    starting_cash: Decimal
    fee_rate: Decimal
    margin_rate: Decimal
    final_liquidation_ts: int | None = None


@dataclass(frozen=True)
class OracleResult:
    fills: list[Fill]
    order_transitions: list[OrderStateTransition]
    ledger_snapshots: list[LedgerSnapshot]
    final_ledger: LedgerSnapshot


@dataclass
class _OrderRuntime:
    intent: OrderIntent
    status: OrderStatus = OrderStatus.ACCEPTED
    remaining: Decimal = field(default=Decimal(0))
    stop_triggered: bool = False
    first_event_consumed: bool = False


def _require_price(price: Decimal | None, order_id: str, field_name: str) -> Decimal:
    if price is None:
        raise GoldenOracleError(f"order {order_id!r} is missing required {field_name}")
    return price


def _eligible(order: OrderIntent, event: MarketTick) -> bool:
    if isinstance(event, Bar):
        return order.created_ts <= event.bar_open_ts
    return event.exchange_ts > order.created_ts


def _event_ts(event: MarketTick) -> int:
    return event.bar_close_ts if isinstance(event, Bar) else event.exchange_ts


def _trade_marketability(runtime: _OrderRuntime, event: Trade) -> tuple[bool, Decimal]:
    order = runtime.intent
    price = event.price
    if order.order_type == OrderType.MARKET:
        return True, price
    if order.order_type == OrderType.LIMIT:
        limit_price = _require_price(order.limit_price, order.order_id, "limit_price")
        marketable = price <= limit_price if order.side == OrderSide.BUY else price >= limit_price
        return marketable, limit_price
    if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
        stop_price = _require_price(order.stop_price, order.order_id, "stop_price")
        if not runtime.stop_triggered:
            triggered = price >= stop_price if order.side == OrderSide.BUY else price <= stop_price
            if not triggered:
                return False, Decimal(0)
            runtime.stop_triggered = True
        if order.order_type == OrderType.STOP:
            return True, price
        limit_price = _require_price(order.limit_price, order.order_id, "limit_price")
        marketable = price <= limit_price if order.side == OrderSide.BUY else price >= limit_price
        return marketable, limit_price
    raise GoldenOracleError(f"unsupported order type: {order.order_type}")


def _bar_marketability(runtime: _OrderRuntime, event: Bar) -> tuple[bool, Decimal]:
    order = runtime.intent
    open_, high, low = event.open, event.high, event.low
    if order.order_type == OrderType.MARKET:
        return True, open_
    if order.order_type == OrderType.LIMIT:
        limit_price = _require_price(order.limit_price, order.order_id, "limit_price")
        marketable = low <= limit_price if order.side == OrderSide.BUY else high >= limit_price
        return marketable, limit_price
    if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
        stop_price = _require_price(order.stop_price, order.order_id, "stop_price")
        trigger_price = _bar_trigger_price(runtime, order.side, stop_price, (open_, high, low))
        if trigger_price is None:
            return False, Decimal(0)
        if order.order_type == OrderType.STOP:
            return True, trigger_price
        limit_price = _require_price(order.limit_price, order.order_id, "limit_price")
        marketable = low <= limit_price if order.side == OrderSide.BUY else high >= limit_price
        return marketable, limit_price
    raise GoldenOracleError(f"unsupported order type: {order.order_type}")


def _bar_trigger_price(
    runtime: _OrderRuntime,
    side: OrderSide,
    stop_price: Decimal,
    ohl: tuple[Decimal, Decimal, Decimal],
) -> Decimal | None:
    open_, high, low = ohl
    if runtime.stop_triggered:
        return open_
    if side == OrderSide.BUY:
        gapped, touched = open_ >= stop_price, high >= stop_price
    else:
        gapped, touched = open_ <= stop_price, low <= stop_price
    if not (gapped or touched):
        return None
    runtime.stop_triggered = True
    return open_ if gapped else stop_price


def _zero_ledger_snapshot(instrument: InstrumentIdentity, starting_cash: Decimal) -> LedgerSnapshot:
    return LedgerSnapshot(
        cash=CashSnapshot(cash=starting_cash, ts=0, sequence=0),
        positions=[
            PositionSnapshot(
                instrument=instrument,
                quantity=Decimal(0),
                average_price=Decimal(0),
                ts=0,
                sequence=0,
            )
        ],
        margin=MarginSnapshot(
            used_margin=Decimal(0), available_margin=starting_cash, ts=0, sequence=0
        ),
        pnl=PnLSnapshot(realized_pnl=Decimal(0), unrealized_pnl=Decimal(0), ts=0, sequence=0),
        ts=0,
        sequence=0,
    )


@dataclass
class _Ledger:
    """Mutable per-run cash/position/PnL state plus the output streams
    (fills, order transitions, ledger snapshots) being accumulated."""

    instrument: InstrumentIdentity
    config: OracleConfig
    fills: list[Fill] = field(default_factory=list)
    transitions: list[OrderStateTransition] = field(default_factory=list)
    ledger_snapshots: list[LedgerSnapshot] = field(default_factory=list)
    cash: Decimal = Decimal(0)
    position_qty: Decimal = Decimal(0)
    avg_price: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    last_price: Decimal = Decimal(0)
    fill_seq: int = 0
    transition_seq: int = 0
    ledger_seq: int = 0

    def emit_transition(
        self, order_id: str, from_status: OrderStatus | None, to_status: OrderStatus, ts: int
    ) -> None:
        try:
            validate_transition(from_status, to_status)
        except OrderTransitionError as exc:
            raise GoldenOracleError(str(exc)) from exc
        self.transitions.append(
            OrderStateTransition(
                order_id=order_id,
                from_status=from_status,
                to_status=to_status,
                ts=ts,
                sequence=self.transition_seq,
                reason=None,
            )
        )
        self.transition_seq += 1

    def _append_ledger_snapshot(self, ts: int) -> None:
        seq = self.ledger_seq
        used_margin = abs(self.position_qty) * self.last_price * self.config.margin_rate
        available_margin = max(self.cash - used_margin, Decimal(0))
        unrealized = (self.last_price - self.avg_price) * self.position_qty
        self.ledger_snapshots.append(
            LedgerSnapshot(
                cash=CashSnapshot(cash=self.cash, ts=ts, sequence=seq),
                positions=[
                    PositionSnapshot(
                        instrument=self.instrument,
                        quantity=self.position_qty,
                        average_price=self.avg_price if self.position_qty != 0 else Decimal(0),
                        ts=ts,
                        sequence=seq,
                    )
                ],
                margin=MarginSnapshot(
                    used_margin=used_margin, available_margin=available_margin, ts=ts, sequence=seq
                ),
                pnl=PnLSnapshot(
                    realized_pnl=self.realized_pnl, unrealized_pnl=unrealized, ts=ts, sequence=seq
                ),
                ts=ts,
                sequence=seq,
            )
        )
        self.ledger_seq += 1

    def _apply_position_delta(self, side: OrderSide, price: Decimal, qty: Decimal) -> None:
        signed_qty = qty if side == OrderSide.BUY else -qty
        position_qty = self.position_qty
        if position_qty == 0 or (position_qty > 0) == (signed_qty > 0):
            new_qty = position_qty + signed_qty
            self.avg_price = (
                price
                if position_qty == 0
                else (self.avg_price * abs(position_qty) + price * qty) / abs(new_qty)
            )
            self.position_qty = new_qty
            return
        closing_qty = min(abs(signed_qty), abs(position_qty))
        direction = Decimal(1) if position_qty > 0 else Decimal(-1)
        self.realized_pnl += (price - self.avg_price) * closing_qty * direction
        self.position_qty = position_qty + signed_qty
        if abs(signed_qty) > abs(position_qty):
            self.avg_price = price
        elif self.position_qty == 0:
            self.avg_price = Decimal(0)

    def execute_fill(
        self,
        order_id: str,
        side: OrderSide,
        price: Decimal,
        qty: Decimal,
        ts: int,
        *,
        liquidity: LiquidityFlag,
        provenance: str,
    ) -> None:
        fee = price * qty * self.config.fee_rate
        self._apply_position_delta(side, price, qty)
        self.cash += -(price * qty) - fee if side == OrderSide.BUY else (price * qty) - fee
        self.last_price = price
        seq = self.fill_seq
        self.fills.append(
            Fill(
                fill_id=f"{order_id}-fill-{seq}",
                order_id=order_id,
                instrument=self.instrument,
                side=side,
                price=price,
                quantity=qty,
                fee=fee,
                ts=ts,
                sequence=seq,
                liquidity=liquidity,
                provenance=provenance,
            )
        )
        self.fill_seq += 1
        self._append_ledger_snapshot(ts)

    def fill_order(self, runtime: _OrderRuntime, price: Decimal, qty: Decimal, ts: int) -> None:
        self.execute_fill(
            runtime.intent.order_id,
            runtime.intent.side,
            price,
            qty,
            ts,
            liquidity=LiquidityFlag.TAKER,
            provenance="golden_oracle",
        )
        runtime.remaining -= qty
        new_status = OrderStatus.FILLED if runtime.remaining <= 0 else OrderStatus.PARTIALLY_FILLED
        if new_status != runtime.status:
            self.emit_transition(runtime.intent.order_id, runtime.status, new_status, ts)
            runtime.status = new_status


def _validate_and_order_intents(
    order_intents: list[OrderIntent], instrument: InstrumentIdentity
) -> list[OrderIntent]:
    try:
        ordered = canonical_order(order_intents)
    except SequenceError as exc:
        raise GoldenOracleError(str(exc)) from exc
    for intent in ordered:
        if intent.instrument != instrument:
            raise GoldenOracleError(
                f"order {intent.order_id!r} references a different instrument than this oracle run"
            )
    return ordered


def _validate_and_order_events(events: list[MarketTick]) -> list[MarketTick]:
    try:
        return canonical_order(events)
    except SequenceError as exc:
        raise GoldenOracleError(str(exc)) from exc


def _accept_orders(ledger: _Ledger, ordered_intents: list[OrderIntent]) -> dict[str, _OrderRuntime]:
    runtimes: dict[str, _OrderRuntime] = {}
    for intent in ordered_intents:
        runtimes[intent.order_id] = _OrderRuntime(intent=intent, remaining=intent.quantity)
        ledger.emit_transition(intent.order_id, None, OrderStatus.NEW, intent.created_ts)
        ledger.emit_transition(
            intent.order_id, OrderStatus.NEW, OrderStatus.ACCEPTED, intent.created_ts
        )
    return runtimes


def _expire_gtd_orders(
    ledger: _Ledger,
    ordered_intents: list[OrderIntent],
    runtimes: dict[str, _OrderRuntime],
    event_ts: int,
) -> None:
    for intent in ordered_intents:
        runtime = runtimes[intent.order_id]
        if (
            intent.time_in_force == TimeInForce.GTD
            and intent.expiry_ts is not None
            and runtime.status in _ACTIVE_STATUSES
            and event_ts > intent.expiry_ts
        ):
            ledger.emit_transition(intent.order_id, runtime.status, OrderStatus.EXPIRED, event_ts)
            runtime.status = OrderStatus.EXPIRED


def _match_runtime(
    ledger: _Ledger,
    runtime: _OrderRuntime,
    event: MarketTick,
    event_ts: int,
    available_liquidity: Decimal,
) -> Decimal:
    """Attempt to match ``runtime`` against ``event``; returns the
    liquidity consumed (0 if no fill occurred)."""
    marketable, fill_price = (
        _trade_marketability(runtime, event)
        if isinstance(event, Trade)
        else _bar_marketability(runtime, event)
    )
    if not marketable:
        return Decimal(0)
    if runtime.intent.time_in_force == TimeInForce.FOK:
        if available_liquidity < runtime.remaining:
            return Decimal(0)
        fill_qty = runtime.remaining
    else:
        fill_qty = min(runtime.remaining, available_liquidity)
    if fill_qty <= 0:
        return Decimal(0)
    ledger.fill_order(runtime, fill_price, fill_qty, event_ts)
    return fill_qty


def _process_event(
    ledger: _Ledger,
    ordered_intents: list[OrderIntent],
    runtimes: dict[str, _OrderRuntime],
    event: MarketTick,
) -> None:
    event_ts = _event_ts(event)
    _expire_gtd_orders(ledger, ordered_intents, runtimes, event_ts)

    available_liquidity = event.size if isinstance(event, Trade) else event.volume
    touched: list[_OrderRuntime] = []
    for intent in ordered_intents:
        runtime = runtimes[intent.order_id]
        if runtime.status not in _ACTIVE_STATUSES or not _eligible(intent, event):
            continue
        if intent.time_in_force in _SINGLE_SHOT_TIF and runtime.first_event_consumed:
            continue
        touched.append(runtime)
        if intent.time_in_force in _SINGLE_SHOT_TIF:
            runtime.first_event_consumed = True
        if available_liquidity <= 0:
            continue
        available_liquidity -= _match_runtime(ledger, runtime, event, event_ts, available_liquidity)

    for runtime in touched:
        if (
            runtime.intent.time_in_force in _SINGLE_SHOT_TIF
            and runtime.remaining > 0
            and runtime.status in _ACTIVE_STATUSES
        ):
            ledger.emit_transition(
                runtime.intent.order_id, runtime.status, OrderStatus.CANCELED, event_ts
            )
            runtime.status = OrderStatus.CANCELED


def _apply_final_liquidation(ledger: _Ledger) -> None:
    if ledger.config.final_liquidation_ts is None or ledger.position_qty == 0:
        return
    side = OrderSide.SELL if ledger.position_qty > 0 else OrderSide.BUY
    qty = abs(ledger.position_qty)
    ledger.execute_fill(
        "__final_liquidation__",
        side,
        ledger.last_price,
        qty,
        ledger.config.final_liquidation_ts,
        liquidity=LiquidityFlag.TAKER,
        provenance="final_liquidation",
    )


def run_oracle(
    *,
    instrument: InstrumentIdentity,
    order_intents: list[OrderIntent],
    events: list[MarketTick],
    config: OracleConfig,
) -> OracleResult:
    """Replay ``order_intents`` against ``events`` and return the
    resulting fills, order-state transitions and ledger snapshots.

    Raises ``GoldenOracleError`` if the input streams are not causally
    valid (duplicate sequence numbers) or an order references an
    instrument other than ``instrument``.
    """
    ordered_intents = _validate_and_order_intents(order_intents, instrument)
    ordered_events = _validate_and_order_events(events)

    ledger = _Ledger(instrument=instrument, config=config, cash=config.starting_cash)
    runtimes = _accept_orders(ledger, ordered_intents)

    for event in ordered_events:
        _process_event(ledger, ordered_intents, runtimes, event)

    _apply_final_liquidation(ledger)

    final_ledger = (
        ledger.ledger_snapshots[-1]
        if ledger.ledger_snapshots
        else _zero_ledger_snapshot(instrument, config.starting_cash)
    )

    return OracleResult(
        fills=ledger.fills,
        order_transitions=ledger.transitions,
        ledger_snapshots=ledger.ledger_snapshots,
        final_ledger=final_ledger,
    )
