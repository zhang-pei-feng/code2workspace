#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <agent-name> [--session <name>] [--openclaw-session-key <key>|--openclaw-session-id <id>] [--close] <prompt...>" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ACPX_CWD="${ACPX_CWD:-$ROOT_DIR}"
ACPX_BIN=(acpx --cwd "$ACPX_CWD")
NAME_SCRIPT="$ROOT_DIR/.acpx-tools/acpx-session-name.sh"

is_code2workspace_smoke_test() {
  local prompt_lower
  prompt_lower="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  [[ "$1" == *"连通性测试"* ]] \
    || [[ "$prompt_lower" == *"connectivity"* ]] \
    || [[ "$prompt_lower" == *"smoke test"* ]] \
    || [[ "$prompt_lower" == *"minimal connectivity"* ]] \
    || [[ "$prompt_lower" == *"paper2workspace_ok"* ]] \
    || [[ "$prompt_lower" == *"code2workspace_ok"* ]]
}

AGENT_NAME="$1"
shift

SESSION_NAME=""
OPENCLAW_SESSION_KEY="${OPENCLAW_SESSION_KEY:-}"
OPENCLAW_SESSION_ID="${OPENCLAW_SESSION_ID:-}"
CLOSE_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session)
      [[ $# -ge 2 ]] || { echo "Missing session name" >&2; exit 1; }
      SESSION_NAME="$2"
      shift 2
      ;;
    --openclaw-session-key)
      [[ $# -ge 2 ]] || { echo "Missing OpenClaw session key" >&2; exit 1; }
      OPENCLAW_SESSION_KEY="$2"
      shift 2
      ;;
    --openclaw-session-id)
      [[ $# -ge 2 ]] || { echo "Missing OpenClaw session id" >&2; exit 1; }
      OPENCLAW_SESSION_ID="$2"
      shift 2
      ;;
    --close)
      CLOSE_ONLY=1
      shift
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

if [[ -z "$SESSION_NAME" ]] && [[ -x "$NAME_SCRIPT" ]]; then
  if [[ -n "$OPENCLAW_SESSION_KEY" ]]; then
    SESSION_NAME="$("$NAME_SCRIPT" "$AGENT_NAME" --openclaw-session-key "$OPENCLAW_SESSION_KEY")"
  elif [[ -n "$OPENCLAW_SESSION_ID" ]]; then
    SESSION_NAME="$("$NAME_SCRIPT" "$AGENT_NAME" --openclaw-session-id "$OPENCLAW_SESSION_ID")"
  fi
fi

SESSION_ARGS=()
PROMPT_SESSION_ARGS=()
if [[ -n "$SESSION_NAME" ]]; then
  SESSION_ARGS=(--name "$SESSION_NAME")
  PROMPT_SESSION_ARGS=(-s "$SESSION_NAME")
fi

if [[ "$CLOSE_ONLY" == "1" ]]; then
  if [[ -n "$SESSION_NAME" ]]; then
    "${ACPX_BIN[@]}" "$AGENT_NAME" sessions close "$SESSION_NAME" || true
  else
    "${ACPX_BIN[@]}" "$AGENT_NAME" sessions close || true
  fi
  exit 0
fi

PROMPT="$*"
if [[ -z "$PROMPT" ]]; then
  echo "Missing prompt" >&2
  exit 1
fi

RUN_ENV=()
RUN_SUBCOMMAND="prompt"

case "$AGENT_NAME" in
  benchmark_agent|data_governance_agent|code2workspace_agent|deep_research_agent|report_agent)
    RUN_SUBCOMMAND="exec"
    ;;
esac

if [[ "$AGENT_NAME" == "code2workspace_agent" ]]; then
  CODE2_NO_MCP="${CODE2WORKSPACE_AGENT_NO_MCP:-}"
  if [[ -n "$CODE2_NO_MCP" ]]; then
    RUN_ENV+=(CODE2WORKSPACE_AGENT_NO_MCP="$CODE2_NO_MCP")
  fi
fi

if [[ "$AGENT_NAME" == "code2workspace_agent" ]] \
  && [[ -z "${CODE2WORKSPACE_AGENT_NO_MCP:-}" ]] \
  && is_code2workspace_smoke_test "$PROMPT"; then
  # The code2workspace smoke path should stay minimal and avoid project MCP setup.
  RUN_ENV+=(CODE2WORKSPACE_AGENT_NO_MCP=1)
fi

if [[ "$RUN_SUBCOMMAND" == "prompt" ]]; then
  "${ACPX_BIN[@]}" "$AGENT_NAME" sessions ensure "${SESSION_ARGS[@]}"
fi

if [[ ${#RUN_ENV[@]} -gt 0 ]]; then
  env "${RUN_ENV[@]}" "${ACPX_BIN[@]}" --approve-all "$AGENT_NAME" "$RUN_SUBCOMMAND" "${PROMPT_SESSION_ARGS[@]}" "$PROMPT"
else
  "${ACPX_BIN[@]}" --approve-all "$AGENT_NAME" "$RUN_SUBCOMMAND" "${PROMPT_SESSION_ARGS[@]}" "$PROMPT"
fi
