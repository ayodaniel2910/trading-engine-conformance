"""The `tec` no-network command-line interface.

Every command is offline: no network access, no credentials, no
broker/live-execution capability, and no way to make ``execution_authorized``
anything other than ``False``. Commands support ``--json`` for
machine-readable output and use stable exit codes (``0`` success,
``1`` failure/mismatch) so they can be scripted in CI.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from trading_engine_conformance.adapters.nautilus.capabilities import probe_environment
from trading_engine_conformance.adapters.nautilus.dbn import decode_dbn_file
from trading_engine_conformance.adapters.nautilus.errors import NautilusAdapterError
from trading_engine_conformance.adapters.nautilus.golden import compare_golden_cases
from trading_engine_conformance.adapters.nautilus.profile import NautilusResearchProfile
from trading_engine_conformance.adapters.nautilus.runner import launch_worker
from trading_engine_conformance.adapters.vectorbt.benchmark import run_benchmark
from trading_engine_conformance.adapters.vectorbt.capabilities import (
    probe_environment as probe_vectorbt_environment,
)
from trading_engine_conformance.adapters.vectorbt.errors import VectorbtAdapterError
from trading_engine_conformance.adapters.vectorbt.models import ScreeningCosts
from trading_engine_conformance.adapters.vectorbt.runner import (
    launch_worker as launch_vectorbt_worker,
)
from trading_engine_conformance.adapters.vectorbt.worker import verify_published_ledger
from trading_engine_conformance.canonical import canonical_json_dumps
from trading_engine_conformance.golden.cases import run_all_cases, run_case_file
from trading_engine_conformance.integrity.atomic import atomic_write_bytes
from trading_engine_conformance.integrity.manifest import (
    MANIFEST_FILENAME,
    build_manifest,
    load_manifest,
    verify_manifest,
    write_manifest,
)
from trading_engine_conformance.schema.envelope import RunArtifact
from trading_engine_conformance.schema.export import export_json_schemas
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.run import RunHeader
from trading_engine_conformance.schema.version import CURRENT_SCHEMA_VERSION

_DEFAULT_GOLDEN_DIR = Path("golden")


def _emit(payload: dict[str, Any], text_lines: list[str], *, as_json: bool) -> None:
    if as_json:
        click.echo(canonical_json_dumps(payload))
    else:
        for line in text_lines:
            click.echo(line)


def _format_validation_errors(exc: ValidationError) -> list[str]:
    formatted = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"]) or "<root>"
        formatted.append(f"{location}: {err['msg']}")
    return formatted


@click.group()
def main() -> None:
    """tec: engine-neutral conformance toolkit.

    No network access, no credentials, no broker/live-execution capability.
    """


@main.command("doctor")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit machine-readable JSON.")
def doctor(as_json: bool) -> None:
    """Confirm environment, schema, golden fixtures and the no-network / no-execution posture."""
    execution_field = RunHeader.model_fields["execution_authorized"]
    execution_locked = execution_field.default is False and "Literal" in str(
        execution_field.annotation
    )
    python_version_ok = sys.version_info >= (3, 11)
    golden_dir = _DEFAULT_GOLDEN_DIR
    fixture_count = len(list(golden_dir.glob("*.json"))) if golden_dir.is_dir() else 0
    ok = python_version_ok and execution_locked

    payload: dict[str, Any] = {
        "ok": ok,
        "python_version": platform.python_version(),
        "python_version_ok": python_version_ok,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "golden_fixtures_dir": str(golden_dir),
        "golden_fixtures_found": fixture_count,
        "execution_authorized_locked_false": execution_locked,
        "network_access": "disabled: no client path; adapter workers deny socket operations",
        "live_execution_capability": "none",
    }
    lines = [f"{key}: {value}" for key, value in payload.items()]
    _emit(payload, lines, as_json=as_json)
    sys.exit(0 if ok else 1)


@main.group("adapter")
def adapter_group() -> None:
    """Optional isolated second-verifier adapters."""


@adapter_group.group("nautilus")
def nautilus_group() -> None:
    """Pinned NautilusTrader v1.231.0 offline research adapter."""


@nautilus_group.command("doctor")
@click.option(
    "--wheel",
    "wheel_path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Official pinned wheel whose SHA-256 will be verified.",
)
@click.option("--out", "output_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, default=False)
def nautilus_doctor(wheel_path: Path | None, output_path: Path | None, as_json: bool) -> None:
    """Probe exact Python, platform, package version and wheel provenance."""
    result = probe_environment(wheel_path=wheel_path)
    payload = result.as_dict()
    if output_path is not None:
        atomic_write_bytes(output_path, canonical_json_dumps(payload).encode("utf-8"))
    lines = [f"{key}: {value}" for key, value in payload.items()]
    _emit(payload, lines, as_json=as_json)
    sys.exit(0 if result.ok else 1)


@nautilus_group.command("run")
@click.option("--input-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--output-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--json", "as_json", is_flag=True, default=False)
def nautilus_run(input_dir: Path, output_dir: Path, as_json: bool) -> None:
    """Launch a fresh offline worker for one manifested immutable request."""
    try:
        launch_worker(input_dir, output_dir)
        payload = {
            "ok": True,
            "output_dir": str(output_dir),
            "execution_authorized": False,
            "profitability_claimed": False,
        }
        _emit(payload, [f"wrote isolated output to {output_dir}"], as_json=as_json)
    except (NautilusAdapterError, OSError, ValueError) as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "execution_authorized": False,
            "profitability_claimed": False,
        }
        _emit(payload, [f"FAILED: {exc}"], as_json=as_json)
        sys.exit(1)


def _load_model(path: Path, model: type[Any]) -> Any:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(raw, strict=False)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise click.ClickException(f"invalid metadata file {path}: {exc}") from exc


@nautilus_group.command("decode-dbn")
@click.option("--input-file", type=click.Path(path_type=Path, dir_okay=False), required=True)
@click.option("--expected-sha256", required=True)
@click.option("--instrument-json", type=click.Path(path_type=Path, dir_okay=False), required=True)
@click.option(
    "--wheel", "wheel_path", type=click.Path(path_type=Path, dir_okay=False), required=True
)
@click.option("--output-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--json", "as_json", is_flag=True, default=False)
def nautilus_decode_dbn(
    *,
    input_file: Path,
    expected_sha256: str,
    instrument_json: Path,
    wheel_path: Path,
    output_dir: Path,
    as_json: bool,
) -> None:
    """Decode one verified local DBN/MBO file; remote inputs are impossible."""
    instrument = _load_model(instrument_json, InstrumentIdentity)
    try:
        payload = decode_dbn_file(
            input_file=input_file,
            expected_sha256=expected_sha256,
            instrument=instrument,
            wheel_path=wheel_path,
            output_dir=output_dir,
        )
        _emit(
            payload, [f"decoded {payload['record_count']} records to {output_dir}"], as_json=as_json
        )
    except (NautilusAdapterError, OSError, ValueError) as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "execution_authorized": False,
            "profitability_claimed": False,
        }
        _emit(payload, [f"FAILED: {exc}"], as_json=as_json)
        sys.exit(1)


@nautilus_group.command("compare-golden")
@click.option("--golden-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--profile-json", type=click.Path(path_type=Path, dir_okay=False), required=True)
@click.option(
    "--wheel", "wheel_path", type=click.Path(path_type=Path, dir_okay=False), required=True
)
@click.option("--output-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--json", "as_json", is_flag=True, default=False)
def nautilus_compare_golden(
    golden_dir: Path,
    profile_json: Path,
    wheel_path: Path,
    output_dir: Path,
    as_json: bool,
) -> None:
    """Compare market and limit/partial-fill microcases with the hand oracle."""
    profile = _load_model(profile_json, NautilusResearchProfile)
    try:
        payload = compare_golden_cases(
            golden_dir=golden_dir,
            profile=profile,
            wheel_path=wheel_path,
            output_dir=output_dir,
        )
        _emit(payload, [f"wrote classified comparison to {output_dir}"], as_json=as_json)
        sys.exit(0 if payload["ok"] else 1)
    except (NautilusAdapterError, OSError, ValueError) as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "execution_authorized": False,
            "profitability_claimed": False,
        }
        _emit(payload, [f"FAILED: {exc}"], as_json=as_json)
        sys.exit(1)


@adapter_group.group("vectorbt")
def vectorbt_group() -> None:
    """Pinned vectorbt 1.1.0 development-only stage-zero screener."""


def _doctor_cost_contract() -> ScreeningCosts:
    """Explicit values used only to exercise the probe's required-cost contract."""
    return ScreeningCosts(
        initial_cash=Decimal(1),
        order_size=Decimal(1),
        fee_rate=Decimal(0),
        fixed_fee=Decimal(0),
        slippage_rate=Decimal(0),
    )


