#!/usr/bin/env bash
# Export named keys from a dotenv file without sourcing it.
# Sourcing .env into a host launchd job imports container paths
# (PROMETHEUS_MULTIPROC_DIR=/dev/shm/...) that do not exist on macOS.
# shellcheck shell=bash

# portal_export_dotenv_keys FILE KEY [KEY...]
# Missing and empty keys stay unset so the caller's defaults still apply.
# The last assignment wins. Quotes in the value are stripped, matching the
# security-sweep plist (756bf3939).
portal_export_dotenv_keys() {
    local file="$1" k v
    shift
    [ -f "$file" ] || return 0
    for k in "$@"; do
        v="$(grep -E "^${k}=" "$file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'" || true)"
        [ -n "$v" ] && export "${k}=${v}"
    done
    return 0
}
