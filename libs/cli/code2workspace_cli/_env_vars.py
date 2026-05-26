"""Canonical registry of `EPIMINDAGENT_CLI_*` environment variables.

Every env var the CLI reads whose name starts with `EPIMINDAGENT_CLI_` must
be defined here as a module-level constant.  A drift-detection test
(`tests/unit_tests/test_env_vars.py`) fails when a bare string literal
like `"EPIMINDAGENT_CLI_FOO"` appears in source code instead of a constant
imported from this module.

Import the short-name constants (e.g. `AUTO_UPDATE`, `DEBUG`) and pass them
to `os.environ.get()` instead of using raw string literals. If the env var is
ever renamed, only the value here changes.

!!! note

    `resolve_env_var` also supports a dynamic prefix override for API keys
    and provider credentials: setting `EPIMINDAGENT_CLI_{NAME}` takes priority
    over `{NAME}`.  For example, `EPIMINDAGENT_CLI_OPENAI_API_KEY` overrides
    `OPENAI_API_KEY`. Legacy `CODE2WORKSPACE_CLI_*` names are still accepted
    as fallback aliases.
    Dynamic overrides are not listed here because they mirror third-party
    variable names.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# ---------------------------------------------------------------------------
# Constants — import these instead of bare string literals.
# Keep alphabetically sorted by constant name.
# ---------------------------------------------------------------------------

ENV_PREFIX = "EPIMINDAGENT_CLI_"
"""Preferred environment-variable prefix for EpiMindAgent CLI settings."""

LEGACY_ENV_PREFIX = "CODE2WORKSPACE_CLI_"
"""Backward-compatible prefix accepted for older local environments."""

PROJECT_ENV_PREFIX = "EPIMINDAGENT_"
"""Preferred project-level environment-variable prefix."""

LEGACY_PROJECT_ENV_PREFIX = "CODE2WORKSPACE_"
"""Backward-compatible project-level prefix."""

AUTO_UPDATE = "EPIMINDAGENT_CLI_AUTO_UPDATE"
"""Enable automatic CLI updates ('1', 'true', or 'yes')."""

DEBUG = "EPIMINDAGENT_CLI_DEBUG"
"""Enable verbose debug logging to a file."""

DEBUG_FILE = "EPIMINDAGENT_CLI_DEBUG_FILE"
"""Path for the debug log file (default: `/tmp/epimindagent_debug.log`)."""

DEFAULT_MODEL = "EPIMINDAGENT_CLI_DEFAULT_MODEL"
"""Default model spec for the CLI, e.g. `openai:gpt-5.4`."""

EXTRA_SKILLS_DIRS = "EPIMINDAGENT_CLI_EXTRA_SKILLS_DIRS"
"""Colon-separated paths added to the skill containment allowlist."""

LANGSMITH_PROJECT = "EPIMINDAGENT_CLI_LANGSMITH_PROJECT"
"""Override LangSmith project name for agent traces."""

MODEL = "EPIMINDAGENT_CLI_MODEL"
"""Default model spec alias for the CLI, e.g. `openai:gpt-5.4`."""

NO_UPDATE_CHECK = "EPIMINDAGENT_CLI_NO_UPDATE_CHECK"
"""Disable automatic update checking when set."""

PROJECT_DEFAULT_MODEL = "EPIMINDAGENT_DEFAULT_MODEL"
"""Project-level default model spec."""

PROJECT_MODEL = "EPIMINDAGENT_MODEL"
"""Project-level default model spec alias."""

SERVER_ENV_PREFIX = "EPIMINDAGENT_CLI_SERVER_"
"""Environment variable prefix used to pass CLI config to the server subprocess."""

SHELL_ALLOW_LIST = "EPIMINDAGENT_CLI_SHELL_ALLOW_LIST"
"""Comma-separated shell commands to allow (or 'recommended'/'all')."""

USER_ID = "EPIMINDAGENT_CLI_USER_ID"
"""Attach a user identifier to LangSmith trace metadata."""


def legacy_env_name(name: str) -> str | None:
    """Return the legacy env-var alias for a preferred EpiMindAgent name."""
    if name.startswith(ENV_PREFIX):
        return f"{LEGACY_ENV_PREFIX}{name[len(ENV_PREFIX) :]}"
    if name.startswith(PROJECT_ENV_PREFIX):
        return f"{LEGACY_PROJECT_ENV_PREFIX}{name[len(PROJECT_ENV_PREFIX) :]}"
    return None


def preferred_env_name(name: str) -> str | None:
    """Return the preferred EpiMindAgent alias for a legacy env-var name."""
    if name.startswith(LEGACY_ENV_PREFIX):
        return f"{ENV_PREFIX}{name[len(LEGACY_ENV_PREFIX) :]}"
    if name.startswith(LEGACY_PROJECT_ENV_PREFIX):
        return f"{PROJECT_ENV_PREFIX}{name[len(LEGACY_PROJECT_ENV_PREFIX) :]}"
    return None


def get_env(name: str, default: str | None = None) -> str | None:
    """Read a preferred env var with legacy fallback."""
    if name in os.environ:
        return os.environ.get(name)
    legacy = legacy_env_name(name)
    if legacy and legacy in os.environ:
        return os.environ.get(legacy)
    preferred = preferred_env_name(name)
    if preferred and preferred in os.environ:
        return os.environ.get(preferred)
    return default


def get_mapping_env(
    environment: Mapping[str, str],
    name: str,
    default: str | None = None,
) -> str | None:
    """Read a preferred env var from an arbitrary mapping with legacy fallback."""
    if name in environment:
        return environment.get(name)
    legacy = legacy_env_name(name)
    if legacy and legacy in environment:
        return environment.get(legacy)
    preferred = preferred_env_name(name)
    if preferred and preferred in environment:
        return environment.get(preferred)
    return default
