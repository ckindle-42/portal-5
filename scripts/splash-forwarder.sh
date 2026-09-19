#!/usr/bin/env bash
# splash-forwarder.sh — supervisor for the splash host forwarder (:8086).
#
# Why this exists: splash is v1.0, deliberately binds 127.0.0.1:8000 with no
# port flag, and the pipeline container can only reach host services through
# host.docker.internal — a loopback-only bind is unreachable from there. A raw
# socat TCP relay on :8086 re-exposes splash to the container path; splash's
# API key is mandatory on that surface (mirror oMLX, which refuses any
# non-loopback bind without one).
#
# What this script supervises, and what it deliberately does not:
#   * it probes splash DIRECT (127.0.0.1:8000) and THROUGH the relay
#     (127.0.0.1:8086); if the relay is broken while splash answers, it
#     restarts the socat relay after two consecutive failures (one failure can
#     be a long in-flight wave — same threshold logic as omlx-watchdog.sh).
#   * it never starts or restarts splash itself. `splash serve` is one-model-
#     at-a-time and operator-run; auto-starting it here could evict a model
#     another lane is using. ./launch.sh must not start this either.
set -u

SPLASH_DIRECT_URL="${SPLASH_DIRECT_URL:-http://127.0.0.1:8000/v1/models}"
RELAY_URL="${SPLASH_RELAY_URL:-http://127.0.0.1:8086/v1/models}"
STATE_FILE="${SPLASH_FORWARDER_STATE:-${TMPDIR:-/tmp}/portal5-splash-forwarder.state}"
LOG_DIR="${HOME}/.portal5/logs"
LOG_FILE="${LOG_DIR}/splash-forwarder.log"
FAIL_THRESHOLD=2
PROBE_TIMEOUT=8
SOCAT_ARGS="TCP-LISTEN:8086,fork,reuseaddr TCP:127.0.0.1:8000"

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
mkdir -p "$LOG_DIR"

_log() { printf '%s  %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$LOG_FILE"; }

_direct="$(curl -fsS -o /dev/null -m "$PROBE_TIMEOUT" -w '%{http_code}' "$SPLASH_DIRECT_URL" 2>/dev/null || true)"
_relay="$(curl -fsS -o /dev/null -m "$PROBE_TIMEOUT" -w '%{http_code}' "$RELAY_URL" 2>/dev/null || true)"

if [ "$_relay" = "200" ]; then
    if [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE" 2>/dev/null || echo 0)" != "0" ]; then
        _log "recovered — relay answering 200 on ${RELAY_URL}"
    fi
    echo 0 > "$STATE_FILE"
    exit 0
fi

if [ "$_direct" != "200" ]; then
    # splash itself is down (or loading). Nothing to relay; record it and wait.
    # Auto-starting the operator's `splash serve` is out of scope by design.
    _log "splash direct probe failed (http_code='${_direct:-000}') — relay left alone"
    exit 0
fi

fails="$(cat "$STATE_FILE" 2>/dev/null || echo 0)"
case "$fails" in ''|*[!0-9]*) fails=0 ;; esac
fails=$((fails + 1))
echo "$fails" > "$STATE_FILE"
_log "relay probe failed (direct=${_direct} relay='${_relay:-000}') — consecutive failures: ${fails}/${FAIL_THRESHOLD}"

if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
    _log "restarting socat relay: ${SOCAT_ARGS}"
    pkill -f "socat ${SOCAT_ARGS}" 2>/dev/null || true
    nohup socat ${SOCAT_ARGS} >> "$LOG_FILE" 2>&1 &
    relay_pid=$!
    sleep 2
    if curl -fsS -o /dev/null -m "$PROBE_TIMEOUT" "$RELAY_URL" 2>/dev/null; then
        _log "relay restart issued OK (pid ${relay_pid})"
    else
        _log "relay restart did not come up yet (pid ${relay_pid}) — will re-probe next run"
    fi
    echo 0 > "$STATE_FILE"
fi

exit 0
