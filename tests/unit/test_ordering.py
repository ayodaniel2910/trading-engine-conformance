"""Unit tests for monotonic sequence/timestamp ordering validation."""

from dataclasses import dataclass

import pytest

from trading_engine_conformance.ordering import SequenceError, assert_monotonic, canonical_order


@dataclass(frozen=True)
class _Event:
    sequence: int
    ts: int


class TestAssertMonotonic:
    def test_accepts_strictly_increasing_sequence_and_nondecreasing_ts(self) -> None:
        events = [_Event(0, 100), _Event(1, 100), _Event(2, 200)]
        assert_monotonic(events)  # should not raise

    def test_rejects_non_increasing_sequence(self) -> None:
        events = [_Event(0, 100), _Event(0, 200)]
        with pytest.raises(SequenceError):
            assert_monotonic(events)

    def test_rejects_decreasing_sequence(self) -> None:
        events = [_Event(1, 100), _Event(0, 200)]
        with pytest.raises(SequenceError):
            assert_monotonic(events)

    def test_rejects_decreasing_timestamp(self) -> None:
        events = [_Event(0, 200), _Event(1, 100)]
        with pytest.raises(SequenceError):
            assert_monotonic(events)

    def test_empty_list_ok(self) -> None:
        assert_monotonic([])

    def test_single_item_ok(self) -> None:
        assert_monotonic([_Event(0, 100)])

    def test_custom_ts_attr(self) -> None:
        @dataclass(frozen=True)
        class _Other:
            sequence: int
            exchange_ts: int

        events = [_Other(0, 1), _Other(1, 2)]
        assert_monotonic(events, ts_attr="exchange_ts")


class TestCanonicalOrder:
    def test_sorts_by_sequence_regardless_of_input_order(self) -> None:
        events = [_Event(2, 300), _Event(0, 100), _Event(1, 200)]
        ordered = canonical_order(events)
        assert [e.sequence for e in ordered] == [0, 1, 2]

    def test_stable_result_independent_of_input_permutation(self) -> None:
        a = [_Event(2, 300), _Event(0, 100), _Event(1, 200)]
        b = [_Event(0, 100), _Event(1, 200), _Event(2, 300)]
        c = [_Event(1, 200), _Event(2, 300), _Event(0, 100)]
        assert canonical_order(a) == canonical_order(b) == canonical_order(c)

    def test_rejects_duplicate_sequence_numbers(self) -> None:
        events = [_Event(0, 100), _Event(0, 200)]
        with pytest.raises(SequenceError):
            canonical_order(events)

    def test_empty_list_ok(self) -> None:
        assert canonical_order([]) == []
