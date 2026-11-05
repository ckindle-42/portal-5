#!/usr/bin/env bash
# Flip PORTAL_TOOL_RESULT_CARRY on the deployed pipeline without rebuilding the image.
#
# The flag is read once at process import. Compose interpolates
# PORTAL_TOOL_RESULT_CARRY from the env file (deploy/portal-5/docker-compose.yml).
# This writes that key and force-recreates only portal-pipeline, the same
# `docker compose up -d --no-deps` launch.sh uses for one service, plus
# --force-recreate. No --build, so /health build_sha (PORTAL_BUILD_SHA) stays
# and the WFE deployed fingerprint does not move.
#
# The deployed stack belongs to the MAIN checkout, not to whatever worktree this
# script is run from, so main's .env is sourced with `set -a` (as launch.sh does)
# and compose runs from main's deploy/portal-5. Recreating from a worktree with no
# .env blanks every interpolated secret while build_sha and the flag both still
# look right. Refuses when health is unreachable before the recreate.
#
# The container env is fingerprinted before and after the recreate: every key must
# come back identical except PORTAL_TOOL_RESULT_CARRY, else the flag is put back and
# the container recreated again. Any failure after the env write restores the flag
# in the env file, so the live .env is never left flipped.
#
#   scripts/pipeline_tool_carry.sh on|off
#
# Tests set PORTAL_GIT, PORTAL_ENV_FILE, PORTAL_COMPOSE_DIR, PORTAL_DOCKER,
# PORTAL_CURL, PORTAL_HEALTH_URL, PORTAL_HEALTH_WAIT_S and PORTAL_HEALTH_INTERVAL_S.
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

GIT="${PORTAL_GIT:-git}"
DOCKER="${PORTAL_DOCKER:-docker}"
CURL="${PORTAL_CURL:-curl}"
HEALTH_URL="${PORTAL_HEALTH_URL:-http://127.0.0.1:9099/health}"
WAIT_S="${PORTAL_HEALTH_WAIT_S:-120}"
INTERVAL_S="${PORTAL_HEALTH_INTERVAL_S:-2}"
CONTAINER="${PORTAL_PIPELINE_CONTAINER:-portal5-pipeline}"
KEY=PORTAL_TOOL_RESULT_CARRY

# The main worktree is the parent of the shared git dir; every linked worktree shares it.
main_checkout() {
    local common
    common="$("$GIT" -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
    common="${common%/.git}"
    if [ -z "$common" ] || [ ! -d "$common" ]; then
        return 1
    fi
    printf '%s' "$common"
}

MAIN="$REPO_ROOT"
if resolved="$(main_checkout)"; then
    MAIN="$resolved"
else
    echo "pipeline-tool-carry: could not resolve the main checkout; using $REPO_ROOT" >&2
fi

ENV_FILE="${PORTAL_ENV_FILE:-$MAIN/.env}"
COMPOSE_DIR="${PORTAL_COMPOSE_DIR:-$MAIN/deploy/portal-5}"

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

snapshot() {
    "$DOCKER" inspect --format '{{json .Config.Env}}' "$CONTAINER" 2>/dev/null
}

# KEY=sha256(value) per key, flag excluded, so values never reach the log.
fingerprint() {
    python3 -c '
import hashlib, json, sys
try:
    env = json.load(sys.stdin)
except Exception:
    sys.exit(3)
if not isinstance(env, list):
    sys.exit(3)
for item in sorted(env):
    key, _, value = item.partition("=")
    if key == sys.argv[1]:
        continue
    print(key + "=" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16])
' "$KEY"
}

flag_of() {
    python3 -c '
import json, sys
for item in json.load(sys.stdin):
    key, _, value = item.partition("=")
    if key == sys.argv[1]:
        print(value)
        break
' "$KEY"
}

flag_value() {
    local line
    line="$(grep -E "^${KEY}=" "$1" 2>/dev/null | tail -n 1 || true)"
    if [ -z "$line" ]; then
        return 1
    fi
    printf '%s' "${line#*=}"
}

write_flag() {
    local file="$1" value="$2" tmp
    tmp="$(mktemp "${TMPDIR:-/tmp}/portal-tool-carry.XXXXXX")"
    grep -vE "^${KEY}=" "$file" >"$tmp" || true
    printf '%s=%s\n' "$KEY" "$value" >>"$tmp"
    if ! cat "$tmp" >"$file"; then
        rm -f "$tmp"
        echo "pipeline-tool-carry: could not write $file" >&2
        return 1
    fi
    rm -f "$tmp"
}

