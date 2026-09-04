"""Pinned Nautilus-to-hand-oracle golden microcase comparison."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from trading_engine_conformance.adapters.nautilus.errors import (
    NautilusInputError,
    NautilusSemanticError,
)
from trading_engine_conformance.adapters.nautilus.profile import NautilusResearchProfile
from trading_engine_conformance.adapters.nautilus.runner import launch_worker
from trading_engine_conformance.adapters.nautilus.worker import NautilusRunRequest
from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.integrity.atomic import atomic_write_bytes
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.market_events import Trade
from trading_engine_conformance.schema.orders import OrderIntent


def _case_request(
    path: Path, profile: NautilusResearchProfile, wheel_name: str
) -> NautilusRunRequest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        instrument_raw = raw["instrument"]
        instrument = InstrumentIdentity.model_validate(instrument_raw, strict=False)
        orders = []
        for value in raw["order_intents"]:
            body = dict(value)
            body["instrument"] = instrument_raw
            orders.append(OrderIntent.model_validate(body, strict=False))
        events = []
        for value in raw["events"]:
            if value.get("type") != "trade":
                raise NautilusSemanticError("bar-path cases are non-authoritative and not run")
            body = {key: item for key, item in value.items() if key != "type"}
            body["instrument"] = instrument_raw
            events.append(Trade.model_validate(body, strict=False))
        config = raw["config"]
    except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
        raise NautilusInputError(f"invalid golden case {path}: {exc}") from exc
    if profile.maker_fee_rate != profile.taker_fee_rate:
        raise NautilusSemanticError(
            "golden cases declare one fee rate; maker and taker rates must match for comparison"
        )
    if str(profile.taker_fee_rate) != str(config["fee_rate"]):
        raise NautilusSemanticError("profile fee rate does not match the golden case")
    if str(profile.initial_margin_rate) != str(config["margin_rate"]):
        raise NautilusSemanticError("profile initial margin rate does not match the golden case")
    return NautilusRunRequest(
        request_type="golden_case",
        case_id=str(raw["case_id"]),
        wheel_relative_path=wheel_name,
        instrument=instrument,
        profile=profile,
        config=config,
        orders=orders,
        events=events,
    )


def _link_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)


def compare_golden_cases(
    *,
    golden_dir: Path,
    profile: NautilusResearchProfile,
    wheel_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the market and limit/partial microcases in separate fresh workers."""
    selected_names = (
        "001_market_buy_full_fill.json",
        "002_limit_buy_partial_then_full.json",
    )
    if output_dir.exists():
        raise NautilusInputError(f"output directory must be new: {output_dir}")
    wheel = wheel_path.resolve(strict=True)
    parent = output_dir.parent.resolve(strict=True)
    staging = parent / f".{output_dir.name}.staging-{time.time_ns()}"
    staging.mkdir(exist_ok=False)
    summaries: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="tec-nautilus-input-") as temp:
            temp_root = Path(temp)
            for name in selected_names:
                source = golden_dir / name
                case_id = source.stem
                input_dir = temp_root / case_id
                input_dir.mkdir()
                local_wheel = input_dir / wheel.name
                _link_or_copy(wheel, local_wheel)
                request = _case_request(source, profile, local_wheel.name)
                atomic_write_bytes(
                    input_dir / "request.json",
                    canonical_json_bytes(request.model_dump(mode="json")),
                )
                write_manifest(
                    input_dir / "manifest.json",
                    build_manifest(input_dir, created_ts=time.time_ns()),
                )
                case_output = staging / case_id
                launch_worker(input_dir, case_output)
                discrepancies = json.loads(
                    (case_output / "discrepancies.json").read_text(encoding="utf-8")
                )
                performance = json.loads(
                    (case_output / "performance.json").read_text(encoding="utf-8")
                )
                summaries.append(
                    {
                        "case_id": case_id,
                        "discrepancy_count": len(discrepancies),
                        "classifications": sorted(
                            {item["classification"] for item in discrepancies}
                        ),
                        "semantic_digest": performance["semantic_digest"],
                    }
                )
        summary = {
            "ok": all("unresolved" not in item["classifications"] for item in summaries),
            "cases": summaries,
            "bar_path_cases": "non-authoritative and deliberately excluded",
            "difference_policy": "all differences retained and classified; agreement is not truth",
            "execution_authorized": False,
            "profitability_claimed": False,
        }
        atomic_write_bytes(staging / "summary.json", canonical_json_bytes(summary))
        write_manifest(
            staging / "manifest.json", build_manifest(staging, created_ts=time.time_ns())
        )
        staging.replace(output_dir)
        return summary
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
