from __future__ import annotations

import pytest

from trading_engine_conformance.adapters.vectorbt.capabilities import (
    SUPPORTED_ENGINE,
    SUPPORTED_VECTORBT_VERSION,
    probe_environment,
)
from trading_engine_conformance.adapters.vectorbt.errors import VectorbtEnvironmentError
from trading_engine_conformance.adapters.vectorbt.models import ScreeningCosts


def _costs() -> ScreeningCosts:
    return ScreeningCosts(
        initial_cash="10000",
        order_size="1",
        fee_rate="0.001",
        fixed_fee="1",
        slippage_rate="0.002",
    )


def test_probe_accepts_only_pinned_numba_stack_without_rust() -> None:
    result = probe_environment(
        engine="numba",
        vectorbt_version="1.1.0",
        plotly_version="6.9.0",
        numba_version="0.67.0",
        rust_version=None,
        assumptions_pinned=True,
        costs=_costs(),
    )
    assert result.ok
    assert result.engine == SUPPORTED_ENGINE
    assert result.vectorbt_version == SUPPORTED_VECTORBT_VERSION
    assert result.rust_present is False
    assert result.execution_authorized is False
    assert result.promotion_authorized is False


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"engine": "auto"}, "engine"),
        ({"engine": "rust"}, "engine"),
        ({"vectorbt_version": None}, "absent"),
        ({"vectorbt_version": "1.0.0"}, "version"),
        ({"plotly_version": None}, "Plotly"),
        ({"plotly_version": "7.0.0"}, "Plotly"),
        ({"numba_version": None}, "Numba"),
        ({"rust_version": "1.1.0"}, "Rust"),
        ({"assumptions_pinned": False}, "assumptions"),
        ({"costs": None}, "cost"),
    ],
)
def test_probe_fails_closed_for_unsafe_or_unpinned_environment(
    updates: dict[str, object], message: str
) -> None:
    kwargs: dict[str, object] = {
        "engine": "numba",
        "vectorbt_version": "1.1.0",
        "plotly_version": "6.9.0",
        "numba_version": "0.67.0",
        "rust_version": None,
        "assumptions_pinned": True,
        "costs": _costs(),
    }
    kwargs.update(updates)
    result = probe_environment(**kwargs)  # type: ignore[arg-type]
    assert not result.ok
    assert message.lower() in " ".join(result.failures).lower()


def test_probe_can_raise_on_failure() -> None:
    with pytest.raises(VectorbtEnvironmentError):
        probe_environment(
            engine="auto",
            vectorbt_version="1.1.0",
            plotly_version="6.9.0",
            numba_version="0.67.0",
            rust_version=None,
            assumptions_pinned=True,
            costs=_costs(),
            raise_on_failure=True,
        )
