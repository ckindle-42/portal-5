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

# shellcheck source=scripts/lib/venv_preflight.sh
source "$PORTAL_ROOT/scripts/lib/venv_preflight.sh"

case "$SERVICE" in
    mlx-transcribe)
        # Shares the fragile MLX runtime with :8917/:8918/:8942 — same drift gate
        # (D1). The pure-Python MCP services below do not depend on that runtime
        # and are deliberately not gated (see KNOWN_LIMITATIONS.md).
        _venv_lock_preflight "mlx-transcribe" || exit 1
        # Under launchd the HF cached-file revalidation HEAD requests hang
        # indefinitely; models are pre-warmed by `launch.sh start-transcribe`, so
        # the service serves strictly from cache.
        export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
        # launchd starts with a bare PATH; mlx-audio shells out to ffmpeg to decode
        # m4a/mp4/webm uploads (what phones and OWUI produce), so make it findable.
        export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
        exec "$PY" "$PORTAL_ROOT/scripts/mlx-transcribe.py"
        ;;
    mlx-speech)
        # Same fragile MLX runtime as :8917/:8924/:8942 — same drift gate (D1).
        _venv_lock_preflight "mlx-speech" || exit 1
        # As for mlx-transcribe: under launchd the HF cached-file revalidation
        # HEAD requests hang, and mlx-audio shells out to ffmpeg on a bare PATH.
        export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
        export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
        exec "$PY" "$PORTAL_ROOT/scripts/mlx-speech.py"
        ;;
    vl-retrieval)
        # Same fragile MLX runtime as :8917/:8918/:8924 — same drift gate (D1).
        # Supervision is load-bearing here, not just hygiene: O1's
        # VL_MAX_REQUESTS self-exit assumes something restarts the process, and
        # P5-VL-RETR-001 needs a KeepAlive that tolerates a serial rerank queue.
        _venv_lock_preflight "vl-retrieval" || exit 1
        export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
        export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
        exec "$PY" "$PORTAL_ROOT/scripts/vl-retrieval-server.py" \
            --port "${VL_PORT:-8942}"
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
    vulnintel-mcp)
        export VULNINTEL_MCP_PORT="${VULNINTEL_MCP_PORT:-8934}"
        exec "$PY" -m portal.modules.vulnintel.tools.vulnintel_mcp
        ;;
    icsot-mcp)
        export ICSOT_MCP_PORT="${ICSOT_MCP_PORT:-8936}"
        exec "$PY" -m portal.modules.icsot.tools.icsot_mcp
        ;;
    compliance-mcp)
        export COMPLIANCE_MCP_PORT="${COMPLIANCE_MCP_PORT:-8937}"
        exec "$PY" -m portal.modules.compliance.tools.compliance_mcp
        ;;
    detection-mcp)
        export DETECTION_MCP_PORT="${DETECTION_MCP_PORT:-8938}"
        exec "$PY" -m portal.modules.detection.tools.detection_mcp
        ;;
    data-mcp)
        export DATA_MCP_PORT="${DATA_MCP_PORT:-8939}"
        exec "$PY" -m portal.modules.data.tools.data_mcp
        ;;
    netforensics-mcp)
        export NETFORENSICS_MCP_PORT="${NETFORENSICS_MCP_PORT:-8941}"
        # tshark ships CLI tools under this path on macOS
        export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Wireshark.app/Contents/MacOS:$PATH"
        exec "$PY" -m portal.modules.netforensics.tools.netforensics_mcp
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
