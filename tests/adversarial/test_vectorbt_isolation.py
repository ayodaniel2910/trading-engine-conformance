from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from trading_engine_conformance.adapters.vectorbt.errors import (
    VectorbtInputError,
    VectorbtNetworkDeniedError,
)
from trading_engine_conformance.adapters.vectorbt.isolation import (
    deny_network,
    sanitize_environment,
    validate_immutable_input,
)
from trading_engine_conformance.adapters.vectorbt.worker import run_worker
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest


@pytest.mark.adversarial
def test_vectorbt_environment_strips_secrets_proxies_and_provider_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = (
        "DATABENTO_API_KEY",
        "BINANCE_TOKEN",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
    )
    for name in names:
        monkeypatch.setenv(name, "secret")
    monkeypatch.setenv("TEC_BENIGN_TEST", "keep")
    removed = sanitize_environment()
    assert os.environ["TEC_BENIGN_TEST"] == "keep"
    assert set(names) <= set(removed)
    assert all(name not in os.environ for name in names)


@pytest.mark.adversarial
def test_vectorbt_worker_denies_socket_operations() -> None:
    with deny_network(), pytest.raises(VectorbtNetworkDeniedError):
        socket.create_connection(("127.0.0.1", 1))


@pytest.mark.adversarial
def test_vectorbt_input_rejects_url_traversal_tamper_and_undeclared_path(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "request.json").write_text("{}", encoding="utf-8")
    write_manifest(input_dir / "manifest.json", build_manifest(input_dir, created_ts=1))
    assert validate_immutable_input(input_dir, "request.json").is_file()
    for invalid in ("../request.json", "https://example.com/data.json", "file:///tmp/x"):
        with pytest.raises(VectorbtInputError):
            validate_immutable_input(input_dir, invalid)
    with pytest.raises(VectorbtInputError, match="declared"):
        validate_immutable_input(input_dir, "missing.json")
    (input_dir / "request.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(VectorbtInputError, match="manifest"):
        validate_immutable_input(input_dir, "request.json")


@pytest.mark.adversarial
def test_vectorbt_input_rejects_symlink_when_supported(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = input_dir / "request.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(VectorbtInputError):
        validate_immutable_input(input_dir, "request.json")


@pytest.mark.adversarial
def test_vectorbt_crash_cleans_staging_and_never_publishes_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "request.json").write_text("{}", encoding="utf-8")
    write_manifest(input_dir / "manifest.json", build_manifest(input_dir, created_ts=1))
    output_dir = tmp_path / "output"

    def crash(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected crash")

    monkeypatch.setattr("trading_engine_conformance.adapters.vectorbt.worker._execute", crash)
    with pytest.raises(RuntimeError, match="injected crash"):
        run_worker(input_dir, output_dir)
    assert not output_dir.exists()
    assert not list(tmp_path.glob(".output.staging-*"))
