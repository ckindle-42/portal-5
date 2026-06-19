#!/bin/bash
# Portal 5 — Claude Code in STOCK mode.
#
# Vanilla cloud Claude Code while sitting inside the repo: ignores the project's
# Portal .mcp.json without renaming or deleting it. Uses the documented MCP bypass
#   claude --strict-mcp-config --mcp-config '{}'
# (loads ONLY command-line MCP servers, ignores all file-based ones).
#
# Default: true vanilla (zero MCP servers).
# Set CC_STOCK_KEEP_GENERIC=1 to keep the 4 non-Portal servers (filesystem, fetch,
#   git, docker) and drop only portal-sandbox + portal-pipeline.
# Set CC_STOCK_IGNORE_SETTINGS=1 to also ignore project/local settings
#   (adds --setting-sources user).
#
# Usage:  scripts/cc-stock.sh [any extra claude args]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ARGS=(--strict-mcp-config)

if [ "${CC_STOCK_KEEP_GENERIC:-0}" = "1" ] && [ -f .mcp.json ]; then
  # Pass an inline config containing only the non-Portal servers.
  GENERIC_JSON="$(python3 - <<'PY'
import json
d = json.load(open(".mcp.json"))
servers = d.get("mcpServers", {})
keep = {k: v for k, v in servers.items()
        if k not in ("portal-sandbox", "portal-pipeline")}
print(json.dumps({"mcpServers": keep}))
PY
)"
  ARGS+=(--mcp-config "$GENERIC_JSON")
else
  ARGS+=(--mcp-config '{}')
fi

if [ "${CC_STOCK_IGNORE_SETTINGS:-0}" = "1" ]; then
  ARGS+=(--setting-sources user)
fi

exec claude "${ARGS[@]}" "$@"
