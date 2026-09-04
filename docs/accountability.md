# Accountability

## Who this tool answers to

This toolkit produces evidence, not verdicts. It never approves a strategy,
never grants execution authority, and never ranks a holdout result. Every
artifact it emits is designed to be reviewed by a human (or a separate,
independent process) rather than acted on automatically.

## What "conformance" means here

A run artifact conforms to this schema if it validates against the current
major schema version, its timestamps and sequences are monotonic, its
economic fields are exact Decimal values, and its order/fill lifecycle is
internally consistent (no duplicate transitions, no impossible state
changes, residual quantity preserved on partial fills).

A golden case passes if replaying it through the reference ledger produces
byte-identical canonical JSON and a matching event/ledger hash to the
hand-calculated expected fixture.

Neither of these is a claim that a strategy works. They are claims that a
producer's *mechanics* are self-consistent and, once engine adapters exist,
that two producers' mechanics *agree or disagree* on a shared input in an
auditable, hash-verifiable way.

## Separation of duties

Consistent with the broader engine-portfolio decision this project
implements the first stage of: no engine, adapter, or component in this
architecture may certify itself. This repository:

- does not select, promote, or rank any strategy;
- does not open, see, or gate access to any sealed holdout (the schema only
  records a `HoldoutState` value; nothing here can transition it);
- does not have live, paper, or broker execution authority
  (`execution_authorized` is always `Literal[False]`);
- does not operate, configure, or restart any production process or fleet.

## Evidence, not automation

All verification, benchmark, and security evidence produced by this
project's own CI is written as machine-readable artifacts under
`artifacts/phase1/` (and future phases' equivalents) with the command,
exit code, environment, duration, and hashes recorded — so a human reviewer
can audit *how* a conclusion was reached, not just trust a green checkmark.

## Escalation

Suspected vulnerabilities: see [SECURITY.md](../SECURITY.md).
Suspected scope creep (e.g. a PR that tries to add network, broker, or
execution capability): reject in review; this is a hard boundary, not a
style preference.
