---
id: unit-MCP_DEV_TOOLING-prerequisites
historical: true
kind: why
title: "MCP_DEV_TOOLING \u2014 Prerequisites"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: Prerequisites
confidence: high
tags:
- docs
- MCP_DEV_TOOLING

---


`npx` and `uvx` must be on PATH:

```bash
node --version && npx --version   # npx ships with Node.js ≥18
uv --version && uvx --version     # uvx ships with uv
