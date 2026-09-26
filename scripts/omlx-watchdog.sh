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
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
mkdir -p "$LOG_DIR"

_log() { printf '%s  %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$LOG_FILE"; }

# --- DeepSeek-R1 oMLX tool-parser self-check (P5-FANOUT-001 follow-up) ---
# scripts/install_omlx_parsers.sh copies deepseek_r1_tool_parser.py into
# Homebrew's Cellar tree and stamps the model's tokenizer_config — both are
# wiped by `brew upgrade omlx` (site-packages replaced wholesale), and it
# already happened once silently: the council-operator seat lost tool calls
# with no error anywhere, only discovered by a live probe weeks later.
# config/backends.yaml's supports_tools:true on this model is a static claim;
# this check is what actually backs it, on the same interval that already
# watches for oMLX wedging.
PARSER_SRC="${REPO_ROOT}/scripts/omlx/deepseek_r1_tool_parser.py"
MODEL_DIR="/Volumes/data01/omlx-models/DeepSeek-R1-0528-Qwen3-8B-4bit"
PARSER_STATE_FILE="${OMLX_WATCHDOG_PARSER_STATE:-${TMPDIR:-/tmp}/portal5-omlx-parser-watchdog.state}"

_check_deepseek_parser() {
    local target_dir stamped
    target_dir="$(ls -d /opt/homebrew/Cellar/omlx/*/libexec/lib/python*/site-packages/mlx_lm/tool_parsers 2>/dev/null | sort | tail -1)"
    if [ -z "$target_dir" ]; then
        _log "PARSER CHECK: no mlx_lm/tool_parsers dir found under Cellar — skipping (oMLX layout may have changed)"
        return 0
    fi
    if [ ! -f "$target_dir/deepseek_r1.py" ] || ! cmp -s "$PARSER_SRC" "$target_dir/deepseek_r1.py"; then
        _log "PARSER CHECK FAILED: deepseek_r1.py missing or stale in ${target_dir}"
        return 1
    fi
    if [ ! -f "${MODEL_DIR}/tokenizer_config.json" ]; then
        _log "PARSER CHECK: model dir ${MODEL_DIR} not found — skipping stamp check"
        return 0
    fi
    stamped="$(python3 -c "import json; print(json.load(open('${MODEL_DIR}/tokenizer_config.json')).get('tool_parser_type',''))" 2>/dev/null || true)"
    if [ "$stamped" != "deepseek_r1" ]; then
        _log "PARSER CHECK FAILED: tokenizer_config.json tool_parser_type='${stamped}' (expected deepseek_r1)"
        return 1
    fi
    return 0
}

_run_parser_check() {
    if _check_deepseek_parser; then
        if [ -f "$PARSER_STATE_FILE" ] && [ "$(cat "$PARSER_STATE_FILE" 2>/dev/null || echo 0)" != "0" ]; then
            _log "PARSER CHECK: recovered"
        fi
        echo 0 > "$PARSER_STATE_FILE"
        return
    fi
    parser_fails="$(cat "$PARSER_STATE_FILE" 2>/dev/null || echo 0)"
    case "$parser_fails" in ''|*[!0-9]*) parser_fails=0 ;; esac
    parser_fails=$((parser_fails + 1))
    echo "$parser_fails" > "$PARSER_STATE_FILE"
    if [ "$parser_fails" -eq 1 ]; then
        _log "PARSER CHECK: reinstalling via install_omlx_parsers.sh"
        if "${REPO_ROOT}/scripts/install_omlx_parsers.sh" >> "$LOG_FILE" 2>&1; then
            _log "PARSER CHECK: reinstalled — restarting oMLX to load it"
            brew services restart "$BREW_SERVICE" >> "$LOG_FILE" 2>&1 \
                && _log "restart issued OK (parser reinstall)" \
                || _log "restart FAILED after parser reinstall — manual intervention needed"
        else
            _log "PARSER CHECK: install_omlx_parsers.sh FAILED — manual intervention needed"
        fi
    else
        _log "PARSER CHECK: still failing after reinstall attempt (${parser_fails} consecutive checks) — needs a human, not retrying again"
    fi
}

code="$(curl -fsS -o /dev/null -m "$PROBE_TIMEOUT" -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || true)"

if [ "$code" = "200" ]; then
    if [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE" 2>/dev/null || echo 0)" != "0" ]; then
        _log "recovered — oMLX answering 200 on ${HEALTH_URL}"
    fi
    echo 0 > "$STATE_FILE"
    _run_parser_check
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
