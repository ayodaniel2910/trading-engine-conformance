"""CLI tests for the `tec` command surface."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from trading_engine_conformance.cli.main import main
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_DIR = _REPO_ROOT / "golden"


def _runner() -> CliRunner:
    return CliRunner()


class TestDoctor:
    def test_exits_zero_and_reports_json(self) -> None:
        result = _runner().invoke(main, ["doctor", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["execution_authorized_locked_false"] is True
        assert payload["python_version_ok"] is True

    def test_human_readable_output_by_default(self) -> None:
        result = _runner().invoke(main, ["doctor"])
        assert result.exit_code == 0
        assert "python_version" in result.output


class TestSchemaExport:
    def test_writes_json_schema_files(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "schema-export"
        result = _runner().invoke(main, ["schema", "export", "--out", str(out_dir)])
        assert result.exit_code == 0
        assert (out_dir / "RunArtifact.json").exists()
        assert (out_dir / "OrderIntent.json").exists()

    def test_json_output_lists_written_files(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "schema-export"
        result = _runner().invoke(main, ["schema", "export", "--out", str(out_dir), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "RunArtifact" in payload["models"]


class TestValidate:
    def test_valid_run_artifact_exits_zero(self, tmp_path: Path) -> None:
        artifact = _minimal_run_artifact()
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        result = _runner().invoke(main, ["validate", str(path), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["valid"] is True

    def test_invalid_artifact_exits_nonzero(self, tmp_path: Path) -> None:
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps({"not": "an artifact"}), encoding="utf-8")
        result = _runner().invoke(main, ["validate", str(path), "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["valid"] is False
        assert payload["errors"]

    def test_malformed_json_exits_nonzero(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        result = _runner().invoke(main, ["validate", str(path), "--json"])
        assert result.exit_code == 1

    def test_unreadable_path_exits_nonzero(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.json"
        result = _runner().invoke(main, ["validate", str(missing), "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["valid"] is False

    def test_invalid_artifact_human_readable_output(self, tmp_path: Path) -> None:
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps({"not": "an artifact"}), encoding="utf-8")
        result = _runner().invoke(main, ["validate", str(path)])
        assert result.exit_code == 1
        assert "INVALID" in result.output

    def test_execution_authorized_true_is_rejected(self, tmp_path: Path) -> None:
        artifact = _minimal_run_artifact()
        artifact["header"]["execution_authorized"] = True
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        result = _runner().invoke(main, ["validate", str(path), "--json"])
        assert result.exit_code == 1


class TestGoldenRun:
    def test_runs_all_repository_fixtures(self) -> None:
        result = _runner().invoke(
            main, ["golden", "run", "all", "--dir", str(_GOLDEN_DIR), "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert len(payload["cases"]) >= 10

    def test_runs_single_named_case(self) -> None:
        result = _runner().invoke(
            main,
            [
                "golden",
                "run",
                "001_market_buy_full_fill",
                "--dir",
                str(_GOLDEN_DIR),
                "--json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert len(payload["cases"]) == 1

    def test_unknown_case_exits_nonzero(self) -> None:
        result = _runner().invoke(
            main, ["golden", "run", "does-not-exist", "--dir", str(_GOLDEN_DIR), "--json"]
        )
        assert result.exit_code == 1

    def test_empty_directory_exits_nonzero(self, tmp_path: Path) -> None:
        result = _runner().invoke(main, ["golden", "run", "all", "--dir", str(tmp_path), "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["cases"] == []

    def test_human_readable_output_shows_pass_fail(self) -> None:
        result = _runner().invoke(
            main, ["golden", "run", "001_market_buy_full_fill", "--dir", str(_GOLDEN_DIR)]
        )
        assert result.exit_code == 0
        assert "PASS" in result.output


class TestManifest:
    def _make_run_dir(self, tmp_path: Path) -> Path:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "a.json").write_text('{"a":1}', encoding="utf-8")
        return run_dir

    def test_build_then_verify_round_trip(self, tmp_path: Path) -> None:
        run_dir = self._make_run_dir(tmp_path)
        build_result = _runner().invoke(main, ["manifest", "build", str(run_dir), "--json"])
        assert build_result.exit_code == 0
        manifest_path = run_dir / "manifest.json"
        assert manifest_path.exists()

        verify_result = _runner().invoke(main, ["manifest", "verify", str(manifest_path), "--json"])
        assert verify_result.exit_code == 0
        payload = json.loads(verify_result.output)
        assert payload["ok"] is True

    def test_verify_detects_tampering(self, tmp_path: Path) -> None:
        run_dir = self._make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        write_manifest(run_dir / "manifest.json", manifest)
        (run_dir / "a.json").write_text('{"a":"tampered"}', encoding="utf-8")

        result = _runner().invoke(
            main, ["manifest", "verify", str(run_dir / "manifest.json"), "--json"]
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert "a.json" in payload["changed"]

    def test_build_on_missing_directory_exits_nonzero(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        result = _runner().invoke(main, ["manifest", "build", str(missing), "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False

    def test_verify_on_missing_manifest_exits_nonzero(self, tmp_path: Path) -> None:
        missing = tmp_path / "manifest.json"
        result = _runner().invoke(main, ["manifest", "verify", str(missing), "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False

    def test_verify_human_readable_output_on_tampering(self, tmp_path: Path) -> None:
        run_dir = self._make_run_dir(tmp_path)
        manifest = build_manifest(run_dir, created_ts=1)
        write_manifest(run_dir / "manifest.json", manifest)
        (run_dir / "a.json").write_text('{"a":"tampered"}', encoding="utf-8")

        result = _runner().invoke(main, ["manifest", "verify", str(run_dir / "manifest.json")])
        assert result.exit_code == 1
        assert "changed=" in result.output


def _minimal_run_artifact() -> dict[str, object]:
    instrument = {
        "venue": "CME",
        "symbol": "GCZ26",
        "asset_class": "FUTURE",
        "currency": "USD",
        "price_precision": 1,
        "size_precision": 0,
        "tick_size": "0.1",
        "tick_value": "10.00",
        "multiplier": "100",
        "expiry_ts": 1798761600000000000,
        "metadata_effective_ts": 1767225600000000000,
        "is_continuous": False,
    }
    return {
        "header": {
            "run_id": "run-0001",
            "schema_version": "1.0.0",
            "created_ts": 1767225600000000000,
            "source_revision": {
                "commit_hash": "a" * 40,
                "is_dirty": False,
                "repository_url": None,
            },
            "environment_lock": {
                "lock_hash": "b" * 64,
                "python_version": "3.11.8",
                "platform": "win32",
                "tool_versions": {"tec": "0.1.0"},
            },
            "seed": 1,
            "tool_versions": {"tec": "0.1.0"},
            "holdout_state": {"state": "SEALED", "sealed_ts": 1, "opened_ts": None},
            "execution_authorized": False,
        },
        "datasets": [],
        "instruments": [instrument],
        "market_events": [],
        "signals": [],
        "order_intents": [],
        "order_transitions": [],
        "fills": [],
        "ledger_snapshots": [],
        "execution_assumptions": {
            "fee_model": "fixed",
            "fee_rate": "1",
            "spread_model": "fixed",
            "slippage_model": "none",
            "latency_ns": 0,
            "queue_model": "fifo",
            "partial_fill_policy": "preserve-residual",
            "margin_model": "reg-t",
            "session_policy": "cme",
            "settlement_policy": "daily",
            "roll_policy": "manual",
        },
    }
