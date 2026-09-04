from __future__ import annotations

from decimal import Decimal

import pytest

from tests.unit.test_vectorbt_models import request_payload
from trading_engine_conformance.adapters.vectorbt.errors import VectorbtLedgerError
from trading_engine_conformance.adapters.vectorbt.ledger import (
    build_ledger,
    verify_ledger,
)
from trading_engine_conformance.adapters.vectorbt.metrics import (
    build_execution_plan,
    recompute_metrics,
)
from trading_engine_conformance.adapters.vectorbt.models import (
    ScreeningCosts,
    ScreeningDataset,
    ScreeningEvent,
    ScreeningMetrics,
    ScreeningRequest,
    TrialResult,
    TrialVariant,
)


def _dataset(*prices: str) -> ScreeningDataset:
    return ScreeningDataset(
        dataset_id="development-bars",
        partition_id="development-only",
        events=[
            ScreeningEvent(event_ts=(index + 1) * 100, price=price)
            for index, price in enumerate(prices)
        ],
    )


def _request() -> ScreeningRequest:
    return ScreeningRequest.model_validate(request_payload(), strict=False)


def test_next_declared_event_is_the_only_accepted_execution_boundary() -> None:
    request = _request()
    plan = build_execution_plan(_dataset("100", "110", "120", "130"), request.variants[0])
    assert [(item.execution_ts, item.action) for item in plan] == [
        (200, "enter_long"),
        (400, "exit_long"),
    ]

    bad = TrialVariant.model_validate(
        {
            "trial_id": "bad",
            "parameters": {},
            "signals": [
                {
                    "computed_at_ts": 100,
                    "available_at_ts": 100,
                    "execution_ts": 300,
                    "action": "enter_long",
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="next declared event"):
        build_execution_plan(_dataset("100", "110", "120", "130"), bad)


def test_future_price_mutation_cannot_change_earlier_decisions() -> None:
    request = _request()
    original = _dataset("100", "110", "120", "130")
    mutated = _dataset("100", "110", "999", "0.01")
    original_plan = build_execution_plan(original, request.variants[0])
    mutated_plan = build_execution_plan(mutated, request.variants[0])
    cutoff = 250
    assert [x for x in original_plan if x.execution_ts < cutoff] == [
        x for x in mutated_plan if x.execution_ts < cutoff
    ]


def test_independent_fee_slippage_turnover_drawdown_and_baseline_oracle() -> None:
    costs = ScreeningCosts(
        initial_cash="1000",
        order_size="2",
        fee_rate="0.01",
        fixed_fee="1",
        slippage_rate="0.10",
    )
    variant = TrialVariant.model_validate(
        {
            "trial_id": "fixture",
            "parameters": {},
            "signals": [
                {
                    "computed_at_ts": 100,
                    "available_at_ts": 100,
                    "execution_ts": 200,
                    "action": "enter_long",
                },
                {
                    "computed_at_ts": 300,
                    "available_at_ts": 300,
                    "execution_ts": 400,
                    "action": "exit_long",
                },
            ],
        }
    )
    data = _dataset("100", "100", "80", "120")
    metrics = recompute_metrics(data, variant, costs)

    # Buy 2 at 110 and sell 2 at 108. Fees are 3.20 and 3.16.
    assert metrics.final_equity == Decimal("989.64")
    assert metrics.net_profit == Decimal("-10.36")
    assert metrics.total_cost == Decimal("50.36")
    assert metrics.turnover == Decimal("0.436")
    assert metrics.max_drawdown == Decimal("0.0632")
    assert metrics.trade_count == 2
    assert metrics.baseline_return == Decimal("0.2")


def test_duplicate_missing_or_budget_mismatched_ledgers_fail() -> None:
    request = _request()
    metrics = ScreeningMetrics(
        final_equity="10000",
        net_profit="0",
        total_return="0",
        baseline_return="0.3",
        turnover="0",
        max_drawdown="0",
        total_cost="0",
        trade_count=0,
    )
    results = [
        TrialResult.completed(request.variants[0], request.costs, metrics),
        TrialResult.completed(request.variants[1], request.costs, metrics),
    ]
    ledger = build_ledger(request, results)
    receipt = verify_ledger(request, ledger)
    assert receipt.ok
    assert receipt.emitted_trial_count == 2
    assert [item.rank for item in ledger.trials] == [1, 2]
    assert all(
        item.output_label == "eligible_for_independent_reimplementation" for item in ledger.trials
    )

    missing = ledger.model_copy(update={"trials": ledger.trials[:1]})
    with pytest.raises(VectorbtLedgerError, match=r"missing|budget"):
        verify_ledger(request, missing)
    duplicate = ledger.model_copy(update={"trials": [ledger.trials[0], ledger.trials[0]]})
    with pytest.raises(VectorbtLedgerError, match=r"duplicate|missing"):
        verify_ledger(request, duplicate)


def test_failed_trials_are_emitted_and_digest_is_reproducible() -> None:
    request = _request()
    failed = TrialResult.failed(request.variants[0], request.costs, "engine rejected fixture")
    empty_metrics = recompute_metrics(
        _dataset("100", "110", "120", "130"), request.variants[1], request.costs
    )
    completed = TrialResult.completed(request.variants[1], request.costs, empty_metrics)
    first = build_ledger(request, [failed, completed])
    second = build_ledger(request, [failed, completed])
    assert first.semantic_digest == second.semantic_digest
    failed_result = next(item for item in first.trials if item.status == "failed")
    assert failed_result.reason == "engine rejected fixture"
    assert verify_ledger(request, first).ok


def test_metrics_and_ledger_reject_non_finite_values() -> None:
    with pytest.raises(ValueError):
        ScreeningMetrics(
            final_equity="NaN",
            net_profit="0",
            total_return="0",
            baseline_return="0",
            turnover="0",
            max_drawdown="0",
            total_cost="0",
            trade_count=0,
        )
