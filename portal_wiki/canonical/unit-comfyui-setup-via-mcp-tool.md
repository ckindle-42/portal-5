---
id: unit-comfyui-setup-via-mcp-tool
kind: what
title: "COMFYUI_SETUP \u2014 Via MCP tool"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: Via MCP tool
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5584798
updated_at: 1784946220.5584798
---

curl -X POST http://localhost:8911/tools/start_video_generation \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"prompt": "your prompt", "model": "wan22-ti2v-5b", "steps": 30}}'
```
