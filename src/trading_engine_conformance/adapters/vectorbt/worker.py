"""Fresh-process offline worker for a complete preregistered screening family."""

from __future__ import annotations

import importlib
import json
import math
import shutil
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from trading_engine_conformance.adapters.vectorbt.capabilities import probe_environment
from trading_engine_conformance.adapters.vectorbt.errors import (
    VectorbtAdapterError,
    VectorbtInputError,
)
from trading_engine_conformance.adapters.vectorbt.isolation import (
    deny_network,
    sanitize_environment,
    validate_immutable_input,
)
from trading_engine_conformance.adapters.vectorbt.ledger import build_ledger, verify_ledger
from trading_engine_conformance.adapters.vectorbt.metrics import (
    build_execution_plan,
    recompute_metrics,
)
from trading_engine_conformance.adapters.vectorbt.models import (
    LedgerVerificationReceipt,
    ScreeningDataset,
    ScreeningLedger,
    ScreeningRequest,
    TrialResult,
)
from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.hashing import sha256_file
from trading_engine_conformance.integrity.atomic import atomic_write_bytes
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest


def _write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))


def _load_model(path: Path, model: type[Any], *, label: str) -> Any:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(raw, strict=False)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise VectorbtInputError(f"invalid {label}: {exc}") from exc


def load_screening_inputs(input_dir: Path) -> tuple[ScreeningRequest, ScreeningDataset]:
    """Verify both manifested files, hashes, partition identity, and boundaries."""
    request_path = validate_immutable_input(input_dir, "request.json")
    request = _load_model(request_path, ScreeningRequest, label="screening request")
    dataset_path = validate_immutable_input(input_dir, request.dataset.relative_path)
    digest, size = sha256_file(dataset_path)
    if digest != request.dataset.sha256 or size != request.dataset.byte_size:
        raise VectorbtInputError("dataset identity hash or byte size does not match request")
    dataset = _load_model(dataset_path, ScreeningDataset, label="development dataset")
    partition = request.development_partition
    if dataset.dataset_id != request.dataset.dataset_id:
        raise VectorbtInputError("dataset_id does not match request")
    if dataset.partition_id != partition.partition_id:
        raise VectorbtInputError("development partition_id does not match request")
    if len(dataset.events) != partition.event_count:
        raise VectorbtInputError("development event_count does not match request")
    if (
        dataset.events[0].event_ts != partition.start_ts
        or dataset.events[-1].event_ts != partition.end_ts
    ):
        raise VectorbtInputError("development partition boundaries do not match dataset")
    return request, dataset


def _run_vectorbt(
    request: ScreeningRequest, dataset: ScreeningDataset, valid_trial_ids: list[str]
) -> dict[str, float]:
    """Run one vectorized family call with engine='numba' explicitly."""
    if not valid_trial_ids:
        return {}
    np = importlib.import_module("numpy")
    vectorbt = importlib.import_module("vectorbt")
    variants = {variant.trial_id: variant for variant in request.variants}
    rows = len(dataset.events)
    columns = len(valid_trial_ids)
    prices = np.asarray([float(event.price) for event in dataset.events], dtype=np.float64)
    close = np.broadcast_to(prices[:, None], (rows, columns))
    entries = np.zeros((rows, columns), dtype=np.bool_)
    exits = np.zeros((rows, columns), dtype=np.bool_)
    event_index = {event.event_ts: index for index, event in enumerate(dataset.events)}
    for column, trial_id in enumerate(valid_trial_ids):
        for action in build_execution_plan(dataset, variants[trial_id]):
            row = event_index[action.execution_ts]
            if action.action == "enter_long":
                entries[row, column] = True
            else:
                exits[row, column] = True
    portfolio = vectorbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=float(request.costs.initial_cash),
        size=float(request.costs.order_size),
        size_type="amount",
        direction="longonly",
        fees=float(request.costs.fee_rate),
        fixed_fees=float(request.costs.fixed_fee),
        slippage=float(request.costs.slippage_rate),
        seed=request.seed,
        cash_sharing=False,
        engine="numba",
    )
    values = np.atleast_1d(np.asarray(portfolio.final_value(engine="numba"), dtype=np.float64))
    if values.size != columns:
        raise VectorbtAdapterError("vectorbt returned an incomplete family result")
    return {trial_id: float(values[index]) for index, trial_id in enumerate(valid_trial_ids)}


