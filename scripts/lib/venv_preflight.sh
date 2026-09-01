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
    if echo "$out" | grep -qE '^\s*[-~]'; then
        echo "       The venv is AHEAD of the lock. Do NOT run 'uv sync --all-extras'" >&2
        echo "       (it would uninstall/downgrade the packages below). Reconcile the" >&2
        echo "       LOCK to the venv ('uv lock') after reviewing the diff, or restore" >&2
        echo "       a known-good venv from ~/.portal5/backups/." >&2
    else
        echo "       The venv is behind the lock. Run 'uv sync --all-extras'" >&2
        echo "       (after reviewing the diff) to catch it up." >&2
    fi
    echo "$out" | grep -E '^\s*[+~-]' | head -40 >&2 || true
    return 1
}
