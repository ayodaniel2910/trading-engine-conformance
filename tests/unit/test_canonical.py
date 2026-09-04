"""Unit tests for canonical JSON serialization: deterministic key ordering
and a stable byte representation independent of input dict order."""

from decimal import Decimal

from trading_engine_conformance.canonical import canonical_json_bytes, canonical_json_dumps


class TestCanonicalJson:
    def test_sorts_keys_deterministically(self) -> None:
        a = canonical_json_dumps({"b": 1, "a": 2})
        b = canonical_json_dumps({"a": 2, "b": 1})
        assert a == b
        assert a == '{"a":2,"b":1}'

    def test_no_whitespace(self) -> None:
        out = canonical_json_dumps({"a": [1, 2, 3]})
        assert out == '{"a":[1,2,3]}'

    def test_decimal_serializes_as_string(self) -> None:
        out = canonical_json_dumps({"price": Decimal("1.50")})
        assert out == '{"price":"1.50"}'

    def test_rejects_float(self) -> None:
        try:
            canonical_json_dumps({"x": 1.5})
        except TypeError:
            pass
        else:
            raise AssertionError("expected TypeError for float input")

    def test_nested_key_ordering(self) -> None:
        nested = {"z": {"y": 1, "x": 2}, "a": 1}
        out = canonical_json_dumps(nested)
        assert out == '{"a":1,"z":{"x":2,"y":1}}'

    def test_bytes_are_utf8_encoded_dumps(self) -> None:
        as_bytes = canonical_json_bytes({"a": 1})
        as_str = canonical_json_dumps({"a": 1})
        assert as_bytes == as_str.encode("utf-8")

    def test_non_ascii_preserved_not_escaped(self) -> None:
        out = canonical_json_dumps({"name": "café"})
        assert out == '{"name":"café"}'

    def test_deterministic_across_key_insertion_order(self) -> None:
        d1 = {}
        d1["x"] = 1
        d1["a"] = 2
        d2 = {}
        d2["a"] = 2
        d2["x"] = 1
        assert canonical_json_bytes(d1) == canonical_json_bytes(d2)
