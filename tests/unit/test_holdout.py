"""Unit tests for HoldoutState and the explicit refusal to transition a
sealed holdout to opened from inside this package's worker APIs."""

import pytest
from pydantic import ValidationError

from trading_engine_conformance.schema.enums import HoldoutAccessState
from trading_engine_conformance.schema.holdout import HoldoutState, open_holdout


class TestHoldoutState:
    def test_sealed_requires_null_opened_ts(self) -> None:
        state = HoldoutState(state=HoldoutAccessState.SEALED, sealed_ts=100, opened_ts=None)
        assert state.opened_ts is None

    def test_sealed_rejects_non_null_opened_ts(self) -> None:
        with pytest.raises(ValidationError):
            HoldoutState(state=HoldoutAccessState.SEALED, sealed_ts=100, opened_ts=200)

    def test_opened_requires_opened_ts(self) -> None:
        with pytest.raises(ValidationError):
            HoldoutState(state=HoldoutAccessState.OPENED, sealed_ts=100, opened_ts=None)

    def test_opened_valid(self) -> None:
        state = HoldoutState(state=HoldoutAccessState.OPENED, sealed_ts=100, opened_ts=200)
        assert state.opened_ts == 200

    def test_opened_ts_not_before_sealed_ts(self) -> None:
        with pytest.raises(ValidationError):
            HoldoutState(state=HoldoutAccessState.OPENED, sealed_ts=200, opened_ts=100)


class TestOpenHoldoutIsForbidden:
    def test_open_holdout_always_raises(self) -> None:
        sealed = HoldoutState(state=HoldoutAccessState.SEALED, sealed_ts=100, opened_ts=None)
        with pytest.raises(PermissionError):
            open_holdout(sealed)

    def test_open_holdout_raises_even_for_already_opened_state(self) -> None:
        opened = HoldoutState(state=HoldoutAccessState.OPENED, sealed_ts=100, opened_ts=200)
        with pytest.raises(PermissionError):
            open_holdout(opened)
