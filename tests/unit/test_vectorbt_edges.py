from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from tests.unit.test_vectorbt_models import request_payload
from trading_engine_conformance.adapters.vectorbt.benchmark import (
    BenchmarkPass,
    run_benchmark,
)
from trading_engine_conformance.adapters.vectorbt.errors import VectorbtLedgerError
from trading_engine_conformance.adapters.vectorbt.ledger import build_ledger, verify_ledger
from trading_engine_conformance.adapters.vectorbt.metrics import (
    build_execution_plan,
    recompute_metrics,
)
from trading_engine_conformance.adapters.vectorbt.models import (
    DevelopmentPartition,
    ScreeningCosts,
    ScreeningDataset,
    ScreeningEvent,
    ScreeningMetrics,
    ScreeningRequest,
    SignalDecision,
    TrialResult,
    TrialVariant,
)


def _request() -> ScreeningRequest:
    return ScreeningRequest.model_validate(request_payload(), strict=False)


def _data() -> ScreeningDataset:
    return ScreeningDataset(
        dataset_id="development-bars",
        partition_id="development-only",
        events=[
            ScreeningEvent(event_ts=100, price="100"),
            ScreeningEvent(event_ts=200, price="110"),
            ScreeningEvent(event_ts=300, price="120"),
            ScreeningEvent(event_ts=400, price="130"),
        ],
    )


def test_model_edge_validators() -> None:
    with pytest.raises(ValidationError, match="end_ts"):
        DevelopmentPartition(partition_id="x", start_ts=2, end_ts=1, event_count=1)
    with pytest.raises(ValidationError, match="less than one"):
        ScreeningCosts(
            initial_cash="1",
            order_size="1",
            fee_rate="0",
            fixed_fee="0",
            slippage_rate="1",
        )
    with pytest.raises(ValidationError, match="available"):
        SignalDecision(
            computed_at_ts=2,
            available_at_ts=1,
            execution_ts=3,
            action="enter_long",
        )
    with pytest.raises(ValidationError, match="duplicate"):
        TrialVariant(
            trial_id="x",
            parameters={},
            signals=[
                SignalDecision(
                    computed_at_ts=100,
                    available_at_ts=100,
                    execution_ts=200,
                    action="enter_long",
                ),
                SignalDecision(
                    computed_at_ts=100,
                    available_at_ts=100,
                    execution_ts=200,
                    action="exit_long",
                ),
            ],
        )
    with pytest.raises(ValidationError, match="strictly increasing"):
        ScreeningDataset(
            dataset_id="x",
            partition_id="x",
            events=[
                ScreeningEvent(event_ts=2, price="1"),
                ScreeningEvent(event_ts=1, price="1"),
            ],
        )
    with pytest.raises(ValidationError, match="positive"):
        ScreeningEvent(event_ts=1, price="0")


def test_execution_plan_and_metric_state_errors() -> None:
    missing_compute = TrialVariant(
        trial_id="bad-compute",
        parameters={},
        signals=[
            SignalDecision(
                computed_at_ts=150,
                available_at_ts=150,
                execution_ts=200,
                action="enter_long",
            )
        ],
    )
    with pytest.raises(ValueError, match="computed_at_ts"):
        build_execution_plan(_data(), missing_compute)

    no_future = TrialVariant(
        trial_id="bad-future",
        parameters={},
        signals=[
            SignalDecision(
                computed_at_ts=400,
                available_at_ts=400,
                execution_ts=500,
                action="enter_long",
            )
        ],
    )
    with pytest.raises(ValueError, match="no event"):
        build_execution_plan(_data(), no_future)

    enter_twice = TrialVariant(
        trial_id="enter-twice",
        parameters={},
        signals=[
            SignalDecision(
                computed_at_ts=100, available_at_ts=100, execution_ts=200, action="enter_long"
            ),
            SignalDecision(
                computed_at_ts=200, available_at_ts=200, execution_ts=300, action="enter_long"
            ),
        ],
    )
    with pytest.raises(ValueError, match="already long"):
        recompute_metrics(_data(), enter_twice, _request().costs)

    exit_flat = TrialVariant(
        trial_id="exit-flat",
        parameters={},
        signals=[
            SignalDecision(
                computed_at_ts=100, available_at_ts=100, execution_ts=200, action="exit_long"
            )
        ],
    )
    with pytest.raises(ValueError, match="flat"):
        recompute_metrics(_data(), exit_flat, _request().costs)

    poor = _request().costs.model_copy(update={"initial_cash": _request().costs.order_size})
    with pytest.raises(ValueError, match="insufficient"):
        recompute_metrics(_data(), _request().variants[0], poor)


def test_ledger_detects_identity_cost_parameter_shape_and_digest_tamper() -> None:
    request = _request()
    metrics = ScreeningMetrics(
        final_equity="10000",
        net_profit="0",
        total_return="0",
        baseline_return="0",
        turnover="0",
        max_drawdown="0",
        total_cost="0",
        trade_count=0,
    )
    results = [
        TrialResult.completed(variant, request.costs, metrics) for variant in request.variants
    ]
    ledger = build_ledger(request, results)
    mutations = [
        ledger.model_copy(update={"family_id": "wrong"}),
        ledger.model_copy(update={"emitted_trial_count": 1}),
        ledger.model_copy(update={"declared_total_trial_budget": 3}),
        ledger.model_copy(
            update={
                "trials": [
                    ledger.trials[0].model_copy(update={"parameters": {"changed": True}}),
                    ledger.trials[1],
                ]
            }
        ),
        ledger.model_copy(
            update={
                "trials": [
                    ledger.trials[0].model_copy(
                        update={"costs": request.costs.model_copy(update={"fixed_fee": 9})}
                    ),
                    ledger.trials[1],
                ]
            }
        ),
        ledger.model_copy(update={"semantic_digest": "f" * 64}),
    ]
    for changed in mutations:
        with pytest.raises(VectorbtLedgerError):
            verify_ledger(request, changed)


def test_benchmark_outer_gate_determinism_threshold_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = BenchmarkPass(
        rows=5_000,
        strategies=400,
        strategy_cells=2_000_000,
        elapsed_seconds=0.1,
        semantic_digest="a" * 64,
        finite_outputs=400,
        estimated_array_bytes=20_000_000,
        peak_traced_bytes=10_000,
    )
    monkeypatch.setattr(
        "trading_engine_conformance.adapters.vectorbt.benchmark._one_pass", lambda *_args: base
    )
    assert run_benchmark()["ok"] is True

    changed = replace(base, semantic_digest="b" * 64)
    calls = iter((base, changed))
    monkeypatch.setattr(
        "trading_engine_conformance.adapters.vectorbt.benchmark._one_pass",
        lambda *_args: next(calls),
    )
    result = run_benchmark()
    assert result["ok"] is False
    assert result["deterministic"] is False

    with pytest.raises(ValueError, match="2,000,000"):
        run_benchmark(rows=1, strategies=1)
