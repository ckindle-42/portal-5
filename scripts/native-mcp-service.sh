#!/bin/bash
set -euo pipefail

SERVICE="${1:-}"
PORTAL_ROOT="${PORTAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$PORTAL_ROOT/.env"
PY="$PORTAL_ROOT/.venv/bin/python3"

# Usage error first: unknown service names exit 2 before any environment check
case "$SERVICE" in
    mlx-transcribe|mlx-speech|vl-retrieval|eg2-embedding|pipeline-mcp|mitre-mcp|\
detections-mcp|vulnintel-mcp|icsot-mcp|compliance-mcp|compliance-mcp-eval|\
detection-mcp|data-mcp|netforensics-mcp|review-mcp|wiki-mcp) ;;
    *)
        echo "Unknown native MCP service: ${SERVICE:-<empty>}" >&2
        exit 2
        ;;
esac

if [ ! -x "$PY" ]; then
    echo "Portal venv interpreter missing: $PY" >&2
    exit 1
fi

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# `.env` is shared with the Docker stack, so its URLs are written from a CONTAINER's
# point of view (OLLAMA_URL=http://host.docker.internal:11434,
# PIPELINE_URL=http://portal-pipeline:9099). Every service started here is host-native,
# where those names do not resolve at all — the failure is a bare `[Errno 8] nodename
# nor servname provided`, which reads like a dead service rather than a misaddressed
# one (2026-09-12 `explore_repository` via OLLAMA_URL, 2026-10-23 `list_workspaces` via
# PIPELINE_URL). Rewrite the Docker-only host of any *_URL / *_ENDPOINT to loopback for
# the host side; a URL naming anything else (a remote node, an unpublishable lab
# container) is left exactly as the operator set it.
# Only hosts whose container port is the same port published on the host. A service
# whose ports differ (searxng: 8080 inside, 8088 on the host, where 8080 is Open WebUI)
# must not be rewritten blindly — add it only with an explicit port mapping.
_CONTAINER_ONLY_HOSTS="host.docker.internal portal-pipeline"
for _var in $(compgen -v); do
    case "$_var" in
        *_URL | *_ENDPOINT) ;;
        *) continue ;;
    esac
    _value="${!_var}"
    for _host in $_CONTAINER_ONLY_HOSTS; do
        _value="${_value//$_host/localhost}"
    done
    if [ "$_value" != "${!_var}" ]; then
        export "${_var}=${_value}"
    fi
done

export PYTHONPATH="$PORTAL_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$PORTAL_ROOT"

# shellcheck source=scripts/lib/venv_preflight.sh
source "$PORTAL_ROOT/scripts/lib/venv_preflight.sh"

# What this process runs: the repository HEAD at launch and how many uncommitted changes
# portal/ had (root-fix Part 2c). MCP health routes report both; WFE preflight checks them.
# Not a git checkout (or no git): stamp unknown, never stop the service from starting.
if PORTAL_BUILD_SHA="$(git -C "$PORTAL_ROOT" rev-parse HEAD 2>/dev/null)"; then
    PORTAL_BUILD_DIRTY="$(git -C "$PORTAL_ROOT" status --porcelain -- portal 2>/dev/null | wc -l | tr -d ' ')"
else
    PORTAL_BUILD_SHA=unknown
    PORTAL_BUILD_DIRTY=-1
fi
export PORTAL_BUILD_SHA PORTAL_BUILD_DIRTY

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
    eg2-embedding)
        # EmbeddingGemma 2 platform embedder (:8946), TASK_EMBEDDINGGEMMA2_PLATFORM_V1.
        # Its OWN venv (scripts/eg2-venv-setup.sh) — never the project .venv, so
        # the fragile MLX runtime behind drift gate D1 is untouched.
        EG2_PY="${EG2_VENV:-$HOME/.portal5/eg2-venv}/bin/python3"
        if [ ! -x "$EG2_PY" ]; then
            echo "eg2-embedding: venv missing — run scripts/eg2-venv-setup.sh" >&2
            exit 1
        fi
        # launchd: HF revalidation HEADs hang; the model is pre-fetched by setup.
        export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
        # ffmpeg (audio/video decode) lives here; launchd starts with a bare PATH.
        export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
        exec "$EG2_PY" "$PORTAL_ROOT/scripts/eg2-embedding-server.py" --port "${EG2_PORT:-8946}"
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
    compliance-mcp-eval)
        # The compliance EVALUATION instance (WFE root-fix Part 2c-2): every state path under
        # its own root, built from public material only; serves verified read-only tools.
        exec "$PY" -m portal.modules.compliance.core.eval_instance serve \
            --root "${COMPLIANCE_EVAL_ROOT:-$HOME/.portal-data/compliance-eval}" \
            --port "${COMPLIANCE_EVAL_PORT:-8948}"
        ;;
    detection-mcp)
        export DETECTION_MCP_PORT="${DETECTION_MCP_PORT:-8938}"
        exec "$PY" -m portal.modules.detection.tools.detection_mcp
        ;;
    data-mcp)
        export DATA_MCP_PORT="${DATA_MCP_PORT:-8939}"
        # Same root the Docker services mount (${AI_OUTPUT_DIR:-$HOME/AI_Output}); an explicit
        # DATA_MCP_ROOT still wins. Without this a custom AI_OUTPUT_DIR left data on another root.
        export DATA_MCP_ROOT="${DATA_MCP_ROOT:-${AI_OUTPUT_DIR:-$HOME/AI_Output}}"
        exec "$PY" -m portal.modules.data.tools.data_mcp
        ;;
    netforensics-mcp)
        export NETFORENSICS_MCP_PORT="${NETFORENSICS_MCP_PORT:-8941}"
        # tshark ships CLI tools under this path on macOS
        export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Wireshark.app/Contents/MacOS:$PATH"
        exec "$PY" -m portal.modules.netforensics.tools.netforensics_mcp
        ;;
    review-mcp)
        export REVIEW_MCP_PORT="${REVIEW_MCP_PORT:-8943}"
        exec "$PY" -m portal.modules.security.tools.review_mcp
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
