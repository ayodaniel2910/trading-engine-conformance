# Changelog

All notable changes to this project are documented in this file. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/) once it
reaches 1.0.

## [Unreleased]

### Added

- Phase 1: neutral immutable schema (run header, source revision,
  environment lock, dataset identity, instrument identity, market events,
  signals, order intents/transitions, fills, ledger snapshots, execution
  assumptions, holdout state, `execution_authorized: Literal[False]`).
- Canonical JSON serialization with deterministic key ordering and
  Decimal-as-string economic fields.
- Artifact and manifest integrity tooling: streaming SHA-256, atomic
  write-to-temp + fsync/replace, path-containment checks, manifest
  build/verify, verification receipts.
- Hand-calculated golden oracle covering market/limit/stop/stop-limit/OCO
  order lifecycles with explicit causal rules.
- No-network `tec` CLI: `schema export`, `validate`, `golden run`,
  `manifest build`, `manifest verify`, `doctor`.
- Unit, integration, property/metamorphic, CLI and adversarial test suites.
- Governance, security, contributing, and CI/CD scaffolding.
