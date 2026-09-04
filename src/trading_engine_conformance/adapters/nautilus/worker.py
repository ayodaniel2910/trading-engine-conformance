"""Fresh-process, offline Nautilus worker.

The worker has one operation: verify a manifested golden request, execute it
through the pinned matching engine, and atomically publish research artifacts.
It has no client, subscription, broker, live execution, or process-control API.
"""

from __future__ import annotations

import importlib
import json
import shutil
import sys
import time
import tracemalloc
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from trading_engine_conformance.adapters.nautilus.capabilities import probe_environment
from trading_engine_conformance.adapters.nautilus.compare import (
    ClassifiedDifference,
    classify_difference,
)
from trading_engine_conformance.adapters.nautilus.errors import (
    NautilusAdapterError,
    NautilusInputError,
    NautilusSemanticError,
)
from trading_engine_conformance.adapters.nautilus.isolation import (
    deny_network,
    sanitize_environment,
    validate_immutable_input,
)
from trading_engine_conformance.adapters.nautilus.profile import NautilusResearchProfile
from trading_engine_conformance.adapters.nautilus.translators import (
    from_nautilus_fill,
    to_nautilus_instrument,
    to_nautilus_order,
    to_nautilus_trade,
)
from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.golden.oracle import MarketTick, OracleConfig, run_oracle
from trading_engine_conformance.hashing import sha256_bytes
from trading_engine_conformance.integrity.atomic import atomic_write_bytes
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest
from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.market_events import Trade
from trading_engine_conformance.schema.orders import OrderIntent


class NautilusRunRequest(StrictBaseModel):
    request_type: Literal["golden_case"]
    case_id: str
    wheel_relative_path: str
    instrument: InstrumentIdentity
    profile: NautilusResearchProfile
    config: dict[str, str | int | None]
    orders: list[OrderIntent]
    events: list[Trade]


def _write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))


def _parse_request(path: Path) -> NautilusRunRequest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return NautilusRunRequest.model_validate(raw, strict=False)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise NautilusInputError(f"invalid worker request: {exc}") from exc


def _check_event_order(events: list[Trade]) -> None:
    previous: tuple[int, int, int] | None = None
    seen_sequences: set[int] = set()
    for event in events:
        key = (event.receive_ts, event.exchange_ts, event.sequence)
        if previous is not None and key < previous:
            raise NautilusSemanticError("timestamp reversal in input event stream")
        if event.sequence in seen_sequences:
            raise NautilusSemanticError(f"duplicate event sequence: {event.sequence}")
        previous = key
        seen_sequences.add(event.sequence)


def _engine_run(request: NautilusRunRequest) -> tuple[list[dict[str, Any]], list[Fill]]:
    # Dynamic imports preserve the optional dependency boundary.
    engine_module = importlib.import_module("nautilus_trader.backtest.engine")
    models = importlib.import_module("nautilus_trader.backtest.models")
    cache_module = importlib.import_module("nautilus_trader.cache.cache")
    component = importlib.import_module("nautilus_trader.common.component")
    enums = importlib.import_module("nautilus_trader.model.enums")
    identifiers = importlib.import_module("nautilus_trader.model.identifiers")

    _check_event_order(request.events)
    native_instrument = to_nautilus_instrument(request.instrument, request.profile)
    clock = component.TestClock()
    clock.set_time(request.instrument.metadata_effective_ts)
    message_bus = component.MessageBus(identifiers.TraderId("TEC-001"), clock)
    cache = cache_module.Cache()
    cache.add_instrument(native_instrument)
    upstream_events: list[Any] = []
    message_bus.register("ExecEngine.process", upstream_events.append)

    book_type = (
        enums.BookType.L1_MBP
        if request.profile.fill_model == "L1_FINITE_TRADE"
        else enums.BookType.L3_MBO
    )
    engine = engine_module.OrderMatchingEngine(
        instrument=native_instrument,
        raw_id=0,
        fill_model=models.FillModel(
            prob_fill_on_limit=float(request.profile.limit_fill_probability),
            prob_slippage=float(request.profile.slippage_probability),
            random_seed=request.profile.random_seed,
        ),
        fee_model=models.MakerTakerFeeModel(),
        book_type=book_type,
        oms_type=enums.OmsType.NETTING,
        account_type=enums.AccountType.MARGIN,
        reject_stop_orders=request.profile.reject_stop_orders,
        trade_execution=request.profile.trade_execution,
        msgbus=message_bus,
        cache=cache,
        clock=clock,
    )
    account_id = identifiers.AccountId("SIM-001")
    for order in request.orders:
        clock.set_time(order.created_ts)
        engine.process_order(to_nautilus_order(order), account_id)
    for event in request.events:
        clock.set_time(event.receive_ts + request.profile.latency_ns)
        engine.process_trade_tick(to_nautilus_trade(event))

    raw: list[dict[str, Any]] = []
    fills: list[Fill] = []
    for event in upstream_events:
        event_type = type(event)
        try:
            payload = event_type.to_dict(event)
        except AttributeError:
            payload = {"repr": repr(event)}
        raw.append({"event_type": event_type.__name__, "payload": payload})
        if event_type.__name__ == "OrderFilled":
            fills.append(from_nautilus_fill(event, request.instrument, sequence=len(fills)))
    return raw, fills


