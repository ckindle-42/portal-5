#!/bin/bash
# Launch code sandbox MCP server
set -euo pipefail

PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$PORTAL_ROOT/.venv"

source "$VENV/bin/activate"

# Load env
[ -f "$PORTAL_ROOT/.env" ] && { set -a; source "$PORTAL_ROOT/.env"; set +a; }

# Add portal_mcp to Python path
export PYTHONPATH="${PORTAL_ROOT}:${PYTHONPATH:-}"

SANDBOX_ENABLED="${SANDBOX_ENABLED:-false}"

if [ "$SANDBOX_ENABLED" != "true" ]; then
    echo "[sandbox-mcp] SANDBOX_ENABLED=false — skipping"
    exit 0
fi

SANDBOX_MCP_PORT="${SANDBOX_MCP_PORT:-8914}"

launch_server() {
    local name="sandbox"
    local script="code_sandbox_mcp.py"
    local pid_file="/tmp/portal-mcp-${name}.pid"
    local log_file="$HOME/.portal/logs/mcp-${name}.log"

    mkdir -p "$(dirname "$log_file")"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "[mcp-${name}] already running"
        return
    fi

    SANDBOX_MCP_PORT=$SANDBOX_MCP_PORT nohup python "$PORTAL_ROOT/portal_mcp/execution/$script" >> "$log_file" 2>&1 &
    echo $! > "$pid_file"
    echo "[mcp-${name}] started (PID $(cat "$pid_file"), port $SANDBOX_MCP_PORT)"
}

launch_server

echo "[sandbox-mcp] server launched"