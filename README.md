# trading-engine-conformance

An engine-neutral conformance toolkit for comparing trading-engine mechanics
without trusting any engine's native output.

## What this is

- A versioned, immutable, strictly-typed schema for run headers, instruments,
  market events, signals, order lifecycles, fills and ledger snapshots.
- Artifact and manifest integrity tooling: streaming SHA-256, atomic writes,
  path-containment checks and tamper-evident verification receipts.
- A small, hand-calculated, pure-Python Decimal **golden oracle** ledger that
  encodes causal execution rules (eligibility timestamps, same-timestamp
  ordering, gap handling, partial fills, fees, liquidation) independent of
  any external backtesting engine.
- A no-network CLI (`tec`) to export the schema, validate artifacts, run
  golden cases, build/verify manifests, and invoke an optional isolated
  NautilusTrader second verifier.

## What this is not

- **Not a trading bot.** There is no strategy, signal generation, or alpha
  logic here.
- **Not a production execution or promotion system.** `execution_authorized`
  is hard-coded `Literal[False]` everywhere in the schema and cannot be
  changed by configuration, environment variable, or CLI flag.
- **Not a broker, MT5, or live/paper trading integration.** There are no
  network-capable clients or credential options. The optional worker strips
  secret/provider variables and fails closed on socket operations.
- **Not a profitability claim.** This toolkit validates *mechanics* — that
  an engine's declared order lifecycle, fills and ledger are internally
  consistent and causally sound — and *disagreement* between engines. It
  never validates or implies that any strategy is profitable.

## Decision boundary

If you are looking for a way to decide whether a strategy should go live,
this is the wrong tool. If you are looking for a way to prove that two (or
more) backtesting/execution engines agree — or precisely how and why they
disagree — on the mechanical consequences of the same market data and order
intents, start here.

## Quick start

```bash
# From a clean checkout, using a local virtual environment (do not use a
# shared/global environment or one pointed to by UV_PROJECT_ENVIRONMENT).
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install -e ".[test,security,dev]"
# POSIX
.venv/bin/python -m pip install -e ".[test,security,dev]"

# Confirm the environment, schema, golden fixtures and no-network/no-execution
# posture:
tec doctor

# Export the current schema as JSON Schema documents:
tec schema export --out ./schema-export

# Validate an artifact against the schema:
tec validate path/to/artifact.json

# Run the hand-calculated golden oracle cases:
tec golden run all

# Build and verify a manifest binding a run directory's artifacts:
tec manifest build ./run-dir
tec manifest verify ./run-dir/manifest.json
```

## Optional NautilusTrader verifier

The Nautilus adapter accepts only the official CPython 3.13 Windows wheel at
v1.231.0 with SHA-256
`5fc8e08e98b6a47a5f0104c12ac6d8d3cefa0fd9dd2bb0d211c1b14517ff9aaf`.
It remains outside core dependencies and is an offline second verifier only.

```powershell
python -m pip install -e ".[test,dev]" path\to\nautilus_trader-1.231.0-cp313-cp313-win_amd64.whl
tec adapter nautilus doctor --wheel path\to\nautilus_trader-1.231.0-cp313-cp313-win_amd64.whl
tec adapter nautilus run --input-dir manifested-input --output-dir new-output
tec adapter nautilus compare-golden --golden-dir golden --profile-json explicit-profile.json --wheel path\to\wheel.whl --output-dir new-comparison
tec adapter nautilus decode-dbn --input-file cached.mbo.dbn.zst --expected-sha256 HASH --instrument-json exact-outright.json --wheel path\to\wheel.whl --output-dir new-decode
```

Every economics/execution profile field is required. Continuous contracts,
bar-path fill claims, one-sided quote coercion, unsupported order/event types,
timestamp reversal, precision loss, mutable/tampered inputs, live/API DBN
inputs, and output-directory reuse fail explicitly. Raw output is separate
from normalized output and all differences remain classified.

## Running the test suite

```bash
.venv/Scripts/python.exe -m pytest --cov
```

## Repository layout

- `src/trading_engine_conformance/schema/` — versioned typed models and JSON
  Schema export.
- `src/trading_engine_conformance/integrity/` — hashing, atomic writes,
  manifest build/verify, verification receipts.
- `src/trading_engine_conformance/golden/` — the hand-calculated Decimal
  reference ledger and case runner.
- `src/trading_engine_conformance/adapters/nautilus/` — pinned optional,
  fresh-process offline second verifier and local DBN/MBO decoder.
- `src/trading_engine_conformance/cli/` — the `tec` command-line interface.
- `golden/` — human-readable golden case fixtures (JSON) with hand
  calculations and expected hashes.
- `docs/` — architecture, threat model, accountability and roadmap docs.
- `tests/` — unit, integration, property/metamorphic, CLI and adversarial
  tests.

## Security and safety boundaries

See [SECURITY.md](SECURITY.md) and [docs/threat_model.md](docs/threat_model.md).
In summary: no network access, no credentials, no broker/MT5/live-data
integration, no execution authority, and no code path that can flip
`execution_authorized` to `True`.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
