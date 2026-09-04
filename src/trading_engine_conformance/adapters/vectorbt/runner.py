"""Parent-side launcher for a fixed fresh offline worker process."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path

from trading_engine_conformance.adapters.vectorbt.errors import VectorbtAdapterError


@dataclass(frozen=True)
class WorkerResult:
    returncode: int
    stdout: str
    stderr: str


def _scrubbed_child_environment() -> dict[str, str]:
    env = dict(os.environ)
    for name in tuple(env):
        upper = name.upper()
        if any(
            token in upper
            for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PROXY", "CREDENTIAL")
        ):
            env.pop(name, None)
    return env


def launch_worker(input_dir: Path, output_dir: Path) -> WorkerResult:
    """Launch only this package's fixed module with the current isolated Python."""
    completed = subprocess.run(  # noqa: S603  # nosec B603
        [
            sys.executable,
            "-m",
            "trading_engine_conformance.adapters.vectorbt.worker",
            str(input_dir),
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_scrubbed_child_environment(),
        timeout=300,
    )
    result = WorkerResult(completed.returncode, completed.stdout, completed.stderr)
    if result.returncode != 0:
        raise VectorbtAdapterError(
            f"offline vectorbt worker failed with exit {result.returncode}: {result.stderr.strip()}"
        )
    return result
