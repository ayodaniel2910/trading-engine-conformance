"""Market event models: quote, trade, order-book delta/snapshot, bar,
session status, and settlement.

Every event carries an exchange timestamp, a receive timestamp (never
earlier than the exchange timestamp), the instrument it applies to, and a
stream-position ``sequence`` used for deterministic ordering (see
``trading_engine_conformance.ordering``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.enums import OrderSide, SessionStatus
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.types import EconomicDecimal, SequenceNo, UtcNanos


class MarketEventBase(StrictBaseModel):
    instrument: InstrumentIdentity
    exchange_ts: UtcNanos
    receive_ts: UtcNanos
    sequence: SequenceNo

    @model_validator(mode="after")
    def _check_receive_not_before_exchange(self) -> MarketEventBase:
        if self.receive_ts < self.exchange_ts:
            raise ValueError("receive_ts must not be earlier than exchange_ts")
        return self


class Quote(MarketEventBase):
    bid_price: EconomicDecimal | None = None
    bid_size: EconomicDecimal | None = None
    ask_price: EconomicDecimal | None = None
    ask_size: EconomicDecimal | None = None

    @model_validator(mode="after")
    def _check_at_least_one_side_and_paired_price_size(self) -> Quote:
        if self.bid_price is None and self.ask_price is None:
            raise ValueError("a quote must have at least one of bid_price/ask_price present")
        if (self.bid_price is None) != (self.bid_size is None):
            raise ValueError("bid_price and bid_size must both be present or both be absent")
        if (self.ask_price is None) != (self.ask_size is None):
            raise ValueError("ask_price and ask_size must both be present or both be absent")
        return self


class Trade(MarketEventBase):
    price: EconomicDecimal
    size: EconomicDecimal
    aggressor_side: OrderSide | None = None

    @model_validator(mode="after")
    def _check_positive(self) -> Trade:
        if self.price <= 0:
            raise ValueError("trade price must be strictly positive")
        if self.size <= 0:
            raise ValueError("trade size must be strictly positive")
        return self


BookDeltaAction = Literal["ADD", "UPDATE", "DELETE"]


class BookDelta(MarketEventBase):
    side: OrderSide
    price: EconomicDecimal
    size: EconomicDecimal
    level: int = Field(ge=0)
    action: BookDeltaAction

    @model_validator(mode="after")
    def _check_size_bounds(self) -> BookDelta:
        if self.size < 0:
            raise ValueError("book delta size must not be negative")
        if self.action != "DELETE" and self.size == 0:
            raise ValueError("only a DELETE action may carry zero size")
        return self


class BookLevel(StrictBaseModel):
    price: EconomicDecimal
    size: EconomicDecimal

    @model_validator(mode="after")
    def _check_non_negative(self) -> BookLevel:
        if self.price <= 0:
            raise ValueError("book level price must be strictly positive")
        if self.size < 0:
            raise ValueError("book level size must not be negative")
        return self


class BookSnapshot(MarketEventBase):
    bids: list[BookLevel]
    asks: list[BookLevel]


class Bar(MarketEventBase):
    open: EconomicDecimal
    high: EconomicDecimal
    low: EconomicDecimal
    close: EconomicDecimal
    volume: EconomicDecimal
    bar_open_ts: UtcNanos
    bar_close_ts: UtcNanos

    @model_validator(mode="after")
    def _check_ohlc_consistency(self) -> Bar:
        if self.high < self.open or self.high < self.close or self.high < self.low:
            raise ValueError("high must be the maximum of open/high/low/close")
        if self.low > self.open or self.low > self.close or self.low > self.high:
            raise ValueError("low must be the minimum of open/high/low/close")
        if self.volume < 0:
            raise ValueError("volume must not be negative")
        if self.bar_close_ts < self.bar_open_ts:
            raise ValueError("bar_close_ts must not be earlier than bar_open_ts")
        return self


class SessionStatusEvent(MarketEventBase):
    status: SessionStatus


class SettlementEvent(MarketEventBase):
    settlement_price: EconomicDecimal

    @model_validator(mode="after")
    def _check_positive_settlement_price(self) -> SettlementEvent:
        if self.settlement_price <= 0:
            raise ValueError("settlement_price must be strictly positive")
        return self


MarketEvent = Quote | Trade | BookDelta | BookSnapshot | Bar | SessionStatusEvent | SettlementEvent
