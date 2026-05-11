"""Helpers for running miniwdl with the project-default configuration."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Return the project repository root."""
    return Path(__file__).resolve().parents[2]


def project_miniwdl_cfg() -> Path:
    """Return the committed miniwdl config path."""
    return repo_root() / "experiments" / "oneshot" / "miniwdl.cfg"


def resolve_miniwdl_cfg() -> Path:
    """Resolve the miniwdl config path from env or the project default."""
    env_value = os.environ.get("MINIWDL_CFG", "").strip()
    if env_value:
        candidate = Path(env_value).expanduser()
        if not candidate.is_absolute():
            candidate = (repo_root() / candidate).resolve()
        return candidate
    return project_miniwdl_cfg()


def miniwdl_run_marker() -> str:
    """Return the stable command marker used by completion detection."""
    return "miniwdl run"


def build_miniwdl_run_command(
    wdl_path: Path,
    *,
    inputs_path: Path | None = None,
    output_path: Path | None = None,
) -> list[str]:
    """Build a `miniwdl run` command with the project defaults."""
    cmd = [
        "miniwdl",
        "run",
        "--cfg",
        str(resolve_miniwdl_cfg()),
        "--as-me",
        str(wdl_path),
    ]
    if inputs_path is not None:
        cmd.extend(["-i", str(inputs_path)])
    if output_path is not None:
        cmd.extend(["-o", str(output_path)])
    return cmd
