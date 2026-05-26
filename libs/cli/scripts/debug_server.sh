#!/usr/bin/env bash
# Debug script for EpiMindAgent server startup failures.
# Captures CLI version, environment, and the server log that contains
# the actual make_graph() exception.
#
# Usage: bash debug_server.sh

set -euo pipefail

OUT=$(mktemp "${TMPDIR:-/tmp}epimindagent_debug_XXXXXX")

{
    echo "=== EpiMindAgent debug dump ==="
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo ""

    echo "=== CLI version ==="
    if command -v EpiMindAgent >/dev/null 2>&1; then
        EpiMindAgent -v 2>&1 || echo "(EpiMindAgent -v failed)"
    else
        code2workspace -v 2>&1 || echo "(EpiMindAgent/code2workspace -v failed)"
    fi
    echo ""

    echo "=== Python ==="
    python3 --version 2>&1
    which python3 2>&1
    echo ""

    echo "=== uv tool list (EpiMindAgent) ==="
    uv tool list 2>&1 | grep -iE 'epimindagent|code2workspace' || echo "(not found in uv tool list)"
    echo ""

    echo "=== Key env vars ==="
    env | grep -iE '^(ANTHROPIC_|OPENAI_|AZURE_OPENAI_|GOOGLE_|EPIMINDAGENT_|CODE2WORKSPACE_|LANGCHAIN_|LANGGRAPH_|TAVILY_|GROQ_|DEEPSEEK_|FIREWORKS_|MISTRAL_|COHERE_|NVIDIA_|TOGETHER_|XAI_|HUGGINGFACEHUB_|PPLX_|WATSONX_|BASETEN_|LITELLM_|OPENROUTER_)' \
        | sed 's/=.*/=<set>/' | sort || echo "(none set)"
    echo ""

    echo "=== pip/uv packages (EpiMindAgent + langgraph) ==="
    pip list 2>/dev/null | grep -iE 'epimindagent|code2workspace|langgraph|langchain' || true
    echo ""

    echo "=== Latest server log ==="
    TMPDIR_RESOLVED="${TMPDIR:-/tmp}"
    LOG=$(ls -t "$TMPDIR_RESOLVED"/epimindagent_server_log_* "$TMPDIR_RESOLVED"/code2workspace_server_log_* 2>/dev/null | head -1)
    if [ -n "$LOG" ]; then
        echo "file: $LOG"
        echo "modified: $(stat -f '%Sm' "$LOG" 2>/dev/null || stat -c '%y' "$LOG" 2>/dev/null)"
        echo "---"
        tail -200 "$LOG"
    else
        echo "(no server log found in $TMPDIR_RESOLVED)"
        # Try the macOS private var path as fallback
        LOG=$(ls -t /private/var/folders/*/*/T/epimindagent_server_log_* /private/var/folders/*/*/T/code2workspace_server_log_* 2>/dev/null | head -1)
        if [ -n "$LOG" ]; then
            echo "file: $LOG"
            echo "modified: $(stat -f '%Sm' "$LOG" 2>/dev/null || stat -c '%y' "$LOG" 2>/dev/null)"
            echo "---"
            tail -200 "$LOG"
        else
            echo "(no server log found in /private/var/folders either)"
        fi
    fi
    echo ""
    echo "=== end ==="
} > "$OUT" 2>&1

echo "Debug output saved to: $OUT"
echo "Send this file in Slack, or paste the contents:"
echo ""
cat "$OUT"
