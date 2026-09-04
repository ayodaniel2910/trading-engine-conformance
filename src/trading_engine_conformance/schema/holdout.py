"""Holdout access state.

This package only ever *records* holdout access state; it never grants it.
``open_holdout`` exists solely to make that boundary testable: it always
raises ``PermissionError`` regardless of input. Opening a sealed holdout is
an out-of-band, human/authoritative-system action that happens entirely
outside this codebase; no worker API here can perform it.
"""

from __future__ import annotations

from pydantic import model_validator

from trading_engine_conformance.schema.base import StrictBaseModel
from trading_engine_conformance.schema.enums import HoldoutAccessState
from trading_engine_conformance.schema.types import UtcNanos


class HoldoutState(StrictBaseModel):
    state: HoldoutAccessState
    sealed_ts: UtcNanos
    opened_ts: UtcNanos | None = None

    @model_validator(mode="after")
    def _check_opened_ts_presence(self) -> HoldoutState:
        if self.state == HoldoutAccessState.SEALED and self.opened_ts is not None:
            raise ValueError("opened_ts must be null while state is SEALED")
        if self.state == HoldoutAccessState.OPENED and self.opened_ts is None:
            raise ValueError("opened_ts is required once state is OPENED")
        return self

    @model_validator(mode="after")
    def _check_opened_not_before_sealed(self) -> HoldoutState:
        if self.opened_ts is not None and self.opened_ts < self.sealed_ts:
            raise ValueError("opened_ts must not be earlier than sealed_ts")
        return self


def open_holdout(current: HoldoutState) -> HoldoutState:
    """Always raises. There is no code path in this package that can
    transition a holdout to OPENED; that authority does not exist here."""
    raise PermissionError(
        "trading_engine_conformance cannot open a holdout; this requires an "
        "external, out-of-band authoritative action outside this package"
    )
