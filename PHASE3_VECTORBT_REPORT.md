# Phase 3 vectorbt stage-zero screening report

Date: 2026-09-04 UTC  
Status: PASS  
Scope: quarantined, offline, development-only hypothesis-family screening

## Outcome

Phase 3 is complete. The adapter can reduce a preregistered development family
to entries labelled only `eligible_for_independent_reimplementation`. It cannot
open or evaluate a holdout, certify profitability or trades, authorize
promotion, declare paper/live readiness, access a broker, or submit an order.

The core package remains independent of NumPy, Numba, Plotly, pandas and
vectorbt. The optional stack imports only inside the worker/benchmark execution
path. A separate CI job installs it in a fresh CPython 3.13 environment.

## Implemented contract

- Frozen, strict request/result models bind hypothesis and family IDs, an
  immutable dataset SHA-256 and byte size, one development partition, the total
  trial budget, every variant and parameter set, explicit compute/availability/
  execution timestamps, costs, assumptions, seed, engine label and output
  label.
- `holdout_state` must be `SEALED`; opened state and any undeclared holdout data
  are rejected by validation.
- Only `engine="numba"` is representable. Capability probing rejects `auto`,
  `rust`, vectorbt versions other than 1.1.0, Plotly 7+, absent assumptions,
  absent cost fields, and any installed `vectorbt-rust` distribution.
- Signals execute only at the first declared event strictly after their
  availability timestamp. Same-bar execution, missing timestamps, non-event
  computation times and skipped execution boundaries fail closed.
- The worker accepts only complete verified manifests and contained local
  files. It rejects URLs, traversal, symlinks, undeclared files, hash/size
  mismatch and tamper. Parent and child strip secret/provider/proxy variables;
  the child denies socket resolution/connect entry points.
- Output is built in a new sibling staging directory and atomically renamed.
  Crashes remove staging and cannot publish a partial run.
- Every declared trial is emitted, including preflight and engine/parity
  failures. Completeness verification rejects missing, duplicate, unexpected or
  budget-mismatched trials, changed parameters/costs, illegal labels and digest
  tamper. Ranking is explicitly `development_only`; failures are never hidden.
- Final equity, net profit, return, gross buy-and-hold baseline, turnover,
  drawdown, costs and trade count are recomputed with an independent exact
  `Decimal` ledger. vectorbt output is only a final-equity parity check and is
  never the sole metric authority.

CLI surface:

```text
tec adapter vectorbt doctor
tec adapter vectorbt screen
tec adapter vectorbt verify-ledger
tec adapter vectorbt benchmark
```

There is no holdout-open, live, broker, signal-generation or promotion flag.

## Dependency and engine gate

The optional extra declares `vectorbt==1.1.0` and `plotly>=4.12,<7`. The audited
resolved direct stack is recorded in `requirements/vectorbt-resolved.txt`:
NumPy 2.5.2, pandas 3.0.5, SciPy 1.18.1, Matplotlib 3.11.1, Plotly 6.9.0,
Numba 0.67.0 and the remaining vectorbt direct dependencies. Rust is absent.

The environment doctor passed with:

```text
Python 3.13.14
vectorbt 1.1.0
Plotly 6.9.0
Numba 0.67.0
engine numba
vectorbt-rust absent
```

Read-only external evidence was verified at source commit
`34b6d5935e3ea3eccd549e2592bc0f455b8045f5`; the vault SHA-256 manifest also
verified. The earlier audit's Plotly 7 import break and four catastrophic Rust
rolling-standard-deviation failures are preserved as reasons for the upper
bound, explicit Numba dispatch and Rust denial. Neither external tree has a
tracked modification.

## TDD and correctness evidence

The required red phase was observed first: five test modules failed collection
because the vectorbt adapter package did not exist. Implementation followed the
tests. The final suites are:

- Core CPython 3.11 suite: 443 collected, 437 passed, 6 optional-adapter skips,
  2.55 seconds. Branch-aware coverage: 95.66% (1,398/1,441 lines and 256/288
  branches covered).
- Optional CPython 3.13/vectorbt suite: 443 collected, 440 passed, 3 Nautilus
  optional skips, 9.32 seconds. Adapter branch-aware coverage: 95.56%
  (645/668 lines and 152/166 branches covered).
- The vectorbt suite includes real explicit-Numba execution, independent metric
  parity, a complete fresh worker, repeat semantic digest, and the 2,000,000-cell
  performance test.

