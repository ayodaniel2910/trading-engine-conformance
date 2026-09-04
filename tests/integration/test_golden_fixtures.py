"""Integration test: every hand-calculated fixture under the repository's
``golden/`` directory must pass when replayed through the oracle."""

from __future__ import annotations

from pathlib import Path

from trading_engine_conformance.golden.cases import run_all_cases

_GOLDEN_DIR = Path(__file__).resolve().parents[2] / "golden"


def test_golden_directory_exists() -> None:
    assert _GOLDEN_DIR.is_dir()


def test_all_golden_fixtures_pass() -> None:
    results = run_all_cases(_GOLDEN_DIR)
    assert results, "expected at least one golden fixture"
    failures = [(r.case_id, r.error) for r in results if not r.ok]
    assert failures == []


def test_at_least_one_expect_error_fixture_present() -> None:
    results = run_all_cases(_GOLDEN_DIR)
    error_cases = [r for r in results if r.result is None and r.error is not None]
    assert error_cases


def test_fixture_results_are_deterministic_across_runs() -> None:
    first = run_all_cases(_GOLDEN_DIR)
    second = run_all_cases(_GOLDEN_DIR)
    assert [(r.case_id, r.final_ledger_hash) for r in first] == [
        (r.case_id, r.final_ledger_hash) for r in second
    ]
