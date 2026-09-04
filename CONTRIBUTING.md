# Contributing

Thank you for considering a contribution to `trading-engine-conformance`.
This project is a public-community-quality conformance toolkit — it
validates mechanics and disagreement between trading engines, never
profitability. Please read the [README](README.md) decision boundary before
proposing new scope.

## Ground rules

- **Clean-room only.** Do not copy source, tests, or fixtures from
  NautilusTrader, LEAN, QF-Lib, vectorbt, or any proprietary codebase. If you
  believe behavior should match a known engine, describe the behavior in
  your own words and derive tests from public specifications or hand
  calculations, not from reading that engine's source.
- **No execution authority, ever.** `execution_authorized` must remain
  `Literal[False]` everywhere. PRs that add any path to flip it — via
  config, environment variable, CLI flag, or otherwise — will be rejected.
- **No network, broker, MT5, or live-data code.** This toolkit is offline
  and deterministic by design.
- **Strict TDD.** Every new production behavior needs a failing test first,
  then the minimal implementation, then refactor while green. Please include
  the red/green command output in your PR description (or a short note in
  `docs/evidence/` if it's a substantial slice).
- **Decimal, not float, for economic fields.** New fields representing
  price, quantity, fees, or PnL must use the project's canonical Decimal
  type and be serialized as strings.
- **Fail closed.** Unknown/missing data, cost, timestamp, contract, or
  schema facts should raise, not silently degrade or default.

## Development setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test,security,dev]"   # Windows
.venv/bin/python -m pip install -e ".[test,security,dev]"           # POSIX
pre-commit install
```

Do not run `uv sync` on a host where `UV_PROJECT_ENVIRONMENT` points at a
shared environment; create and target this repository's own `.venv`.

## Running checks locally

```bash
.venv/Scripts/python.exe -m pytest --cov
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m bandit -c pyproject.toml -r src
.venv/Scripts/python.exe -m pip_audit
```

## Pull requests

1. One logical change per PR.
2. Add or update tests for every behavior change (unit, integration,
   property, CLI, or adversarial as appropriate).
3. Update `CHANGELOG.md` under "Unreleased".
4. Ensure `docs/` reflects any schema, CLI, or architecture change.
5. Do not include account IDs, credentials, proprietary strategy logic, or
   real market data in fixtures — golden fixtures are synthetic and prove
   mechanics only, never edge.

## Reporting security issues

See [SECURITY.md](SECURITY.md); do not open a public issue for suspected
vulnerabilities.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
