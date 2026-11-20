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
detection-mcp|data-mcp|netforensics-mcp|review-mcp|wiki-mcp|git-mcp|unifi-mcp) ;;
    *)
        echo "Unknown native MCP service: ${SERVICE:-<empty>}" >&2
        exit 2
        ;;
esac

if [ ! -x "$PY" ]; then
    echo "Portal venv interpreter missing: $PY" >&2
    exit 1
fi

# shellcheck source=scripts/lib/host_dotenv.sh
source "$PORTAL_ROOT/scripts/lib/host_dotenv.sh"

# `.env` is shared with the Docker stack, so its URLs are written from a CONTAINER's
# point of view (OLLAMA_URL=http://host.docker.internal:11434,
# PIPELINE_URL=http://portal-pipeline:9099). Every service started here is host-native,
# where those names do not resolve. Rewrite the Docker-only host of any exported
# *_URL / *_ENDPOINT to loopback. Only hosts whose container port is the same port
# published on the host (not searxng, whose container :8080 is Open WebUI on the host).
_rewrite_container_urls() {
    local _var _value _host
    local _hosts="host.docker.internal portal-pipeline"
    for _var in $(compgen -v); do
        case "$_var" in
            *_URL | *_ENDPOINT) ;;
            *) continue ;;
        esac
        _value="${!_var}"
        for _host in $_hosts; do
            _value="${_value//$_host/localhost}"
        done
        if [ "$_value" != "${!_var}" ]; then
            export "${_var}=${_value}"
        fi
    done
}

