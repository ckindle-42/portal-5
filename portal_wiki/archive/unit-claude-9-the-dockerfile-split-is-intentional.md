---
id: unit-claude-9-the-dockerfile-split-is-intentional
historical: true
kind: why
title: "CLAUDE.md \u2014 9 \u2014 The Dockerfile Split Is Intentional"
sources:
- type: design
  path: CLAUDE.md
  section: "9 \u2014 The Dockerfile Split Is Intentional"
confidence: high
tags:
- claude
- architecture
- law

---


- `Dockerfile.pipeline` — minimal: fastapi, uvicorn, httpx, pyyaml only. Fast build, lean image.
- `Dockerfile.mcp` — heavier: adds python-docx, python-pptx, openpyxl, fastmcp, etc.

Do not merge them. The pipeline container must stay small for fast restarts.
