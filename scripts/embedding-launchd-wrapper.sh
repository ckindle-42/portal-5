#!/bin/bash
# Portal 5 — embedding server launchd wrapper
#
# Called by com.portal5.embedding launchd agent. Sources .env so that
# EMBEDDING_MODEL and EMBEDDING_HOST_PORT overrides are respected.
# launchd does not inherit the user shell environment, so .env must be
# sourced explicitly here.
#
# As of TASK_BULLY_SA5 P0.4 the default backend at :8917 is the ADOPTED
# Arm A MLX server (mlx_embeddings, Qwen3-Embedding-0.6B mxfp8) — it clears
# the one-session throughput bar and wins discovery precision (0.6875 vs
# Arm B's 0.4615). The retired CPU sentence-transformers path is reachable
# via `./launch.sh start-embedding-cpu-arm` (fallback only). Set
# EMBEDDING_BACKEND=mlx|cpu to override.

set -euo pipefail

PORTAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PORTAL_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

EMBEDDING_BACKEND="${EMBEDDING_BACKEND:-mlx}"
EMBEDDING_HOST_PORT="${EMBEDDING_HOST_PORT:-8917}"

if [ "$EMBEDDING_BACKEND" = "cpu" ]; then
    # ── retired CPU fallback (sentence-transformers harrier; P0.4 displaced) ──
    EMBEDDING_MODEL="${EMBEDDING_MODEL:-microsoft/harrier-oss-v1-0.6b}"
    EM_VENV="${HOME}/.portal5/embedding-venv"
    EM_PY="${EM_VENV}/bin/python3"
    EM_SITE_PACKAGES="${EM_VENV}/lib/python3.14/site-packages"
    EM_SERVICE_MODEL="${HOME}/.portal5/models/${EMBEDDING_MODEL//\//--}"

    if [ -d "$EM_SERVICE_MODEL" ]; then
        EMBEDDING_MODEL="$EM_SERVICE_MODEL"
    elif [[ "$EMBEDDING_MODEL" != /* ]]; then
        EM_MODEL_REPOSITORY="${HOME}/.cache/huggingface/hub/models--${EMBEDDING_MODEL//\//--}"
        EM_MODEL_REFERENCE="${EM_MODEL_REPOSITORY}/refs/main"
        EM_REVISION=""
        if [ -r "$EM_MODEL_REFERENCE" ]; then
            IFS= read -r EM_REVISION < "$EM_MODEL_REFERENCE" || true
        fi
        if [ -n "$EM_REVISION" ] && [ -d "${EM_MODEL_REPOSITORY}/snapshots/${EM_REVISION}" ]; then
            EMBEDDING_MODEL="${EM_MODEL_REPOSITORY}/snapshots/${EM_REVISION}"
        fi
    fi

    if [ ! -x "$EM_PY" ]; then
        echo "ERROR: embedding venv not found at $EM_VENV" >&2
        echo "Run: ./launch.sh install-embedding-service" >&2
        exit 1
    fi

    # A Homebrew patch-version replacement can leave the venv interpreter symlink
    # pointing at a compatible Python outside the venv prefix. Keep the installed
    # packages discoverable and resolve Hugging Face models from the local cache so
    # launchd startup never depends on network metadata.
    export PYTHONPATH="${EM_SITE_PACKAGES}${PYTHONPATH:+:${PYTHONPATH}}"
    export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"

    exec "$EM_PY" "$PORTAL_ROOT/scripts/embedding-server.py" \
        --model "$EMBEDDING_MODEL" \
        --port "$EMBEDDING_HOST_PORT" \
        --host 0.0.0.0
fi

# ── ADOPTED default: Arm A MLX embedding server (P0.4) ──────────────────────
# GPU-native via mlx_embeddings on :8917. Runs in the project venv (mlx_embeddings
# is a project dependency), not the retired CPU venv. uv is not on launchd's PATH,
# so its absolute path is used.
#
# TASK_VL_RUNTIME_LANDING_V4 P1.5 — drift guard.
# A plain `uv run` re-syncs the venv to uv.lock on every invocation. Between
# 2026-04 and 2026-09 the venv was hand-patched to a VL-capable mlx-embeddings
# 0.1.0 / torch 2.13.0 while the lock still resolved 0.0.5 / 2.11.0, so the next
# restart here would have silently destroyed the working runtime. The lock is now
# reconciled to the runtime; this wrapper runs with `--no-sync` (never mutate the
# venv from launchd) and asserts venv==lock up front, failing loudly on drift so
# the divergence can never again pass unnoticed.
UV_BIN="${UV_BIN:-${HOME}/.local/bin/uv}"

# Shared, direction-aware drift gate (D1) — one implementation, also used by
# :8942/:8918/:8924.
# shellcheck source=scripts/lib/venv_preflight.sh
source "$PORTAL_ROOT/scripts/lib/venv_preflight.sh"
_venv_lock_preflight "embedding :$EMBEDDING_HOST_PORT" || exit 1

exec "$UV_BIN" run --project "$PORTAL_ROOT" --no-sync python3 "$PORTAL_ROOT/scripts/embedding-server-mlx.py" \
    --model "${EMBEDDING_MODEL_ARM_A:-${HOME}/.portal5/models/Qwen3-Embedding-0.6B-mxfp8}" \
    --port "$EMBEDDING_HOST_PORT" \
    --host 0.0.0.0
