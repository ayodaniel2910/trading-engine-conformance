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
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from trading_engine_conformance.canonical import canonical_json_dumps
from trading_engine_conformance.golden.cases import run_all_cases, run_case_file
from trading_engine_conformance.integrity.manifest import (
    MANIFEST_FILENAME,
    build_manifest,
    load_manifest,
    verify_manifest,
    write_manifest,
)
from trading_engine_conformance.schema.envelope import RunArtifact
from trading_engine_conformance.schema.export import export_json_schemas
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
        "network_access": "disabled: no network code path exists in this package",
        "live_execution_capability": "none",
    }
    lines = [f"{key}: {value}" for key, value in payload.items()]
    _emit(payload, lines, as_json=as_json)
    sys.exit(0 if ok else 1)


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
