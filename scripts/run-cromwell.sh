#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_JAR="${ROOT_DIR}/.local-tools/cromwell/cromwell.jar"
DEFAULT_JAR="/mnt/data2/bin/cromwell.jar"

if [[ -n "${CROMWELL_JAR:-}" ]]; then
  JAR_PATH="${CROMWELL_JAR}"
elif [[ -f "${PROJECT_JAR}" ]]; then
  JAR_PATH="${PROJECT_JAR}"
else
  JAR_PATH="${DEFAULT_JAR}"
fi

if [[ ! -f "${JAR_PATH}" ]]; then
  echo "Cromwell jar not found: ${JAR_PATH}" >&2
  echo "Run scripts/setup_cromwell.sh or set CROMWELL_JAR." >&2
  exit 1
fi

exec java -jar "${JAR_PATH}" "$@"
