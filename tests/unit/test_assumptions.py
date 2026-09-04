"""Unit tests for ExecutionAssumptions: every cost/behavior policy is
explicit -- no silent defaults."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.assumptions import ExecutionAssumptions


def _make(**overrides: object) -> ExecutionAssumptions:
    fields: dict[str, object] = {
        "fee_model": "fixed-per-contract",
        "fee_rate": "2.50",
        "spread_model": "fixed-half-tick",
        "slippage_model": "none",
        "latency_ns": 0,
        "queue_model": "fifo",
        "partial_fill_policy": "preserve-residual",
        "margin_model": "reg-t",
        "session_policy": "cme-globex",
        "settlement_policy": "daily-mark",
        "roll_policy": "manual-only",
    }
    fields.update(overrides)
    return ExecutionAssumptions(**fields)  # type: ignore[arg-type]


class TestExecutionAssumptions:
    def test_valid(self) -> None:
        assumptions = _make()
        assert assumptions.fee_model == "fixed-per-contract"

    def test_rejects_empty_fee_model(self) -> None:
        with pytest.raises(ValidationError):
            _make(fee_model="")

    def test_rejects_empty_spread_model(self) -> None:
        with pytest.raises(ValidationError):
            _make(spread_model="")

    def test_rejects_empty_slippage_model(self) -> None:
        with pytest.raises(ValidationError):
            _make(slippage_model="")

    def test_rejects_negative_latency(self) -> None:
        with pytest.raises(ValidationError):
            _make(latency_ns=-1)

    def test_rejects_empty_queue_model(self) -> None:
        with pytest.raises(ValidationError):
            _make(queue_model="")

    def test_rejects_empty_partial_fill_policy(self) -> None:
        with pytest.raises(ValidationError):
            _make(partial_fill_policy="")

    def test_rejects_empty_margin_model(self) -> None:
        with pytest.raises(ValidationError):
            _make(margin_model="")

    def test_rejects_empty_session_policy(self) -> None:
        with pytest.raises(ValidationError):
            _make(session_policy="")

    def test_rejects_empty_settlement_policy(self) -> None:
        with pytest.raises(ValidationError):
            _make(settlement_policy="")

    def test_rejects_empty_roll_policy(self) -> None:
        with pytest.raises(ValidationError):
            _make(roll_policy="")

    def test_rejects_negative_fee_rate(self) -> None:
        with pytest.raises(ValidationError):
            _make(fee_rate="-1")