def _oracle_result(request: NautilusRunRequest) -> Any:
    config = request.config
    try:
        expiry_raw = config.get("final_liquidation_ts")
        if expiry_raw is not None and not isinstance(expiry_raw, int):
            raise ValueError("final_liquidation_ts must be an integer or null")
        oracle_config = OracleConfig(
            starting_cash=Decimal(str(config["starting_cash"])),
            fee_rate=Decimal(str(config["fee_rate"])),
            margin_rate=Decimal(str(config["margin_rate"])),
            final_liquidation_ts=expiry_raw,
        )
    except (KeyError, ValueError) as exc:
        raise NautilusInputError(f"invalid explicit oracle config: {exc}") from exc
    events: list[MarketTick] = list(request.events)
    return run_oracle(
        instrument=request.instrument,
        order_intents=request.orders,
        events=events,
        config=oracle_config,
    )


def _compare_fills(
    oracle_fills: list[Fill], native_fills: list[Fill]
) -> list[ClassifiedDifference]:
    differences: list[ClassifiedDifference] = []
    fields = ("order_id", "side", "price", "quantity", "fee", "ts", "liquidity")
    count = max(len(oracle_fills), len(native_fills))
    for index in range(count):
        if index >= len(oracle_fills):
            differences.append(classify_difference(f"fill[{index}]", None, "unexpected"))
            continue
        if index >= len(native_fills):
            differences.append(classify_difference(f"fill[{index}]", "expected", None))
            continue
        oracle = oracle_fills[index]
        native = native_fills[index]
        for field in fields:
            oracle_value = getattr(oracle, field)
            native_value = getattr(native, field)
            if oracle_value != native_value:
                differences.append(
                    classify_difference(
                        f"fill[{index}].{field}",
                        str(oracle_value),
                        str(native_value),
                    )
                )
    return differences


def _execute(input_dir: Path, request_path: Path) -> dict[str, Any]:
    request = _parse_request(request_path)
    wheel_path = validate_immutable_input(input_dir, request.wheel_relative_path)
    capability = probe_environment(wheel_path=wheel_path, raise_on_failure=True)
    removed = sanitize_environment()
    tracemalloc.start()
    started = time.perf_counter()
    with deny_network():
        raw_events, native_fills = _engine_run(request)
    duration = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    oracle = _oracle_result(request)
    differences = _compare_fills(oracle.fills, native_fills)
    normalized = {
        "case_id": request.case_id,
        "fills": [fill.model_dump(mode="json") for fill in native_fills],
        "execution_authorized": False,
        "profitability_claimed": False,
    }
    semantic_digest = sha256_bytes(canonical_json_bytes(normalized))
    return {
        "raw": {
            "case_id": request.case_id,
            "events": raw_events,
            "notice": "verbatim Nautilus event dictionaries; generated IDs are not normalized here",
        },
        "normalized": normalized,
        "differences": [difference.as_dict() for difference in differences],
        "metadata": {
            "adapter_role": "offline_second_verifier_only",
            "capability": capability.as_dict(),
            "cleared_environment_variable_names": list(removed),
            "network_access": "denied",
            "live_client": False,
            "broker": False,
            "subscriptions": False,
            "process_control": False,
            "resolved_profile": request.profile.model_dump(mode="json"),
            "execution_authorized": False,
            "profitability_claimed": False,
        },
        "performance": {
            "input_count": len(request.events) + len(request.orders),
            "duration_seconds": format(duration, ".9f"),
            "semantic_digest": semantic_digest,
            "peak_traced_bytes": peak_bytes,
            "threshold_seconds": "30.0",
            "threshold_peak_bytes": 536_870_912,
            "within_threshold": duration < 30.0 and peak_bytes < 536_870_912,
        },
    }


def run_worker(input_dir: Path, output_dir: Path) -> None:
    """Verify inputs, execute, and rename a complete staging directory atomically."""
    request_path = validate_immutable_input(input_dir, "request.json")
    if output_dir.exists():
        raise NautilusInputError(f"output directory must be new: {output_dir}")
    parent = output_dir.parent.resolve(strict=True)
    if output_dir.name in {"", ".", ".."} or parent.is_symlink():
        raise NautilusInputError("invalid output directory")
    staging = parent / f".{output_dir.name}.staging-{time.time_ns()}"
    staging.mkdir(exist_ok=False)
    try:
        result = _execute(input_dir.resolve(strict=True), request_path)
        _write_json(staging / "upstream_raw.json", result["raw"])
        _write_json(staging / "normalized.json", result["normalized"])
        _write_json(staging / "discrepancies.json", result["differences"])
        _write_json(staging / "run_metadata.json", result["metadata"])
        _write_json(staging / "performance.json", result["performance"])
        manifest = build_manifest(staging, created_ts=time.time_ns())
        write_manifest(staging / "manifest.json", manifest)
        staging.replace(output_dir)
    except BaseException:
        # Staging is a newly-created, validated child of the chosen parent.
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> None:
    """Minimal internal entry point used only by the CLI launcher."""
    if len(sys.argv) != 3:
        raise SystemExit("usage: worker INPUT_DIR OUTPUT_DIR")
    try:
        run_worker(Path(sys.argv[1]), Path(sys.argv[2]))
    except (NautilusAdapterError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":  # pragma: no cover - exercised as a fresh process
    main()
