from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading_engine_conformance.adapters.nautilus.errors import NautilusSemanticError
from trading_engine_conformance.adapters.nautilus.translators import decimal_to_fixed


@pytest.mark.property
@given(st.integers(min_value=-(10**9), max_value=10**9), st.integers(min_value=0, max_value=9))
def test_fixed_decimal_boundary_round_trips_exactly(coefficient: int, precision: int) -> None:
    value = Decimal(coefficient).scaleb(-precision)
    encoded = decimal_to_fixed(value, precision, field="economic")
    assert Decimal(encoded) == value
    assert "E" not in encoded.upper()


@pytest.mark.property
@given(st.integers(min_value=0, max_value=8))
def test_excess_fractional_digit_is_never_silently_rounded(precision: int) -> None:
    value = Decimal(1).scaleb(-(precision + 1))
    with pytest.raises(NautilusSemanticError):
        decimal_to_fixed(value, precision, field="economic")
