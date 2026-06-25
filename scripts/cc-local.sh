#!/bin/bash
# Portal 5 — Claude Code in LOCAL model mode.
#
# Routes Claude Code's AI inference through Portal 5's pipeline (:9099)
# instead of Anthropic cloud. All tokens stay on this machine.
#
# Usage:
#   scripts/cc-local.sh                                    # default: auto-agentic
#   scripts/cc-local.sh --model auto-coding-agentic        # Laguna-XS.2 33B agentic
#   scripts/cc-local.sh --model auto-agentic               # Qwen3-Coder-Next 80B / AgentWorld 35B fallback
#   scripts/cc-local.sh --model auto-reasoning             # DeepSeek-R1 reasoning
#   scripts/cc-local.sh --model auto-coding                # Qwen3-Coder 30B one-shot
#   scripts/cc-local.sh --model auto-security              # VulnLLM-R-7B security
#
# Any extra args pass through to claude (e.g. --no-git, --dangerously-skip-permissions).
#
# Prerequisites:
#   1. Stack running: ./launch.sh up
#   2. PIPELINE_API_KEY set in .env (auto-exported below)
#
# How it works:
#   ANTHROPIC_BASE_URL=http://localhost:9099 tells the claude CLI to send
#   all /v1/messages requests to portal-pipeline instead of Anthropic cloud.
#   ANTHROPIC_API_KEY=$PIPELINE_API_KEY satisfies the SDK's auth check.
#   The pipeline's /v1/messages endpoint translates to OpenAI format and
#   routes through the full workspace stack (routing, tools, streaming).
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Export PIPELINE_API_KEY from .env
if [ -f .env ] && grep -q '^PIPELINE_API_KEY=' .env; then
  export "$(grep '^PIPELINE_API_KEY=' .env | head -1 | xargs)"
fi

if [ -z "${PIPELINE_API_KEY:-}" ]; then
  echo "error: PIPELINE_API_KEY not set. Run ./launch.sh up first, or set it manually." >&2
  exit 1
fi

# Check pipeline is up
if ! curl -sf http://localhost:9099/health > /dev/null 2>&1; then
  echo "error: portal-pipeline not reachable at :9099. Run ./launch.sh up first." >&2
  exit 1
fi

export ANTHROPIC_BASE_URL="http://localhost:9099"
export ANTHROPIC_API_KEY="$PIPELINE_API_KEY"

# Default: heavy agentic workspace (Qwen3-Coder-Next 80B / AgentWorld 35B fallback).
# AgentWorld's env-simulation training (MCP/Terminal/SWE/Web trajectories) maps
# directly to Claude Code's agentic loop — ideal when the primary 80B isn't warm.
DEFAULT_MODEL="${CC_LOCAL_MODEL:-auto-agentic}"

# If --model is already in args, use it; otherwise inject the default.
HAS_MODEL=0
for arg in "$@"; do
  [ "$arg" = "--model" ] && HAS_MODEL=1 && break
done

if [ "$HAS_MODEL" -eq 0 ]; then
  exec claude --model "$DEFAULT_MODEL" "$@"
else
  exec claude "$@"
fi
