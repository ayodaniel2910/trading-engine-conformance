"""Parent-side launcher for the fresh offline worker."""

from __future__ import annotations

import os

# The executable and module are fixed; no shell or executable input is accepted.
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path

from trading_engine_conformance.adapters.nautilus.errors import NautilusAdapterError


@dataclass(frozen=True)
class WorkerResult:
    returncode: int
    stdout: str
    stderr: str


def launch_worker(input_dir: Path, output_dir: Path) -> WorkerResult:
    env = dict(os.environ)
    # The child also strips its environment before importing Nautilus; this
    # parent scrub prevents values from crossing the process boundary at all.
    for name in tuple(env):
        upper = name.upper()
        if any(token in upper for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PROXY")):
            env.pop(name, None)
    # Arguments can select only manifested data paths, never an executable or shell syntax.
    completed = subprocess.run(  # noqa: S603  # nosec B603
        [
            sys.executable,
            "-m",
            "trading_engine_conformance.adapters.nautilus.worker",
            str(input_dir),
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    result = WorkerResult(completed.returncode, completed.stdout, completed.stderr)
    if result.returncode != 0:
        raise NautilusAdapterError(
            f"offline worker failed with exit {result.returncode}: {result.stderr.strip()}"
        )
    return result
