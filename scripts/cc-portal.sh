#!/bin/bash
# Portal 5 — Claude Code in PORTAL mode (default).
#
# Runs Claude Code from the repo root so it auto-discovers .mcp.json (filesystem,
# fetch, git, docker, portal-sandbox, portal-pipeline) and CLAUDE.md. Claude Code's
# intelligence is always Anthropic (cloud); Portal provides TOOLS only.
#
# Usage:  scripts/cc-portal.sh [any extra claude args]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f .mcp.json ]; then
  echo "warning: .mcp.json not found at $REPO_ROOT — Portal tools will be unavailable" >&2
fi

# Portal MCP tools that call the pipeline need the key in the environment.
if [ -f .env ] && grep -q '^PIPELINE_API_KEY=' .env; then
  export "$(grep '^PIPELINE_API_KEY=' .env | head -1 | xargs)"
fi

exec claude "$@"
