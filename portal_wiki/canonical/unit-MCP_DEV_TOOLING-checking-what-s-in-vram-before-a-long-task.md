---
id: unit-MCP_DEV_TOOLING-checking-what-s-in-vram-before-a-long-task
kind: why
title: "MCP_DEV_TOOLING \u2014 Checking what's in VRAM before a long task"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: Checking what's in VRAM before a long task
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.8747149
updated_at: 1783195000.8747149
---


```
You: "Is devstral loaded? I don't want to wait for a cold start"

Claude Code:
  portal-pipeline/get_loaded_models
  → [{"name": "laguna-xs.2:Q4_K_M", "size_gb": 19.0, "expires_at": "2026-06-17T23:45:00"}]
  → Yes, warm for 33 more minutes
```

---
