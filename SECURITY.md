# Security Policy

The optional NautilusTrader adapter is offline-only: it verifies the exact
wheel digest and manifested inputs, clears secret/provider/proxy environment
variables, denies socket operations, and exposes no credential, live-client,
broker, subscription, or execution option. Reports always preserve
`execution_authorized: false` and `profitability_claimed: false`.

## Scope and non-goals

This project is a conformance toolkit: an immutable schema, artifact
integrity tooling and a hand-calculated golden oracle. It intentionally has
**no network client, no broker/MT5/live-data integration, no credential
handling and no execution authority**. `execution_authorized` is hard-coded
`Literal[False]` in the schema and cannot be set to `True` by configuration,
environment variable, CLI flag or parsing of untrusted input. If you find a
path that changes this, it is a critical vulnerability — report it
immediately (see below).

## Supported versions

Only the latest released minor version on the default branch receives
security fixes during the pre-1.0 phase.

| Version | Supported |
| ------- | --------- |
| 0.x (latest) | yes |
| < latest 0.x | no |

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub's "Report a
vulnerability" flow (Security Advisories) on this repository rather than a
public issue. Include:

- affected version/commit;
- minimal reproduction;
- expected vs. actual behavior;
- impact assessment (what an attacker could achieve).

We aim to acknowledge reports within 5 business days. Please do not disclose
publicly until a fix or mitigation is available.

## What counts as in-scope

- Any code path that could enable network access, credential exfiltration,
  process execution, or arbitrary file write/read outside a declared
  artifact/manifest boundary.
- Any code path that could cause `execution_authorized` to become `True`.
- Path traversal, symlink escape, or archive/zip-slip-style issues in the
  manifest or atomic-write tooling.
- Deserialization of untrusted JSON leading to code execution, resource
  exhaustion, or schema-validation bypass (e.g. NaN/Infinity smuggled into
  economic fields).

## Out of scope

- Findings in strategy/alpha logic — this repository contains none.
- Findings that require modifying the source before building (i.e. "if I
  change the code to do X, X happens").

## Hardening practices in this repository

- Dependencies are pinned and scanned with `pip-audit` and Bandit in CI
  (`.github/workflows/security.yml`) and CodeQL (`.github/workflows/codeql.yml`).
- All artifact writes are atomic (write-to-temp + fsync + replace) with
  containment checks against path traversal and symlink escape.
- All economic values are Decimal, serialized as strings; floats, NaN and
  Infinity are rejected at the schema boundary.
- Secrets are never logged, echoed, or included in evidence artifacts.
