"""Unit tests for shared schema enums: string-valued, JSON round-trippable."""

from trading_engine_conformance.schema.enums import (
    AssetClass,
    HoldoutAccessState,
    LiquidityFlag,
    OrderSide,
    OrderStatus,
    OrderType,
    SessionStatus,
    TimeInForce,
)


class TestEnumsAreStringValued:
    def test_order_side_values(self) -> None:
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"

    def test_order_type_members(self) -> None:
        assert {m.value for m in OrderType} == {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}

    def test_time_in_force_members(self) -> None:
        assert {m.value for m in TimeInForce} == {"DAY", "GTC", "IOC", "FOK", "GTD"}

    def test_order_status_members(self) -> None:
        assert {m.value for m in OrderStatus} == {
            "NEW",
            "ACCEPTED",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELED",
            "REJECTED",
            "EXPIRED",
        }

    def test_asset_class_has_future(self) -> None:
        assert AssetClass.FUTURE.value == "FUTURE"

    def test_liquidity_flag_members(self) -> None:
        assert {m.value for m in LiquidityFlag} == {"MAKER", "TAKER", "UNKNOWN"}

    def test_session_status_members(self) -> None:
        assert {m.value for m in SessionStatus} == {
            "PRE_OPEN",
            "OPEN",
            "CLOSED",
            "HALTED",
            "MAINTENANCE",
        }

    def test_holdout_access_state_members(self) -> None:
        assert {m.value for m in HoldoutAccessState} == {"SEALED", "OPENED"}

    def test_enums_are_str_subclass_for_json_friendliness(self) -> None:
        assert isinstance(OrderSide.BUY, str)