drop_flag() {
    local file="$1" tmp
    tmp="$(mktemp "${TMPDIR:-/tmp}/portal-tool-carry.XXXXXX")"
    grep -vE "^${KEY}=" "$file" >"$tmp" || true
    if ! cat "$tmp" >"$file"; then
        rm -f "$tmp"
        echo "pipeline-tool-carry: could not write $file" >&2
        return 1
    fi
    rm -f "$tmp"
}

restore_flag() {
    if [ "$2" -eq 1 ]; then
        write_flag "$1" "$3"
    else
        drop_flag "$1"
    fi
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

if ! before_json="$(snapshot)"; then
    echo "pipeline-tool-carry: cannot read the running pipeline container env; refuse to recreate" >&2
    exit 1
fi
before_env="$(printf '%s' "$before_json" | fingerprint)"
if [ -z "$before_env" ]; then
    echo "pipeline-tool-carry: container env is empty; refuse to recreate" >&2
    exit 1
fi
before_flag="$(printf '%s' "$before_json" | flag_of)"

ENV_HAD=0
ENV_OLD=""
COMPOSE_FILE=""
COMPOSE_HAD=0
COMPOSE_OLD=""
ENV_WRITTEN=0
DONE=0

on_exit() {
    if [ "$DONE" -eq 1 ] || [ "$ENV_WRITTEN" -eq 0 ]; then
        return 0
    fi
    set +e
    restore_flag "$ENV_FILE" "$ENV_HAD" "$ENV_OLD"
    echo "pipeline-tool-carry: failure; restored ${KEY}=${ENV_OLD:-<absent>} in $ENV_FILE" >&2
    if [ -n "$COMPOSE_FILE" ]; then
        restore_flag "$COMPOSE_FILE" "$COMPOSE_HAD" "$COMPOSE_OLD"
    fi
    return 0
}
trap on_exit EXIT

# Recreate exactly the way launch.sh does: source the env file, then compose from its dir.
recreate() {
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    export "${KEY}=$1"
    (
        cd "$COMPOSE_DIR"
        "$DOCKER" compose up -d --no-deps --force-recreate portal-pipeline
    )
}

if ENV_OLD="$(flag_value "$ENV_FILE")"; then
    ENV_HAD=1
else
    ENV_OLD=""
fi
ENV_WRITTEN=1
write_flag "$ENV_FILE" "$VALUE"

compose_env="$COMPOSE_DIR/.env"
if [ -f "$compose_env" ] && [ ! "$ENV_FILE" -ef "$compose_env" ]; then
    if COMPOSE_OLD="$(flag_value "$compose_env")"; then
        COMPOSE_HAD=1
    else
        COMPOSE_OLD=""
    fi
    COMPOSE_FILE="$compose_env"
    write_flag "$compose_env" "$VALUE"
fi

recreate "$VALUE"

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

if ! after_json="$(snapshot)"; then
    echo "pipeline-tool-carry: cannot read the pipeline container env after the recreate" >&2
    exit 1
fi
after_env="$(printf '%s' "$after_json" | fingerprint)"
if [ "$before_env" != "$after_env" ]; then
    delta="$(diff <(printf '%s\n' "$before_env") <(printf '%s\n' "$after_env") | head -n 20 || true)"
    echo "pipeline-tool-carry: pipeline container env changed across the recreate (${KEY} excluded):" >&2
    printf '%s\n' "$delta" >&2
    restore_flag "$ENV_FILE" 1 "${before_flag:-false}"
    if [ -n "$COMPOSE_FILE" ]; then
        write_flag "$COMPOSE_FILE" "${before_flag:-false}"
    fi
    ENV_WRITTEN=0
    recreate "${before_flag:-false}" || true
    echo "pipeline-tool-carry: recreated again with ${KEY}=${before_flag:-false}" >&2
    exit 1
fi

if ! got="$("$DOCKER" exec "$CONTAINER" printenv "$KEY")"; then
    echo "pipeline-tool-carry: printenv $KEY failed" >&2
    exit 1
fi
got="${got//$'\r'/}"
got="${got%%$'\n'*}"
if [ "$got" != "$VALUE" ]; then
    echo "pipeline-tool-carry: container ${KEY}=${got:-<unset>} want ${VALUE}" >&2
    exit 1
fi

DONE=1
echo "pipeline-tool-carry: ${KEY}=${VALUE} build_sha=${before}"
