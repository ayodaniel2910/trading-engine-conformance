# Threat Model

## Assets to protect

1. **Integrity of comparison results.** A tampered or silently-corrupted
   artifact must never be accepted as valid input to a conformance
   comparison.
2. **The `execution_authorized = False` invariant.** No parsing path,
   configuration surface, environment variable, or CLI flag may cause any
   artifact to be treated as authorizing live or paper execution.
3. **Host boundaries.** Production trading infrastructure (`C:/IPDA_GOLD`,
   KILLZONE, MT5 terminals, broker credentials, live bot trees, production
   ledgers, running processes) must be unreachable from this codebase.
4. **Supply chain.** Dependencies must be pinned, scanned, and free of code
   that could smuggle network or execution behavior into a "no-network"
   tool.

## Explicitly out of scope (by design, not oversight)

- Confidentiality of market data — fixtures are synthetic and public-safe.
- Availability/DoS of any live system — there is no live system here.
- Authentication/authorization of human users — this is a local CLI/library,
  not a service.

## Trust boundaries and adversarial inputs

| Boundary | Threat | Mitigation |
|---|---|---|
| JSON artifact parsing | Float/NaN/Infinity smuggled into economic fields | Economic fields use a strict Decimal type; float input is rejected at validation, not coerced |
| JSON artifact parsing | Unknown fields silently accepted, masking a bad producer | All models use `extra="forbid"` |
| JSON artifact parsing | Non-monotonic or out-of-order event/sequence data reordering causal outcomes | Explicit monotonic sequence + timestamp ordering validation; same-timestamp ties resolved deterministically by sequence, not by input order |
| Manifest paths | Path traversal (`../..`), absolute paths, symlink escape | `integrity.paths` containment checks reject all three before any read/write |
| Manifest paths | Case-colliding paths silently overwrite on case-insensitive filesystems (Windows/macOS) | Manifest verification explicitly rejects case collisions |
| Artifact writes | Process crash mid-write leaves a partially-written file that looks valid | Atomic write-to-temp + fsync + rename/replace; no partial file is ever visible under its final name |
| Manifest verification | Missing, extra, changed, or duplicate entries silently ignored | Verification enumerates and rejects each category explicitly and reports which |
| Schema evolution | An old/unknown major schema version silently misinterpreted by a newer or older tool | Explicit `schema_version` dispatch; unknown major versions fail closed |
| CLI | Secrets echoed into logs/JSON output | No credential-bearing fields exist in the schema; CLI has no code path that reads credentials |
| Dependency supply chain | A compromised or vulnerable dependency introduces network or exec behavior | Locked, minimal dependency set; `pip-audit`, Bandit, and CodeQL run in CI |
| `execution_authorized` | Any future change accidentally makes it settable | It is typed `Literal[False]` (not `bool`) at the schema level, so no valid input value other than `False` type-checks or validates; adversarial tests assert this cannot change via parsing, environment, or CLI |

## Residual risk

- This is a Phase 1 foundation; no engine adapters exist yet, so
  cross-engine discrepancy classification is not yet implemented (tracked
  in [roadmap.md](roadmap.md)).
- Golden fixtures are synthetic and intentionally do not encode proprietary
  TradingOps strategy edge; they prove causal mechanics only.
