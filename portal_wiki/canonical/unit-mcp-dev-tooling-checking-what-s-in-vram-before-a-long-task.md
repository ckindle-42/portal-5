---
id: unit-mcp-dev-tooling-checking-what-s-in-vram-before-a-long-task
kind: what
title: "MCP_DEV_TOOLING \u2014 Checking what's in VRAM before a long task"
sources:
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5794618
updated_at: 1784946220.5794618
---

Before a long coding session, check whether the model you need is already resident in
memory so the first request is not a cold load. The `get_loaded_models` tool in
`portal/platform/mcp_host/pipeline_mcp.py` asks Ollama's `/api/ps` endpoint and
returns each loaded model's name, `size_gb`, `vram_size_gb`, and `expires_at`. A
model listed there is warm and will answer immediately; one that is absent will cost
a load before it can produce tokens. The `trigger_backend_warmup` tool exists for the
opposite case — pre-loading a workspace before you start.

## Why

Warm-model awareness is what turns a long agentic task from a sequence of
ten-second stalls into a continuous flow. Checking residency once at the start, and
optionally warming the workspace you plan to use, lets the model plan around cold
starts instead of being surprised by them mid-task.
