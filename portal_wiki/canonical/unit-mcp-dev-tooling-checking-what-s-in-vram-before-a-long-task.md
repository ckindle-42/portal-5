---
id: unit-mcp-dev-tooling-checking-what-s-in-vram-before-a-long-task
kind: what
title: "MCP_DEV_TOOLING \u2014 Checking what's in VRAM before a long task"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: Checking what's in VRAM before a long task
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5794618
updated_at: 1784946220.5794618
---

```
You: "Is devstral loaded? I don't want to wait for a cold start"

Claude Code:
  portal-pipeline/get_loaded_models
  → [{"name": "laguna-xs.2:Q4_K_M", "size_gb": 19.0, "expires_at": "2026-06-17T23:45:00"}]
  → Yes, warm for 33 more minutes
```

---
