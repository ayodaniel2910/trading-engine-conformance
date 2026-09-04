from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading_engine_conformance.adapters.nautilus.dbn import decode_dbn_file
from trading_engine_conformance.adapters.nautilus.golden import _case_request, compare_golden_cases
from trading_engine_conformance.adapters.nautilus.profile import NautilusResearchProfile
from trading_engine_conformance.adapters.nautilus.worker import run_worker
from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.integrity.atomic import atomic_write_bytes
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest
from trading_engine_conformance.schema.instrument import InstrumentIdentity


def _paths() -> tuple[Path, Path]:
    python_value = os.environ.get("TEC_NAUTILUS_INTEGRATION_PYTHON")
    wheel_value = os.environ.get("TEC_NAUTILUS_WHEEL")
    if not python_value or not wheel_value:
        pytest.skip("set pinned Nautilus integration Python and wheel environment variables")
    return Path(python_value), Path(wheel_value)


@pytest.mark.integration
@pytest.mark.benchmark
def test_real_golden_workers_are_deterministic_and_within_smoke_threshold(tmp_path: Path) -> None:
    python, wheel = _paths()
    profile = Path(__file__).parents[1] / "fixtures" / "nautilus_golden_profile.json"
    golden = Path(__file__).parents[2] / "golden"
    outputs = [tmp_path / "first", tmp_path / "second"]
    digests: list[list[str]] = []
    for output in outputs:
        completed = subprocess.run(  # noqa: S603
            [
                str(python.parent / "tec.exe"),
                "adapter",
                "nautilus",
                "compare-golden",
                "--golden-dir",
                str(golden),
                "--profile-json",
                str(profile),
                "--wheel",
                str(wheel),
                "--output-dir",
                str(output),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert completed.returncode == 0, completed.stderr
        summary = json.loads(completed.stdout)
        assert summary["execution_authorized"] is False
        assert summary["profitability_claimed"] is False
        assert summary["bar_path_cases"].startswith("non-authoritative")
        digests.append([case["semantic_digest"] for case in summary["cases"]])
        for case_dir in (
            output / "001_market_buy_full_fill",
            output / "002_limit_buy_partial_then_full",
        ):
            performance = json.loads((case_dir / "performance.json").read_text(encoding="utf-8"))
            assert performance["within_threshold"] is True
            assert performance["input_count"] > 0
            assert (case_dir / "upstream_raw.json").is_file()
            assert (case_dir / "normalized.json").is_file()
    assert digests[0] == digests[1]

    if sys.version_info[:2] == (3, 13):
        explicit_profile = NautilusResearchProfile.model_validate_json(
            profile.read_text(encoding="utf-8")
        )
        direct_compare = tmp_path / "direct-compare"
        direct_summary = compare_golden_cases(
            golden_dir=golden,
            profile=explicit_profile,
            wheel_path=wheel,
            output_dir=direct_compare,
        )
        assert direct_summary["ok"] is True

        # Direct invocation supplements the separately asserted fresh-process
        # CLI behavior so coverage observes the worker's fail-closed internals.
        input_dir = tmp_path / "direct-input"
        input_dir.mkdir()
        local_wheel = input_dir / wheel.name
        os.link(wheel, local_wheel)
        request = _case_request(
            golden / "002_limit_buy_partial_then_full.json",
            explicit_profile,
            local_wheel.name,
        )
        atomic_write_bytes(
            input_dir / "request.json",
            canonical_json_bytes(request.model_dump(mode="json")),
        )
        write_manifest(input_dir / "manifest.json", build_manifest(input_dir, created_ts=1))
        direct_worker = tmp_path / "direct-worker"
        run_worker(input_dir, direct_worker)
        assert (direct_worker / "manifest.json").is_file()


@pytest.mark.integration
@pytest.mark.benchmark
def test_real_dbn_mbo_decode_is_deterministic_and_preserves_count(tmp_path: Path) -> None:
    python, wheel = _paths()
    evaluation_root = os.environ.get("TEC_NAUTILUS_EVALUATION_ROOT")
    if not evaluation_root:
        pytest.skip("set TEC_NAUTILUS_EVALUATION_ROOT for the bundled DBN smoke")
    fixture = (
        Path(evaluation_root)
        / "tests"
        / "test_data"
        / "databento"
        / "esh4-glbx-mdp3-20231224.mbo.dbn.zst"
    )
    instrument = Path(__file__).parents[1] / "fixtures" / "esh4_instrument.json"
    digests: list[str] = []
    for name in ("dbn-first", "dbn-second"):
        output = tmp_path / name
        completed = subprocess.run(  # noqa: S603
            [
                str(python.parent / "tec.exe"),
                "adapter",
                "nautilus",
                "decode-dbn",
                "--input-file",
                str(fixture),
                "--expected-sha256",
                "f186e479ad0c381c40ef35384c4125d2088fb11f4ac31b0558da3fdaadb0317c",
                "--instrument-json",
                str(instrument),
                "--wheel",
                str(wheel),
                "--output-dir",
                str(output),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert completed.returncode == 0, completed.stdout
        payload = json.loads(completed.stdout)
        assert payload["record_count"] == 8725
        performance = json.loads((output / "performance.json").read_text(encoding="utf-8"))
        assert performance["within_threshold"] is True
        digests.append(payload["semantic_digest"])
    assert digests[0] == digests[1]

    if sys.version_info[:2] == (3, 13):
        instrument_model = InstrumentIdentity.model_validate_json(
            instrument.read_text(encoding="utf-8"), strict=False
        )
        direct_output = tmp_path / "dbn-direct"
        direct = decode_dbn_file(
            input_file=fixture,
            expected_sha256=("f186e479ad0c381c40ef35384c4125d2088fb11f4ac31b0558da3fdaadb0317c"),
            instrument=instrument_model,
            wheel_path=wheel,
            output_dir=direct_output,
        )
        assert direct["record_count"] == 8725
