"""JSON golden-case fixture loader and runner.

A golden case is a single human-readable JSON file: an instrument, an
oracle config, order intents, market events and an "expected" section
(hand-calculated fills and a final-ledger hash), or an ``expect_error``
flag for deliberately invalid/look-ahead cases. Running a case never
raises for a malformed or mismatched fixture -- discrepancies are
reported in the returned ``GoldenCaseResult``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from trading_engine_conformance.canonical import canonical_json_bytes
from trading_engine_conformance.golden.oracle import (
    GoldenOracleError,
    MarketTick,
    OracleConfig,
    OracleResult,
    run_oracle,
)
from trading_engine_conformance.hashing import sha256_bytes
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.market_events import Bar, Trade
from trading_engine_conformance.schema.orders import OrderIntent


@dataclass(frozen=True)
class GoldenCaseResult:
    case_id: str
    ok: bool
    result: OracleResult | None
    error: str | None
    final_ledger_hash: str | None


def _parse_event(raw: dict[str, Any], instrument: dict[str, Any]) -> MarketTick:
    kind = raw.get("type")
    body = {k: v for k, v in raw.items() if k != "type"}
    body.setdefault("instrument", instrument)
    # strict=False: this data originates from JSON, so string-valued enum
    # fields (e.g. "BUY") must be coerced to their enum members; custom
    # annotated types (EconomicDecimal, UtcNanos, ...) enforce their own
    # strictness unconditionally and are unaffected by this override.
    if kind == "trade":
        return Trade.model_validate(body, strict=False)
    if kind == "bar":
        return Bar.model_validate(body, strict=False)
    raise GoldenOracleError(f"unsupported golden-case event type: {kind!r}")


def _parse_order(raw: dict[str, Any], instrument: dict[str, Any]) -> OrderIntent:
    body = dict(raw)
    body.setdefault("instrument", instrument)
    return OrderIntent.model_validate(body, strict=False)


def _parse_config(raw: dict[str, Any]) -> OracleConfig:
    return OracleConfig(
        starting_cash=Decimal(raw["starting_cash"]),
        fee_rate=Decimal(raw["fee_rate"]),
        margin_rate=Decimal(raw["margin_rate"]),
        final_liquidation_ts=raw.get("final_liquidation_ts"),
    )


def _project_actual_fill(fill: Fill) -> dict[str, object]:
    return {
        "order_id": fill.order_id,
        "side": fill.side.value,
        "price": fill.price,
        "quantity": fill.quantity,
        "fee": fill.fee,
    }


def _project_expected_fill(raw: dict[str, Any]) -> dict[str, object]:
    return {
        "order_id": raw["order_id"],
        "side": raw["side"],
        "price": Decimal(raw["price"]),
        "quantity": Decimal(raw["quantity"]),
        "fee": Decimal(raw["fee"]),
    }


def _final_ledger_hash(result: OracleResult) -> str:
    return sha256_bytes(canonical_json_bytes(result.final_ledger.model_dump(mode="json")))


def _evaluate_expected(result: OracleResult, expected: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    actual_hash = _final_ledger_hash(result)
    expected_hash = expected.get("final_ledger_hash")
    if expected_hash is not None and expected_hash != actual_hash:
        mismatches.append(
            f"final_ledger_hash mismatch: expected {expected_hash}, got {actual_hash}"
        )

    expected_fills = expected.get("fills")
    if expected_fills is not None:
        actual_fills = [_project_actual_fill(f) for f in result.fills]
        want_fills = [_project_expected_fill(f) for f in expected_fills]
        if actual_fills != want_fills:
            mismatches.append(f"fills mismatch: expected {want_fills!r}, got {actual_fills!r}")
    return mismatches


def run_case_file(path: Path) -> GoldenCaseResult:
    """Load and run a single golden-case JSON file, returning a
    ``GoldenCaseResult``. Never raises: parse errors, oracle errors and
    fixture mismatches are all reported in the result."""
    case_id = path.stem
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return GoldenCaseResult(
            case_id=case_id,
            ok=False,
            result=None,
            error=f"malformed JSON: {exc}",
            final_ledger_hash=None,
        )

    case_id = raw.get("case_id", case_id)
    expect_error = bool(raw.get("expect_error", False))

    try:
        instrument_raw = raw["instrument"]
        instrument = InstrumentIdentity.model_validate(instrument_raw, strict=False)
        order_intents = [_parse_order(o, instrument_raw) for o in raw["order_intents"]]
        events: list[MarketTick] = [_parse_event(e, instrument_raw) for e in raw["events"]]
        config = _parse_config(raw["config"])
        result = run_oracle(
            instrument=instrument, order_intents=order_intents, events=events, config=config
        )
    except (GoldenOracleError, ValidationError, KeyError, InvalidOperation, TypeError) as exc:
        if expect_error:
            return GoldenCaseResult(
                case_id=case_id, ok=True, result=None, error=str(exc), final_ledger_hash=None
            )
        return GoldenCaseResult(
            case_id=case_id, ok=False, result=None, error=str(exc), final_ledger_hash=None
        )

    if expect_error:
        return GoldenCaseResult(
            case_id=case_id,
            ok=False,
            result=result,
            error="case declared expect_error=true but no error was raised",
            final_ledger_hash=_final_ledger_hash(result),
        )

    mismatches = _evaluate_expected(result, raw.get("expected", {}))
    return GoldenCaseResult(
        case_id=case_id,
        ok=not mismatches,
        result=result,
        error="; ".join(mismatches) or None,
        final_ledger_hash=_final_ledger_hash(result),
    )


def run_all_cases(golden_dir: Path) -> list[GoldenCaseResult]:
    """Run every ``*.json`` file directly under ``golden_dir``, sorted by
    filename for deterministic output."""
    paths = sorted(golden_dir.glob("*.json"), key=lambda p: p.name)
    return [run_case_file(path) for path in paths]