@vectorbt_group.command("doctor")
@click.option("--out", "output_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, default=False)
def vectorbt_doctor(output_path: Path | None, as_json: bool) -> None:
    """Probe the pinned Numba-only dependency stack without importing it."""
    result = probe_vectorbt_environment(
        engine="numba",
        assumptions_pinned=True,
        costs=_doctor_cost_contract(),
    )
    payload = result.as_dict()
    if output_path is not None:
        atomic_write_bytes(output_path, canonical_json_dumps(payload).encode("utf-8"))
    _emit(payload, [f"{key}: {value}" for key, value in payload.items()], as_json=as_json)
    sys.exit(0 if result.ok else 1)


@vectorbt_group.command("screen")
@click.option("--input-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--output-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--json", "as_json", is_flag=True, default=False)
def vectorbt_screen(input_dir: Path, output_dir: Path, as_json: bool) -> None:
    """Launch a fresh offline worker for one complete manifested family."""
    try:
        launch_vectorbt_worker(input_dir, output_dir)
        payload = {
            "ok": True,
            "output_dir": str(output_dir),
            "output_label": "eligible_for_independent_reimplementation",
            "execution_authorized": False,
            "profitability_claimed": False,
            "promotion_authorized": False,
        }
        _emit(payload, [f"wrote isolated screening ledger to {output_dir}"], as_json=as_json)
    except (VectorbtAdapterError, OSError, ValueError) as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "execution_authorized": False,
            "profitability_claimed": False,
            "promotion_authorized": False,
        }
        _emit(payload, [f"FAILED: {exc}"], as_json=as_json)
        sys.exit(1)


