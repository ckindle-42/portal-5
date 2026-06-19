#!/bin/bash
# Portal 5 — opencode in PORTAL mode (default).
#
# Runs opencode from the repo root so it auto-discovers opencode.jsonc (Portal pipeline
# as the AI backend, cloud providers disabled) and .mcp.json. All inference is local.
#
# Usage:  scripts/oc-portal.sh [any extra opencode args]   (default arg: ".")
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f opencode.jsonc ]; then
  echo "warning: opencode.jsonc not found at $REPO_ROOT — falling back to opencode defaults" >&2
fi

# opencode reads PIPELINE_API_KEY from the environment (per opencode.jsonc "env").
if [ -f .env ] && grep -q '^PIPELINE_API_KEY=' .env; then
  export "$(grep '^PIPELINE_API_KEY=' .env | head -1 | xargs)"
fi

if [ "$#" -eq 0 ]; then
  exec opencode .
else
  exec opencode "$@"
fi
