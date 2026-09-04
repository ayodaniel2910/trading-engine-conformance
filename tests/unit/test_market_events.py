"""Unit tests for market event models: quotes, trades, book deltas/snapshots,
bars, session status, and settlement."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.enums import AssetClass, OrderSide, SessionStatus
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.market_events import (
    Bar,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Quote,
    SessionStatusEvent,
    SettlementEvent,
    Trade,
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


_BASE = {
    "instrument": None,
    "exchange_ts": 1_767_225_600_000_000_000,
    "receive_ts": 1_767_225_600_000_000_100,
    "sequence": 0,
}


def _base(**overrides: object) -> dict[str, object]:
    fields = dict(_BASE)
    fields["instrument"] = _instrument()
    fields.update(overrides)
    return fields


class TestQuote:
    def test_valid_two_sided(self) -> None:
        q = Quote(**_base(bid_price="2000.0", bid_size="1", ask_price="2000.1", ask_size="1"))
        assert q.bid_price is not None

    def test_valid_bid_only(self) -> None:
        q = Quote(**_base(bid_price="2000.0", bid_size="1", ask_price=None, ask_size=None))
        assert q.ask_price is None

    def test_rejects_neither_side_present(self) -> None:
        with pytest.raises(ValidationError):
            Quote(**_base(bid_price=None, bid_size=None, ask_price=None, ask_size=None))

    def test_rejects_receive_before_exchange(self) -> None:
        with pytest.raises(ValidationError):
            Quote(
                **_base(
                    bid_price="2000.0",
                    bid_size="1",
                    ask_price=None,
                    ask_size=None,
                    exchange_ts=200,
                    receive_ts=100,
                )
            )

    def test_rejects_price_without_size(self) -> None:
        with pytest.raises(ValidationError):
            Quote(**_base(bid_price="2000.0", bid_size=None, ask_price=None, ask_size=None))


class TestTrade:
    def test_valid(self) -> None:
        t = Trade(**_base(price="2000.5", size="1", aggressor_side=OrderSide.BUY))
        assert t.size == 1

    def test_rejects_non_positive_size(self) -> None:
        with pytest.raises(ValidationError):
            Trade(**_base(price="2000.5", size="0", aggressor_side=None))

    def test_aggressor_side_optional(self) -> None:
        t = Trade(**_base(price="2000.5", size="1", aggressor_side=None))
        assert t.aggressor_side is None


class TestBookDelta:
    def test_valid_add(self) -> None:
        d = BookDelta(**_base(side=OrderSide.BUY, price="2000.0", size="5", level=0, action="ADD"))
        assert d.action == "ADD"

    def test_delete_allows_zero_size(self) -> None:
        d = BookDelta(
            **_base(side=OrderSide.BUY, price="2000.0", size="0", level=0, action="DELETE")
        )
        assert d.size == 0

    def test_add_rejects_zero_size(self) -> None:
        with pytest.raises(ValidationError):
            BookDelta(**_base(side=OrderSide.BUY, price="2000.0", size="0", level=0, action="ADD"))

    def test_rejects_negative_size(self) -> None:
        with pytest.raises(ValidationError):
            BookDelta(
                **_base(side=OrderSide.BUY, price="2000.0", size="-1", level=0, action="UPDATE")
            )

    def test_rejects_invalid_action(self) -> None:
        with pytest.raises(ValidationError):
            BookDelta(
                **_base(side=OrderSide.BUY, price="2000.0", size="1", level=0, action="BOGUS")
            )


class TestBookSnapshot:
    def test_valid(self) -> None:
        snap = BookSnapshot(
            **_base(
                bids=[BookLevel(price="2000.0", size="5")],
                asks=[BookLevel(price="2000.1", size="3")],
            )
        )
        assert snap.bids[0].price == 2000

    def test_empty_book_allowed(self) -> None:
        snap = BookSnapshot(**_base(bids=[], asks=[]))
        assert snap.bids == []


class TestBar:
    def test_valid_ohlc(self) -> None:
        bar = Bar(
            **_base(
                open="10",
                high="12",
                low="9",
                close="11",
                volume="100",
                bar_open_ts=1_767_225_600_000_000_000,
                bar_close_ts=1_767_225_660_000_000_000,
            )
        )
        assert bar.high == 12

    def test_rejects_high_below_open(self) -> None:
        with pytest.raises(ValidationError):
            Bar(
                **_base(
                    open="15",
                    high="12",
                    low="9",
                    close="11",
                    volume="100",
                    bar_open_ts=1_767_225_600_000_000_000,
                    bar_close_ts=1_767_225_660_000_000_000,
                )
            )

    def test_rejects_low_above_close(self) -> None:
        with pytest.raises(ValidationError):
            Bar(
                **_base(
                    open="10",
                    high="12",
                    low="11.5",
                    close="11",
                    volume="100",
                    bar_open_ts=1_767_225_600_000_000_000,
                    bar_close_ts=1_767_225_660_000_000_000,
                )
            )

    def test_rejects_close_before_open_ts(self) -> None:
        with pytest.raises(ValidationError):
            Bar(
                **_base(
                    open="10",
                    high="12",
                    low="9",
                    close="11",
                    volume="100",
                    bar_open_ts=1_767_225_660_000_000_000,
                    bar_close_ts=1_767_225_600_000_000_000,
                )
            )

    def test_rejects_negative_volume(self) -> None:
        with pytest.raises(ValidationError):
            Bar(
                **_base(
                    open="10",
                    high="12",
                    low="9",
                    close="11",
                    volume="-1",
                    bar_open_ts=1_767_225_600_000_000_000,
                    bar_close_ts=1_767_225_660_000_000_000,
                )
            )


class TestSessionStatusEvent:
    def test_valid(self) -> None:
        e = SessionStatusEvent(**_base(status=SessionStatus.OPEN))
        assert e.status == SessionStatus.OPEN


class TestSettlementEvent:
    def test_valid(self) -> None:
        e = SettlementEvent(**_base(settlement_price="2001.3"))
        assert e.settlement_price == Decimal("2001.3")

    def test_rejects_non_positive_settlement_price(self) -> None:
        with pytest.raises(ValidationError):
            SettlementEvent(**_base(settlement_price="0"))
