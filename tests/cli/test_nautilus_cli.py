from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from trading_engine_conformance.adapters.nautilus.errors import NautilusAdapterError
from trading_engine_conformance.cli.main import main


@pytest.mark.cli
def test_nautilus_cli_surface_has_no_credential_or_live_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["adapter", "nautilus", "--help"])
    assert result.exit_code == 0
    assert {"doctor", "run", "decode-dbn", "compare-golden"} <= set(result.output.split())
    lowered = result.output.lower()
    assert "api-key" not in lowered
    assert "credential" not in lowered
    assert "--live" not in lowered
    assert "broker" not in lowered


@pytest.mark.cli
def test_nautilus_doctor_reports_absent_or_unsupported_runtime() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["adapter", "nautilus", "doctor", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["execution_authorized"] is False
    assert payload["profitability_claimed"] is False


@pytest.mark.cli
def test_decode_dbn_requires_hash_and_local_path() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["adapter", "nautilus", "decode-dbn", "--help"])
    assert result.exit_code == 0
    assert "--expected-sha256" in result.output
    assert "--input-file" in result.output
    assert "api" not in result.output.lower()


@pytest.mark.cli
def test_adapter_cli_success_and_failure_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    monkeypatch.setattr("trading_engine_conformance.cli.main.launch_worker", lambda *_args: None)
    result = runner.invoke(
        main,
        [
            "adapter",
            "nautilus",
            "run",
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["ok"] is True

    def fail(*_args: object, **_kwargs: object) -> None:
        raise NautilusAdapterError("blocked")

    monkeypatch.setattr("trading_engine_conformance.cli.main.launch_worker", fail)
    result = runner.invoke(
        main,
        [
            "adapter",
            "nautilus",
            "run",
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["ok"] is False


@pytest.mark.cli
def test_decode_and_compare_cli_mocked_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    instrument = tmp_path / "instrument.json"
    instrument.write_text(
        (Path(__file__).parents[1] / "fixtures" / "esh4_instrument.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    profile = Path(__file__).parents[1] / "fixtures" / "nautilus_golden_profile.json"
    common_decode = [
        "adapter",
        "nautilus",
        "decode-dbn",
        "--input-file",
        str(tmp_path / "dbn"),
        "--expected-sha256",
        "0" * 64,
        "--instrument-json",
        str(instrument),
        "--wheel",
        str(tmp_path / "wheel"),
        "--output-dir",
        str(tmp_path / "decoded"),
        "--json",
    ]
    monkeypatch.setattr(
        "trading_engine_conformance.cli.main.decode_dbn_file",
        lambda **_kwargs: {"ok": True, "record_count": 1},
    )
    assert runner.invoke(main, common_decode).exit_code == 0

    def fail_keywords(**_kwargs: object) -> None:
        raise NautilusAdapterError("blocked")

    monkeypatch.setattr("trading_engine_conformance.cli.main.decode_dbn_file", fail_keywords)
    assert runner.invoke(main, common_decode).exit_code == 1

    common_compare = [
        "adapter",
        "nautilus",
        "compare-golden",
        "--golden-dir",
        str(tmp_path),
        "--profile-json",
        str(profile),
        "--wheel",
        str(tmp_path / "wheel"),
        "--output-dir",
        str(tmp_path / "compared"),
        "--json",
    ]
    monkeypatch.setattr(
        "trading_engine_conformance.cli.main.compare_golden_cases",
        lambda **_kwargs: {"ok": True},
    )
    assert runner.invoke(main, common_compare).exit_code == 0
    monkeypatch.setattr("trading_engine_conformance.cli.main.compare_golden_cases", fail_keywords)
    assert runner.invoke(main, common_compare).exit_code == 1


@pytest.mark.cli
def test_cli_rejects_malformed_metadata(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    result = CliRunner().invoke(
        main,
        [
            "adapter",
            "nautilus",
            "compare-golden",
            "--golden-dir",
            str(tmp_path),
            "--profile-json",
            str(bad),
            "--wheel",
            str(tmp_path / "wheel"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code != 0
    assert "invalid metadata" in result.output
