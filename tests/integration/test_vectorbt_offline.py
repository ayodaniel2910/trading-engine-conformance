from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import pytest

from tests.unit.test_vectorbt_worker import write_input
from trading_engine_conformance.adapters.vectorbt.benchmark import run_benchmark
from trading_engine_conformance.adapters.vectorbt.capabilities import probe_environment
from trading_engine_conformance.adapters.vectorbt.worker import (
    _run_vectorbt,
    load_screening_inputs,
    run_worker,
    verify_published_ledger,
)

pytestmark = pytest.mark.integration


def _require_optional_stack() -> None:
    pytest.importorskip("numpy")
    pytest.importorskip("vectorbt")


def test_actual_vectorbt_call_forces_numba_and_matches_independent_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_optional_stack()
    import vectorbt  # type: ignore[import-not-found]  # noqa: PLC0415

    input_dir = write_input(tmp_path)
    request, dataset = load_screening_inputs(input_dir)
    seen: dict[str, object] = {}
    original = vectorbt.Portfolio.from_signals

    def recording_from_signals(*args: object, **kwargs: object) -> object:
        seen["engine"] = kwargs.get("engine")
        return original(*args, **kwargs)

    monkeypatch.setattr(vectorbt.Portfolio, "from_signals", recording_from_signals)
    values = _run_vectorbt(request, dataset, [variant.trial_id for variant in request.variants])
    assert seen["engine"] == "numba"
    assert values["trial-a"] == pytest.approx(10017.28004)
    assert values["trial-b"] == pytest.approx(10000)


def test_actual_worker_is_offline_complete_and_reproducible(tmp_path: Path) -> None:
    _require_optional_stack()
    try:
        importlib.metadata.version("vectorbt-rust")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        pytest.skip("accepted worker environment must not contain vectorbt-rust")
    input_dir = write_input(tmp_path)
    request, _ = load_screening_inputs(input_dir)
    capability = probe_environment(engine="numba", assumptions_pinned=True, costs=request.costs)
    assert capability.ok

    first = tmp_path / "first"
    second = tmp_path / "second"
    run_worker(input_dir, first)
    run_worker(input_dir, second)
    assert verify_published_ledger(input_dir, first).ok
    assert verify_published_ledger(input_dir, second).ok
    first_ledger = json.loads((first / "ledger.json").read_text(encoding="utf-8"))
    second_ledger = json.loads((second / "ledger.json").read_text(encoding="utf-8"))
    assert first_ledger["semantic_digest"] == second_ledger["semantic_digest"]


@pytest.mark.benchmark
def test_two_million_cell_performance_gate() -> None:
    _require_optional_stack()
    result = run_benchmark()
    assert result["ok"] is True
    assert result["first"]["strategy_cells"] >= 2_000_000
    assert result["first"]["semantic_digest"] == result["second"]["semantic_digest"]
    assert result["strategy_evidence"] is False
