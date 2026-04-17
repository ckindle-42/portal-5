#!/bin/bash
# Portal 5 — embedding server launchd wrapper
#
# Called by com.portal5.embedding launchd agent. Sources .env so that
# EMBEDDING_MODEL and EMBEDDING_HOST_PORT overrides are respected.
# launchd does not inherit the user shell environment, so .env must be
# sourced explicitly here.

set -euo pipefail

PORTAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PORTAL_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

EMBEDDING_MODEL="${EMBEDDING_MODEL:-microsoft/harrier-oss-v1-0.6b}"
EMBEDDING_HOST_PORT="${EMBEDDING_HOST_PORT:-8917}"
EM_VENV="${HOME}/.portal5/embedding-venv"
EM_PY="${EM_VENV}/bin/python3"

if [ ! -x "$EM_PY" ]; then
    echo "ERROR: embedding venv not found at $EM_VENV" >&2
    echo "Run: ./launch.sh install-embedding-service" >&2
    exit 1
fi

exec "$EM_PY" "$PORTAL_ROOT/scripts/embedding-server.py" \
    --model "$EMBEDDING_MODEL" \
    --port "$EMBEDDING_HOST_PORT" \
    --host 0.0.0.0
