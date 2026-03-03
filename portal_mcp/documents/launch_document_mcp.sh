#!/bin/bash
# Launch document MCP server
set -euo pipefail

PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$PORTAL_ROOT/.venv"

source "$VENV/bin/activate"

# Load env
[ -f "$PORTAL_ROOT/.env" ] && { set -a; source "$PORTAL_ROOT/.env"; set +a; }

DOCUMENTS_MCP_PORT="${DOCUMENTS_MCP_PORT:-8913}"

launch_server() {
    local name="document"
    local script="document_mcp.py"
    local pid_file="/tmp/portal-mcp-${name}.pid"
    local log_file="$HOME/.portal/logs/mcp-${name}.log"

    mkdir -p "$(dirname "$log_file")"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "[mcp-${name}] already running"
        return
    fi

    DOCUMENTS_MCP_PORT=$DOCUMENTS_MCP_PORT nohup python "$PORTAL_ROOT/mcp/documents/$script" >> "$log_file" 2>&1 &
    echo $! > "$pid_file"
    echo "[mcp-${name}] started (PID $(cat "$pid_file"), port $DOCUMENTS_MCP_PORT)"
}

launch_server

echo "[document-mcp] server launched"