"""Helpers for per-session working directory selection."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

SessionWorkdirMode = Literal["isolated", "inherit"]

DEFAULT_SESSION_WORKDIR_MODE: SessionWorkdirMode = "isolated"
SESSION_WORKDIR_ROOT_NAME = "workspace"


def session_timestamp() -> str:
    """Return a local timestamp suitable for workspace directory names."""
    return datetime.now().strftime("%Y%m%d%H%M%S")


def prepare_session_cwd(
    invocation_cwd: str | Path,
    *,
    mode: SessionWorkdirMode = DEFAULT_SESSION_WORKDIR_MODE,
    timestamp_factory: Callable[[], str] | None = None,
) -> Path:
    """Resolve the working directory for a new session.

    In isolated mode, creates `<invocation_cwd>/workspace/<timestamp>`.
    In inherit mode, returns `invocation_cwd` unchanged.
    """
    base = Path(invocation_cwd).expanduser().resolve()
    if mode == "inherit":
        return base

    workspace_root = base / SESSION_WORKDIR_ROOT_NAME
    workspace_root.mkdir(parents=True, exist_ok=True)
    make_timestamp = timestamp_factory or session_timestamp

    while True:
        candidate = workspace_root / make_timestamp()
        try:
            candidate.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue
        return candidate.resolve()
