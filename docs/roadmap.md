# Roadmap

## Phase 1 (this repository, current)

- Neutral immutable schema covering run identity, instruments, market
  events, signals, orders, fills, and ledger snapshots.
- Artifact and manifest integrity tooling with tamper-evident verification.
- Hand-calculated golden oracle for order-lifecycle causal mechanics.
- No-network `tec` CLI and a public-community-quality governance baseline.

## Phase 2 (not started; separately scoped and approved)

- Offline, clean-room engine-adapter conformance harness: feed a golden case
  into an external engine adapter (starting with a NautilusTrader offline
  spike against one immutable cached DBN fixture, per the engine-portfolio
  decision) and diff its declared output against this schema/oracle.
- Cross-engine discrepancy ledger: append-only classification of every
  disagreement between two or more adapters on the same input, with no
  adapter permitted to review or resolve its own discrepancy.

## Phase 3+ (conceptual; requires its own approval and acceptance contract)

- Additional adapters (QF-Lib calculation-only surface, vectorbt stage-zero
  screening protocol, LEAN third-verifier once its environment gates close)
  per `ENGINE_PORTFOLIO_DECISION.md`.
- Independent human/agent review workflow for discrepancy ledgers.

## Explicit non-goals at every phase

- Live or paper trading execution.
- Signal generation, risk sizing, or promotion authority.
- Broker, MT5, or production credential handling.
- Profitability claims of any kind.
