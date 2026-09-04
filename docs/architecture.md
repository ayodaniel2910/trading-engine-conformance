# Architecture

## Purpose

This toolkit gives multiple trading-engine adapters (built elsewhere, later,
under separately approved plans) one shared, independently-defined contract
to emit data into, and one hand-calculated oracle to check causal mechanics
against. It validates **mechanics and disagreement between engines** — never
profitability, and never a signal to trade.

## Layers

```text
schema/       versioned, strictly-typed, immutable data contract
integrity/    hashing, atomic writes, manifest binding, verification receipts
golden/       hand-calculated Decimal reference ledger ("the oracle")
cli/          no-network `tec` command surface over the above
```

### `schema/`

Pydantic v2 models with `extra="forbid"`, canonical Decimal-as-string
economic fields, bounded UTC-nanosecond integer timestamps, and explicit
schema-version dispatch. Every top-level run artifact carries
`execution_authorized: Literal[False]`; nothing in this package can change
that value.

Core objects: `RunHeader`, `SourceRevision`, `EnvironmentLock`,
`DatasetIdentity`, `InstrumentIdentity`, market events (`Quote`, `Trade`,
`BookDelta`, `BookSnapshot`, `Bar`, `SessionStatusEvent`,
`SettlementEvent`), `Signal`, `OrderIntent`, `OrderStateTransition`, `Fill`,
ledger snapshots (`CashSnapshot`, `PositionSnapshot`, `MarginSnapshot`,
`PnLSnapshot`), `ExecutionAssumptions`, `HoldoutState`, and the top-level
`RunArtifact` envelope that binds all of the above together with a
deterministic seed and tool-version record.

### `integrity/`

Streaming SHA-256 and byte counting for large files without loading them
into memory; a `Manifest`/`ManifestEntry` schema binding every declared
input/output artifact's relative path, size and hash; atomic
write-to-temp-then-fsync-then-replace so a crash never leaves a partially
written file visible under its final name; path-containment checks that
reject traversal (`..`), absolute paths, symlink escape, and case-colliding
duplicate paths on case-insensitive filesystems; and a `VerificationReceipt`
that itself has a deterministic hash so the verification result is tamper
evident.

### `golden/`

A small, pure-Python, `Decimal`-only reference ledger. It is **not** a
production simulator — it exists to encode a small number of unambiguous,
hand-calculable causal rules (eligibility timestamps, same-timestamp
ordering, bid/ask exit sides, adverse-gap fills, TP/SL simultaneity,
partial fills, finite liquidity, fees/rounding, forced liquidation) that any
conforming engine adapter must also satisfy. Golden cases live in `golden/`
as human-readable JSON fixtures with hand calculations and expected
event/ledger hashes, so a human reviewer — not just a test runner — can
check the oracle's arithmetic.

### `cli/`

`tec` wraps the above with a no-network, no-secret-echoing command surface:
`schema export`, `validate`, `golden run`, `manifest build`,
`manifest verify`, `doctor`. All commands support `--json` output and use
stable, documented exit codes so they can be scripted in CI by future
engine-adapter projects without depending on stdout text formatting.

## What is explicitly out of scope here

- Engine adapters (NautilusTrader/LEAN/QF-Lib/vectorbt or any other engine).
- Any network, broker, MT5, or live/paper data path.
- Any signal, risk, sizing, or promotion authority.
- Any code path that reads `C:/IPDA_GOLD`, KILLZONE, or other production
  bot trees, ledgers, or running processes.

See [threat_model.md](threat_model.md) for the enumerated boundary and
[accountability.md](accountability.md) for how disagreement is classified
and who is responsible for reviewing it.
