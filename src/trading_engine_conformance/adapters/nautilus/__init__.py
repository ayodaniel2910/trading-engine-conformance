"""NautilusTrader v1.231.0 offline second-verifier adapter.

The package deliberately performs no Nautilus import at module import time,
so the core toolkit stays usable without the optional dependency.
"""

from trading_engine_conformance.adapters.nautilus.capabilities import (
    SUPPORTED_VERSION,
    SUPPORTED_WHEEL_SHA256,
    NautilusCapability,
    probe_environment,
)

__all__ = [
    "SUPPORTED_VERSION",
    "SUPPORTED_WHEEL_SHA256",
    "NautilusCapability",
    "probe_environment",
]
