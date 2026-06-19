#!/bin/bash
# Portal 5 — opencode in STOCK mode.
#
# Vanilla opencode (your normal cloud providers / global config) while inside the repo,
# ignoring the project's opencode.jsonc without renaming it. opencode has no
# --strict MCP bypass, so this points OPENCODE_CONFIG at your global config file, which
# takes precedence in a way that excludes the project provider block.
#
# Note: opencode merges configs; OPENCODE_CONFIG loads between global and project. To
# fully ignore the Portal provider you normally run opencode from OUTSIDE the repo. This
# wrapper forces the global config explicitly; if you still see Portal models, run it
# from your home directory instead (cd ~ && opencode).
#
# Override the global config path with OC_GLOBAL_CONFIG if yours is non-standard.
#
# Usage:  scripts/oc-stock.sh [any extra opencode args]
set -euo pipefail

OC_GLOBAL_CONFIG="${OC_GLOBAL_CONFIG:-$HOME/.config/opencode/opencode.json}"

if [ ! -f "$OC_GLOBAL_CONFIG" ]; then
  echo "warning: global opencode config not found at $OC_GLOBAL_CONFIG" >&2
  echo "         set OC_GLOBAL_CONFIG=/path/to/your/opencode.json, or run 'cd ~ && opencode'" >&2
fi

export OPENCODE_CONFIG="$OC_GLOBAL_CONFIG"
exec opencode "$@"
