"""Typed request, dataset, metric, and ledger models for stage-zero screening."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.hashing import sha256_bytes
from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.dataset import DatasetIdentity
from trading_engine_conformance.schema.enums import HoldoutAccessState
from trading_engine_conformance.schema.holdout import HoldoutState
from trading_engine_conformance.schema.types import EconomicDecimal, Sha256Hex, UtcNanos

EligibilityLabel = Literal["eligible_for_independent_reimplementation"]
ParameterValue = str | int | bool | None


class DevelopmentPartition(StrictBaseModel):
    """The only partition this adapter can receive or inspect."""

    partition_id: str = Field(min_length=1)
    start_ts: UtcNanos
    end_ts: UtcNanos
    event_count: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> DevelopmentPartition:
        if self.end_ts < self.start_ts:
            raise ValueError("development partition end_ts must not precede start_ts")
        return self


class ScreeningCosts(StrictBaseModel):
    """Mandatory economics. There are intentionally no defaults."""

    initial_cash: EconomicDecimal
    order_size: EconomicDecimal
    fee_rate: EconomicDecimal
    fixed_fee: EconomicDecimal
    slippage_rate: EconomicDecimal

    @model_validator(mode="after")
    def _valid_costs(self) -> ScreeningCosts:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be strictly positive")
        if self.order_size <= 0:
            raise ValueError("order_size must be strictly positive")
        for name in ("fee_rate", "fixed_fee", "slippage_rate"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        if self.slippage_rate >= 1:
            raise ValueError("slippage_rate must be less than one")
        return self


class ScreeningAssumptions(StrictBaseModel):
    """The complete fixed semantic profile accepted by the worker."""

    price_model: Literal["next_event_close"]
    position_model: Literal["long_only_fixed_size"]
    fee_model: Literal["proportional_plus_fixed"]
    slippage_model: Literal["adverse_proportional"]
    ranking_metric: Literal["development_total_return"]


class SignalDecision(StrictBaseModel):
    """A causal signal and its separately declared execution boundary."""

    computed_at_ts: UtcNanos
    available_at_ts: UtcNanos
    execution_ts: UtcNanos
    action: Literal["enter_long", "exit_long"]

    @model_validator(mode="after")
    def _strict_lag(self) -> SignalDecision:
        if self.available_at_ts < self.computed_at_ts:
            raise ValueError("signal cannot be available before it is computed")
        if self.execution_ts <= self.available_at_ts:
            raise ValueError(
                "same-bar execution is forbidden; execution must be after availability"
            )
        return self


class TrialVariant(StrictBaseModel):
    trial_id: str = Field(min_length=1)
    parameters: dict[str, ParameterValue]
    signals: list[SignalDecision]

    @model_validator(mode="after")
    def _unique_signal_boundaries(self) -> TrialVariant:
        execution_times = [signal.execution_ts for signal in self.signals]
        if len(execution_times) != len(set(execution_times)):
            raise ValueError("duplicate signal execution timestamp within trial")
        return self


class ScreeningEvent(StrictBaseModel):
    event_ts: UtcNanos
    price: EconomicDecimal

    @model_validator(mode="after")
    def _positive_price(self) -> ScreeningEvent:
        if self.price <= 0:
            raise ValueError("event price must be strictly positive")
        return self


class ScreeningDataset(StrictBaseModel):
    """Development events only; no holdout-shaped field exists."""

    dataset_id: str = Field(min_length=1)
    partition_id: str = Field(min_length=1)
    events: list[ScreeningEvent] = Field(min_length=1)

    @model_validator(mode="after")
    def _strict_event_order(self) -> ScreeningDataset:
        timestamps = [event.event_ts for event in self.events]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("dataset event timestamps must be unique and strictly increasing")
        return self


class ScreeningRequest(StrictBaseModel):
    """Immutable preregistration for one bounded development-only family."""

    request_type: Literal["stage_zero_screen"]
    hypothesis_id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    dataset: DatasetIdentity
    development_partition: DevelopmentPartition
    declared_total_trial_budget: int = Field(gt=0)
    variants: list[TrialVariant] = Field(min_length=1)
    costs: ScreeningCosts
    assumptions: ScreeningAssumptions
    holdout_state: HoldoutState
    seed: int = Field(ge=0, le=2**32 - 1)
    engine: Literal["numba"]
    engine_label: Literal["vectorbt_stage_zero_non_execution"]
    output_label: EligibilityLabel

    @model_validator(mode="after")
    def _closed_complete_family(self) -> ScreeningRequest:
        if self.holdout_state.state is not HoldoutAccessState.SEALED:
            raise ValueError("holdout_state must remain sealed")
        if self.holdout_state.opened_ts is not None:
            raise ValueError("sealed holdout cannot have an opened timestamp")
        if self.declared_total_trial_budget != len(self.variants):
            raise ValueError("declared total trial budget must equal the complete variant count")
        trial_ids = [variant.trial_id for variant in self.variants]
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("duplicate trial_id in declared family")
        return self


class ScreeningMetrics(StrictBaseModel):
    """Metrics independently recomputed without trusting vectorbt analytics."""

    final_equity: EconomicDecimal
    net_profit: EconomicDecimal
    total_return: EconomicDecimal
    baseline_return: EconomicDecimal
    turnover: EconomicDecimal
    max_drawdown: EconomicDecimal
    total_cost: EconomicDecimal
    trade_count: int = Field(ge=0)


class TrialResult(StrictBaseModel):
    trial_id: str = Field(min_length=1)
    parameters: dict[str, ParameterValue]
    status: Literal["completed", "failed"]
    metrics: ScreeningMetrics | None
    costs: ScreeningCosts
    rank: int | None = Field(default=None, ge=1)
    output_label: EligibilityLabel | None
    semantic_digest: Sha256Hex
    reason: str

    @staticmethod
    def _digest_payload(
        *,
        trial_id: str,
        parameters: dict[str, ParameterValue],
        status: str,
        metrics: ScreeningMetrics | None,
        costs: ScreeningCosts,
        output_label: str | None,
        reason: str,
    ) -> dict[str, object]:
        return {
            "trial_id": trial_id,
            "parameters": parameters,
            "status": status,
            "metrics": metrics.model_dump(mode="json") if metrics is not None else None,
            "costs": costs.model_dump(mode="json"),
            "output_label": output_label,
            "reason": reason,
        }

    @classmethod
    def completed(
        cls, variant: TrialVariant, costs: ScreeningCosts, metrics: ScreeningMetrics
    ) -> TrialResult:
        label: EligibilityLabel = "eligible_for_independent_reimplementation"
        reason = "completed development-only approximate screen"
        payload = cls._digest_payload(
            trial_id=variant.trial_id,
            parameters=variant.parameters,
            status="completed",
            metrics=metrics,
            costs=costs,
            output_label=label,
            reason=reason,
        )
        return cls(
            trial_id=variant.trial_id,
            parameters=variant.parameters,
            status="completed",
            metrics=metrics,
            costs=costs,
            output_label=label,
            reason=reason,
            semantic_digest=sha256_bytes(canonical_json_bytes(payload)),
            rank=None,
        )

    @classmethod
    def failed(cls, variant: TrialVariant, costs: ScreeningCosts, reason: str) -> TrialResult:
        payload = cls._digest_payload(
            trial_id=variant.trial_id,
            parameters=variant.parameters,
            status="failed",
            metrics=None,
            costs=costs,
            output_label=None,
            reason=reason,
        )
        return cls(
            trial_id=variant.trial_id,
            parameters=variant.parameters,
            status="failed",
            metrics=None,
            costs=costs,
            output_label=None,
            reason=reason,
            semantic_digest=sha256_bytes(canonical_json_bytes(payload)),
            rank=None,
        )


class ScreeningLedger(StrictBaseModel):
    hypothesis_id: str
    family_id: str
    dataset_sha256: Sha256Hex
    development_partition_id: str
    holdout_state: Literal["SEALED"]
    declared_total_trial_budget: int = Field(gt=0)
    emitted_trial_count: int = Field(gt=0)
    engine: Literal["numba"]
    engine_label: Literal["vectorbt_stage_zero_non_execution"]
    ranking_scope: Literal["development_only"]
    trials: list[TrialResult]
    semantic_digest: Sha256Hex
    execution_authorized: Literal[False] = False
    profitability_claimed: Literal[False] = False
    holdout_evaluated: Literal[False] = False
    paper_ready: Literal[False] = False
    live_ready: Literal[False] = False
    promotion_authorized: Literal[False] = False


class LedgerVerificationReceipt(StrictBaseModel):
    ok: bool
    declared_trial_count: int = Field(ge=0)
    emitted_trial_count: int = Field(ge=0)
    duplicate_trial_ids: list[str]
    missing_trial_ids: list[str]
    unexpected_trial_ids: list[str]
    semantic_digest: Sha256Hex
