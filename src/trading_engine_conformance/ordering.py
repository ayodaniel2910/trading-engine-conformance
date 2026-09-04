"""Monotonic sequence/timestamp ordering utilities.

Any stream of events in this project (market events, order transitions,
fills, ledger snapshots) carries an integer ``sequence`` that is the sole
authority for ordering -- including tie-breaking events that share the same
timestamp. Two independent guarantees are provided here:

- ``assert_monotonic`` proves a *given* ordering is causally valid: sequence
  strictly increases and timestamp never decreases as sequence increases.
- ``canonical_order`` derives the *only* valid ordering from a set of
  events by sequence alone, so shuffling the input array can never change
  downstream replay results, and duplicate sequence numbers are rejected
  rather than silently tolerated.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar


class SequenceError(ValueError):
    """Raised when a stream's sequence/timestamp ordering is invalid."""


class _Sequenced(Protocol):
    sequence: int


T = TypeVar("T", bound=_Sequenced)


def assert_monotonic(items: list[T], ts_attr: str = "ts") -> None:
    """Assert ``items`` are already ordered: sequence strictly increasing,
    timestamp (read from ``ts_attr``) never decreasing. Raises
    ``SequenceError`` on the first violation."""
    last_seq: int | None = None
    last_ts: Any = None
    for item in items:
        seq = item.sequence
        ts = getattr(item, ts_attr)
        if last_seq is not None:
            if seq <= last_seq:
                raise SequenceError(
                    f"sequence must strictly increase: {seq} did not follow {last_seq}"
                )
            if ts < last_ts:
                raise SequenceError(f"timestamp must not decrease: {ts} followed {last_ts}")
        last_seq = seq
        last_ts = ts


def canonical_order(items: list[T]) -> list[T]:
    """Return ``items`` sorted by ``.sequence`` ascending, independent of
    input order. Raises ``SequenceError`` on duplicate sequence numbers."""
    ordered = sorted(items, key=lambda item: item.sequence)
    seen: set[int] = set()
    for item in ordered:
        if item.sequence in seen:
            raise SequenceError(f"duplicate sequence number: {item.sequence}")
        seen.add(item.sequence)
    return ordered
