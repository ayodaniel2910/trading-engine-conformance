from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from trading_engine_conformance.adapters.vectorbt.errors import VectorbtAdapterError
from trading_engine_conformance.cli.main import main


@pytest.mark.cli
def test_vectorbt_cli_surface_is_screening_only() -> None:
    result = CliRunner().invoke(main, ["adapter", "vectorbt", "--help"])
    assert result.exit_code == 0
    commands = set(result.output.split())
    assert {"doctor", "screen", "verify-ledger", "benchmark"} <= commands
    forbidden = ("holdout-open", "--live", "broker", "promotion", "signal")
    assert all(word not in result.output.lower() for word in forbidden)


@pytest.mark.cli
def test_vectorbt_doctor_reports_exact_optional_stack_posture() -> None:
    result = CliRunner().invoke(main, ["adapter", "vectorbt", "doctor", "--json"])
    payload = json.loads(result.output)
    try:
        importlib.metadata.version("vectorbt")
        importlib.metadata.version("plotly")
        importlib.metadata.version("numba")
    except importlib.metadata.PackageNotFoundError:
        expected_ok = False
    else:
        try:
            importlib.metadata.version("vectorbt-rust")
        except importlib.metadata.PackageNotFoundError:
            expected_ok = True
        else:
            expected_ok = False
    assert result.exit_code == (0 if expected_ok else 1)
    assert payload["ok"] is expected_ok
    assert payload["engine"] == "numba"
    assert payload["execution_authorized"] is False
    assert payload["promotion_authorized"] is False


@pytest.mark.cli
def test_vectorbt_screen_success_and_failure_are_machine_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        "trading_engine_conformance.cli.main.launch_vectorbt_worker", lambda *_: None
    )
    args = [
        "adapter",
        "vectorbt",
        "screen",
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
        "--json",
    ]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0
    assert json.loads(result.output)["ok"] is True

    def fail(*_args: object) -> None:
        raise VectorbtAdapterError("blocked")

    monkeypatch.setattr("trading_engine_conformance.cli.main.launch_vectorbt_worker", fail)
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 1
    assert json.loads(result.output)["ok"] is False


@pytest.mark.cli
def test_vectorbt_benchmark_rejects_fewer_than_two_million_cells() -> None:
    result = CliRunner().invoke(
        main,
        ["adapter", "vectorbt", "benchmark", "--rows", "100", "--strategies", "100"],
    )
    assert result.exit_code == 1
    assert "2,000,000" in result.output
