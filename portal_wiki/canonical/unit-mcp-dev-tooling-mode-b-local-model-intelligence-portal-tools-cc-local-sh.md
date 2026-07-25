---
id: unit-mcp-dev-tooling-mode-b-local-model-intelligence-portal-tools-cc-local-sh
kind: what
title: "MCP_DEV_TOOLING \u2014 Mode B \u2014 Local model intelligence + Portal tools\
  \ (`cc-local.sh`)"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: "Mode B \u2014 Local model intelligence + Portal tools (`cc-local.sh`)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.577048
updated_at: 1784946220.577048
---

Portal 5's local models provide the AI via the pipeline's `/v1/messages` Anthropic
compatibility endpoint. All tokens stay on your hardware. Same tool set as Mode A.

```bash
scripts/cc-local.sh                                    # default: auto-coding workspace, heavy variant
scripts/cc-local.sh --model 'auto-coding?variant=laguna'   # Laguna-XS.2 33B (agentic loop)
scripts/cc-local.sh --model 'auto-coding?variant=heavy'    # Qwen3-Coder-Next 80B / AgentWorld 35B fallback
scripts/cc-local.sh --model 'auto-coding?variant=lite'     # AgentWorld 35B direct (lighter, 45 t/s)
scripts/cc-local.sh --model 'auto-coding?variant=ornith'   # Ornith-1.0-35B direct — agentic option, not a replacement
scripts/cc-local.sh --model auto-coding                # Qwen3-Coder 30B (one-shot)
scripts/cc-local.sh --model 'auto-coding?variant=northmini' # North-Mini-Code 30B-A3B — coding diversity option
scripts/cc-local.sh --model auto-reasoning             # DeepSeek-R1-0528 8B (reasoning)
scripts/cc-local.sh --model auto-security              # VulnLLM-R-7B (security)
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
Claude Code exercises. It runs as the `auto-coding` `heavy`-variant fallback when the primary 80B isn't warm.
(2026-06-30: a re-validation bench scored noticeably below what this training profile would
predict — production status is unchanged while that gap is investigated, see
`config/MODEL_CATALOG.md`.)

**Ornith-1.0-35B for IDE use:** Ornith (DeepReinforce, `auto-coding` `ornith` variant) is a second,
architecturally distinct agentic option — self-improving RL jointly optimizes solution
rollout and scaffold rather than env-simulation pretraining. Promoted 2026-06-30 on strong
tool-chain and SWE-handoff probe scores. Not a replacement for AgentWorld or the 80B
primary — pick it when you want a different agentic lineage to compare against, or when
the others aren't warm.

**Environment variable shortcut** (without the script):
```bash
export ANTHROPIC_BASE_URL=http://localhost:9099
export ANTHROPIC_API_KEY=$(grep PIPELINE_API_KEY .env | cut -d= -f2)
claude --model 'auto-coding?variant=heavy'
```
