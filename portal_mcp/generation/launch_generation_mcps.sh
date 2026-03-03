#!/bin/bash
# Launch all generation MCP servers
set -euo pipefail

PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$PORTAL_ROOT/.venv"

source "$VENV/bin/activate"

# Add portal_mcp to Python path
export PYTHONPATH="${PORTAL_ROOT}:${PYTHONPATH:-}"

# Load env
[ -f "$PORTAL_ROOT/.env" ] && { set -a; source "$PORTAL_ROOT/.env"; set +a; }

GENERATION_SERVICES="${GENERATION_SERVICES:-false}"

if [ "$GENERATION_SERVICES" != "true" ]; then
    echo "[generation-mcps] GENERATION_SERVICES=false — skipping"
    exit 0
fi

launch_server() {
    local name="$1"
    local script="$2"
    local pid_file="/tmp/portal-mcp-${name}.pid"
    local log_file="$HOME/.portal/logs/mcp-${name}.log"

    mkdir -p "$(dirname "$log_file")"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "[mcp-${name}] already running"
        return
    fi

    nohup python "$PORTAL_ROOT/portal_mcp/generation/$script" >> "$log_file" 2>&1 &
    echo $! > "$pid_file"
    echo "[mcp-${name}] started (PID $(cat "$pid_file"))"
}

launch_server "comfyui" "comfyui_mcp.py"
launch_server "whisper" "whisper_mcp.py"
launch_server "video" "video_mcp.py"
launch_server "music" "music_mcp.py"
launch_server "tts" "tts_mcp.py"

echo "[generation-mcps] all servers launched"
