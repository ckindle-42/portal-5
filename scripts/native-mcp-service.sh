#!/bin/bash
set -euo pipefail

SERVICE="${1:-}"
PORTAL_ROOT="${PORTAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$PORTAL_ROOT/.env"
PY="$PORTAL_ROOT/.venv/bin/python3"

if [ ! -x "$PY" ]; then
    PY="$(command -v python3)"
fi

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

export PYTHONPATH="$PORTAL_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$PORTAL_ROOT"

case "$SERVICE" in
    mlx-transcribe)
        exec "$PY" "$PORTAL_ROOT/scripts/mlx-transcribe.py"
        ;;
    pipeline-mcp)
        export PIPELINE_URL="${PIPELINE_URL:-http://localhost:9099}"
        export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
        export PIPELINE_MCP_REPO_ROOT="${PIPELINE_MCP_REPO_ROOT:-$PORTAL_ROOT}"
        export PIPELINE_MCP_PORT="${PIPELINE_MCP_PORT:-8928}"
        exec "$PY" -m portal.platform.mcp_host.pipeline_mcp
        ;;
    mitre-mcp)
        export MITRE_MCP_PORT="${MITRE_MCP_PORT:-8929}"
        exec "$PY" -m portal.modules.security.tools.mitre_mcp
        ;;
    detections-mcp)
        export DETECTIONS_MCP_PORT="${DETECTIONS_MCP_PORT:-8932}"
        exec "$PY" -m portal.modules.security.tools.detections_mcp
        ;;
    wiki-mcp)
        export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
        export WIKI_MCP_PORT="${WIKI_MCP_PORT:-8931}"
        exec "$PY" -m portal_wiki.wiki_mcp
        ;;
    *)
        echo "Unknown native MCP service: ${SERVICE:-<empty>}" >&2
        exit 2
        ;;
esac
