---
id: unit-MCP_DEV_TOOLING-fixing-a-bug-claude-code
kind: why
title: "MCP_DEV_TOOLING \u2014 Fixing a bug (Claude Code)"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: Fixing a bug (Claude Code)
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.873975
updated_at: 1783195000.873975
---


```
You: "Workspace routing is sending some requests to the wrong model"

Claude Code:
  portal-pipeline/explore_repository("workspace routing, model_hint resolution")
  → citations: router/routing.py:380-430, router/workspaces.py:205-250
  filesystem/read_file router/routing.py (lines 380-430)
  [diagnoses the keyword scoring threshold]
  filesystem/edit_file router/routing.py
  portal-sandbox/execute_bash "pytest tests/unit/test_pipeline.py -q"
  git/git_diff
  git/git_commit
```
