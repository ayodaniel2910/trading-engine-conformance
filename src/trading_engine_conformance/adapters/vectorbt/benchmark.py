"""Synthetic throughput/reproducibility gate; never strategy evidence."""

from __future__ import annotations

import hashlib
import importlib
import time
import tracemalloc
from dataclasses import dataclass
from typing import Any

from trading_engine_conformance.adapters.vectorbt.errors import VectorbtEnvironmentError

MIN_STRATEGY_CELLS = 2_000_000
MAX_SECONDS = 120.0
MAX_BYTES = 1_073_741_824


@dataclass(frozen=True)
class BenchmarkPass:
    rows: int
    strategies: int
    strategy_cells: int
    elapsed_seconds: float
    semantic_digest: str
    finite_outputs: int
    estimated_array_bytes: int
    peak_traced_bytes: int


def _one_pass(rows: int, strategies: int, seed: int) -> BenchmarkPass:
    try:
        np = importlib.import_module("numpy")
        vectorbt = importlib.import_module("vectorbt")
    except ImportError as exc:
        raise VectorbtEnvironmentError(
            f"vectorbt benchmark dependencies are absent: {exc}"
        ) from exc
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.00002, 0.001, rows)
    close_1d = 100.0 * np.exp(np.cumsum(returns))
    close = np.broadcast_to(close_1d[:, None], (rows, strategies))
    entries = rng.random((rows, strategies)) < 0.002
    exits = rng.random((rows, strategies)) < 0.002
    estimated_bytes = close.nbytes + entries.nbytes + exits.nbytes
    tracemalloc.start()
    started = time.perf_counter()
    portfolio = vectorbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=10_000.0,
        fees=0.0005,
        fixed_fees=0.0,
        slippage=0.0002,
        seed=seed,
        engine="numba",
        freq="1min",
    )
    total_return = np.asarray(portfolio.total_return(engine="numba"), dtype=np.float64)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return BenchmarkPass(
        rows=rows,
        strategies=strategies,
        strategy_cells=rows * strategies,
        elapsed_seconds=elapsed,
        semantic_digest=hashlib.sha256(total_return.tobytes()).hexdigest(),
        finite_outputs=int(np.isfinite(total_return).sum()),
        estimated_array_bytes=estimated_bytes,
        peak_traced_bytes=peak,
    )


def run_benchmark(*, rows: int = 5_000, strategies: int = 400, seed: int = 42) -> dict[str, Any]:
    """Run identical explicit-Numba screens twice and enforce generous CI bounds."""
    cells = rows * strategies
    if rows <= 0 or strategies <= 0 or cells < MIN_STRATEGY_CELLS:
        raise ValueError("benchmark requires at least 2,000,000 synthetic strategy cells")
    first = _one_pass(rows, strategies, seed)
    second = _one_pass(rows, strategies, seed)
    deterministic = first.semantic_digest == second.semantic_digest
    peak_bound = max(
        first.estimated_array_bytes + first.peak_traced_bytes,
        second.estimated_array_bytes + second.peak_traced_bytes,
    )
    within_threshold = (
        deterministic
        and first.elapsed_seconds < MAX_SECONDS
        and second.elapsed_seconds < MAX_SECONDS
        and peak_bound < MAX_BYTES
        and first.finite_outputs == strategies
        and second.finite_outputs == strategies
    )

    def pass_payload(result: BenchmarkPass) -> dict[str, int | str]:
        return {
            "rows": result.rows,
            "strategies": result.strategies,
            "strategy_cells": result.strategy_cells,
            "elapsed_seconds": format(result.elapsed_seconds, ".9f"),
            "semantic_digest": result.semantic_digest,
            "finite_outputs": result.finite_outputs,
            "estimated_array_bytes": result.estimated_array_bytes,
            "peak_traced_bytes": result.peak_traced_bytes,
        }

    return {
        "ok": within_threshold,
        "engine": "numba",
        "first": pass_payload(first),
        "second": pass_payload(second),
        "deterministic": deterministic,
        "threshold_seconds_per_pass": format(MAX_SECONDS, ".1f"),
        "threshold_bytes": MAX_BYTES,
        "observed_bound_bytes": peak_bound,
        "strategy_evidence": False,
        "profitability_claimed": False,
        "notice": "synthetic performance gate only; not strategy or execution evidence",
    }
