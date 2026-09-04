"""Unit tests for the pure-Python Decimal golden oracle.

These tests hand-calculate every expected fill price, fee and ledger value
so a human reviewer can check the arithmetic without running the code.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from trading_engine_conformance.golden.oracle import GoldenOracleError, OracleConfig, run_oracle
from trading_engine_conformance.schema.enums import (
    AssetClass,
    LiquidityFlag,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.market_events import Bar, Trade
from trading_engine_conformance.schema.orders import OrderIntent

_INSTRUMENT = InstrumentIdentity(
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

_T0 = 1_767_225_600_000_000_000
_NS = 1_000_000_000


def _order(**overrides: object) -> OrderIntent:
    fields: dict[str, object] = {
        "order_id": "ord-1",
        "instrument": _INSTRUMENT,
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.GTC,
        "quantity": "10",
        "limit_price": None,
        "stop_price": None,
        "expiry_ts": None,
        "created_ts": _T0,
        "sequence": 0,
        "linked_order_id": None,
        "oco_group_id": None,
    }
    fields.update(overrides)
    return OrderIntent(**fields)  # type: ignore[arg-type]


def _trade(ts: int, price: str, size: str, sequence: int = 0) -> Trade:
    return Trade(
        instrument=_INSTRUMENT,
        exchange_ts=ts,
        receive_ts=ts,
        sequence=sequence,
        price=price,
        size=size,
        aggressor_side=OrderSide.BUY,
    )


def _bar(
    open_ts: int,
    close_ts: int,
    o: str,
    h: str,
    low_: str,
    c: str,
    sequence: int = 0,
    volume: str = "1000",
) -> Bar:
    return Bar(
        instrument=_INSTRUMENT,
        exchange_ts=close_ts,
        receive_ts=close_ts,
        sequence=sequence,
        open=o,
        high=h,
        low=low_,
        close=c,
        volume=volume,
        bar_open_ts=open_ts,
        bar_close_ts=close_ts,
    )


_CONFIG = OracleConfig(
    starting_cash=Decimal("100000"),
    fee_rate=Decimal("0.001"),
    margin_rate=Decimal("0.05"),
)


class TestMarketOrder:
    def test_full_fill_at_trade_price(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10")
        events = [_trade(_T0 + _NS, "2000.0", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        fill = result.fills[0]
        assert fill.price == Decimal("2000.0")
        assert fill.quantity == Decimal("10")
        # fee = 0.001 * 2000.0 * 10 = 20.000
        assert fill.fee == Decimal("20.000")
        final = result.final_ledger
        # cash = 100000 - (2000*10) - 20 = 79980
        assert final.cash.cash == Decimal("79980.000")
        assert final.positions[0].quantity == Decimal("10")
        assert final.positions[0].average_price == Decimal("2000.0")

    def test_no_fill_on_same_event_as_creation_ts(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10", created_ts=_T0)
        events = [_trade(_T0, "2000.0", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert result.fills == []

    def test_partial_fill_then_residual_fills_on_next_event(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10")
        events = [
            _trade(_T0 + _NS, "2000.0", "4", sequence=0),
            _trade(_T0 + 2 * _NS, "2001.0", "20", sequence=1),
        ]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert [f.quantity for f in result.fills] == [Decimal("4"), Decimal("6")]
        assert [f.price for f in result.fills] == [Decimal("2000.0"), Decimal("2001.0")]
        final = result.final_ledger
        assert final.positions[0].quantity == Decimal("10")
        # weighted avg price = (4*2000.0 + 6*2001.0) / 10 = 2000.6
        assert final.positions[0].average_price == Decimal("2000.6")

    def test_insufficient_liquidity_preserves_residual_quantity(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10")
        events = [_trade(_T0 + _NS, "2000.0", "3")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].quantity == Decimal("3")
        transitions = [t.to_status for t in result.order_transitions if t.order_id == "ord-1"]
        assert OrderStatus.PARTIALLY_FILLED in transitions
        assert OrderStatus.FILLED not in transitions


class TestLimitOrder:
    def test_buy_limit_fills_when_price_at_or_below_limit(self) -> None:
        order = _order(order_type=OrderType.LIMIT, limit_price="10", quantity="5")
        events = [_trade(_T0 + _NS, "9.5", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        # fills at the limit price, not the (better) trade price
        assert result.fills[0].price == Decimal("10")

    def test_buy_limit_does_not_fill_above_limit(self) -> None:
        order = _order(order_type=OrderType.LIMIT, limit_price="10", quantity="5")
        events = [_trade(_T0 + _NS, "10.5", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert result.fills == []

    def test_sell_limit_fills_when_price_at_or_above_limit(self) -> None:
        order = _order(
            order_type=OrderType.LIMIT, side=OrderSide.SELL, limit_price="10", quantity="5"
        )
        events = [_trade(_T0 + _NS, "10.5", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("10")


class TestStopOrder:
    def test_buy_stop_triggers_and_fills_at_trade_price(self) -> None:
        order = _order(order_type=OrderType.STOP, stop_price="10", quantity="5")
        events = [_trade(_T0 + _NS, "10.2", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("10.2")

    def test_sell_stop_adverse_gap_fills_at_first_available_price(self) -> None:
        order = _order(
            order_type=OrderType.STOP, side=OrderSide.SELL, stop_price="10", quantity="5"
        )
        # gap: price jumps from above 10 straight down to 8.0 -- worse than stop_price
        events = [_trade(_T0 + _NS, "8.0", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("8.0")

    def test_stop_not_triggered_before_stop_price_reached(self) -> None:
        order = _order(order_type=OrderType.STOP, stop_price="10", quantity="5")
        events = [_trade(_T0 + _NS, "9.9", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert result.fills == []


class TestStopLimitOrder:
    def test_triggers_then_fills_within_limit_on_same_event(self) -> None:
        order = _order(
            order_type=OrderType.STOP_LIMIT, stop_price="10", limit_price="10.5", quantity="5"
        )
        events = [_trade(_T0 + _NS, "10.2", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("10.5")

    def test_triggers_but_waits_for_limit_on_later_event(self) -> None:
        order = _order(
            order_type=OrderType.STOP_LIMIT, stop_price="10", limit_price="10.0", quantity="5"
        )
        events = [
            _trade(_T0 + _NS, "10.5", "50", sequence=0),
            _trade(_T0 + 2 * _NS, "9.8", "50", sequence=1),
        ]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("10.0")
        assert result.fills[0].ts == _T0 + 2 * _NS


class TestGapBar:
    def test_gap_open_fills_stop_at_open_not_stop_price(self) -> None:
        order = _order(
            order_type=OrderType.STOP, side=OrderSide.SELL, stop_price="10", quantity="5"
        )
        events = [_bar(_T0 + _NS, _T0 + 2 * _NS, "8.0", "8.5", "7.5", "8.2")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("8.0")

    def test_buy_side_gap_fills_at_open(self) -> None:
        order = _order(order_type=OrderType.STOP, side=OrderSide.BUY, stop_price="10", quantity="5")
        events = [_bar(_T0 + _NS, _T0 + 2 * _NS, "12.0", "12.5", "11.5", "12.2")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("12.0")

    def test_buy_side_touch_within_bar_fills_at_stop_price(self) -> None:
        order = _order(order_type=OrderType.STOP, side=OrderSide.BUY, stop_price="10", quantity="5")
        events = [_bar(_T0 + _NS, _T0 + 2 * _NS, "9.0", "10.5", "8.5", "9.5")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("10")

    def test_already_triggered_stop_continues_at_next_bar_open(self) -> None:
        order = _order(
            order_type=OrderType.STOP,
            side=OrderSide.SELL,
            stop_price="10",
            quantity="10",
        )
        events = [
            _bar(
                _T0 + _NS,
                _T0 + 2 * _NS,
                "9.5",
                "9.6",
                "9.0",
                "9.2",
                sequence=0,
                volume="4",
            ),
            _bar(
                _T0 + 2 * _NS,
                _T0 + 3 * _NS,
                "9.0",
                "9.4",
                "8.8",
                "9.1",
                sequence=1,
                volume="20",
            ),
        ]
        # first bar touches the stop but liquidity (volume) covers only part
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) >= 1
        assert result.fills[-1].price == Decimal("9.0")

    def test_bar_limit_order_fills_at_limit_price(self) -> None:
        order = _order(order_type=OrderType.LIMIT, limit_price="10.0", quantity="5")
        events = [_bar(_T0 + _NS, _T0 + 2 * _NS, "10.5", "10.6", "9.5", "10.1")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("10.0")

    def test_bar_limit_order_no_fill_when_not_touched(self) -> None:
        order = _order(order_type=OrderType.LIMIT, limit_price="5.0", quantity="5")
        events = [_bar(_T0 + _NS, _T0 + 2 * _NS, "10.5", "10.6", "9.5", "10.1")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert result.fills == []

    def test_bar_stop_limit_triggers_and_fills_within_limit(self) -> None:
        order = _order(
            order_type=OrderType.STOP_LIMIT,
            side=OrderSide.SELL,
            stop_price="10.0",
            limit_price="9.5",
            quantity="5",
        )
        events = [_bar(_T0 + _NS, _T0 + 2 * _NS, "9.8", "9.9", "9.4", "9.6")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("9.5")

    def test_no_same_bar_close_fill_for_order_created_intrabar(self) -> None:
        order = _order(
            order_type=OrderType.MARKET,
            quantity="5",
            created_ts=_T0 + _NS,
        )
        # bar starts before order creation but closes after -- order was
        # created *during* this bar, so it must not fill on this bar's close
        events = [
            _bar(_T0, _T0 + 2 * _NS, "100", "105", "95", "102", sequence=0),
            _bar(_T0 + 2 * _NS, _T0 + 3 * _NS, "102", "106", "101", "104", sequence=1),
        ]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].price == Decimal("102")  # next bar's open


class TestTimeInForce:
    def test_ioc_cancels_unfilled_residual_after_first_eligible_event(self) -> None:
        order = _order(order_type=OrderType.MARKET, time_in_force=TimeInForce.IOC, quantity="10")
        events = [
            _trade(_T0 + _NS, "2000.0", "4", sequence=0),
            _trade(_T0 + 2 * _NS, "2001.0", "20", sequence=1),
        ]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].quantity == Decimal("4")
        transitions = [t.to_status for t in result.order_transitions if t.order_id == "ord-1"]
        assert OrderStatus.CANCELED in transitions

    def test_fok_cancels_entirely_if_liquidity_insufficient(self) -> None:
        order = _order(order_type=OrderType.MARKET, time_in_force=TimeInForce.FOK, quantity="10")
        events = [_trade(_T0 + _NS, "2000.0", "4")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert result.fills == []
        transitions = [t.to_status for t in result.order_transitions if t.order_id == "ord-1"]
        assert OrderStatus.CANCELED in transitions

    def test_fok_fills_fully_when_liquidity_sufficient(self) -> None:
        order = _order(order_type=OrderType.MARKET, time_in_force=TimeInForce.FOK, quantity="10")
        events = [_trade(_T0 + _NS, "2000.0", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.fills) == 1
        assert result.fills[0].quantity == Decimal("10")

    def test_gtd_expires_after_expiry_ts_without_fill(self) -> None:
        order = _order(
            order_type=OrderType.LIMIT,
            limit_price="1",
            time_in_force=TimeInForce.GTD,
            expiry_ts=_T0 + _NS,
            quantity="10",
        )
        events = [_trade(_T0 + 2 * _NS, "2000.0", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert result.fills == []
        transitions = [t.to_status for t in result.order_transitions if t.order_id == "ord-1"]
        assert OrderStatus.EXPIRED in transitions


class TestSameTimestampPriority:
    def test_lower_sequence_order_has_priority_for_shared_liquidity(self) -> None:
        first = _order(order_id="ord-1", quantity="10", sequence=0, created_ts=_T0)
        second = _order(order_id="ord-2", quantity="10", sequence=1, created_ts=_T0)
        events = [_trade(_T0 + _NS, "2000.0", "12")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[first, second], events=events, config=_CONFIG
        )
        by_order = {f.order_id: f.quantity for f in result.fills}
        assert by_order["ord-1"] == Decimal("10")
        assert by_order["ord-2"] == Decimal("2")

    def test_result_independent_of_input_order_of_intents(self) -> None:
        first = _order(order_id="ord-1", quantity="10", sequence=0, created_ts=_T0)
        second = _order(order_id="ord-2", quantity="10", sequence=1, created_ts=_T0)
        events = [_trade(_T0 + _NS, "2000.0", "12")]
        forward = run_oracle(
            instrument=_INSTRUMENT, order_intents=[first, second], events=events, config=_CONFIG
        )
        reversed_result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[second, first], events=events, config=_CONFIG
        )
        assert [(f.order_id, f.quantity) for f in forward.fills] == [
            (f.order_id, f.quantity) for f in reversed_result.fills
        ]


class TestPositionFlip:
    def test_oversized_reducing_fill_flips_position_direction(self) -> None:
        buy = _order(order_id="ord-1", side=OrderSide.BUY, quantity="5", sequence=0)
        sell = _order(
            order_id="ord-2",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity="8",
            sequence=1,
            created_ts=_T0 + _NS,
        )
        events = [
            _trade(_T0 + _NS, "2000.0", "5", sequence=0),
            _trade(_T0 + 2 * _NS, "2010.0", "8", sequence=1),
        ]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[buy, sell], events=events, config=_CONFIG
        )
        final = result.final_ledger
        # long 5 @ 2000.0 flips to short -3 @ 2010.0 (the flip fill's own price)
        assert final.positions[0].quantity == Decimal("-3")
        assert final.positions[0].average_price == Decimal("2010.0")


class TestOrderTransitions:
    def test_full_lifecycle_new_accepted_filled(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10")
        events = [_trade(_T0 + _NS, "2000.0", "50")]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        statuses = [
            (t.from_status, t.to_status) for t in result.order_transitions if t.order_id == "ord-1"
        ]
        assert statuses == [
            (None, OrderStatus.NEW),
            (OrderStatus.NEW, OrderStatus.ACCEPTED),
            (OrderStatus.ACCEPTED, OrderStatus.FILLED),
        ]

    def test_partial_then_full_fill_transitions(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10")
        events = [
            _trade(_T0 + _NS, "2000.0", "4", sequence=0),
            _trade(_T0 + 2 * _NS, "2001.0", "20", sequence=1),
        ]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        statuses = [
            (t.from_status, t.to_status) for t in result.order_transitions if t.order_id == "ord-1"
        ]
        assert statuses == [
            (None, OrderStatus.NEW),
            (OrderStatus.NEW, OrderStatus.ACCEPTED),
            (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED),
            (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED),
        ]

    def test_ledger_snapshot_emitted_per_fill(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10")
        events = [
            _trade(_T0 + _NS, "2000.0", "4", sequence=0),
            _trade(_T0 + 2 * _NS, "2001.0", "20", sequence=1),
        ]
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=_CONFIG
        )
        assert len(result.ledger_snapshots) == len(result.fills)
        seqs = [s.sequence for s in result.ledger_snapshots]
        assert seqs == sorted(seqs)


class TestFinalLiquidation:
    def test_forces_close_of_remaining_position_at_last_price(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10")
        events = [_trade(_T0 + _NS, "2000.0", "10")]
        config = OracleConfig(
            starting_cash=Decimal("100000"),
            fee_rate=Decimal("0.001"),
            margin_rate=Decimal("0.05"),
            final_liquidation_ts=_T0 + 5 * _NS,
        )
        result = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events, config=config
        )
        assert len(result.fills) == 2
        liquidation_fill = result.fills[-1]
        assert liquidation_fill.side == OrderSide.SELL
        assert liquidation_fill.quantity == Decimal("10")
        assert liquidation_fill.price == Decimal("2000.0")
        assert liquidation_fill.provenance == "final_liquidation"
        assert liquidation_fill.liquidity == LiquidityFlag.TAKER
        final = result.final_ledger
        assert final.positions[0].quantity == Decimal("0")
        # realized pnl on the round trip at flat price = 0, minus two fees
        # fee1 = 0.001*2000.0*10 = 20.000, fee2 same = 20.000
        assert final.cash.cash == Decimal("100000") - Decimal("20.000") - Decimal("20.000")

    def test_no_liquidation_fill_when_no_open_position(self) -> None:
        config = OracleConfig(
            starting_cash=Decimal("100000"),
            fee_rate=Decimal("0.001"),
            margin_rate=Decimal("0.05"),
            final_liquidation_ts=_T0 + 5 * _NS,
        )
        result = run_oracle(instrument=_INSTRUMENT, order_intents=[], events=[], config=config)
        assert result.fills == []


class TestCausalityAndValidation:
    def test_future_event_mutation_does_not_change_prior_fills(self) -> None:
        order = _order(order_type=OrderType.MARKET, quantity="10")
        events_a = [
            _trade(_T0 + _NS, "2000.0", "10", sequence=0),
            _trade(_T0 + 2 * _NS, "5000.0", "10", sequence=1),
        ]
        events_b = [
            _trade(_T0 + _NS, "2000.0", "10", sequence=0),
            _trade(_T0 + 2 * _NS, "1.0", "10", sequence=1),
        ]
        result_a = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events_a, config=_CONFIG
        )
        result_b = run_oracle(
            instrument=_INSTRUMENT, order_intents=[order], events=events_b, config=_CONFIG
        )
        assert result_a.fills[0] == result_b.fills[0]

    def test_rejects_order_for_different_instrument(self) -> None:
        other_instrument = InstrumentIdentity(
            venue="CME",
            symbol="ESZ26",
            asset_class=AssetClass.FUTURE,
            currency="USD",
            price_precision=2,
            size_precision=0,
            tick_size="0.25",
            tick_value="12.50",
            multiplier="50",
            expiry_ts=1_798_761_600_000_000_000,
            metadata_effective_ts=1_767_225_600_000_000_000,
            is_continuous=False,
        )
        order = _order(instrument=other_instrument)
        with pytest.raises(GoldenOracleError):
            run_oracle(instrument=_INSTRUMENT, order_intents=[order], events=[], config=_CONFIG)

    def test_rejects_duplicate_event_sequence(self) -> None:
        events = [
            _trade(_T0 + _NS, "2000.0", "10", sequence=0),
            _trade(_T0 + 2 * _NS, "2001.0", "10", sequence=0),
        ]
        with pytest.raises(GoldenOracleError):
            run_oracle(instrument=_INSTRUMENT, order_intents=[], events=events, config=_CONFIG)

    def test_rejects_duplicate_order_sequence(self) -> None:
        first = _order(order_id="ord-1", sequence=0)
        second = _order(order_id="ord-2", sequence=0)
        with pytest.raises(GoldenOracleError):
            run_oracle(
                instrument=_INSTRUMENT, order_intents=[first, second], events=[], config=_CONFIG
            )
