---
id: unit-mcp-dev-tooling-prerequisites
kind: what
title: "MCP_DEV_TOOLING \u2014 Prerequisites"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: Prerequisites
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.570942
updated_at: 1784946220.570942
---

`npx` and `uvx` must be on PATH:

```bash
node --version && npx --version   # npx ships with Node.js ≥18
uv --version && uvx --version     # uvx ships with uv
