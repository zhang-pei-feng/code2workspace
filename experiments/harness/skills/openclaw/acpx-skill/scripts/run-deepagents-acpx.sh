#!/usr/bin/env bash
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_BASE_DIR="$SKILL_ROOT/external-agents/deep_research_agent/deepagents/libs/acp"
BASE_DIR="${DEEPAGENTS_ACP_BASE_DIR:-$DEFAULT_BASE_DIR}"
VENV_PYTHON="$BASE_DIR/.venv/bin/python"
ENTRYPOINT="$BASE_DIR/examples/demo_agent.py"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing Python interpreter: $VENV_PYTHON" >&2
  exit 1
fi

if [[ ! -f "$ENTRYPOINT" ]]; then
  echo "Missing entrypoint: $ENTRYPOINT" >&2
  exit 1
fi

export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$SKILL_ROOT/.cache/acpx-deepagents}"
mkdir -p "$XDG_CACHE_HOME"

exec "$VENV_PYTHON" "$ENTRYPOINT"
