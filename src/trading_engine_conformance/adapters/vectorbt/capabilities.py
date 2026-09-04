"""Metadata-only probe for the exact accepted vectorbt/Numba environment."""

from __future__ import annotations

import importlib.metadata
import re
from dataclasses import dataclass

from trading_engine_conformance.adapters.vectorbt.errors import VectorbtEnvironmentError
from trading_engine_conformance.adapters.vectorbt.models import ScreeningCosts

SUPPORTED_VECTORBT_VERSION = "1.1.0"
SUPPORTED_ENGINE = "numba"
MIN_PLOTLY = (4, 12, 0)
MAX_PLOTLY_MAJOR = 7
_AUTO = "<auto-detect>"


def _installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value)[:3])


@dataclass(frozen=True)
class VectorbtCapability:
    ok: bool
    engine: str
    vectorbt_version: str | None
    plotly_version: str | None
    numba_version: str | None
    rust_version: str | None
    rust_present: bool
    assumptions_pinned: bool
    costs_complete: bool
    failures: tuple[str, ...]
    execution_authorized: bool = False
    profitability_claimed: bool = False
    holdout_access: bool = False
    promotion_authorized: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "engine": self.engine,
            "vectorbt_version": self.vectorbt_version,
            "plotly_version": self.plotly_version,
            "numba_version": self.numba_version,
            "rust_version": self.rust_version,
            "rust_present": self.rust_present,
            "assumptions_pinned": self.assumptions_pinned,
            "costs_complete": self.costs_complete,
            "failures": list(self.failures),
            "accepted": {
                "engine": SUPPORTED_ENGINE,
                "vectorbt": SUPPORTED_VECTORBT_VERSION,
                "plotly": ">=4.12,<7",
                "rust": "absent",
            },
            "execution_authorized": self.execution_authorized,
            "profitability_claimed": self.profitability_claimed,
            "holdout_access": self.holdout_access,
            "promotion_authorized": self.promotion_authorized,
        }


def probe_environment(
    *,
    engine: str,
    vectorbt_version: str | None = _AUTO,
    plotly_version: str | None = _AUTO,
    numba_version: str | None = _AUTO,
    rust_version: str | None = _AUTO,
    assumptions_pinned: bool,
    costs: ScreeningCosts | None,
    raise_on_failure: bool = False,
) -> VectorbtCapability:
    """Fail closed unless every dependency and semantic precondition is explicit."""
    actual_vectorbt = (
        _installed_version("vectorbt") if vectorbt_version == _AUTO else vectorbt_version
    )
    actual_plotly = _installed_version("plotly") if plotly_version == _AUTO else plotly_version
    actual_numba = _installed_version("numba") if numba_version == _AUTO else numba_version
    actual_rust = _installed_version("vectorbt-rust") if rust_version == _AUTO else rust_version
    failures: list[str] = []
    if engine != SUPPORTED_ENGINE:
        failures.append(f"engine must be explicit numba; {engine!r} is forbidden")
    if actual_vectorbt is None:
        failures.append("vectorbt dependency is absent")
    elif actual_vectorbt != SUPPORTED_VECTORBT_VERSION:
        failures.append(
            "vectorbt version mismatch: expected "
            f"{SUPPORTED_VECTORBT_VERSION}, got {actual_vectorbt}"
        )
    if actual_plotly is None:
        failures.append("Plotly dependency is absent")
    else:
        plotly_parts = _version_tuple(actual_plotly)
        if plotly_parts < MIN_PLOTLY or plotly_parts[0] >= MAX_PLOTLY_MAJOR:
            failures.append(f"Plotly must satisfy >=4.12,<7; got {actual_plotly}")
    if actual_numba is None:
        failures.append("Numba dependency is absent")
    if actual_rust is not None:
        failures.append(f"Rust dependency is forbidden; vectorbt-rust {actual_rust} is installed")
    if not assumptions_pinned:
        failures.append("all screening assumptions must be pinned")
    if costs is None:
        failures.append("all cost fields must be present and validated")

    result = VectorbtCapability(
        ok=not failures,
        engine=engine,
        vectorbt_version=actual_vectorbt,
        plotly_version=actual_plotly,
        numba_version=actual_numba,
        rust_version=actual_rust,
        rust_present=actual_rust is not None,
        assumptions_pinned=assumptions_pinned,
        costs_complete=costs is not None,
        failures=tuple(failures),
    )
    if raise_on_failure and not result.ok:
        raise VectorbtEnvironmentError("; ".join(result.failures))
    return result