Tests explicitly cover Numba enforcement; Rust/auto denial; Plotly 7 denial;
missing, duplicate and budget-mismatched trials; future mutation invariance;
same-bar denial; fee/slippage arithmetic; NaN/infinity rejection;
reproducibility; traversal, URL, symlink and tamper rejection; environment
stripping; socket denial; crash cleanup; output-label limits; and independent
metric parity.

Machine-readable test and coverage evidence is in `artifacts/phase3/`.

## Security and quality gates

All required gates passed on the final implementation:

| Gate | Exact result |
|---|---|
| Ruff format | 116 files already formatted |
| Ruff lint | zero findings |
| strict mypy | success, 53 source files |
| Bandit | 0 high, 0 medium, 0 low; 0 issues |
| core pip-audit | 61 dependencies, 0 known vulnerabilities |
| vectorbt pip-audit | 108 dependencies, 0 known vulnerabilities |
| core branch-aware coverage | 95.66% |
| adapter branch-aware coverage | 95.56% |
| sdist/wheel build | both built successfully |
| fresh core wheel | installed offline; core doctor passed; vectorbt doctor correctly failed closed |
| fresh vectorbt wheel | installed offline with local pinned vectorbt source; doctor, screen and ledger verification passed; Rust absent |

The first offline fresh-wheel resolver attempt could not identify the locally
built vectorbt source as a registry cache candidate. The final successful smoke
supplied the same verified read-only source tree explicitly; no network or Rust
dependency was used. A benchmark artifact serialization attempt also correctly
failed because canonical JSON forbids binary floats. Durations and thresholds
were changed to deterministic decimal strings, no partial artifact existed, and
the rerun passed.

## Performance gate

The recorded synthetic benchmark used 5,000 rows by 400 strategy columns:

- strategy cells: 2,000,000;
- first pass (includes compilation): 5.391861000 seconds;
- second pass: 0.094036800 seconds;
- matching semantic digest:
  `a283ea4f4a85c8bcdf82be890ec9f29ea7c0a531106e5f3610e556d1946378e6`;
- finite outputs: 400/400 on both passes;
- conservative observed memory bound: 230,842,558 bytes;
- limits: 120 seconds per pass and 1,073,741,824 bytes.

This is synthetic throughput and reproducibility evidence only. It is not
strategy, profitability, fill, execution or promotion evidence.

## Screening artifact

The manifested synthetic smoke declared four trials and emitted all four:
three completed and one intentionally invalid next-event lag failure. Ledger
verification found zero missing, duplicate or unexpected trials. The source and
fresh-wheel runs produced the same semantic digest:
`0a07b0807fe12ddd62db2966902653bae24bafacadd038e23a8c356b5096dc67`.

No holdout data, credential, live data, broker, MT5, fleet, GOLD1 or KILLZONE
path was accessed.

## Artifact map

- `doctor.json` — accepted dependency/engine posture.
- `benchmark.json` — deterministic 2,000,000-cell performance/memory result.
- `screen_input/` — synthetic development-only request, dataset and manifest.
- `screen_output/` — complete trial ledger, metadata, performance and manifest.
- `wheel_screen_output/` — independent fresh-wheel screening output.
- `ledger_verification.json` — semantic complete-family receipt.
- `core-tests.xml`, `core-coverage.json` — complete core suite evidence.
- `vectorbt-tests.xml`, `vectorbt-coverage.json` — optional adapter suite evidence.
- `ruff.json`, `mypy.xml`, `bandit.json` — quality/security evidence.
- `pip-audit-core.json`, `pip-audit-vectorbt.json` — dependency audit evidence.
- `distributions/` — built wheel and source distribution.
- `verification_summary.json` — concise machine-readable gate summary.
- `manifest.json` — SHA-256/size binding for all Phase 3 artifacts.
- `../phase3_verification_receipt.json` — clean verification receipt outside the
  manifested directory, avoiding a circular self-hash.

## Limitations

Vectorbt remains an approximate array simulator and screening accelerator. It
does not model market depth, queue position, finite venue liquidity, causal
intrabar paths, futures settlement/margin/rolls, broker reconciliation or
point-in-time production calendars. Cheap family breadth increases selection
bias; the complete ledger does not make the selected family statistically or
economically valid. Each survivor requires an independent causal
reimplementation and later truth-engine validation. The sealed outer holdout
remains outside this adapter. No result here certifies profitability, a trade,
paper readiness, live readiness or promotion.