# Export only the keys this service's code reads, then rewrite container URLs.
_host_dotenv() {
    portal_export_dotenv_keys "$ENV_FILE" "$@"
    _rewrite_container_urls
}

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
        _host_dotenv AI_OUTPUT_DIR WORKSPACE_DIR HF_HOME HF_HUB_CACHE HUGGINGFACE_HUB_CACHE XDG_CACHE_HOME \
            MLX_TRANSCRIBE_PORT MLX_TRANSCRIBE_HOST MLX_PARAKEET_MODEL MLX_PARAKEET_CHUNK_S \
            MLX_PARAKEET_OVERLAP_S MLX_DIARIZE_MODEL MLX_DIARIZE_MAX_S MLX_AUDIO_IDLE_UNLOAD_S \
            MLX_DIARIZE_FULL_CONTEXT_MAX_S MLX_DIARIZE_THRESHOLD MLX_DIARIZE_MIN_DURATION \
            MLX_DIARIZE_MERGE_GAP MLX_DIARIZE_CHUNK_S MLX_DIARIZE_MIN_TURN
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
        _host_dotenv AI_OUTPUT_DIR \
            HF_HOME HF_HUB_CACHE HUGGINGFACE_HUB_CACHE XDG_CACHE_HOME \
            MLX_SPEECH_PORT MLX_SPEECH_HOST MLX_TTS_BACKEND MLX_TTS_VOICE MLX_TTS_SPEED \
            MLX_KOKORO_MODEL MLX_QWEN3_TTS_CUSTOM MLX_QWEN3_TTS_DESIGN MLX_CLONE_MODEL \
            MLX_CHATTERBOX_MODEL MLX_QWEN3_ASR VOICE_PROFILES_DIR MLX_AUDIO_IDLE_UNLOAD_S
        # Same fragile MLX runtime as :8917/:8924/:8942 — same drift gate (D1).
        _venv_lock_preflight "mlx-speech" || exit 1
        # As for mlx-transcribe: under launchd the HF cached-file revalidation
        # HEAD requests hang, and mlx-audio shells out to ffmpeg on a bare PATH.
        export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
        export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
        exec "$PY" "$PORTAL_ROOT/scripts/mlx-speech.py"
        ;;
    vl-retrieval)
        _host_dotenv HF_HOME HF_HUB_CACHE HUGGINGFACE_HUB_CACHE \
            VL_EMBED_MODEL VL_RERANK_MODEL VL_EMBEDDING_DIM VL_RERANK_CHUNK VL_MAX_BATCH \
            VL_MX_CLEAR_CACHE VL_MX_CACHE_LIMIT_MB VL_QUERY_INSTRUCTION VL_MAX_PIXELS VL_MIN_PIXELS \
            VL_EMBEDDING_MAX_LENGTH VL_RERANKING_MAX_LENGTH VL_MX_EXECUTOR VL_MAX_REQUESTS \
            VL_IDLE_EXIT_SECONDS VL_PORT
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
        _host_dotenv EG2_VENV EG2_MODEL EG2_MODEL_ALIASES EG2_MODALITIES EG2_VL_DIM EG2_MAX_BATCH \
            EG2_STRICT_MODEL EG2_DTYPE EG2_MEDIA_ROOTS EG2_HOST EG2_PORT VL_UPSTREAM_URL \
            AI_OUTPUT_DIR HF_HOME HF_HUB_CACHE HUGGINGFACE_HUB_CACHE
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
        _host_dotenv PIPELINE_URL OLLAMA_URL PIPELINE_API_KEY PIPELINE_MCP_PORT \
            PIPELINE_MCP_REPO_ROOT PIPELINE_MCP_EXPLORER_MODEL
        export PIPELINE_URL="${PIPELINE_URL:-http://localhost:9099}"
        export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
        export PIPELINE_MCP_REPO_ROOT="${PIPELINE_MCP_REPO_ROOT:-$PORTAL_ROOT}"
        export PIPELINE_MCP_PORT="${PIPELINE_MCP_PORT:-8928}"
        exec "$PY" -m portal.platform.mcp_host.pipeline_mcp
        ;;
    mitre-mcp)
        _host_dotenv MITRE_MCP_PORT MCP_PORT
        export MITRE_MCP_PORT="${MITRE_MCP_PORT:-8929}"
        exec "$PY" -m portal.modules.security.tools.mitre_mcp
        ;;
    detections-mcp)
        _host_dotenv DETECTIONS_MCP_PORT MCP_PORT
        export DETECTIONS_MCP_PORT="${DETECTIONS_MCP_PORT:-8932}"
        exec "$PY" -m portal.modules.security.tools.detections_mcp
        ;;
    vulnintel-mcp)
        _host_dotenv VULNINTEL_MCP_PORT MCP_PORT VULNINTEL_AUDIT_LOG VULNINTEL_HTTP_TIMEOUT NVD_API_KEY
        export VULNINTEL_MCP_PORT="${VULNINTEL_MCP_PORT:-8934}"
        exec "$PY" -m portal.modules.vulnintel.tools.vulnintel_mcp
        ;;
    icsot-mcp)
        _host_dotenv ICSOT_MCP_PORT MCP_PORT
        export ICSOT_MCP_PORT="${ICSOT_MCP_PORT:-8936}"
        exec "$PY" -m portal.modules.icsot.tools.icsot_mcp
        ;;
    compliance-mcp)
        _host_dotenv COMPLIANCE_MCP_PORT MCP_PORT COMPLIANCE_EVAL_INSTANCE COMPLIANCE_DB_PATH \
            COMPLIANCE_OPERATOR_PROFILE COMPLIANCE_ORG_GRAPH COMPLIANCE_READING_CONTEXT_LIMIT \
            COMPLIANCE_READING_MODEL COMPLIANCE_REVIEWERS_PATH COMPLIANCE_MAPPING_STORE \
            COMPLIANCE_PAGES_DIR COMPLIANCE_TRANSPORT COMPLIANCE_LOAD_WAIT_S \
            PIPELINE_API_KEY PIPELINE_URL PIPELINE_BASE OLLAMA_BASE OLLAMA_URL BACKEND_CONFIG_PATH
        export COMPLIANCE_MCP_PORT="${COMPLIANCE_MCP_PORT:-8937}"
        exec "$PY" -m portal.modules.compliance.tools.compliance_mcp
        ;;
    compliance-mcp-eval)
        _host_dotenv COMPLIANCE_EVAL_ROOT COMPLIANCE_EVAL_PORT COMPLIANCE_EVAL_INSTANCE \
            COMPLIANCE_DB_PATH COMPLIANCE_MAPPING_STORE
        # The compliance EVALUATION instance (WFE root-fix Part 2c-2): every state path under
        # its own root, built from public material only; serves verified read-only tools.
        exec "$PY" -m portal.modules.compliance.core.eval_instance serve \
            --root "${COMPLIANCE_EVAL_ROOT:-$HOME/.portal-data/compliance-eval}" \
            --port "${COMPLIANCE_EVAL_PORT:-8948}"
        ;;
    detection-mcp)
        _host_dotenv DETECTION_MCP_PORT MCP_PORT DETECTION_YARA_ROOT AI_OUTPUT_DIR
        export DETECTION_MCP_PORT="${DETECTION_MCP_PORT:-8938}"
        exec "$PY" -m portal.modules.detection.tools.detection_mcp
        ;;
    data-mcp)
        _host_dotenv DATA_MCP_PORT MCP_PORT DATA_MCP_ROOT DATA_MCP_SESSIONS DATA_MCP_MAX_ROWS \
            DATA_MCP_MEMORY_LIMIT DATA_MCP_MEMORY_CEILING DATA_MCP_THREADS DATA_MCP_MAX_CONNS \
            AI_OUTPUT_DIR
        export DATA_MCP_PORT="${DATA_MCP_PORT:-8939}"
        # Same root the Docker services mount (${AI_OUTPUT_DIR:-$HOME/AI_Output}); an explicit
        # DATA_MCP_ROOT still wins. Without this a custom AI_OUTPUT_DIR left data on another root.
        export DATA_MCP_ROOT="${DATA_MCP_ROOT:-${AI_OUTPUT_DIR:-$HOME/AI_Output}}"
        exec "$PY" -m portal.modules.data.tools.data_mcp
        ;;
    netforensics-mcp)
        _host_dotenv NETFORENSICS_MCP_PORT MCP_PORT NETFORENSICS_ROOT NETFORENSICS_RECON_ENABLED \
            NETFORENSICS_TSHARK_TIMEOUT PORTAL_LAB_CIDR
        export NETFORENSICS_MCP_PORT="${NETFORENSICS_MCP_PORT:-8941}"
        # tshark ships CLI tools under this path on macOS
        export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Wireshark.app/Contents/MacOS:$PATH"
        exec "$PY" -m portal.modules.netforensics.tools.netforensics_mcp
        ;;
    review-mcp)
        _host_dotenv REVIEW_MCP_PORT MCP_PORT PIPELINE_API_KEY PIPELINE_URL OLLAMA_URL \
            PORTAL_HUNT_JUDGE_URL PORTAL_HUNT_JUDGE_MODEL PORTAL_HUNT_JUDGE_KEY_ENV \
            PORTAL_HUNT_JUDGE_BACKEND PORTAL_HUNT_EMBEDDING_URL PORTAL_HUNT_EMBEDDING_MODEL \
            PORTAL_HUNT_EMBEDDING_KEY_ENV PORTAL_HUNT_KNOWLEDGE_STORE PORTAL_HUNT_KNOWLEDGE_FAMILIES \
            PORTAL5_HUNT_DIR PORTAL5_REVIEW_DIR PORTAL5_REVIEW_EMBEDDING_DIM \
            PORTAL5_REVIEW_ENVIRONMENT_ID PORTAL_REVIEW_PIPELINE_URL PORTAL_REVIEW_OLLAMA_URL \
            PORTAL_REVIEW_OMLX_URL LAB_SPLUNK_PASSWORD HUNT_SPLUNK_CONCURRENCY
        export REVIEW_MCP_PORT="${REVIEW_MCP_PORT:-8943}"
        export PORTAL_HUNT_JUDGE_URL="${PORTAL_HUNT_JUDGE_URL:-http://localhost:9099}"
        export PORTAL_HUNT_JUDGE_MODEL="${PORTAL_HUNT_JUDGE_MODEL:-hunt-reasoning}"
        export PORTAL_HUNT_EMBEDDING_URL="${PORTAL_HUNT_EMBEDDING_URL:-http://localhost:9099}"
        export PORTAL_HUNT_EMBEDDING_MODEL="${PORTAL_HUNT_EMBEDDING_MODEL:-google/embeddinggemma-2}"
        exec "$PY" -m portal.modules.security.tools.review_mcp
        ;;
    wiki-mcp)
        _host_dotenv OLLAMA_URL WIKI_MCP_PORT MCP_PORT
        export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
        export WIKI_MCP_PORT="${WIKI_MCP_PORT:-8931}"
        exec "$PY" -m portal_wiki.wiki_mcp
        ;;
    git-mcp)
        _host_dotenv GIT_MCP_PORT GIT_MCP_CALL_TIMEOUT_S GIT_MCP_ALLOW_ROOT
        # Pipeline git surface (:8950). Read-only status/log/diff; commit/push
        # are confirm-gated by the Jarvis personal policy; the server refuses
        # the live Portal checkout it is deployed from.
        exec "$PY" -m portal.modules.orchestration.mcp.git_mcp
        ;;
    unifi-mcp)
        _host_dotenv STDIO_BRIDGE_CALL_TIMEOUT_S STDIO_BRIDGE_INIT_TIMEOUT_S STDIO_MCP_BRIDGE_ID
        # Stdio bridge (:8949) over the operator's sirkirby unifi-network-mcp
        # (~/mcp/unifi-network/run.sh, credentials outside the repo). launchd
        # starts with a bare PATH, so uvx must be findable.
        export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
        export STDIO_MCP_BRIDGE_ID=unifi
        exec "$PY" -m portal.modules.orchestration.mcp.stdio_bridge_mcp
        ;;
    *)
        echo "Unknown native MCP service: ${SERVICE:-<empty>}" >&2
        exit 2
        ;;
esac
