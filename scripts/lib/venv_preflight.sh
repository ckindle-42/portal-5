#!/usr/bin/env bash
# venv_preflight.sh — shared venv/lock drift gate for every service that
# resolves its interpreter from the project .venv (TASK_VL_RETRIEVAL_HARDENING
# _AND_CLOSEOUT_V2 D1).
#
# One implementation. Between 2026-04 and 2026-09 the venv was hand-patched to a
# VL-capable runtime while uv.lock still resolved the old one, so the next
# `uv run` (which re-syncs) would have silently destroyed it. embedding-launchd-
# wrapper.sh grew a drift assertion for :8917; this factors that out so :8942,
# :8918 and :8924 get the same protection.
#
# _venv_lock_preflight <service-label>
#   returns 0 if the venv matches uv.lock, 1 (with a direction-aware message on
#   stderr) on drift. Callers refuse to start on non-zero.
# shellcheck shell=bash

_venv_lock_preflight() {
    local label="${1:-service}"
    local root="${PORTAL_ROOT:?PORTAL_ROOT must be set}"
    local uv_bin="${UV_BIN:-${HOME}/.local/bin/uv}"
    [ -x "$uv_bin" ] || uv_bin="$(command -v uv 2>/dev/null || true)"
    if [ -z "$uv_bin" ]; then
        echo "[$label] WARNING: uv not found — cannot verify venv/lock; starting anyway." >&2
        return 0
    fi

    local out
    if out="$("$uv_bin" sync --project "$root" --all-extras --frozen --check 2>&1)"; then
        return 0
    fi

    echo "ERROR: [$label] project venv does not match uv.lock (dependency drift)." >&2
    echo "       Refusing to start against an unknown runtime." >&2
    local py="${root}/.venv/bin/python"
    [ -x "$py" ] || py="$(command -v python3 2>/dev/null || true)"
    local classified="" direction=""
    if [ -n "$py" ]; then
        classified="$(printf '%s\n' "$out" | "$py" "$root/scripts/venv_lock_direction.py" 2>/dev/null || true)"
    fi
    direction="${classified%%$'\n'*}"
    case "$direction" in
        lock_ahead|venv_ahead|reinstall|unknown)
            echo "       ${classified#*$'\n'}" >&2
            ;;
        *)
            echo "       could not tell which side is ahead. Refusing to sync." >&2
            ;;
    esac
    echo "$out" | grep -E '^\s*[+~-]' | head -40 >&2 || true
    return 1
}

# When `uv sync --check` says the lock is ahead (or only a same-version
# reinstall), bring the project venv up to uv.lock. A venv that is ahead is
# left untouched — sync would downgrade it.
_sync_venv_when_lock_ahead() {
    local root="${PORTAL_ROOT:?PORTAL_ROOT must be set}"
    local uv_bin="${UV_BIN:-${HOME}/.local/bin/uv}"
    [ -x "$uv_bin" ] || uv_bin="$(command -v uv 2>/dev/null || true)"
    if [ -z "$uv_bin" ]; then
        echo "ERROR: uv not found — cannot sync the project venv to uv.lock." >&2
        return 1
    fi
    local py="${root}/.venv/bin/python"
    [ -x "$py" ] || py="$(command -v python3 2>/dev/null || true)"
    local out
    if out="$("$uv_bin" sync --project "$root" --all-extras --frozen --check 2>&1)"; then
        return 0
    fi
    if [ -z "$py" ]; then
        echo "ERROR: cannot classify venv/lock drift (python missing)." >&2
        return 1
    fi
    local classified direction
    classified="$(printf '%s\n' "$out" | "$py" "$root/scripts/venv_lock_direction.py")" || {
        echo "ERROR: could not classify venv/lock drift." >&2
        return 1
    }
    direction="${classified%%$'\n'*}"
    case "$direction" in
        lock_ahead|reinstall)
            echo "[portal-5] ${classified#*$'\n'}"
            "$uv_bin" sync --project "$root" --all-extras --frozen
            ;;
        *)
            echo "ERROR: ${classified#*$'\n'}" >&2
            printf '%s\n' "$out" | head -40 >&2
            return 1
            ;;
    esac
}
