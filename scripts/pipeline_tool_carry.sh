#!/usr/bin/env bash
# Flip PORTAL_TOOL_RESULT_CARRY on the running pipeline without rebuilding the image.
#
# The flag is read once at process import. Compose interpolates
# PORTAL_TOOL_RESULT_CARRY from the env file (deploy/portal-5/docker-compose.yml).
# This writes that key and force-recreates only portal-pipeline, the same
# `docker compose up -d --no-deps` launch.sh uses for one service, plus
# --force-recreate. No --build, so /health build_sha (PORTAL_BUILD_SHA) stays
# and the WFE deployed fingerprint does not move. Never loads the env file
# into the shell, and does not create one: a one-line file would blank every other
# interpolation. Refuses when health is unreachable before the recreate.
#
#   scripts/pipeline_tool_carry.sh on|off
#
# Tests set PORTAL_ENV_FILE, PORTAL_COMPOSE_DIR, PORTAL_DOCKER, PORTAL_CURL,
# PORTAL_HEALTH_URL, PORTAL_HEALTH_WAIT_S, and PORTAL_HEALTH_INTERVAL_S.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

usage() {
    echo "usage: scripts/pipeline_tool_carry.sh on|off" >&2
    exit 2
}

if [ "$#" -ne 1 ]; then
    usage
fi
case "$1" in
    on) VALUE=true ;;
    off) VALUE=false ;;
    *) usage ;;
esac

ENV_FILE="${PORTAL_ENV_FILE:-$REPO_ROOT/.env}"
COMPOSE_DIR="${PORTAL_COMPOSE_DIR:-$REPO_ROOT/deploy/portal-5}"
DOCKER="${PORTAL_DOCKER:-docker}"
CURL="${PORTAL_CURL:-curl}"
HEALTH_URL="${PORTAL_HEALTH_URL:-http://127.0.0.1:9099/health}"
WAIT_S="${PORTAL_HEALTH_WAIT_S:-120}"
INTERVAL_S="${PORTAL_HEALTH_INTERVAL_S:-2}"
KEY=PORTAL_TOOL_RESULT_CARRY

if [ ! -f "$ENV_FILE" ]; then
    echo "pipeline-tool-carry: env file missing: $ENV_FILE" >&2
    exit 2
fi
if [ ! -d "$COMPOSE_DIR" ]; then
    echo "pipeline-tool-carry: compose dir missing: $COMPOSE_DIR" >&2
    exit 1
fi

fetch_health() {
    "$CURL" -fsS --max-time 5 "$HEALTH_URL"
}

sha_of() {
    python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("build_sha") or ""))'
}

if ! before_body="$(fetch_health)"; then
    echo "pipeline-tool-carry: pipeline health unreachable; refuse to recreate" >&2
    exit 1
fi
before="$(printf '%s' "$before_body" | sha_of)"
if [ -z "$before" ]; then
    echo "pipeline-tool-carry: health returned no build_sha" >&2
    exit 1
fi

upsert_env() {
    local file="$1" tmp
    tmp="$(mktemp "${TMPDIR:-/tmp}/portal-tool-carry.XXXXXX")"
    grep -vE "^${KEY}=" "$file" >"$tmp" || true
    printf '%s=%s\n' "$KEY" "$VALUE" >>"$tmp"
    if ! cat "$tmp" >"$file"; then
        rm -f "$tmp"
        echo "pipeline-tool-carry: could not write $file" >&2
        exit 1
    fi
    rm -f "$tmp"
}

upsert_env "$ENV_FILE"
compose_env="$COMPOSE_DIR/.env"
if [ -f "$compose_env" ] && [ ! "$ENV_FILE" -ef "$compose_env" ]; then
    upsert_env "$compose_env"
fi

export PORTAL_TOOL_RESULT_CARRY="$VALUE"
(
    cd "$COMPOSE_DIR"
    "$DOCKER" compose up -d --no-deps --force-recreate portal-pipeline
)

deadline=$((SECONDS + WAIT_S))
after=""
while :; do
    if after_body="$(fetch_health 2>/dev/null)"; then
        after="$(printf '%s' "$after_body" | sha_of)"
        if [ -n "$after" ]; then
            break
        fi
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
        break
    fi
    sleep "$INTERVAL_S"
done
if [ "$after" != "$before" ]; then
    echo "pipeline-tool-carry: build_sha changed (${before} -> ${after:-unreachable})" >&2
    exit 1
fi

if ! got="$("$DOCKER" exec portal5-pipeline printenv PORTAL_TOOL_RESULT_CARRY)"; then
    echo "pipeline-tool-carry: printenv PORTAL_TOOL_RESULT_CARRY failed" >&2
    exit 1
fi
got="${got//$'\r'/}"
got="${got%%$'\n'*}"
if [ "$got" != "$VALUE" ]; then
    echo "pipeline-tool-carry: container ${KEY}=${got:-<unset>} want ${VALUE}" >&2
    exit 1
fi

echo "pipeline-tool-carry: ${KEY}=${VALUE} build_sha=${before}"
