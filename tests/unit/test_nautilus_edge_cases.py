from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from trading_engine_conformance.adapters.nautilus import dbn as dbn_module
from trading_engine_conformance.adapters.nautilus.capabilities import probe_environment
from trading_engine_conformance.adapters.nautilus.dbn import VerifiedDbnInput, decode_dbn_file
from trading_engine_conformance.adapters.nautilus.errors import (
    NautilusInputError,
    NautilusSemanticError,
)
from trading_engine_conformance.adapters.nautilus.golden import _case_request, _link_or_copy
from trading_engine_conformance.adapters.nautilus.profile import NautilusResearchProfile
from trading_engine_conformance.adapters.nautilus.translators import (
    _enum_name,
    _module,
    from_nautilus_book_delta,
    from_nautilus_fill,
    from_nautilus_instrument,
    from_nautilus_order,
    from_nautilus_quote,
    from_nautilus_trade,
)
from trading_engine_conformance.adapters.nautilus.worker import (
    _check_event_order,
    _compare_fills,
    _oracle_result,
    _parse_request,
)
from trading_engine_conformance.schema.enums import AssetClass, LiquidityFlag, OrderSide
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.market_events import Trade


def _instrument() -> InstrumentIdentity:
    return InstrumentIdentity(
        venue="GLBX",
        symbol="MGCZ26",
        asset_class=AssetClass.FUTURE,
        currency="USD",
        price_precision=1,
        size_precision=0,
        tick_size=Decimal("0.1"),
        tick_value=Decimal("1"),
        multiplier=Decimal("10"),
        expiry_ts=1_800_000_000_000_000_000,
        metadata_effective_ts=1_700_000_000_000_000_000,
        is_continuous=False,
    )


def _profile(**updates: object) -> NautilusResearchProfile:
    raw: dict[str, object] = {
        "nautilus_asset_class": "COMMODITY",
        "underlying": "MGC",
        "lot_size": "1",
        "maker_fee_rate": "0.001",
        "taker_fee_rate": "0.001",
        "initial_margin_rate": "0.05",
        "maintenance_margin_rate": "0.05",
        "latency_ns": 0,
        "fill_model": "L1_FINITE_TRADE",
        "queue_model": "NO_QUEUE_L1_DIAGNOSTIC",
        "liquidity_consumption": "FINITE_EVENT_SIZE",
        "limit_fill_probability": "1",
        "slippage_probability": "0",
        "trade_execution": True,
        "reject_stop_orders": False,
        "session_timezone": "America/Chicago",
        "settlement_price": "2000",
        "random_seed": 0,
    }
    raw.update(updates)
    return NautilusResearchProfile.model_validate(raw)


def _trade(ts: int, sequence: int) -> Trade:
    return Trade(
        instrument=_instrument(),
        exchange_ts=ts,
        receive_ts=ts,
        sequence=sequence,
        price=Decimal("2000"),
        size=Decimal("1"),
    )


def _fill(fill_id: str = "f") -> Fill:
    return Fill(
        fill_id=fill_id,
        order_id="o",
        instrument=_instrument(),
        side=OrderSide.BUY,
        price=Decimal("2000"),
        quantity=Decimal("1"),
        fee=Decimal("2"),
        ts=1,
        sequence=0,
        liquidity=LiquidityFlag.TAKER,
        provenance="test",
    )


def test_probe_reports_every_runtime_dimension_and_unreadable_wheel(tmp_path: Path) -> None:
    result = probe_environment(
        wheel_path=tmp_path / "missing.whl",
        package_version="1.231.0",
        implementation="PyPy",
        python_version=(3, 12),
        platform_system="Linux",
    )
    text = " ".join(result.failures)
    assert "implementation" in text
    assert "Python" in text
    assert "platform" in text
    assert "could not read wheel" in text


def test_profile_rejects_inconsistent_l1_and_l3_queue_models() -> None:
    with pytest.raises(ValueError, match="L3"):
        _profile(fill_model="L3_MBO_FINITE")
    with pytest.raises(ValueError, match="L1"):
        _profile(queue_model="FIFO_L3")


def test_dynamic_module_and_enum_helpers_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> Any:
        raise ImportError("absent")

    monkeypatch.setattr("importlib.import_module", missing)
    with pytest.raises(Exception, match="required"):
        _module("missing")
    with pytest.raises(NautilusSemanticError, match="stable name"):
        _enum_name(object())


