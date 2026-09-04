"""Quarantined vectorbt 1.1.0 stage-zero family screener.

No vectorbt import occurs at package import time, preserving the core-only
installation boundary.
"""

from trading_engine_conformance.adapters.vectorbt.capabilities import (
    SUPPORTED_ENGINE,
    SUPPORTED_VECTORBT_VERSION,
    VectorbtCapability,
    probe_environment,
)

__all__ = [
    "SUPPORTED_ENGINE",
    "SUPPORTED_VECTORBT_VERSION",
    "VectorbtCapability",
    "probe_environment",
]
