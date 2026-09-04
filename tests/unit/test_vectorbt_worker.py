from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_vectorbt_models import request_payload
from trading_engine_conformance.adapters.vectorbt.errors import (
    VectorbtAdapterError,
    VectorbtInputError,
)
from trading_engine_conformance.adapters.vectorbt.metrics import recompute_metrics
from trading_engine_conformance.adapters.vectorbt.models import (
    ScreeningDataset,
    ScreeningRequest,
)
from trading_engine_conformance.adapters.vectorbt.runner import launch_worker
from trading_engine_conformance.adapters.vectorbt.worker import (
    _execute,
    load_screening_inputs,
    run_worker,
    verify_published_ledger,
)
from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.hashing import sha256_bytes
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest


def _dataset_payload() -> dict[str, object]:
    return {
        "dataset_id": "development-bars",
        "partition_id": "development-only",
        "events": [
            {"event_ts": 100, "price": "100"},
            {"event_ts": 200, "price": "110"},
            {"event_ts": 300, "price": "120"},
            {"event_ts": 400, "price": "130"},
        ],
    }


def write_input(tmp_path: Path, *, request_updates: dict[str, object] | None = None) -> Path:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    dataset_bytes = canonical_json_bytes(_dataset_payload())
    (input_dir / "development.json").write_bytes(dataset_bytes)
    raw = request_payload()
    dataset = raw["dataset"]
    assert isinstance(dataset, dict)
    dataset["byte_size"] = len(dataset_bytes)
    dataset["sha256"] = sha256_bytes(dataset_bytes)
    if request_updates:
        raw.update(request_updates)
    (input_dir / "request.json").write_bytes(canonical_json_bytes(raw))
    write_manifest(input_dir / "manifest.json", build_manifest(input_dir, created_ts=1))
    return input_dir


def _patch_runtime(monkeypatch: pytest.MonkeyPatch, *, mismatch: bool = False) -> None:
    capability = SimpleNamespace(as_dict=lambda: {"ok": True, "engine": "numba"})
    monkeypatch.setattr(
        "trading_engine_conformance.adapters.vectorbt.worker.probe_environment",
        lambda **_kwargs: capability,
    )

    def fake_engine(
        request: ScreeningRequest, dataset: ScreeningDataset, valid_ids: list[str]
    ) -> dict[str, float]:
        variants = {variant.trial_id: variant for variant in request.variants}
        values = {
            trial_id: float(
                recompute_metrics(dataset, variants[trial_id], request.costs).final_equity
            )
            for trial_id in valid_ids
        }
        if mismatch and valid_ids:
            values[valid_ids[0]] += 100
        return values

    monkeypatch.setattr(
        "trading_engine_conformance.adapters.vectorbt.worker._run_vectorbt", fake_engine
    )


def test_worker_publishes_complete_manifested_ledger_and_verifies_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = write_input(tmp_path)
    output_dir = tmp_path / "output"
    _patch_runtime(monkeypatch)
    run_worker(input_dir, output_dir)
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "ledger.json",
        "ledger_verification.json",
        "manifest.json",
        "performance.json",
        "run_metadata.json",
    ]
    ledger = json.loads((output_dir / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["emitted_trial_count"] == 2
    assert all(item["status"] == "completed" for item in ledger["trials"])
    assert verify_published_ledger(input_dir, output_dir).ok


def test_worker_emits_parity_failure_instead_of_winner_only_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = write_input(tmp_path)
    _patch_runtime(monkeypatch, mismatch=True)
    result = _execute(input_dir)
    trials = result["ledger"]["trials"]
    assert len(trials) == 2
    assert {item["status"] for item in trials} == {"completed", "failed"}
    failed = next(item for item in trials if item["status"] == "failed")
    assert "parity mismatch" in failed["reason"]


def test_worker_records_all_engine_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = write_input(tmp_path)
    capability = SimpleNamespace(as_dict=lambda: {"ok": True, "engine": "numba"})
    monkeypatch.setattr(
        "trading_engine_conformance.adapters.vectorbt.worker.probe_environment",
        lambda **_kwargs: capability,
    )

    def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("engine crash")

    monkeypatch.setattr("trading_engine_conformance.adapters.vectorbt.worker._run_vectorbt", fail)
    result = _execute(input_dir)
    assert len(result["ledger"]["trials"]) == 2
    assert all(item["status"] == "failed" for item in result["ledger"]["trials"])
    assert "engine crash" in result["metadata"]["engine_error"]


def test_worker_records_invalid_next_event_trial_and_runs_remaining_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = request_payload()
    variants = raw["variants"]
    assert isinstance(variants, list) and isinstance(variants[0], dict)
    signals = variants[0]["signals"]
    assert isinstance(signals, list) and isinstance(signals[0], dict)
    signals[0]["execution_ts"] = 300
    input_dir = write_input(tmp_path, request_updates={"variants": variants})
    _patch_runtime(monkeypatch)
    result = _execute(input_dir)
    assert len(result["ledger"]["trials"]) == 2
    failed = next(item for item in result["ledger"]["trials"] if item["status"] == "failed")
    assert "next declared event" in failed["reason"]


@pytest.mark.parametrize(
    "mutation",
    [
        {
            "dataset": {
                "dataset_id": "wrong",
                "relative_path": "development.json",
                "byte_size": 1,
                "sha256": "0" * 64,
            }
        },
        {
            "development_partition": {
                "partition_id": "wrong",
                "start_ts": 100,
                "end_ts": 400,
                "event_count": 4,
            }
        },
        {
            "development_partition": {
                "partition_id": "development-only",
                "start_ts": 100,
                "end_ts": 400,
                "event_count": 3,
            }
        },
        {
            "development_partition": {
                "partition_id": "development-only",
                "start_ts": 101,
                "end_ts": 400,
                "event_count": 4,
            }
        },
    ],
)
def test_worker_rejects_dataset_identity_or_partition_mismatch(
    tmp_path: Path, mutation: dict[str, object]
) -> None:
    input_dir = write_input(tmp_path, request_updates=mutation)
    with pytest.raises(VectorbtInputError, match=r"dataset|partition|event_count|boundaries"):
        load_screening_inputs(input_dir)


def test_published_ledger_tamper_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = write_input(tmp_path)
    output_dir = tmp_path / "output"
    _patch_runtime(monkeypatch)
    run_worker(input_dir, output_dir)
    (output_dir / "ledger.json").write_text("{}", encoding="utf-8")
    with pytest.raises(VectorbtInputError, match="manifest"):
        verify_published_ledger(input_dir, output_dir)


def test_worker_refuses_existing_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = write_input(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _patch_runtime(monkeypatch)
    with pytest.raises(VectorbtInputError, match="new"):
        run_worker(input_dir, output_dir)


def test_runner_uses_fixed_current_python_and_reports_child_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setenv("HTTP_PROXY", "secret")
    monkeypatch.setattr("subprocess.run", fake_run)
    result = launch_worker(tmp_path / "input", tmp_path / "output")
    assert result.returncode == 0
    command, kwargs = calls[0]
    assert isinstance(command, list)
    assert command[1:3] == ["-m", "trading_engine_conformance.adapters.vectorbt.worker"]
    assert "HTTP_PROXY" not in kwargs["env"]

    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=3, stdout="", stderr="blocked"),
    )
    with pytest.raises(VectorbtAdapterError, match="blocked"):
        launch_worker(tmp_path / "input", tmp_path / "output")
