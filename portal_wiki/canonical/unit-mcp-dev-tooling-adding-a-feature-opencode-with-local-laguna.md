---
id: unit-mcp-dev-tooling-adding-a-feature-opencode-with-local-laguna
kind: what
title: "MCP_DEV_TOOLING \u2014 Adding a feature (opencode with local Laguna)"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: Adding a feature (opencode with local Laguna)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.578677
updated_at: 1784946220.578677
---

```
You: "Add a new auto-lab-report workspace for generating pentest reports"

opencode (Laguna-XS.2 33B-A3B via portal/codingagentic):
  explore_repository("how workspaces are defined, backends.yaml routing pattern")
  → citations: router/workspaces.py, config/backends.yaml, router/routing.py
  execute_bash "sed -n '205,250p' portal/platform/inference/router/workspaces.py"
  [writes workspace definition matching the pattern]
  execute_bash "pytest tests/unit/ -q && python3 -c 'workspace consistency check'"
  [reports complete with passing tests]
```
