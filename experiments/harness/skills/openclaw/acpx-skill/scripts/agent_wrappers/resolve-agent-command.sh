#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <agent-name> [args...]" >&2
  exit 1
fi

AGENT_NAME="$1"
shift

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXTERNAL_ROOT="${OPENCLAW_EXTERNAL_AGENTS_ROOT:-$SKILL_ROOT/external-agents}"
REPO_CODE2_ROOT="/home/zhangpf/projects/graduation-design-subagents/unified/superagents/code2workspace_agent"

PRIMARY_ENV_VAR=""
PRIMARY_CANDIDATE=""

case "$AGENT_NAME" in
  benchmark_agent)
    PRIMARY_ENV_VAR="BENCHMARK_AGENT_ACP_COMMAND"
    PRIMARY_CANDIDATE="$EXTERNAL_ROOT/benchmark_agent/run-acp.sh"
    ;;
  data_governance_agent)
    PRIMARY_ENV_VAR="DATA_GOVERNANCE_AGENT_ACP_COMMAND"
    PRIMARY_CANDIDATE="$EXTERNAL_ROOT/data_governance_agent/run-acp.sh"
    ;;
  deep_research_agent)
    PRIMARY_ENV_VAR="DEEP_RESEARCH_AGENT_ACP_COMMAND"
    PRIMARY_CANDIDATE="$EXTERNAL_ROOT/deep_research_agent/run-acp.sh"
    ;;
  code2workspace_agent)
    PRIMARY_ENV_VAR="CODE2WORKSPACE_AGENT_ACP_COMMAND"
    PRIMARY_CANDIDATE="$REPO_CODE2_ROOT/code2workspace_agent_acp/run-acp.sh"
    ;;
  report_agent)
    PRIMARY_ENV_VAR="REPORT_AGENT_ACP_COMMAND"
    PRIMARY_CANDIDATE="$EXTERNAL_ROOT/report_agent/run-acp.sh"
    ;;
  *)
    echo "Unsupported agent: $AGENT_NAME" >&2
    exit 1
    ;;
esac

COMMAND="${!PRIMARY_ENV_VAR:-}"
if [[ -z "$COMMAND" && -n "$PRIMARY_CANDIDATE" && -x "$PRIMARY_CANDIDATE" ]]; then
  COMMAND="$PRIMARY_CANDIDATE"
fi

if [[ ! -x "$COMMAND" ]]; then
  echo "Missing ACP runner for $AGENT_NAME: $COMMAND" >&2
  echo "Set $PRIMARY_ENV_VAR or OPENCLAW_EXTERNAL_AGENTS_ROOT, or place the runner at $PRIMARY_CANDIDATE" >&2
  exit 1
fi

exec "$COMMAND" "$@"
