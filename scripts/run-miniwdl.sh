#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CFG="${ROOT_DIR}/experiments/oneshot/miniwdl.cfg"
CFG_PATH="${MINIWDL_CFG:-${DEFAULT_CFG}}"

if command -v miniwdl >/dev/null 2>&1; then
  exec miniwdl run --cfg "${CFG_PATH}" --as-me "$@"
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --project "${ROOT_DIR}/libs/cli" miniwdl run --cfg "${CFG_PATH}" --as-me "$@"
fi

echo "miniwdl not found in PATH, and uv is unavailable for fallback." >&2
exit 1
