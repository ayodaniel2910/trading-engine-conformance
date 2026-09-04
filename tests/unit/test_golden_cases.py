"""Unit tests for the JSON golden-case fixture loader/runner."""

from __future__ import annotations

import json
from pathlib import Path

from trading_engine_conformance.golden.cases import run_all_cases, run_case_file

_INSTRUMENT = {
    "venue": "CME",
    "symbol": "GCZ26",
    "asset_class": "FUTURE",
    "currency": "USD",
    "price_precision": 1,
    "size_precision": 0,
    "tick_size": "0.1",
    "tick_value": "10.00",
    "multiplier": "100",
    "expiry_ts": 1_798_761_600_000_000_000,
    "metadata_effective_ts": 1_767_225_600_000_000_000,
    "is_continuous": False,
}
_T0 = 1_767_225_600_000_000_000
_NS = 1_000_000_000


def _order(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "order_id": "ord-1",
        "side": "BUY",
        "order_type": "MARKET",
        "time_in_force": "GTC",
        "quantity": "10",
        "limit_price": None,
        "stop_price": None,
        "expiry_ts": None,
        "created_ts": _T0,
        "sequence": 0,
        "linked_order_id": None,
        "oco_group_id": None,
    }
    fields.update(overrides)
    return fields


def _valid_case() -> dict[str, object]:
    return {
        "case_id": "unit_test_market_buy",
        "description": "hand-calculated market buy full fill",
        "instrument": _INSTRUMENT,
        "config": {"starting_cash": "100000", "fee_rate": "0.001", "margin_rate": "0.05"},
        "order_intents": [_order()],
        "events": [
            {
                "type": "trade",
                "exchange_ts": _T0 + _NS,
                "receive_ts": _T0 + _NS,
                "sequence": 0,
                "price": "2000.0",
                "size": "50",
                "aggressor_side": "BUY",
            }
        ],
        "expected": {
            "fills": [
                {
                    "order_id": "ord-1",
                    "side": "BUY",
                    "price": "2000.0",
                    "quantity": "10",
                    "fee": "20.000",
                }
            ],
            "final_ledger_hash": None,
        },
    }


class TestRunCaseFile:
    def test_valid_case_matches_hand_calculated_fills(self, tmp_path: Path) -> None:
        case = _valid_case()
        # compute the real hash first (mechanical function of the hand-derived state)
        path = tmp_path / "case.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        first = run_case_file(path)
        assert first.ok is True

        case["expected"]["final_ledger_hash"] = first.final_ledger_hash  # type: ignore[index]
        path.write_text(json.dumps(case), encoding="utf-8")
        second = run_case_file(path)
        assert second.ok is True
        assert second.final_ledger_hash == first.final_ledger_hash

    def test_detects_fill_mismatch(self, tmp_path: Path) -> None:
        case = _valid_case()
        case["expected"]["fills"][0]["quantity"] = "999"  # type: ignore[index]
        path = tmp_path / "case.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        result = run_case_file(path)
        assert result.ok is False

    def test_detects_ledger_hash_mismatch(self, tmp_path: Path) -> None:
        case = _valid_case()
        case["expected"]["final_ledger_hash"] = "0" * 64  # type: ignore[index]
        path = tmp_path / "case.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        result = run_case_file(path)
        assert result.ok is False

    def test_expected_error_case_with_malformed_order_type(self, tmp_path: Path) -> None:
        case = _valid_case()
        case["order_intents"][0]["order_type"] = "NOT_A_REAL_TYPE"  # type: ignore[index]
        case["expect_error"] = True
        case.pop("expected")
        path = tmp_path / "case.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        result = run_case_file(path)
        assert result.ok is True
        assert result.error is not None

    def test_expect_error_but_none_raised_fails(self, tmp_path: Path) -> None:
        case = _valid_case()
        case["expect_error"] = True
        case.pop("expected")
        path = tmp_path / "case.json"
        path.write_text(json.dumps(case), encoding="utf-8")
        result = run_case_file(path)
        assert result.ok is False

    def test_malformed_json_reports_failure_not_crash(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not valid json", encoding="utf-8")
        result = run_case_file(path)
        assert result.ok is False
        assert result.error is not None


class TestRunAllCases:
    def test_discovers_and_runs_every_json_file(self, tmp_path: Path) -> None:
        case_a = _valid_case()
        case_a["case_id"] = "case_a"
        case_b = _valid_case()
        case_b["case_id"] = "case_b"
        (tmp_path / "a.json").write_text(json.dumps(case_a), encoding="utf-8")
        (tmp_path / "b.json").write_text(json.dumps(case_b), encoding="utf-8")
        results = run_all_cases(tmp_path)
        assert {r.case_id for r in results} == {"case_a", "case_b"}

    def test_results_sorted_by_filename_for_determinism(self, tmp_path: Path) -> None:
        case_a = _valid_case()
        case_a["case_id"] = "zzz"
        case_b = _valid_case()
        case_b["case_id"] = "aaa"
        (tmp_path / "z_file.json").write_text(json.dumps(case_a), encoding="utf-8")
        (tmp_path / "a_file.json").write_text(json.dumps(case_b), encoding="utf-8")
        results = run_all_cases(tmp_path)
        assert [r.case_id for r in results] == ["aaa", "zzz"]
