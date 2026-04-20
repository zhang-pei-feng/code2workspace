#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <agent-name> --openclaw-session-key <key>|--openclaw-session-id <id>" >&2
  exit 1
fi

AGENT_NAME="$1"
shift

IDENTIFIER=""
MODE=""
case "${1:-}" in
  --openclaw-session-key)
    MODE="key"
    IDENTIFIER="${2:-}"
    ;;
  --openclaw-session-id)
    MODE="id"
    IDENTIFIER="${2:-}"
    ;;
  *)
    echo "Expected --openclaw-session-key or --openclaw-session-id" >&2
    exit 1
    ;;
esac

if [[ -z "$IDENTIFIER" ]]; then
  echo "Missing OpenClaw session identifier" >&2
  exit 1
fi

HASH="$(printf '%s' "$IDENTIFIER" | sha256sum | awk '{print substr($1,1,16)}')"
printf 'oc::%s::%s::%s\n' "$AGENT_NAME" "$MODE" "$HASH"
