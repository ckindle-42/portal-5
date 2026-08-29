#!/usr/bin/env bash
# omlx-watchdog.sh — liveness watchdog for the host-native oMLX server (:8085).
#
# Why this exists: oMLX is supervised by Homebrew's `homebrew.mxcl.omlx`
# LaunchAgent, whose `KeepAlive` only restarts the process when it *exits*.
# oMLX has been observed to wedge instead — the process stays alive but stops
# answering on :8085 (RSS collapses, the OpenAI surface times out). launchd
# never notices, and every `omlx-*` backend group in config/backends.yaml then
# reports unhealthy (the "6/12 backends healthy" symptom) until someone runs
# `brew services restart omlx` by hand. This watchdog closes that gap: launchd
# runs it on an interval, it probes the OpenAI surface, and it restarts the
# brew service after two consecutive failures (one failure can just be a long
# cold model load on a single-user box).
set -u

HEALTH_URL="${OMLX_HEALTH_URL:-http://127.0.0.1:8085/v1/models}"
BREW_SERVICE="${OMLX_BREW_SERVICE:-jundot/omlx/omlx}"
STATE_FILE="${OMLX_WATCHDOG_STATE:-${TMPDIR:-/tmp}/portal5-omlx-watchdog.state}"
LOG_DIR="${HOME}/.portal5/logs"
LOG_FILE="${LOG_DIR}/omlx-watchdog.log"
FAIL_THRESHOLD=2
PROBE_TIMEOUT=8

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
mkdir -p "$LOG_DIR"

_log() { printf '%s  %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$LOG_FILE"; }

code="$(curl -fsS -o /dev/null -m "$PROBE_TIMEOUT" -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || true)"

if [ "$code" = "200" ]; then
    if [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE" 2>/dev/null || echo 0)" != "0" ]; then
        _log "recovered — oMLX answering 200 on ${HEALTH_URL}"
    fi
    echo 0 > "$STATE_FILE"
    exit 0
fi

fails="$(cat "$STATE_FILE" 2>/dev/null || echo 0)"
case "$fails" in ''|*[!0-9]*) fails=0 ;; esac
fails=$((fails + 1))
echo "$fails" > "$STATE_FILE"
_log "probe failed (http_code='${code:-000}') — consecutive failures: ${fails}/${FAIL_THRESHOLD}"

if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
    _log "restarting brew service '${BREW_SERVICE}'"
    if brew services restart "$BREW_SERVICE" >> "$LOG_FILE" 2>&1; then
        _log "restart issued OK"
    else
        _log "restart FAILED — check 'brew services list' and /opt/homebrew/var/log/omlx.log"
    fi
    echo 0 > "$STATE_FILE"
fi

exit 0
