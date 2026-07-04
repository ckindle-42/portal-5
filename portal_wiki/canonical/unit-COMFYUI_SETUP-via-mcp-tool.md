---
id: unit-COMFYUI_SETUP-via-mcp-tool
kind: why
title: "COMFYUI_SETUP \u2014 Via MCP tool"
sources:
- type: design
  path: docs/COMFYUI_SETUP.md
  section: Via MCP tool
last_generated_commit: ''
confidence: high
tags:
- docs
- COMFYUI_SETUP
created_at: 1783195000.831684
updated_at: 1783195000.831684
---

curl -X POST http://localhost:8911/tools/start_video_generation \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"prompt": "your prompt", "model": "wan22-ti2v-5b", "steps": 30}}'
```
