from __future__ import annotations

from pathlib import Path

import pytest

from trading_engine_conformance.adapters.nautilus.compare import classify_difference
from trading_engine_conformance.adapters.nautilus.dbn import verify_dbn_input
from trading_engine_conformance.adapters.nautilus.errors import NautilusInputError


def test_dbn_requires_exact_expected_hash(tmp_path: Path) -> None:
    path = tmp_path / "sample.dbn.zst"
    path.write_bytes(b"cached-only")
    verified = verify_dbn_input(
        path,
        expected_sha256="65a4abbbb2c7df842f9d5bec5507a9cad0b311897c5e049516bd45a70de4b97a",
    )
    assert verified.path == path.resolve()
    assert verified.byte_size == len(b"cached-only")
    with pytest.raises(NautilusInputError, match="SHA-256"):
        verify_dbn_input(path, expected_sha256="0" * 64)


@pytest.mark.parametrize("value", ["https://example/dbn", "dbn://live", "api:dataset"])
def test_dbn_rejects_live_or_api_inputs(value: str) -> None:
    with pytest.raises(NautilusInputError, match="local immutable file"):
        verify_dbn_input(Path(value), expected_sha256="0" * 64)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("instrument.symbol", "input_mapping"),
        ("event.exchange_ts", "timestamp_eligibility_rule"),
        ("fill.price", "execution_model_choice"),
        ("fill.fee", "accounting_convention"),
        ("event.unsupported", "unsupported_semantics"),
        ("something_else", "unresolved"),
    ],
)
def test_every_difference_gets_an_explicit_classification(field: str, expected: str) -> None:
    result = classify_difference(field, "oracle", "nautilus")
    assert result.classification == expected
    assert result.oracle_value == "oracle"
    assert result.nautilus_value == "nautilus"
