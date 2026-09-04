# Phase 2 NautilusTrader offline verifier report

## Result

Phase 2 is complete and all required gates pass. The adapter accepts only the
exact NautilusTrader v1.231.0 CPython 3.13 Windows wheel as an isolated,
offline second verifier. It is not a source of truth, strategy authority,
profitability evidence, paper/live readiness, or execution permission.

Every emitted Phase 2 artifact declares `execution_authorized: false` and
`profitability_claimed: false`.

## Exact accepted runtime and provenance

- Runtime: CPython 3.13.14, Windows x86-64, standard-precision wheel.
- Package: `nautilus_trader==1.231.0`.
- Wheel: `nautilus_trader-1.231.0-cp313-cp313-win_amd64.whl`.
- Wheel size from the acceptance audit: 112,708,191 bytes.
- Required and independently rechecked wheel SHA-256:
  `5fc8e08e98b6a47a5f0104c12ac6d8d3cefa0fd9dd2bb0d211c1b14517ff9aaf`.
- Upstream tag commit recorded by the read-only acceptance audit:
  `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`.
- Local Phase 1 base: `398b74b779be71ebbd52ff9ab6863dadbcac875e`.

The external evaluation tree remained read-only. Its minimal `.venv` lacked
this project's Pydantic dependency, so implementation tests used a disposable
Python 3.13 adapter environment inside this repository, populated from the
already verified local wheel. Core gates continued to use the project `.venv`.
No live tree, terminal, service, paid API, broker, GOLD1, or KILLZONE component
was read for execution or modified.

## Implementation

- Optional adapter package with an exact version/platform/Python/wheel probe.
- Required explicit research profile for fees, initial/maintenance margin,
  latency, fill model, queue model, finite-event liquidity consumption,
  limit-fill/slippage probabilities, trade execution, stop rejection,
  settlement, session timezone, seed, underlying, asset class, and lot size.
  Zero/omitted economic values fail and no matching-engine default is accepted.
- Exact Decimal/string translators for neutral instrument, trade, quote,
  book-delta, order, fill, and ledger boundaries. Precision loss, missing
  metadata, continuous instruments, one-sided quotes, unsupported order/event
  types, linked/OCO loss, and timestamp ambiguity/reversal fail explicitly.
- Fresh-process worker restricted to verified, manifest-declared, contained
  immutable paths. It strips secret/provider/proxy environment variables,
  denies socket operations, contains no live client/broker/subscription option,
  preserves upstream raw events separately, and atomically renames a new output
  directory only after success. Crash paths remove staging output.
- Local DBN/MBO decoder that accepts one explicit file and expected SHA-256,
  rejects URL/live/API/symlink/tampered input, keeps native flags/order IDs in
  raw output, and emits exact timestamp/sequence neutral deltas plus a manifest.
- CLI surface: `tec adapter nautilus doctor`, `run`, `decode-dbn`, and
  `compare-golden`. No credential, broker, subscription, or live flag exists.
- Version-pinned optional `nautilus` dependency extra and a separate Windows
  CPython 3.13 CI job which downloads, verifies, and tests the wheel in isolation.

## Golden comparison and discrepancies

The hand oracle is evaluated first and remains independent. Raw Nautilus events
are retained; normalized outputs never hide a difference. Bar-path cases are
explicitly non-authoritative and excluded.

### `001_market_buy_full_fill`

- Semantic digest:
  `36a65acabd08d7388ae860e515e09071624c50393fc8677b8cae6f4aa45445b6`.
- One `execution_model_choice` discrepancy: the hand oracle fills the first
  eligible trade, while the Nautilus L1 matching engine rejects a market order
  submitted without a pre-existing top-of-book. No synthetic quote was added.

### `002_limit_buy_partial_then_full`

- Semantic digest:
  `4b27660ade0b432599c9962b5a8b889e25e99f9c0a2b1414a5a465d5e6fb0b7d`.
- Prices and quantities agree: two fills at 2000.5 for quantities 4 and 6.
- Two `accounting_convention` discrepancies: Nautilus applies the futures
  multiplier of 100 to commission (`800.2`, `1200.3`), while the deliberately
  small hand oracle formula yields `8.0020`, `12.0030`.
