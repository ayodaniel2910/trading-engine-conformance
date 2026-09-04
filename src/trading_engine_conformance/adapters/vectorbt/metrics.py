"""Causal plan construction and independent deterministic arithmetic oracles."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from trading_engine_conformance.adapters.vectorbt.models import (
    ScreeningCosts,
    ScreeningDataset,
    ScreeningMetrics,
    TrialVariant,
)


@dataclass(frozen=True)
class PlannedAction:
    computed_at_ts: int
    available_at_ts: int
    execution_ts: int
    action: Literal["enter_long", "exit_long"]


def build_execution_plan(dataset: ScreeningDataset, variant: TrialVariant) -> list[PlannedAction]:
    """Bind each signal to exactly the first declared event after availability."""
    timestamps = [event.event_ts for event in dataset.events]
    timestamp_set = set(timestamps)
    plan: list[PlannedAction] = []
    for signal in variant.signals:
        if signal.computed_at_ts not in timestamp_set:
            raise ValueError(
                f"trial {variant.trial_id}: computed_at_ts is not a declared data event"
            )
        next_index = bisect_right(timestamps, signal.available_at_ts)
        if next_index >= len(timestamps):
            raise ValueError(f"trial {variant.trial_id}: no event exists after signal availability")
        if timestamps[next_index] != signal.execution_ts:
            raise ValueError(
                f"trial {variant.trial_id}: execution_ts must be the next declared event"
            )
        plan.append(
            PlannedAction(
                computed_at_ts=signal.computed_at_ts,
                available_at_ts=signal.available_at_ts,
                execution_ts=signal.execution_ts,
                action=signal.action,
            )
        )
    return sorted(plan, key=lambda item: item.execution_ts)


def recompute_metrics(
    dataset: ScreeningDataset, variant: TrialVariant, costs: ScreeningCosts
) -> ScreeningMetrics:
    """Recompute a small fixed-size long-only ledger using exact decimals.

    This is authoritative for emitted metrics. vectorbt output is used only as
    a parity check against this intentionally small semantic surface.
    """
    plan = build_execution_plan(dataset, variant)
    actions = {item.execution_ts: item.action for item in plan}
    cash = costs.initial_cash
    position = Decimal(0)
    peak_equity = costs.initial_cash
    max_drawdown = Decimal(0)
    total_cost = Decimal(0)
    traded_notional = Decimal(0)
    trade_count = 0

    for event in dataset.events:
        action = actions.get(event.event_ts)
        if action == "enter_long":
            if position != 0:
                raise ValueError(f"trial {variant.trial_id}: enter_long while already long")
            execution_price = event.price * (Decimal(1) + costs.slippage_rate)
            notional = execution_price * costs.order_size
            fee = notional * costs.fee_rate + costs.fixed_fee
            if notional + fee > cash:
                raise ValueError(f"trial {variant.trial_id}: insufficient development cash")
            cash -= notional + fee
            position = costs.order_size
            total_cost += (execution_price - event.price) * costs.order_size + fee
            traded_notional += notional
            trade_count += 1
        elif action == "exit_long":
            if position == 0:
                raise ValueError(f"trial {variant.trial_id}: exit_long while flat")
            execution_price = event.price * (Decimal(1) - costs.slippage_rate)
            notional = execution_price * position
            fee = notional * costs.fee_rate + costs.fixed_fee
            cash += notional - fee
            total_cost += (event.price - execution_price) * position + fee
            traded_notional += notional
            position = Decimal(0)
            trade_count += 1

        equity = cash + position * event.price
        if equity > peak_equity:
            peak_equity = equity
        elif peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity)

    final_equity = cash + position * dataset.events[-1].price
    net_profit = final_equity - costs.initial_cash
    baseline_return = dataset.events[-1].price / dataset.events[0].price - Decimal(1)
    return ScreeningMetrics(
        final_equity=final_equity,
        net_profit=net_profit,
        total_return=net_profit / costs.initial_cash,
        baseline_return=baseline_return,
        turnover=traded_notional / costs.initial_cash,
        max_drawdown=max_drawdown,
        total_cost=total_cost,
        trade_count=trade_count,
    )