@vectorbt_group.command("verify-ledger")
@click.option("--input-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--ledger-dir", type=click.Path(path_type=Path, file_okay=False), required=True)
@click.option("--out", "output_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, default=False)
def vectorbt_verify_ledger(
    input_dir: Path, ledger_dir: Path, output_path: Path | None, as_json: bool
) -> None:
    """Verify manifests, complete-family accounting, labels, and semantic digests."""
    try:
        receipt = verify_published_ledger(input_dir, ledger_dir)
        payload = receipt.model_dump(mode="json")
        if output_path is not None:
            atomic_write_bytes(output_path, canonical_json_dumps(payload).encode("utf-8"))
        _emit(payload, [f"ok: {receipt.ok}"], as_json=as_json)
    except (VectorbtAdapterError, OSError, ValueError) as exc:
        payload = {"ok": False, "error": str(exc)}
        _emit(payload, [f"FAILED: {exc}"], as_json=as_json)
        sys.exit(1)


@vectorbt_group.command("benchmark")
@click.option("--rows", type=click.IntRange(min=1), default=5_000, show_default=True)
@click.option("--strategies", type=click.IntRange(min=1), default=400, show_default=True)
@click.option("--seed", type=click.IntRange(min=0), default=42, show_default=True)
@click.option("--out", "output_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, default=False)
def vectorbt_benchmark(
    rows: int, strategies: int, seed: int, output_path: Path | None, as_json: bool
) -> None:
    """Run the >=2,000,000-cell deterministic synthetic performance gate."""
    try:
        payload = run_benchmark(rows=rows, strategies=strategies, seed=seed)
        if output_path is not None:
            atomic_write_bytes(output_path, canonical_json_dumps(payload).encode("utf-8"))
        _emit(
            payload,
            [
                f"ok: {payload['ok']}",
                f"cells: {rows * strategies}",
                "synthetic performance only; no strategy evidence",
            ],
            as_json=as_json,
        )
        if not payload["ok"]:
            sys.exit(1)
    except (VectorbtAdapterError, OSError, ValueError) as exc:
        payload = {"ok": False, "error": str(exc), "strategy_evidence": False}
        _emit(payload, [f"FAILED: {exc}"], as_json=as_json)
        sys.exit(1)


@main.group("schema")
def schema_group() -> None:
    """Schema export commands."""


@schema_group.command("export")
@click.option("--out", "out_dir", type=click.Path(path_type=Path), required=True)
@click.option("--json", "as_json", is_flag=True, default=False)
def schema_export(out_dir: Path, as_json: bool) -> None:
    """Export every top-level and shared schema model as JSON Schema."""
    schemas = export_json_schemas(output_dir=out_dir)
    payload = {"out": str(out_dir), "models": sorted(schemas)}
    lines = [f"wrote {len(schemas)} schema file(s) to {out_dir}", *sorted(schemas)]
    _emit(payload, lines, as_json=as_json)


@main.command("validate")
@click.argument("artifact_path", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True, default=False)
def validate(artifact_path: Path, as_json: bool) -> None:
    """Validate a JSON artifact against the RunArtifact schema."""
    try:
        raw_text = artifact_path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except OSError as exc:
        payload = {"valid": False, "errors": [f"could not read {artifact_path}: {exc}"]}
        _emit(payload, [f"INVALID: could not read {artifact_path}: {exc}"], as_json=as_json)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        payload = {"valid": False, "errors": [f"malformed JSON: {exc}"]}
        _emit(payload, [f"INVALID: malformed JSON: {exc}"], as_json=as_json)
        sys.exit(1)

    try:
        RunArtifact.model_validate(raw, strict=False)
    except ValidationError as exc:
        errors = _format_validation_errors(exc)
        payload = {"valid": False, "errors": errors}
        _emit(payload, ["INVALID", *errors], as_json=as_json)
        sys.exit(1)

    payload = {"valid": True, "errors": []}
    _emit(payload, ["VALID"], as_json=as_json)


@main.group("golden")
def golden_group() -> None:
    """Golden-oracle case commands."""


@golden_group.command("run")
@click.argument("case_id")
@click.option("--dir", "golden_dir", type=click.Path(path_type=Path), default=_DEFAULT_GOLDEN_DIR)
@click.option("--json", "as_json", is_flag=True, default=False)
def golden_run(case_id: str, golden_dir: Path, as_json: bool) -> None:
    """Run one golden case (by id) or `all` cases under --dir."""
    if case_id == "all":
        results = run_all_cases(golden_dir)
        if not results:
            payload = {
                "ok": False,
                "cases": [],
                "error": f"no golden cases found under {golden_dir}",
            }
            _emit(payload, [f"no golden cases found under {golden_dir}"], as_json=as_json)
            sys.exit(1)
    else:
        case_path = golden_dir / f"{case_id}.json"
        if not case_path.is_file():
            payload = {"ok": False, "cases": [], "error": f"unknown golden case: {case_id!r}"}
            _emit(payload, [f"unknown golden case: {case_id!r}"], as_json=as_json)
            sys.exit(1)
        results = [run_case_file(case_path)]

    ok = all(r.ok for r in results)
    payload = {
        "ok": ok,
        "cases": [
            {
                "case_id": r.case_id,
                "ok": r.ok,
                "error": r.error,
                "final_ledger_hash": r.final_ledger_hash,
            }
            for r in results
        ],
    }
    lines = [
        f"{r.case_id}: {'PASS' if r.ok else 'FAIL'}" + (f" ({r.error})" if r.error else "")
        for r in results
    ]
    _emit(payload, lines, as_json=as_json)
    sys.exit(0 if ok else 1)


@main.group("manifest")
def manifest_group() -> None:
    """Manifest build/verify commands."""


@manifest_group.command("build")
@click.argument("run_dir", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True, default=False)
def manifest_build(run_dir: Path, as_json: bool) -> None:
    """Build and write manifest.json for every artifact under RUN_DIR."""
    try:
        manifest = build_manifest(run_dir, created_ts=time.time_ns())
        write_manifest(run_dir / MANIFEST_FILENAME, manifest)
    except (OSError, ValueError) as exc:
        payload = {"ok": False, "error": str(exc)}
        _emit(payload, [f"FAILED: {exc}"], as_json=as_json)
        sys.exit(1)

    payload = {
        "ok": True,
        "run_dir": str(run_dir),
        "manifest_path": str(run_dir / MANIFEST_FILENAME),
        "entry_count": len(manifest.entries),
        "root_hash": manifest.root_hash,
    }
    lines = [f"wrote manifest for {len(manifest.entries)} file(s) to {run_dir / MANIFEST_FILENAME}"]
    _emit(payload, lines, as_json=as_json)


@manifest_group.command("verify")
@click.argument("manifest_path", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True, default=False)
def manifest_verify(manifest_path: Path, as_json: bool) -> None:
    """Verify a manifest.json against the real contents of its run directory."""
    try:
        manifest = load_manifest(manifest_path)
        receipt = verify_manifest(manifest_path.parent, manifest, verified_ts=time.time_ns())
    except (OSError, ValueError) as exc:
        payload = {"ok": False, "error": str(exc)}
        _emit(payload, [f"FAILED: {exc}"], as_json=as_json)
        sys.exit(1)

    payload = receipt.model_dump(mode="json")
    lines = [f"ok: {receipt.ok}"]
    if not receipt.ok:
        lines.append(f"missing={receipt.missing} extra={receipt.extra} changed={receipt.changed}")
    _emit(payload, lines, as_json=as_json)
    sys.exit(0 if receipt.ok else 1)
