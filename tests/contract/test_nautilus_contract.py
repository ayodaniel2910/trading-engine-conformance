from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _integration_python() -> Path:
    value = os.environ.get("TEC_NAUTILUS_INTEGRATION_PYTHON")
    if not value:
        pytest.skip("set TEC_NAUTILUS_INTEGRATION_PYTHON for pinned-wheel contract tests")
    path = Path(value)
    if not path.is_file():
        pytest.skip("configured Nautilus integration Python does not exist")
    return path


@pytest.mark.integration
def test_real_v1231_instrument_trade_quote_delta_order_round_trips() -> None:
    python = _integration_python()
    script = r"""
import json
from decimal import Decimal
from trading_engine_conformance.adapters.nautilus.profile import NautilusResearchProfile
from trading_engine_conformance.adapters.nautilus.translators import (
    from_nautilus_book_delta, from_nautilus_instrument, from_nautilus_order,
    from_nautilus_fill, from_nautilus_ledger, from_nautilus_quote, from_nautilus_trade,
    to_nautilus_book_delta, to_nautilus_fill, to_nautilus_instrument,
    to_nautilus_ledger, to_nautilus_order, to_nautilus_quote, to_nautilus_trade,
)
from trading_engine_conformance.schema.enums import (
    AssetClass, LiquidityFlag, OrderSide, OrderType, TimeInForce,
)
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.ledger import (
    CashSnapshot, LedgerSnapshot, MarginSnapshot, PnLSnapshot, PositionSnapshot,
)
from trading_engine_conformance.schema.market_events import BookDelta, Quote, Trade
from trading_engine_conformance.schema.orders import OrderIntent
i=InstrumentIdentity(venue='GLBX',symbol='MGCZ26',asset_class=AssetClass.FUTURE,currency='USD',price_precision=1,size_precision=0,tick_size=Decimal('0.1'),tick_value=Decimal('1.0'),multiplier=Decimal('10'),expiry_ts=1800000000000000000,metadata_effective_ts=1700000000000000000,is_continuous=False)
p=NautilusResearchProfile(nautilus_asset_class='COMMODITY',underlying='MGC',lot_size='1',maker_fee_rate='0.001',taker_fee_rate='0.001',initial_margin_rate='0.05',maintenance_margin_rate='0.04',latency_ns=0,fill_model='L1_FINITE_TRADE',queue_model='NO_QUEUE_L1_DIAGNOSTIC',liquidity_consumption='FINITE_EVENT_SIZE',limit_fill_probability='1',slippage_probability='0',trade_execution=True,reject_stop_orders=False,session_timezone='America/Chicago',settlement_price='2000.0',random_seed=0)
t=Trade(instrument=i,exchange_ts=1700000000000000001,receive_ts=1700000000000000002,sequence=7,price=Decimal('2000.5'),size=Decimal('2'),aggressor_side=OrderSide.BUY)
q=Quote(instrument=i,exchange_ts=1700000000000000001,receive_ts=1700000000000000002,sequence=8,bid_price=Decimal('2000.4'),bid_size=Decimal('3'),ask_price=Decimal('2000.5'),ask_size=Decimal('4'))
d=BookDelta(instrument=i,exchange_ts=1700000000000000001,receive_ts=1700000000000000002,sequence=9,side=OrderSide.BUY,price=Decimal('2000.4'),size=Decimal('3'),level=11,action='ADD')
o=OrderIntent(order_id='order-1',instrument=i,side=OrderSide.BUY,order_type=OrderType.LIMIT,time_in_force=TimeInForce.GTC,quantity=Decimal('2'),limit_price=Decimal('2000.5'),created_ts=1700000000000000000,sequence=10)
f=Fill(fill_id='fill-1',order_id='order-1',instrument=i,side=OrderSide.BUY,price=Decimal('2000.5'),quantity=Decimal('2'),fee=Decimal('4.00'),ts=1700000000000000003,sequence=11,liquidity=LiquidityFlag.MAKER,provenance='contract-test')
l=LedgerSnapshot(cash=CashSnapshot(cash=Decimal('95995'),ts=1700000000000000003,sequence=12),positions=[PositionSnapshot(instrument=i,quantity=Decimal('2'),average_price=Decimal('2000.5'),ts=1700000000000000003,sequence=12)],margin=MarginSnapshot(used_margin=Decimal('1000'),available_margin=Decimal('94995'),ts=1700000000000000003,sequence=12),pnl=PnLSnapshot(realized_pnl=Decimal('0'),unrealized_pnl=Decimal('0'),ts=1700000000000000003,sequence=12),ts=1700000000000000003,sequence=12)
assert from_nautilus_instrument(to_nautilus_instrument(i,p)) == i
assert from_nautilus_trade(to_nautilus_trade(t),i) == t
assert from_nautilus_quote(to_nautilus_quote(q),i,sequence=8) == q
assert from_nautilus_book_delta(to_nautilus_book_delta(d),i) == d
assert from_nautilus_order(to_nautilus_order(o),i,sequence=10) == o
assert from_nautilus_fill(
    to_nautilus_fill(f,order_type=OrderType.LIMIT),i,sequence=11
) == f.model_copy(update={'provenance':'nautilus_trader_v1.231.0'})
assert from_nautilus_ledger(to_nautilus_ledger(l,maintenance_margin=Decimal('800')),i) == l
print(json.dumps({'ok': True}))
"""
    if sys.version_info[:2] == (3, 13):
        exec(script, {})  # noqa: S102 - fixed in-repository contract program
    else:
        completed = subprocess.run(  # noqa: S603
            [str(python), "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout)["ok"] is True
