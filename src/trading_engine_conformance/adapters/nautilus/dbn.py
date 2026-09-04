"""Local-only DBN preflight and exact MBO decoding."""

from __future__ import annotations

import importlib
import shutil
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_engine_conformance.adapters.nautilus.capabilities import probe_environment
from trading_engine_conformance.adapters.nautilus.errors import NautilusInputError
from trading_engine_conformance.adapters.nautilus.isolation import (
    deny_network,
    sanitize_environment,
)
from trading_engine_conformance.adapters.nautilus.translators import from_nautilus_book_delta
from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.hashing import sha256_bytes, sha256_file
from trading_engine_conformance.integrity.atomic import atomic_write_bytes
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest
from trading_engine_conformance.schema.instrument import InstrumentIdentity


@dataclass(frozen=True)
class VerifiedDbnInput:
    path: Path
    sha256: str
    byte_size: int


def verify_dbn_input(path: Path, *, expected_sha256: str) -> VerifiedDbnInput:
    """Verify an explicitly supplied local immutable DBN file before import."""
    raw = str(path)
    if "://" in raw or raw.lower().startswith(("api:", "live:")):
        raise NautilusInputError("DBN input must be an explicitly supplied local immutable file")
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise NautilusInputError("expected SHA-256 must be 64 lowercase hexadecimal characters")
    try:
        if path.is_symlink():
            raise NautilusInputError("DBN input must not be a symlink")
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise NautilusInputError("DBN input must be a regular local immutable file")
        digest, size = sha256_file(resolved)
    except NautilusInputError:
        raise
    except OSError as exc:
        raise NautilusInputError(
            f"DBN input must be an explicitly supplied local immutable file: {exc}"
        ) from exc
    if digest != expected_sha256:
        raise NautilusInputError(f"DBN SHA-256 mismatch: expected {expected_sha256}, got {digest}")
    return VerifiedDbnInput(path=resolved, sha256=digest, byte_size=size)


def _write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))


def decode_dbn_file(
    *,
    input_file: Path,
    expected_sha256: str,
    instrument: InstrumentIdentity,
    wheel_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Decode one verified local MBO DBN into raw and neutral artifacts."""
    verified = verify_dbn_input(input_file, expected_sha256=expected_sha256)
    capability = probe_environment(wheel_path=wheel_path, raise_on_failure=True)
    if output_dir.exists():
        raise NautilusInputError(f"output directory must be new: {output_dir}")
    parent = output_dir.parent.resolve(strict=True)
    staging = parent / f".{output_dir.name}.staging-{time.time_ns()}"
    staging.mkdir(exist_ok=False)
    try:
        removed = sanitize_environment()
        tracemalloc.start()
        started = time.perf_counter()
        with deny_network():
            databento = importlib.import_module("nautilus_trader.adapters.databento")
            loader = databento.DatabentoDataLoader()
            decoded = loader.from_dbn_file(
                verified.path,
                instrument_id=None,
                price_precision=instrument.price_precision,
                as_legacy_cython=True,
                include_trades=False,
                use_exchange_as_venue=False,
                skip_on_error=False,
            )
        duration = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        raw_records: list[dict[str, Any]] = []
        neutral_records: list[dict[str, Any]] = []
        previous_ts: int | None = None
        for value in decoded:
            if type(value).__name__ != "OrderBookDelta":
                raise NautilusInputError(
                    f"DBN is not a pure supported MBO delta stream: {type(value).__name__}"
                )
            if str(value.instrument_id) != f"{instrument.symbol}.{instrument.venue}":
                raise NautilusInputError(
                    "DBN instrument metadata mismatch: "
                    f"{value.instrument_id} != {instrument.symbol}.{instrument.venue}"
                )
            if previous_ts is not None and value.ts_event < previous_ts:
                raise NautilusInputError("decoded DBN contains timestamp reversal")
            previous_ts = value.ts_event
            raw_records.append(type(value).to_dict(value))
            neutral_records.append(
                from_nautilus_book_delta(value, instrument).model_dump(mode="json")
            )

        normalized = {
            "source_sha256": verified.sha256,
            "source_byte_size": verified.byte_size,
            "timestamp_mapping": {
                "neutral_exchange_ts": "nautilus_ts_event",
                "neutral_receive_ts": "nautilus_ts_init",
                "warning": "Nautilus Databento decoding maps DBN receive time into ts_event",
            },
            "records": neutral_records,
            "execution_authorized": False,
            "profitability_claimed": False,
        }
        semantic_digest = sha256_bytes(canonical_json_bytes(normalized))
        performance = {
            "input_count": len(decoded),
            "duration_seconds": format(duration, ".9f"),
            "semantic_digest": semantic_digest,
            "peak_traced_bytes": peak_bytes,
            "threshold_seconds": "60.0",
            "threshold_peak_bytes": 1_073_741_824,
            "within_threshold": duration < 60.0 and peak_bytes < 1_073_741_824,
        }
        metadata = {
            "adapter_role": "offline_second_verifier_only",
            "capability": capability.as_dict(),
            "cleared_environment_variable_names": list(removed),
            "network_access": "denied",
            "live_or_api_input": False,
            "execution_authorized": False,
            "profitability_claimed": False,
        }
        _write_json(
            staging / "upstream_raw.json",
            {
                "source_sha256": verified.sha256,
                "records": raw_records,
                "notice": "verbatim Nautilus decoded records, including order IDs and flags",
            },
        )
        _write_json(staging / "neutral_book_deltas.json", normalized)
        _write_json(staging / "run_metadata.json", metadata)
        _write_json(staging / "performance.json", performance)
        manifest = build_manifest(staging, created_ts=time.time_ns())
        write_manifest(staging / "manifest.json", manifest)
        staging.replace(output_dir)
        return {
            "ok": True,
            "output_dir": str(output_dir),
            "record_count": len(decoded),
            "semantic_digest": semantic_digest,
            "execution_authorized": False,
            "profitability_claimed": False,
        }
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
