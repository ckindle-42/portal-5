---
id: unit-MCP_DEV_TOOLING-what-opencode-gets
kind: why
title: "MCP_DEV_TOOLING \u2014 What opencode gets"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: What opencode gets
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.87217
updated_at: 1783195000.87217
---


- **Fully local inference** — all completions go through portal-pipeline (:9099) to Ollama
  on your hardware. No tokens leave the machine.
- **94 workspaces as models** — `opencode models` lists every Portal 5 workspace. Default:
  `portal/auto-coding-agentic` (Laguna-XS.2 33B-A3B with FastContext explore loop).
- **All 19 MCP servers** — opencode reads `.mcp.json` automatically, so it has the same
  filesystem, git, docker, sandbox, pipeline, and all 15 portal-* tool servers.
- **Cloud providers disabled** — `anthropic`, `openai`, `google`, `bedrock`, `vertex` are
  all disabled to prevent accidental cloud use.
