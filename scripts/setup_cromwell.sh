#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_JAR="${1:-/mnt/data2/bin/cromwell.jar}"
TARGET_DIR="${ROOT_DIR}/.local-tools/cromwell"
TARGET_JAR="${TARGET_DIR}/cromwell.jar"

mkdir -p "${TARGET_DIR}"

if [[ ! -f "${SOURCE_JAR}" ]]; then
  echo "Source Cromwell jar not found: ${SOURCE_JAR}" >&2
  exit 1
fi

cp -f "${SOURCE_JAR}" "${TARGET_JAR}"
chmod 0644 "${TARGET_JAR}"

echo "Cromwell jar copied to ${TARGET_JAR}"
