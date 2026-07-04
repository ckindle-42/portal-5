---
id: unit-MCP_DEV_TOOLING-mode-b-local-model-intelligence-portal-tools-cc-lo
kind: why
title: "MCP_DEV_TOOLING \u2014 Mode B \u2014 Local model intelligence + Portal tools\
  \ (`cc-local.sh`)"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: "Mode B \u2014 Local model intelligence + Portal tools (`cc-local.sh`)"
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.873197
updated_at: 1783195000.873197
---


Portal 5's local models provide the AI via the pipeline's `/v1/messages` Anthropic
compatibility endpoint. All tokens stay on your hardware. Same tool set as Mode A.

```bash
scripts/cc-local.sh                              # default: auto-agentic workspace
scripts/cc-local.sh --model auto-coding-agentic  # Laguna-XS.2 33B (agentic loop)
scripts/cc-local.sh --model auto-agentic         # Qwen3-Coder-Next 80B / AgentWorld 35B fallback
scripts/cc-local.sh --model auto-agentic-lite    # AgentWorld 35B direct (lighter, 45 t/s)
scripts/cc-local.sh --model auto-agentic-ornith  # Ornith-1.0-35B direct — agentic option, not a replacement
scripts/cc-local.sh --model auto-coding          # Qwen3-Coder 30B (one-shot)
scripts/cc-local.sh --model auto-coding-northmini # North-Mini-Code 30B-A3B — coding diversity option
scripts/cc-local.sh --model auto-reasoning       # DeepSeek-R1-0528 8B (reasoning)
scripts/cc-local.sh --model auto-security        # VulnLLM-R-7B (security)
```

**How it works:** `cc-local.sh` sets `ANTHROPIC_BASE_URL=http://localhost:9099` and
`ANTHROPIC_API_KEY=$PIPELINE_API_KEY`, then launches `claude`. The claude CLI sends all
`/v1/messages` requests to portal-pipeline instead of Anthropic's servers.
Portal-pipeline's `/v1/messages` endpoint translates to OpenAI format, routes through
the workspace stack (LLM router → backend selection → streaming), and returns Anthropic
SSE format. No change to `.mcp.json` — all Portal tools still available.

**AgentWorld for IDE use:** AgentWorld (Qwen-AgentWorld-35B-A3B, 45 t/s) is
particularly well-matched — its pretraining covers MCP tool-calling, Terminal execution,
SWE workflows, and web/OS environment simulation. These are exactly the trajectories
Claude Code exercises. It runs as the `auto-agentic` fallback when the primary 80B isn't warm.
(2026-06-30: a re-validation bench scored noticeably below what this training profile would
predict — production status is unchanged while that gap is investigated, see
`config/M
