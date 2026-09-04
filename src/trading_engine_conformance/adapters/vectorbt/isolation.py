"""Manifest verification, environment scrubbing, and socket denial."""

from __future__ import annotations

import contextlib
import os
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from trading_engine_conformance.adapters.vectorbt.errors import (
    VectorbtInputError,
    VectorbtNetworkDeniedError,
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
_SENSITIVE_PREFIXES = (
    "ALPACA_",
    "AWS_",
    "AZURE_",
    "BINANCE_",
    "GITHUB_",
    "GOOGLE_",
    "IB_",
)


def sanitize_environment() -> tuple[str, ...]:
    """Remove credentials, provider settings, and proxies without reading values."""
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
    raise VectorbtNetworkDeniedError("network access is denied in the offline vectorbt worker")


@contextlib.contextmanager
def deny_network() -> Iterator[None]:
    """Patch common socket entry points fail-closed for the worker lifetime."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(socket, "create_connection", _network_denied))
        stack.enter_context(mock.patch.object(socket, "getaddrinfo", _network_denied))
        stack.enter_context(mock.patch.object(socket.socket, "connect", _network_denied))
        stack.enter_context(mock.patch.object(socket.socket, "connect_ex", _network_denied))
        yield


def validate_immutable_input(input_dir: Path, relative_path: str) -> Path:
    """Verify the complete directory manifest and return one declared local file."""
    if "://" in relative_path:
        raise VectorbtInputError("URLs are forbidden; only manifested local files are accepted")
    try:
        if input_dir.is_symlink():
            raise VectorbtInputError("input directory must not be a symlink")
        root = input_dir.resolve(strict=True)
        manifest_path = resolve_contained(root, "manifest.json")
        manifest = load_manifest(manifest_path)
        receipt = verify_manifest(root, manifest, verified_ts=0)
        if not receipt.ok:
            raise VectorbtInputError(
                "input manifest verification failed: "
                f"missing={receipt.missing}, extra={receipt.extra}, changed={receipt.changed}"
            )
        path = resolve_contained(root, relative_path)
        declared = {entry.relative_path for entry in manifest.entries}
        if relative_path not in declared:
            raise VectorbtInputError(
                f"requested path is not a declared manifest input: {relative_path!r}"
            )
        if not path.is_file():
            raise VectorbtInputError(f"declared input is not a regular file: {relative_path!r}")
        return path
    except VectorbtInputError:
        raise
    except (OSError, ValueError, PathContainmentError) as exc:
        raise VectorbtInputError(f"invalid immutable input or relative path: {exc}") from exc
