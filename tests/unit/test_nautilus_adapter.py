from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from trading_engine_conformance.adapters.nautilus.capabilities import (
    SUPPORTED_IMPLEMENTATION,
    SUPPORTED_PLATFORM,
    SUPPORTED_PYTHON,
    SUPPORTED_VERSION,
    SUPPORTED_WHEEL_SHA256,
    probe_environment,
)
from trading_engine_conformance.adapters.nautilus.errors import (
    NautilusEnvironmentError,
    NautilusSemanticError,
)
from trading_engine_conformance.adapters.nautilus.profile import NautilusResearchProfile
from trading_engine_conformance.adapters.nautilus.translators import (
    decimal_to_fixed,
    to_nautilus_order,
    validate_instrument_profile,
)
from trading_engine_conformance.schema.enums import AssetClass, OrderSide, OrderType, TimeInForce
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.orders import OrderIntent


def _instrument(**updates: object) -> InstrumentIdentity:
    values: dict[str, object] = {
        "venue": "GLBX",
        "symbol": "MGCZ26",
        "asset_class": AssetClass.FUTURE,
        "currency": "USD",
        "price_precision": 1,
        "size_precision": 0,
        "tick_size": Decimal("0.1"),
        "tick_value": Decimal("1.0"),
        "multiplier": Decimal("10"),
        "expiry_ts": 1_800_000_000_000_000_000,
        "metadata_effective_ts": 1_700_000_000_000_000_000,
        "is_continuous": False,
    }
    values.update(updates)
    return InstrumentIdentity(**values)  # type: ignore[arg-type]


def _profile(**updates: object) -> NautilusResearchProfile:
    values: dict[str, object] = {
        "nautilus_asset_class": "COMMODITY",
        "underlying": "MGC",
        "lot_size": "1",
        "maker_fee_rate": "0.0001",
        "taker_fee_rate": "0.0002",
        "initial_margin_rate": "0.05",
        "maintenance_margin_rate": "0.04",
        "latency_ns": 0,
        "fill_model": "L1_FINITE_TRADE",
        "queue_model": "NO_QUEUE_L1_DIAGNOSTIC",
        "liquidity_consumption": "FINITE_EVENT_SIZE",
        "limit_fill_probability": "1",
        "slippage_probability": "0",
        "trade_execution": True,
        "reject_stop_orders": False,
        "session_timezone": "America/Chicago",
        "settlement_price": "2000.0",
        "random_seed": 0,
    }
    values.update(updates)
    return NautilusResearchProfile.model_validate(values)


def test_supported_environment_is_exactly_pinned() -> None:
    assert SUPPORTED_IMPLEMENTATION == "CPython"
    assert SUPPORTED_PYTHON == (3, 13)
    assert SUPPORTED_PLATFORM == "Windows"
    assert SUPPORTED_VERSION == "1.231.0"
    assert SUPPORTED_WHEEL_SHA256 == (
        "5fc8e08e98b6a47a5f0104c12ac6d8d3cefa0fd9dd2bb0d211c1b14517ff9aaf"
    )


def test_probe_rejects_wrong_version_and_hash(tmp_path: Path) -> None:
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"wrong wheel")
    result = probe_environment(
        wheel_path=wheel,
        package_version="1.230.0",
        implementation="CPython",
        python_version=(3, 13),
        platform_system="Windows",
    )
    assert not result.ok
    assert "version" in " ".join(result.failures)
    assert "SHA-256" in " ".join(result.failures)


def test_probe_absent_dependency_is_explicit() -> None:
    result = probe_environment(package_version=None)
    assert not result.ok
    assert result.dependency_present is False


def test_decimal_boundary_rejects_precision_loss() -> None:
    assert decimal_to_fixed(Decimal("2000.5"), 1, field="price") == "2000.5"
    with pytest.raises(NautilusSemanticError, match="precision"):
        decimal_to_fixed(Decimal("2000.55"), 1, field="price")


def test_instrument_profile_rejects_continuous_and_bad_tick_value() -> None:
    with pytest.raises(NautilusSemanticError, match="continuous"):
        validate_instrument_profile(_instrument(is_continuous=True), _profile())
    with pytest.raises(NautilusSemanticError, match="tick_value"):
        validate_instrument_profile(_instrument(tick_value=Decimal("9")), _profile())


@pytest.mark.parametrize(
    "missing",
    [
        "maker_fee_rate",
        "taker_fee_rate",
        "initial_margin_rate",
        "maintenance_margin_rate",
        "latency_ns",
        "fill_model",
        "queue_model",
        "liquidity_consumption",
        "limit_fill_probability",
        "slippage_probability",
        "trade_execution",
        "reject_stop_orders",
        "session_timezone",
        "settlement_price",
    ],
)
def test_profile_has_no_implicit_economic_or_execution_defaults(missing: str) -> None:
    raw = json.loads(_profile().model_dump_json())
    raw.pop(missing)
    with pytest.raises(ValueError):
        NautilusResearchProfile.model_validate(raw)


def test_profile_rejects_zero_fee_or_margin() -> None:
    with pytest.raises(ValueError):
        _profile(taker_fee_rate="0")
    with pytest.raises(ValueError):
        _profile(initial_margin_rate="0")


def test_probe_can_require_verified_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"not pinned")
    with pytest.raises(NautilusEnvironmentError):
        probe_environment(
            wheel_path=wheel,
            package_version=SUPPORTED_VERSION,
            implementation="CPython",
            python_version=(3, 13),
            platform_system="Windows",
            raise_on_failure=True,
        )


def test_linked_and_oco_order_semantics_are_rejected_before_runtime_import() -> None:
    common = {
        "order_id": "one",
        "instrument": _instrument(),
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.GTC,
        "quantity": Decimal("1"),
        "created_ts": 1_700_000_000_000_000_000,
        "sequence": 0,
    }
    linked = OrderIntent(**common, linked_order_id="two")  # type: ignore[arg-type]
    oco = OrderIntent(**common, oco_group_id="group")  # type: ignore[arg-type]
    with pytest.raises(NautilusSemanticError, match="linked"):
        to_nautilus_order(linked)
    with pytest.raises(NautilusSemanticError, match="OCO"):
        to_nautilus_order(oco)
