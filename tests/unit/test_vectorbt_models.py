from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_engine_conformance.adapters.vectorbt.models import (
    DevelopmentPartition,
    ScreeningAssumptions,
    ScreeningCosts,
    ScreeningDataset,
    ScreeningEvent,
    ScreeningRequest,
    SignalDecision,
    TrialVariant,
)
from trading_engine_conformance.schema.dataset import DatasetIdentity
from trading_engine_conformance.schema.enums import HoldoutAccessState
from trading_engine_conformance.schema.holdout import HoldoutState


def request_payload() -> dict[str, object]:
    return {
        "request_type": "stage_zero_screen",
        "hypothesis_id": "hypothesis-momentum",
        "family_id": "family-001",
        "dataset": {
            "dataset_id": "development-bars",
            "relative_path": "development.json",
            "byte_size": 123,
            "sha256": "a" * 64,
        },
        "development_partition": {
            "partition_id": "development-only",
            "start_ts": 100,
            "end_ts": 400,
            "event_count": 4,
        },
        "declared_total_trial_budget": 2,
        "variants": [
            {
                "trial_id": "trial-a",
                "parameters": {"lookback": 2, "threshold": "0.1"},
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
            },
            {
                "trial_id": "trial-b",
                "parameters": {"lookback": 3, "threshold": "0.2"},
                "signals": [],
            },
        ],
        "costs": {
            "initial_cash": "10000",
            "order_size": "1",
            "fee_rate": "0.001",
            "fixed_fee": "1",
            "slippage_rate": "0.002",
        },
        "assumptions": {
            "price_model": "next_event_close",
            "position_model": "long_only_fixed_size",
            "fee_model": "proportional_plus_fixed",
            "slippage_model": "adverse_proportional",
            "ranking_metric": "development_total_return",
        },
        "holdout_state": {"state": "SEALED", "sealed_ts": 1, "opened_ts": None},
        "seed": 42,
        "engine": "numba",
        "engine_label": "vectorbt_stage_zero_non_execution",
        "output_label": "eligible_for_independent_reimplementation",
    }


def test_screening_request_is_typed_frozen_and_complete() -> None:
    request = ScreeningRequest.model_validate(request_payload(), strict=False)
    assert request.dataset.sha256 == "a" * 64
    assert request.declared_total_trial_budget == len(request.variants)
    assert request.engine == "numba"
    assert request.holdout_state.state is HoldoutAccessState.SEALED
    with pytest.raises(ValidationError):
        request.seed = 7  # type: ignore[misc]


@pytest.mark.parametrize(
    "missing",
    ["initial_cash", "order_size", "fee_rate", "fixed_fee", "slippage_rate"],
)
def test_every_cost_field_is_mandatory(missing: str) -> None:
    raw = request_payload()
    costs = copy.deepcopy(raw["costs"])
    assert isinstance(costs, dict)
    costs.pop(missing)
    raw["costs"] = costs
    with pytest.raises(ValidationError):
        ScreeningRequest.model_validate(raw, strict=False)


@pytest.mark.parametrize("engine", ["auto", "rust"])
def test_request_rejects_auto_and_rust_engines(engine: str) -> None:
    raw = request_payload()
    raw["engine"] = engine
    with pytest.raises(ValidationError, match="numba"):
        ScreeningRequest.model_validate(raw, strict=False)


def test_holdout_must_remain_sealed_and_holdout_data_is_forbidden() -> None:
    raw = request_payload()
    raw["holdout_state"] = {"state": "OPENED", "sealed_ts": 1, "opened_ts": 2}
    with pytest.raises(ValidationError, match="sealed"):
        ScreeningRequest.model_validate(raw, strict=False)

    raw = request_payload()
    raw["holdout_data"] = [1, 2, 3]
    with pytest.raises(ValidationError, match="Extra inputs"):
        ScreeningRequest.model_validate(raw, strict=False)


def test_budget_and_trial_identity_must_match_complete_declared_family() -> None:
    raw = request_payload()
    raw["declared_total_trial_budget"] = 3
    with pytest.raises(ValidationError, match="budget"):
        ScreeningRequest.model_validate(raw, strict=False)

    raw = request_payload()
    variants = copy.deepcopy(raw["variants"])
    assert isinstance(variants, list) and isinstance(variants[1], dict)
    variants[1]["trial_id"] = "trial-a"
    raw["variants"] = variants
    with pytest.raises(ValidationError, match="duplicate"):
        ScreeningRequest.model_validate(raw, strict=False)


def test_signal_timestamps_are_explicit_and_strictly_lagged() -> None:
    raw = request_payload()
    variants = copy.deepcopy(raw["variants"])
    assert isinstance(variants, list) and isinstance(variants[0], dict)
    signals = variants[0]["signals"]
    assert isinstance(signals, list) and isinstance(signals[0], dict)
    signals[0]["execution_ts"] = 100
    raw["variants"] = variants
    with pytest.raises(ValidationError, match=r"same-bar|after"):
        ScreeningRequest.model_validate(raw, strict=False)

    with pytest.raises(ValidationError):
        SignalDecision.model_validate({"action": "enter_long"})


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_dataset_rejects_non_finite_prices(bad: str) -> None:
    with pytest.raises(ValidationError, match="finite"):
        ScreeningDataset(
            dataset_id="development-bars",
            partition_id="development-only",
            events=[ScreeningEvent(event_ts=1, price=bad)],
        )


def test_models_have_no_implicit_screening_assumptions() -> None:
    with pytest.raises(ValidationError):
        ScreeningCosts.model_validate({})
    with pytest.raises(ValidationError):
        ScreeningAssumptions.model_validate({})
    with pytest.raises(ValidationError):
        DevelopmentPartition.model_validate({})
    with pytest.raises(ValidationError):
        TrialVariant.model_validate({})
    with pytest.raises(ValidationError):
        DatasetIdentity.model_validate({})
    with pytest.raises(ValidationError):
        HoldoutState.model_validate({})


def test_costs_reject_negative_values_and_zero_capital_or_size() -> None:
    common = {
        "initial_cash": "10000",
        "order_size": "1",
        "fee_rate": "0",
        "fixed_fee": "0",
        "slippage_rate": "0",
    }
    for field, bad in (
        ("initial_cash", "0"),
        ("order_size", "0"),
        ("fee_rate", "-0.1"),
        ("fixed_fee", "-1"),
        ("slippage_rate", "-0.1"),
    ):
        values = {**common, field: bad}
        with pytest.raises(ValidationError):
            ScreeningCosts.model_validate(values)
    assert ScreeningCosts.model_validate(common).fee_rate == Decimal("0")
