"""Fresh-worker input verification, environment scrubbing and network denial."""

from __future__ import annotations

import contextlib
import os
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from trading_engine_conformance.adapters.nautilus.errors import (
    NautilusInputError,
    NautilusNetworkDeniedError,
)
from trading_engine_conformance.integrity.manifest import load_manifest, verify_manifest
from trading_engine_conformance.integrity.paths import PathContainmentError, resolve_contained

_SENSITIVE_FRAGMENTS = (
    "API_KEY",
    "APIKEY",
    "AUTH",
    "BROKER",
    "CREDENTIAL",
    "DATABENTO",
    "PASSWORD",
    "PROXY",
    "SECRET",
    "TOKEN",
)
_SENSITIVE_PREFIXES = ("ALPACA_", "AWS_", "AZURE_", "BINANCE_", "GOOGLE_", "IB_")


def sanitize_environment() -> tuple[str, ...]:
    """Remove provider, proxy and credential variables without reading values."""
    removed: list[str] = []
    for name in tuple(os.environ):
        upper = name.upper()
        if upper.startswith(_SENSITIVE_PREFIXES) or any(
            fragment in upper for fragment in _SENSITIVE_FRAGMENTS
        ):
            os.environ.pop(name, None)
            removed.append(name)
    return tuple(sorted(removed))


def _network_denied(*_args: Any, **_kwargs: Any) -> Any:
    raise NautilusNetworkDeniedError("network access is denied in the offline Nautilus worker")


@contextlib.contextmanager
def deny_network() -> Iterator[None]:
    """Temporarily replace all common socket entry points with fail-closed stubs."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(socket, "create_connection", _network_denied))
        stack.enter_context(mock.patch.object(socket, "getaddrinfo", _network_denied))
        stack.enter_context(mock.patch.object(socket.socket, "connect", _network_denied))
        stack.enter_context(mock.patch.object(socket.socket, "connect_ex", _network_denied))
        yield


def validate_immutable_input(input_dir: Path, relative_path: str) -> Path:
    """Verify a complete manifest and return one contained declared input path."""
    try:
        if input_dir.is_symlink():
            raise NautilusInputError("input directory must not be a symlink")
        root = input_dir.resolve(strict=True)
        manifest_path = resolve_contained(root, "manifest.json")
        manifest = load_manifest(manifest_path)
        receipt = verify_manifest(root, manifest, verified_ts=0)
        if not receipt.ok:
            raise NautilusInputError(
                "input manifest verification failed: "
                f"missing={receipt.missing}, extra={receipt.extra}, changed={receipt.changed}"
            )
        path = resolve_contained(root, relative_path)
        declared = {entry.relative_path for entry in manifest.entries}
        if relative_path not in declared:
            raise NautilusInputError(
                f"requested path is not a declared manifest input: {relative_path!r}"
            )
        if not path.is_file():
            raise NautilusInputError(f"declared input is not a regular file: {relative_path!r}")
        return path
    except NautilusInputError:
        raise
    except (OSError, ValueError, PathContainmentError) as exc:
        raise NautilusInputError(f"invalid immutable input or relative path: {exc}") from exc
