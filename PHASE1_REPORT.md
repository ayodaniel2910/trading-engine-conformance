# Phase 1 verification report

**Scope:** clean-room neutral schema, artifact integrity, hand-calculated Decimal golden oracle, no-network CLI and repository governance.

## Result

Phase 1 is complete and verified. This report certifies only conformance mechanics; it does not certify any strategy, profitability, paper trading or live operation.

## Implemented

- Versioned Pydantic models for exact instruments, datasets, run headers, market events, signals, orders, order transitions, fills, execution assumptions and ledger snapshots.
- Canonical JSON and streaming SHA-256.
- Deterministic `(timestamp, sequence)` ordering and duplicate rejection.
- Path-contained atomic writes, immutable manifests, tamper detection and verification receipts.
- Decimal golden oracle for market, limit, stop, stop-limit, partial fill, IOC/FOK/GTD, finite liquidity, adverse gaps, deterministic priority and explicit final liquidation.
- Ten human-readable golden fixtures, including deliberate invalid and no-look-ahead cases.
- `tec doctor`, schema export, validation, golden execution and manifest build/verify commands.
- Apache-2.0 community governance, contribution guide, security policy, CI and threat model.

## Verified commands and results

- Full suite: **313 passed**.
- Branch coverage: **96.83%**, gate 95%.
- Ruff check: passed.
- Ruff format check: passed; 76 files formatted.
- Strict mypy: passed across 31 source files.
- Bandit: passed with no reported finding.
- Pip audit after upgrading isolated-environment pip/setuptools: no known vulnerability; editable local distribution skipped because it is not on PyPI.
- Source distribution and wheel built successfully.
- `tec doctor`: Python/schema/fixtures valid, `execution_authorized` locked false, no network path, no live capability.
- All ten golden fixtures passed.

## Artifact evidence

- Phase directory: `artifacts/phase1/`
- Manifest SHA-256: `6a98ac95506c4a651c9334c0bb2c2120b7b2bb65f9dcda368a067e9f6118ef45`
- Manifest root hash: `f6b0acc3b17939f32694b3299b2ba46c532e2c89f9894bc31964426abb52c0fb`
- Verification receipt SHA-256: `fdfe848700c6270df46f61024759e670270719b913390c646c8f71a4c3536e05`
- Receipt hash: `4faf94d5db0fdba2cb0aebcd051fb6c59aa8f5306845128f5348544f2f965188`
- Verification result: `ok: true`; no missing, changed, extra, duplicate or case-collision path.

## Failure retained

A generated test originally claimed the first gap bar had partial liquidity while its helper hard-coded volume 1000. The order therefore correctly filled fully on the first bar, contradicting the test expectation. The fixture was corrected to volume 4 on the first bar and volume 20 on the second; the test now proves residual stop quantity continues at the next bar open. Production code was not weakened.

The first manifest attempt redirected command output into the directory being manifested, changing those files after hashing. The run was discarded and rebuilt with command receipts outside the manifest root. The final receipt is clean.

## Boundaries

- `execution_authorized` cannot become true.
- No network, credentials, broker, MT5, Databento live feed or process-control code exists.
- Continuous contracts cannot identify executable orders.
- No holdout-opening command exists.
- Golden rules are intentionally small and hand-calculable; they are not a complete exchange simulator.
- External adapters remain unimplemented at this phase.
- GOLD1/KILLZONE and every live fleet component were untouched.
