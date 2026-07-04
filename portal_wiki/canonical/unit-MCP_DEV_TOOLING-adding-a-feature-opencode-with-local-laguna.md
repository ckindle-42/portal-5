---
id: unit-MCP_DEV_TOOLING-adding-a-feature-opencode-with-local-laguna
kind: why
title: "MCP_DEV_TOOLING \u2014 Adding a feature (opencode with local Laguna)"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: Adding a feature (opencode with local Laguna)
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.874206
updated_at: 1783195000.874206
---


```
You: "Add a new auto-lab-report workspace for generating pentest reports"

opencode (Laguna-XS.2 33B-A3B via portal/auto-coding-agentic):
  explore_repository("how workspaces are defined, backends.yaml routing pattern")
  → citations: router/workspaces.py, config/backends.yaml, router/routing.py
  execute_bash "sed -n '205,250p' portal_pipeline/router/workspaces.py"
  [writes workspace definition matching the pattern]
  execute_bash "pytest tests/unit/ -q && python3 -c 'workspace consistency check'"
  [reports complete with passing tests]
```
