---
id: unit-claude-9-the-dockerfile-split-is-intentional
kind: why
title: "CLAUDE.md \u2014 9 \u2014 The Dockerfile Split Is Intentional"
sources:
- type: design
  path: CLAUDE.md
  section: "9 \u2014 The Dockerfile Split Is Intentional"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.808539
updated_at: 1783195000.808539
---


- `Dockerfile.pipeline` — minimal: fastapi, uvicorn, httpx, pyyaml only. Fast build, lean image.
- `Dockerfile.mcp` — heavier: adds python-docx, python-pptx, openpyxl, fastmcp, etc.

Do not merge them. The pipeline container must stay small for fast restarts.
