#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-$PWD}"
AGENT_NAME="${2:-deepagents}"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS_DIR="$TARGET_DIR/.acpx-tools"
RUNNER_SRC="$SKILL_DIR/scripts/run-deepagents-acpx.sh"
RUNNER_DST="$TOOLS_DIR/run-deepagents-acpx.sh"
LOCAL_WRAPPER_DST="$TOOLS_DIR/acpx-local.sh"
LEGACY_LOCAL_WRAPPER_DST="$TOOLS_DIR/acpx-deepagents-local.sh"
RELAY_SCRIPT_SRC="$SKILL_DIR/scripts/acpx-agent-relay.sh"
RELAY_SCRIPT_DST="$TOOLS_DIR/acpx-agent-relay.sh"
NAME_SCRIPT_SRC="$SKILL_DIR/scripts/acpx-session-name.sh"
NAME_SCRIPT_DST="$TOOLS_DIR/acpx-session-name.sh"
EXTRACT_SCRIPT_SRC="$SKILL_DIR/scripts/extract-openclaw-session-context.py"
EXTRACT_SCRIPT_DST="$TOOLS_DIR/extract-openclaw-session-context.py"
CONFIG_PATH="$TARGET_DIR/.acpxrc.json"

mkdir -p "$TOOLS_DIR"
cp "$RUNNER_SRC" "$RUNNER_DST"
cp "$RELAY_SCRIPT_SRC" "$RELAY_SCRIPT_DST"
cp "$NAME_SCRIPT_SRC" "$NAME_SCRIPT_DST"
cp "$EXTRACT_SCRIPT_SRC" "$EXTRACT_SCRIPT_DST"
chmod +x "$RUNNER_DST" "$RELAY_SCRIPT_DST" "$NAME_SCRIPT_DST" "$EXTRACT_SCRIPT_DST"

DEFAULT_COMMAND="$RUNNER_DST"
if [[ "$AGENT_NAME" == "code2workspace_agent" ]] && [[ -n "${CODE2WORKSPACE_AGENT_ACP_COMMAND:-}" ]]; then
  DEFAULT_COMMAND="$CODE2WORKSPACE_AGENT_ACP_COMMAND"
fi
AGENT_COMMAND="${3:-$DEFAULT_COMMAND}"

cat > "$LOCAL_WRAPPER_DST" <<EOF
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$TARGET_DIR"
export HOME="\$ROOT_DIR/.acpx-home"
mkdir -p "\$HOME"

exec acpx "\$@"
EOF
chmod +x "$LOCAL_WRAPPER_DST"
cp "$LOCAL_WRAPPER_DST" "$LEGACY_LOCAL_WRAPPER_DST"
chmod +x "$LEGACY_LOCAL_WRAPPER_DST"

node - "$CONFIG_PATH" "$AGENT_NAME" "$AGENT_COMMAND" <<'EOF'
const fs = require("fs");

const [configPath, agentName, agentCommand] = process.argv.slice(2);
let config = {};

if (fs.existsSync(configPath)) {
  config = JSON.parse(fs.readFileSync(configPath, "utf8"));
}

if (typeof config !== "object" || config === null || Array.isArray(config)) {
  config = {};
}

config.ttl = 0;
config.agents = config.agents && typeof config.agents === "object" && !Array.isArray(config.agents)
  ? config.agents
  : {};
config.agents[agentName] = {
  ...(config.agents[agentName] && typeof config.agents[agentName] === "object" ? config.agents[agentName] : {}),
  command: agentCommand,
};

fs.writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`);
EOF

echo "Installed or updated:"
echo "  $CONFIG_PATH"
echo "  $RUNNER_DST"
echo "  $RELAY_SCRIPT_DST"
echo "  $NAME_SCRIPT_DST"
echo "  $EXTRACT_SCRIPT_DST"
echo "  $LOCAL_WRAPPER_DST"
echo "Agent:"
echo "  $AGENT_NAME -> $AGENT_COMMAND"
