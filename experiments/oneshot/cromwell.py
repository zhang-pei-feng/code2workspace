"""Helpers for resolving and launching the local Cromwell jar."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Return the project repository root."""
    return Path(__file__).resolve().parents[2]


def project_cromwell_jar() -> Path:
    """Return the preferred project-local Cromwell jar location."""
    return repo_root() / ".local-tools" / "cromwell" / "cromwell.jar"


def fallback_cromwell_jar() -> Path:
    """Return the historical machine-local fallback location."""
    return Path("/mnt/data2/bin/cromwell.jar")


def resolve_cromwell_jar() -> Path:
    """Resolve the Cromwell jar path from env, project-local copy, or fallback."""
    env_value = os.environ.get("CROMWELL_JAR", "").strip()
    if env_value:
        candidate = Path(env_value).expanduser()
        if not candidate.is_absolute():
            candidate = (repo_root() / candidate).resolve()
        return candidate
    project_path = project_cromwell_jar()
    if project_path.exists():
        return project_path
    return fallback_cromwell_jar()


def cromwell_run_marker() -> str:
    """Return the stable command marker used by completion detection."""
    return "cromwell.jar run"


def build_cromwell_run_command(
    wdl_path: Path,
    *,
    inputs_path: Path | None = None,
    options_path: Path | None = None,
) -> list[str]:
    """Build a `java -jar ... run` command for Cromwell."""
    cmd = ["java", "-jar", str(resolve_cromwell_jar()), "run", str(wdl_path)]
    if inputs_path is not None:
        cmd.extend(["-i", str(inputs_path)])
    if options_path is not None:
        cmd.extend(["-o", str(options_path)])
    return cmd
