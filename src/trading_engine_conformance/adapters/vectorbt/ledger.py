"""Complete-family ledger construction and semantic verification."""

from __future__ import annotations

from collections import Counter

from trading_engine_conformance.adapters.vectorbt.errors import VectorbtLedgerError
from trading_engine_conformance.adapters.vectorbt.models import (
    LedgerVerificationReceipt,
    ScreeningLedger,
    ScreeningRequest,
    TrialResult,
)
from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.hashing import sha256_bytes


def _trial_digest(trial: TrialResult) -> str:
    payload = TrialResult._digest_payload(
        trial_id=trial.trial_id,
        parameters=trial.parameters,
        status=trial.status,
        metrics=trial.metrics,
        costs=trial.costs,
        output_label=trial.output_label,
        reason=trial.reason,
    )
    return sha256_bytes(canonical_json_bytes(payload))


def _ledger_payload(ledger: ScreeningLedger) -> dict[str, object]:
    payload = ledger.model_dump(mode="json", exclude={"semantic_digest"})
    for trial in payload["trials"]:
        trial.pop("rank", None)
    return payload


def build_ledger(request: ScreeningRequest, results: list[TrialResult]) -> ScreeningLedger:
    """Rank all completed development trials and retain every failure."""
    completed = sorted(
        (result for result in results if result.metrics is not None),
        key=lambda result: (-result.metrics.total_return, result.trial_id),  # type: ignore[union-attr]
    )
    failed = sorted(
        (result for result in results if result.metrics is None), key=lambda result: result.trial_id
    )
    ranked = [result.model_copy(update={"rank": rank}) for rank, result in enumerate(completed, 1)]
    trials = [*ranked, *failed]
    draft = ScreeningLedger(
        hypothesis_id=request.hypothesis_id,
        family_id=request.family_id,
        dataset_sha256=request.dataset.sha256,
        development_partition_id=request.development_partition.partition_id,
        holdout_state="SEALED",
        declared_total_trial_budget=request.declared_total_trial_budget,
        emitted_trial_count=len(trials),
        engine="numba",
        engine_label="vectorbt_stage_zero_non_execution",
        ranking_scope="development_only",
        trials=trials,
        semantic_digest="0" * 64,
    )
    digest = sha256_bytes(canonical_json_bytes(_ledger_payload(draft)))
    return draft.model_copy(update={"semantic_digest": digest})


def _trial_problems(request: ScreeningRequest, ledger: ScreeningLedger) -> list[str]:
    problems: list[str] = []
    variants = {variant.trial_id: variant for variant in request.variants}
    for trial in ledger.trials:
        variant = variants.get(trial.trial_id)
        if variant is not None and trial.parameters != variant.parameters:
            problems.append(f"parameters changed for trial {trial.trial_id}")
        if trial.costs != request.costs:
            problems.append(f"costs changed for trial {trial.trial_id}")
        if trial.status == "completed" and (
            trial.metrics is None
            or trial.output_label != "eligible_for_independent_reimplementation"
        ):
            problems.append(f"invalid completed trial shape for {trial.trial_id}")
        if trial.status == "failed" and (
            trial.metrics is not None or trial.output_label is not None
        ):
            problems.append(f"invalid failed trial shape for {trial.trial_id}")
        if trial.semantic_digest != _trial_digest(trial):
            problems.append(f"semantic digest mismatch for trial {trial.trial_id}")
    return problems


def verify_ledger(request: ScreeningRequest, ledger: ScreeningLedger) -> LedgerVerificationReceipt:
    """Fail on any omission, duplicate, mismatch, unsafe label, or digest change."""
    declared_ids = [variant.trial_id for variant in request.variants]
    emitted_ids = [trial.trial_id for trial in ledger.trials]
    duplicate_ids = sorted(key for key, count in Counter(emitted_ids).items() if count > 1)
    missing_ids = sorted(set(declared_ids) - set(emitted_ids))
    unexpected_ids = sorted(set(emitted_ids) - set(declared_ids))
    problems: list[str] = []
    if duplicate_ids:
        problems.append(f"duplicate trial IDs: {duplicate_ids}")
    if missing_ids:
        problems.append(f"missing trial IDs: {missing_ids}")
    if unexpected_ids:
        problems.append(f"unexpected trial IDs: {unexpected_ids}")
    if ledger.declared_total_trial_budget != request.declared_total_trial_budget:
        problems.append("declared trial budget mismatch")
    if ledger.emitted_trial_count != len(ledger.trials):
        problems.append("emitted trial count does not match ledger length")
    if len(ledger.trials) != request.declared_total_trial_budget:
        problems.append("ledger length does not match declared trial budget")
    if (
        ledger.hypothesis_id != request.hypothesis_id
        or ledger.family_id != request.family_id
        or ledger.dataset_sha256 != request.dataset.sha256
        or ledger.development_partition_id != request.development_partition.partition_id
    ):
        problems.append("ledger identity does not match request")

    problems.extend(_trial_problems(request, ledger))

    expected_digest = sha256_bytes(canonical_json_bytes(_ledger_payload(ledger)))
    if ledger.semantic_digest != expected_digest:
        problems.append("ledger semantic digest mismatch")
    if problems:
        raise VectorbtLedgerError("; ".join(problems))
    return LedgerVerificationReceipt(
        ok=True,
        declared_trial_count=len(declared_ids),
        emitted_trial_count=len(emitted_ids),
        duplicate_trial_ids=[],
        missing_trial_ids=[],
        unexpected_trial_ids=[],
        semantic_digest=ledger.semantic_digest,
    )
