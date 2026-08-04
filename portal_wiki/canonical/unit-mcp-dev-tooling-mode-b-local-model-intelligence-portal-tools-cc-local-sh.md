---
id: unit-mcp-dev-tooling-mode-b-local-model-intelligence-portal-tools-cc-local-sh
kind: what
title: "MCP_DEV_TOOLING \u2014 Mode B \u2014 Local model intelligence + Portal tools\
  \ (`cc-local.sh`)"
sources:
- type: code
  path: scripts/cc-local.sh
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/anthropic_compat.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.577048
updated_at: 1784946220.577048
---

Mode B keeps the same Portal tool set as Mode A but moves the intelligence on-box.
`scripts/cc-local.sh` exports `ANTHROPIC_BASE_URL=http://localhost:9099` and
`ANTHROPIC_API_KEY=$PIPELINE_API_KEY`, verifies the pipeline answers on /health, and
then launches `claude`, defaulting the model to `agenticheavy` unless one is passed
with `--model`. The pipeline's `anthropic_messages` handler translates the
`/v1/messages` body via `anthropic_to_openai_body`, routes it through the normal
chat-completions stack, and returns Anthropic-format SSE — so Claude Code believes it
is talking to Anthropic while every token is generated locally.

## Why

The Anthropic compatibility endpoint is what makes Claude Code usable as a local-model
IDE without forking the CLI: the SDK's base URL and key are the only moving parts.
Keeping the wrapper responsible for those two variables, plus the default persona
selection, means local inference stays a one-command operation with the full tool set
intact.
