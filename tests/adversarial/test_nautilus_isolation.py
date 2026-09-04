from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from trading_engine_conformance.adapters.nautilus.errors import (
    NautilusInputError,
    NautilusNetworkDeniedError,
)
from trading_engine_conformance.adapters.nautilus.isolation import (
    deny_network,
    sanitize_environment,
    validate_immutable_input,
)
from trading_engine_conformance.adapters.nautilus.worker import run_worker
from trading_engine_conformance.integrity.manifest import build_manifest, write_manifest


@pytest.mark.adversarial
def test_environment_secret_and_proxy_stripping(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABENTO_API_KEY",
        "IB_PASSWORD",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "AWS_SECRET_ACCESS_KEY",
    ):
        monkeypatch.setenv(name, "secret")
    monkeypatch.setenv("TEC_BENIGN_TEST", "keep")
    removed = sanitize_environment()
    assert "TEC_BENIGN_TEST" in os.environ
    assert all(name not in os.environ for name in removed)
    assert "DATABENTO_API_KEY" in removed
    assert "HTTP_PROXY" in removed


@pytest.mark.adversarial
def test_network_denial_blocks_socket_attempt() -> None:
    with deny_network(), pytest.raises(NautilusNetworkDeniedError):
        socket.create_connection(("127.0.0.1", 1))


@pytest.mark.adversarial
def test_input_manifest_tamper_and_path_traversal_are_rejected(tmp_path: Path) -> None:
    run = tmp_path / "input"
    run.mkdir()
    (run / "request.json").write_text("{}", encoding="utf-8")
    write_manifest(run / "manifest.json", build_manifest(run, created_ts=1))
    assert validate_immutable_input(run, "request.json").name == "request.json"
    with pytest.raises(NautilusInputError, match=r"portable|relative|traversal"):
        validate_immutable_input(run, "../request.json")
    (run / "request.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(NautilusInputError, match="manifest"):
        validate_immutable_input(run, "request.json")


@pytest.mark.adversarial
def test_symlink_escape_is_rejected_when_supported(tmp_path: Path) -> None:
    run = tmp_path / "input"
    run.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = run / "request.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(NautilusInputError):
        validate_immutable_input(run, "request.json")


@pytest.mark.adversarial
def test_crash_removes_partial_staging_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "request.json").write_text("{}", encoding="utf-8")
    write_manifest(input_dir / "manifest.json", build_manifest(input_dir, created_ts=1))
    output_dir = tmp_path / "output"

    def crash(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected crash")

    monkeypatch.setattr("trading_engine_conformance.adapters.nautilus.worker._execute", crash)
    with pytest.raises(RuntimeError, match="injected crash"):
        run_worker(input_dir, output_dir)
    assert not output_dir.exists()
    assert not list(tmp_path.glob(".output.staging-*"))
