"""Exact capability and provenance probe for the accepted wheel."""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from trading_engine_conformance.adapters.nautilus.errors import NautilusEnvironmentError
from trading_engine_conformance.hashing import sha256_file

SUPPORTED_IMPLEMENTATION = "CPython"
SUPPORTED_PYTHON = (3, 13)
SUPPORTED_PLATFORM = "Windows"
SUPPORTED_VERSION = "1.231.0"
SUPPORTED_WHEEL_SHA256 = "5fc8e08e98b6a47a5f0104c12ac6d8d3cefa0fd9dd2bb0d211c1b14517ff9aaf"
SUPPORTED_WHEEL_FILENAME = "nautilus_trader-1.231.0-cp313-cp313-win_amd64.whl"
_AUTO_VERSION = "<auto-detect>"


@dataclass(frozen=True)
class NautilusCapability:
    ok: bool
    dependency_present: bool
    package_version: str | None
    implementation: str
    python_version: str
    platform_system: str
    wheel_path: str | None
    wheel_sha256: str | None
    wheel_hash_verified: bool
    failures: tuple[str, ...]
    execution_authorized: bool = False
    profitability_claimed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "dependency_present": self.dependency_present,
            "package_version": self.package_version,
            "implementation": self.implementation,
            "python_version": self.python_version,
            "platform_system": self.platform_system,
            "wheel_path": self.wheel_path,
            "wheel_sha256": self.wheel_sha256,
            "wheel_hash_verified": self.wheel_hash_verified,
            "failures": list(self.failures),
            "supported_environment": {
                "implementation": SUPPORTED_IMPLEMENTATION,
                "python": f"{SUPPORTED_PYTHON[0]}.{SUPPORTED_PYTHON[1]}",
                "platform": SUPPORTED_PLATFORM,
                "version": SUPPORTED_VERSION,
                "wheel_filename": SUPPORTED_WHEEL_FILENAME,
                "wheel_sha256": SUPPORTED_WHEEL_SHA256,
            },
            "execution_authorized": self.execution_authorized,
            "profitability_claimed": self.profitability_claimed,
        }


def _installed_version() -> str | None:
    try:
        return importlib.metadata.version("nautilus_trader")
    except importlib.metadata.PackageNotFoundError:
        return None


def probe_environment(
    *,
    wheel_path: Path | None = None,
    package_version: str | None = _AUTO_VERSION,
    implementation: str | None = None,
    python_version: tuple[int, int] | None = None,
    platform_system: str | None = None,
    raise_on_failure: bool = False,
) -> NautilusCapability:
    """Probe the exact supported runtime and, when supplied, wheel digest.

    A wheel path is mandatory for a successful probe: an installed package
    version alone cannot prove which artifact was installed.
    """
    actual_version = _installed_version() if package_version == _AUTO_VERSION else package_version
    actual_impl = implementation or platform.python_implementation()
    actual_py = python_version or (sys.version_info.major, sys.version_info.minor)
    actual_platform = platform_system or platform.system()
    failures: list[str] = []

    if actual_version is None:
        failures.append("NautilusTrader dependency is absent")
    elif actual_version != SUPPORTED_VERSION:
        failures.append(
            f"NautilusTrader version mismatch: expected {SUPPORTED_VERSION}, got {actual_version}"
        )
    if actual_impl != SUPPORTED_IMPLEMENTATION:
        failures.append(
            f"implementation mismatch: expected {SUPPORTED_IMPLEMENTATION}, got {actual_impl}"
        )
    if actual_py != SUPPORTED_PYTHON:
        failures.append(
            "Python version mismatch: expected "
            f"{SUPPORTED_PYTHON[0]}.{SUPPORTED_PYTHON[1]}, got {actual_py[0]}.{actual_py[1]}"
        )
    if actual_platform != SUPPORTED_PLATFORM:
        failures.append(f"platform mismatch: expected {SUPPORTED_PLATFORM}, got {actual_platform}")

    wheel_digest: str | None = None
    wheel_display: str | None = None
    if wheel_path is None:
        failures.append("wheel path is required to verify the pinned SHA-256")
    else:
        try:
            resolved_wheel = wheel_path.resolve(strict=True)
            wheel_display = str(resolved_wheel)
            wheel_digest, _ = sha256_file(resolved_wheel)
        except OSError as exc:
            failures.append(f"could not read wheel for SHA-256 verification: {exc}")
        else:
            if wheel_digest != SUPPORTED_WHEEL_SHA256:
                failures.append(
                    f"wheel SHA-256 mismatch: expected {SUPPORTED_WHEEL_SHA256}, got {wheel_digest}"
                )

    result = NautilusCapability(
        ok=not failures,
        dependency_present=actual_version is not None,
        package_version=actual_version,
        implementation=actual_impl,
        python_version=f"{actual_py[0]}.{actual_py[1]}",
        platform_system=actual_platform,
        wheel_path=wheel_display,
        wheel_sha256=wheel_digest,
        wheel_hash_verified=wheel_digest == SUPPORTED_WHEEL_SHA256,
        failures=tuple(failures),
    )
    if raise_on_failure and not result.ok:
        raise NautilusEnvironmentError("; ".join(result.failures))
    return result