@pytest.mark.parametrize(
    ("translator", "message"),
    [
        (from_nautilus_instrument, "instrument"),
        (from_nautilus_trade, "event"),
        (from_nautilus_quote, "event"),
        (from_nautilus_book_delta, "event"),
        (from_nautilus_order, "order"),
        (from_nautilus_fill, "order event"),
    ],
)
def test_from_native_translators_reject_wrong_object_types(translator: Any, message: str) -> None:
    kwargs: dict[str, object] = {}
    if translator in {from_nautilus_trade, from_nautilus_book_delta}:
        kwargs["instrument"] = _instrument()
    elif translator in {from_nautilus_quote, from_nautilus_order, from_nautilus_fill}:
        kwargs.update(instrument=_instrument(), sequence=0)
    with pytest.raises(NautilusSemanticError, match=message):
        translator(object(), **kwargs)


def test_from_native_instrument_requires_adapter_metadata() -> None:
    fake_type = type("FuturesContract", (), {})
    fake = fake_type()
    fake.info = {}
    with pytest.raises(NautilusSemanticError, match="missing"):
        from_nautilus_instrument(fake)


def test_from_native_trade_requires_numeric_preserved_sequence() -> None:
    fake_type = type("TradeTick", (), {})
    fake = fake_type()
    fake.aggressor_side = SimpleNamespace(name="BUYER")
    fake.trade_id = "not-a-sequence"
    with pytest.raises(NautilusSemanticError, match="sequence"):
        from_nautilus_trade(fake, _instrument())