- Two `execution_model_choice` discrepancies: Nautilus classifies the resting
  limit fills as maker; the simple hand oracle labels every fill taker.

These are preserved classifications, not evidence that either convention is
universally correct. There are no unresolved or silently normalized differences.

## DBN/MBO evidence and performance

- Input fixture:
  `esh4-glbx-mdp3-20231224.mbo.dbn.zst`.
- Verified SHA-256:
  `f186e479ad0c381c40ef35384c4125d2088fb11f4ac31b0558da3fdaadb0317c`.
- Size: 53,814 bytes.
- Decoded neutral book deltas: 8,725.
- Semantic digest:
  `a15afeaf2624a41b7e86ec9bfa535212b8d2d66230f39560cfc096d0ae127eb3`.
- Recorded decode duration: 1.928478000 seconds; threshold 60 seconds.
- Recorded peak traced memory: 49,941,207 bytes; threshold 1,073,741,824 bytes.
- Golden market smoke: 2 inputs, 1.661237700 seconds, 50,060,641 peak traced bytes.
- Golden partial-limit smoke: 3 inputs, 1.635915900 seconds, 50,062,933 peak traced bytes.
- Explicit `run` smoke: 3 inputs, 1.616068400 seconds, 50,062,261 peak traced bytes.
- Two-run integration checks reproduced all three semantic digests exactly.

The raw timestamp mapping remains declared: the pinned Nautilus Databento
loader maps DBN receive time into its `ts_event`; the adapter retains native raw
records and labels neutral `exchange_ts <- ts_event` and
`receive_ts <- ts_init`. This fixture is ESH4, not GC/MGC, and validates only
the offline decoder mechanics.

## Tests and gates

- Full Phase 1 + Phase 2 suite: **382 passed**.
- Branch coverage: **95.43%**, gate **95%**.
- Ordinary core/optional-dependency-absent suite: **379 passed, 3 skipped**,
  **96.85%** coverage.
- New tests cover unit, contract, property, adversarial, CLI, deterministic
  benchmark, and optional real-wheel integration paths.
- Ruff: pass; 97 files formatted.
- Ruff format check: pass.
- Strict mypy: pass across 43 source files.
- Bandit: pass, zero findings after documenting the fixed interpreter/module,
  `shell=False` fresh-worker launch.
- Core `pip-audit`: no known vulnerabilities; local unpublished package skipped.
- Adapter `pip-audit`: no known vulnerabilities; local unpublished package skipped.
- Sdist and wheel build: pass.
- Fresh-wheel smoke: pass from a newly created CPython 3.13 environment for
  core doctor and all four Nautilus adapter commands.

Built distributions:

- Wheel: 66,972 bytes, SHA-256
  `cda129593732501791b3eb016bd25ec43a666129083ebb1eada8498b4e1eed33`.
- Sdist: 579,589 bytes, SHA-256
  `093eb920f8a72d17f1f7fb795189b72cb1a9824e43622657c018a47cab193db2`.

## Artifact integrity

- Phase directory: `artifacts/phase2/`.
- Manifest entries: 29.
- Manifest SHA-256:
  `ffd7dd663243af4f44bbd252bb3441e92c264cb6e579e69e146c8e206e8452c5`.
- Manifest root hash:
  `74faa2cb0185e170339a6df10bed2bd6b5f1d87ffee2d4afae9869ee38cca167`.
- Verification receipt hash:
  `55e97db46a641dba7baf71f297da79ff9fc8f629ceb83d7622c391ce471b75e7`.
- Verification: clean; no missing, extra, changed, duplicate, case-collision, or
  root-hash mismatch findings.

## Limits and non-claims

- This adapter is a heterogeneous second verifier, never the truth authority.
- Agreement between the engines would not prove correctness; the hand oracle
  and independent source evidence remain necessary.
- No bar-path result is authoritative because an OHLC traversal invents
  intrabar ordering.
- L1 finite-trade diagnostics do not establish exchange queue priority, hidden
  liquidity, latency, missed events, settlement, fees, margin, or live parity.
- Continuous instruments cannot identify executable orders. No roll-policy,
  GC/MGC economics, profitability, paper readiness, or live readiness is
  certified here.
- No output authorizes execution, and no new command can alter that boundary.