def _screen_trials(
    request: ScreeningRequest, dataset: ScreeningDataset
) -> tuple[list[TrialResult], str | None]:
    preflight_failures: dict[str, str] = {}
    valid_ids: list[str] = []
    for variant in request.variants:
        try:
            build_execution_plan(dataset, variant)
            recompute_metrics(dataset, variant, request.costs)
        except ValueError as exc:
            preflight_failures[variant.trial_id] = str(exc)
        else:
            valid_ids.append(variant.trial_id)

    engine_error: str | None = None
    native_values: dict[str, float] = {}
    try:
        native_values = _run_vectorbt(request, dataset, valid_ids)
    except Exception as exc:
        engine_error = f"vectorbt explicit-numba family failure: {type(exc).__name__}: {exc}"

    results: list[TrialResult] = []
    for variant in request.variants:
        if variant.trial_id in preflight_failures:
            results.append(
                TrialResult.failed(variant, request.costs, preflight_failures[variant.trial_id])
            )
            continue
        if engine_error is not None:
            results.append(TrialResult.failed(variant, request.costs, engine_error))
            continue
        metrics = recompute_metrics(dataset, variant, request.costs)
        native_value = native_values.get(variant.trial_id)
        if native_value is None or not math.isfinite(native_value):
            results.append(
                TrialResult.failed(
                    variant, request.costs, "vectorbt returned missing/non-finite output"
                )
            )
            continue
        tolerance = 1e-8 * max(1.0, abs(float(metrics.final_equity)))
        if abs(native_value - float(metrics.final_equity)) > tolerance:
            results.append(
                TrialResult.failed(
                    variant,
                    request.costs,
                    "independent final-equity parity mismatch against vectorbt",
                )
            )
            continue
        results.append(TrialResult.completed(variant, request.costs, metrics))
    return results, engine_error


def _execute(input_dir: Path) -> dict[str, Any]:
    request, dataset = load_screening_inputs(input_dir)
    removed = sanitize_environment()
    capability = probe_environment(
        engine=request.engine,
        assumptions_pinned=True,
        costs=request.costs,
        raise_on_failure=True,
    )
    tracemalloc.start()
    started = time.perf_counter()
    with deny_network():
        results, engine_error = _screen_trials(request, dataset)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ledger = build_ledger(request, results)
    receipt = verify_ledger(request, ledger)
    return {
        "ledger": ledger.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json"),
        "metadata": {
            "adapter_role": "quarantined_stage_zero_hypothesis_family_screener",
            "capability": capability.as_dict(),
            "cleared_environment_variable_names": list(removed),
            "network_access": "denied",
            "engine_dispatch": "explicit_numba_only",
            "holdout_access": False,
            "live_client": False,
            "broker": False,
            "execution_authorized": False,
            "profitability_claimed": False,
            "promotion_authorized": False,
            "engine_error": engine_error,
        },
        "performance": {
            "event_count": len(dataset.events),
            "trial_count": len(request.variants),
            "strategy_cells": len(dataset.events) * len(request.variants),
            "duration_seconds": format(elapsed, ".9f"),
            "peak_traced_bytes": peak,
            "semantic_digest": ledger.semantic_digest,
            "strategy_evidence": False,
        },
    }


def run_worker(input_dir: Path, output_dir: Path) -> None:
    """Execute into a staging child and atomically publish only complete output."""
    validate_immutable_input(input_dir, "request.json")
    if output_dir.exists():
        raise VectorbtInputError(f"output directory must be new: {output_dir}")
    parent = output_dir.parent.resolve(strict=True)
    if output_dir.name in {"", ".", ".."} or parent.is_symlink():
        raise VectorbtInputError("invalid output directory")
    staging = parent / f".{output_dir.name}.staging-{time.time_ns()}"
    staging.mkdir(exist_ok=False)
    try:
        result = _execute(input_dir.resolve(strict=True))
        _write_json(staging / "ledger.json", result["ledger"])
        _write_json(staging / "ledger_verification.json", result["receipt"])
        _write_json(staging / "run_metadata.json", result["metadata"])
        _write_json(staging / "performance.json", result["performance"])
        manifest = build_manifest(staging, created_ts=time.time_ns())
        write_manifest(staging / "manifest.json", manifest)
        staging.replace(output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_published_ledger(input_dir: Path, output_dir: Path) -> LedgerVerificationReceipt:
    """Verify both manifests and semantically reconcile request to complete ledger."""
    request, _ = load_screening_inputs(input_dir)
    ledger_path = validate_immutable_input(output_dir, "ledger.json")
    ledger = _load_model(ledger_path, ScreeningLedger, label="screening ledger")
    return verify_ledger(request, ledger)


def main() -> None:
    """Internal fixed entry point used by the parent launcher only."""
    if len(sys.argv) != 3:
        raise SystemExit("usage: worker INPUT_DIR OUTPUT_DIR")
    try:
        run_worker(Path(sys.argv[1]), Path(sys.argv[2]))
    except (VectorbtAdapterError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":  # pragma: no cover - exercised in a fresh process
    main()