def test_worker_rejects_malformed_request_reversal_duplicate_and_bad_config(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(NautilusInputError, match="invalid worker request"):
        _parse_request(malformed)
    with pytest.raises(NautilusSemanticError, match="reversal"):
        _check_event_order([_trade(2, 0), _trade(1, 1)])
    with pytest.raises(NautilusSemanticError, match="duplicate"):
        _check_event_order([_trade(1, 0), _trade(2, 0)])

    request = SimpleNamespace(config={"final_liquidation_ts": "wrong"})
    with pytest.raises(NautilusInputError, match="config"):
        _oracle_result(request)


def test_worker_compare_covers_missing_extra_and_changed_fills() -> None:
    first = _fill("one")
    second = _fill("two").model_copy(update={"fee": Decimal("3")})
    assert _compare_fills([], [first])[0].nautilus_value == "unexpected"
    assert _compare_fills([first], [])[0].oracle_value == "expected"
    differences = _compare_fills([first], [second])
    assert {item.field for item in differences} == {"fill[0].fee"}


def test_golden_request_rejects_bar_invalid_json_and_profile_mismatches(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(NautilusInputError):
        _case_request(invalid, _profile(), "wheel.whl")
    root = Path(__file__).parents[2]
    with pytest.raises(NautilusSemanticError, match="non-authoritative"):
        _case_request(root / "golden" / "005_bar_gap_open_fill.json", _profile(), "wheel.whl")
    with pytest.raises(NautilusSemanticError, match="one fee"):
        _case_request(
            root / "golden" / "001_market_buy_full_fill.json",
            _profile(maker_fee_rate="0.002"),
            "wheel.whl",
        )
    with pytest.raises(NautilusSemanticError, match="fee rate"):
        _case_request(
            root / "golden" / "001_market_buy_full_fill.json",
            _profile(maker_fee_rate="0.002", taker_fee_rate="0.002"),
            "wheel.whl",
        )
    with pytest.raises(NautilusSemanticError, match="margin"):
        _case_request(
            root / "golden" / "001_market_buy_full_fill.json",
            _profile(initial_margin_rate="0.06"),
            "wheel.whl",
        )


def test_link_or_copy_has_copy_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_bytes(b"bytes")

    def no_link(_source: Path, _destination: Path) -> None:
        raise OSError("unsupported")

    monkeypatch.setattr("os.link", no_link)
    _link_or_copy(source, destination)
    assert destination.read_bytes() == b"bytes"


def test_dbn_rejects_invalid_digest_missing_directory_and_symlink(tmp_path: Path) -> None:
    with pytest.raises(NautilusInputError, match="64 lowercase"):
        dbn_module.verify_dbn_input(tmp_path / "missing", expected_sha256="bad")
    with pytest.raises(NautilusInputError, match="local immutable"):
        dbn_module.verify_dbn_input(tmp_path / "missing", expected_sha256="0" * 64)
    with pytest.raises(NautilusInputError, match="regular"):
        dbn_module.verify_dbn_input(tmp_path, expected_sha256="0" * 64)
    target = tmp_path / "target"
    target.write_bytes(b"x")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        return
    with pytest.raises(NautilusInputError, match="symlink"):
        dbn_module.verify_dbn_input(link, expected_sha256="0" * 64)


@pytest.mark.parametrize("mode", ["wrong_type", "wrong_instrument", "reversal"])
def test_dbn_decode_failure_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    input_file = tmp_path / "source.dbn"
    input_file.write_bytes(b"dbn")
    wheel = tmp_path / "wheel.whl"
    wheel.write_bytes(b"wheel")
    verified = VerifiedDbnInput(input_file, "0" * 64, 3)
    monkeypatch.setattr(dbn_module, "verify_dbn_input", lambda *_args, **_kwargs: verified)
    monkeypatch.setattr(dbn_module, "probe_environment", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(dbn_module, "sanitize_environment", lambda: ())

    fake_type = type("OrderBookDelta", (), {"to_dict": staticmethod(lambda _value: {})})
    first = fake_type()
    first.instrument_id = "MGCZ26.GLBX"
    first.ts_event = 2
    first.sequence = 1
    second = fake_type()
    second.instrument_id = "MGCZ26.GLBX"
    second.ts_event = 1
    second.sequence = 2
    if mode == "wrong_type":
        decoded = [object()]
    elif mode == "wrong_instrument":
        first.instrument_id = "OTHER.GLBX"
        decoded = [first]
    else:
        decoded = [first, second]

    loader = SimpleNamespace(from_dbn_file=lambda *_args, **_kwargs: decoded)
    module = SimpleNamespace(DatabentoDataLoader=lambda: loader)
    monkeypatch.setattr(dbn_module.importlib, "import_module", lambda _name: module)
    monkeypatch.setattr(
        dbn_module,
        "from_nautilus_book_delta",
        lambda *_args: SimpleNamespace(model_dump=lambda **_kwargs: {}),
    )
    output = tmp_path / "output"
    with pytest.raises(NautilusInputError):
        decode_dbn_file(
            input_file=input_file,
            expected_sha256="0" * 64,
            instrument=_instrument(),
            wheel_path=wheel,
            output_dir=output,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".output.staging-*"))


def test_dbn_decode_mock_success_writes_complete_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_file = tmp_path / "source.dbn"
    input_file.write_bytes(b"dbn")
    wheel = tmp_path / "wheel.whl"
    wheel.write_bytes(b"wheel")
    verified = VerifiedDbnInput(input_file, "0" * 64, 3)
    monkeypatch.setattr(dbn_module, "verify_dbn_input", lambda *_args, **_kwargs: verified)
    capability = SimpleNamespace(as_dict=lambda: {"ok": True})
    monkeypatch.setattr(dbn_module, "probe_environment", lambda **_kwargs: capability)
    monkeypatch.setattr(dbn_module, "sanitize_environment", lambda: ("SECRET",))

    fake_type = type(
        "OrderBookDelta", (), {"to_dict": staticmethod(lambda _value: {"type": "raw"})}
    )
    record = fake_type()
    record.instrument_id = "MGCZ26.GLBX"
    record.ts_event = 1
    record.sequence = 7
    loader = SimpleNamespace(from_dbn_file=lambda *_args, **_kwargs: [record])
    module = SimpleNamespace(DatabentoDataLoader=lambda: loader)
    monkeypatch.setattr(dbn_module.importlib, "import_module", lambda _name: module)
    neutral = SimpleNamespace(model_dump=lambda **_kwargs: {"sequence": 7})
    monkeypatch.setattr(dbn_module, "from_nautilus_book_delta", lambda *_args: neutral)

    output = tmp_path / "output"
    result = decode_dbn_file(
        input_file=input_file,
        expected_sha256="0" * 64,
        instrument=_instrument(),
        wheel_path=wheel,
        output_dir=output,
    )
    assert result["record_count"] == 1
    assert (output / "manifest.json").is_file()


def test_dbn_and_golden_reject_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    verified = VerifiedDbnInput(tmp_path / "missing", "0" * 64, 0)
    with (
        pytest.MonkeyPatch.context() as monkeypatch,
        pytest.raises(NautilusInputError, match="new"),
    ):
        monkeypatch.setattr(dbn_module, "verify_dbn_input", lambda *_args, **_kwargs: verified)
        monkeypatch.setattr(dbn_module, "probe_environment", lambda **_kwargs: SimpleNamespace())
        decode_dbn_file(
            input_file=tmp_path / "missing",
            expected_sha256="0" * 64,
            instrument=_instrument(),
            wheel_path=tmp_path / "wheel",
            output_dir=output,
        )
